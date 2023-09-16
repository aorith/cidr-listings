import msgspec
from asyncpg.pool import PoolConnectionProxy
from litestar import Request, Response
from litestar.controller import Controller
from litestar.datastructures import State
from litestar.dto import DTOData
from litestar.exceptions import HTTPException, NotFoundException
from litestar.handlers import delete, get, post, put
from litestar.status_codes import HTTP_400_BAD_REQUEST

from app.domain.auth.schemas import Token, User
from app.domain.cidr.schemas import CidrNL
from app.domain.lists.schemas import (
    ActionEnum,
    CidrAdd,
    CidrDelete,
    CidrJob,
    CidrList,
    ListCreateDTO,
    ListFull,
    ListUpdateDTO,
)
from app.lib.validations import run_validation

INSERT_LIST = """
INSERT INTO list
    (id, user_id, list_type, enabled, tags, description)
VALUES
    ($1, $2, $3, $4, $5, $6)
ON CONFLICT (id)
    DO NOTHING
RETURNING *;

-- Returns the id if it was created successfully, else nothing
"""
UPDATE_LIST = """
UPDATE list
SET
    list_type = $1,
    enabled = $2,
    tags = $3::text[],
    description = $4
WHERE
    id = $5 and user_id = $6
RETURNING *;
"""

INSERT_JOB = """
INSERT INTO job_queue
    (job_id, payload)
VALUES
    ($1, $2::jsonb)
"""


json_enc = msgspec.json.Encoder()


class ListController(Controller):
    path = "/v1/list"
    tags = ["Lists"]

    @get("/", dto=None)
    async def get_lists(
        self, request: Request[User, Token, State], conn: PoolConnectionProxy
    ) -> Response[list[ListFull]]:
        """Get lists."""
        records = await conn.fetch("select * from list where user_id = $1", request.user.id)
        return Response([ListFull(**x) for x in records])

    @post("/", dto=ListCreateDTO, return_dto=None)
    async def create_list(
        self, request: Request[User, Token, State], conn: PoolConnectionProxy, data: ListFull
    ) -> Response[ListFull]:
        """Create list."""
        await run_validation(data=data, target_type=ListFull)
        async with conn.transaction():
            record = await conn.fetchrow(
                INSERT_LIST,
                data.id,
                request.user.id,
                data.list_type,
                data.enabled,
                list({*data.tags, "DEFAULT"}),
                data.description,
            )
        if not record:
            raise HTTPException(status_code=409, detail=f"List {data.id} already exists.")
        return Response(ListFull(**record))

    @get("/{id:str}")
    async def get_list(
        self, request: Request[User, Token, State], conn: PoolConnectionProxy, id: str
    ) -> Response[ListFull]:
        """Get list."""
        record = await conn.fetchrow("select * from list where id = $1 and user_id = $2", id, request.user.id)
        if not record:
            raise NotFoundException(f"List {id} not found")
        return Response(ListFull(**record))

    @put("/{id:str}", dto=ListUpdateDTO, return_dto=None)
    async def update_list(
        self, request: Request[User, Token, State], conn: PoolConnectionProxy, id: str, data: DTOData[ListFull]
    ) -> Response[ListFull]:
        """Update list."""
        to_update = data.as_builtins()
        async with conn.transaction():
            current_record = await conn.fetchrow(
                "select * from list where id = $1 and user_id = $2", id, request.user.id
            )
            if not current_record:
                raise NotFoundException(f"List {id} not found.")

            list_type = to_update.get("list_type", current_record["list_type"])
            enabled = to_update.get("enabled", current_record["enabled"])
            tags = to_update.get("tags", current_record["tags"])
            description = to_update.get("description", current_record["description"])

            # Force validation
            await run_validation(
                data=ListFull(
                    id=id,
                    user_id=request.user.id,
                    list_type=list_type,
                    enabled=enabled,
                    tags=list({*tags, "DEFAULT"}),
                    description=description,
                ),
                target_type=ListFull,
            )

            record = await conn.fetchrow(
                UPDATE_LIST, list_type, enabled, list({*tags, "DEFAULT"}), description, id, request.user.id
            )
            if not record:
                raise NotFoundException(f"List {id} not found.")

            # force deny cidrs cleanup if the list is safe and goes from disabled to enabled
            if not current_record["enabled"] and to_update.get("enabled", False):
                cidr_job = CidrJob(
                    action=ActionEnum.UPDATE,
                    list_id=id,
                    list_type=list_type,
                    list_enabled=enabled,
                    user_id=request.user.id,
                    cidrs=[],
                    ttl=None,
                )

                async with conn.transaction():
                    await conn.execute(
                        INSERT_JOB,
                        cidr_job.job_id,
                        json_enc.encode(cidr_job).decode(),
                    )
            return Response(ListFull(**record))

    @delete("/{id:str}")
    async def delete_list(self, request: Request[User, Token, State], conn: PoolConnectionProxy, id: str) -> None:
        """Delete list."""
        async with conn.transaction():
            record = await conn.fetchval(
                "delete from list where id = $1 and user_id = $2 returning id", id, request.user.id
            )
            if not record:
                raise NotFoundException(f"List {id} not found.")

    @get("/{id:str}/cidr")
    async def get_cidrs(
        self, request: Request[User, Token, State], conn: PoolConnectionProxy, id: str
    ) -> Response[CidrList]:
        """Get CIDRs."""
        list_record = await conn.fetchrow("select * from list where id = $1 and user_id = $2", id, request.user.id)
        if not list_record:
            raise NotFoundException(f"List {id} not found.")
        records = await conn.fetch(  # even if we have the list_id, we need to ensure that the list belongs to the user
            "select * from cidr where list_id = (select id from list where id = $1 and user_id = $2)",
            id,
            request.user.id,
        )
        cidrs = [
            CidrNL(
                address=x["address"], expires_at=x["expires_at"], created_at=x["created_at"], updated_at=x["updated_at"]
            )
            for x in records
        ]
        return Response(CidrList(cidrs=cidrs, **list_record))

    @post("/{id:str}/cidr/add")
    async def add_cidrs(
        self, request: Request[User, Token, State], conn: PoolConnectionProxy, id: str, data: CidrAdd
    ) -> Response[CidrJob]:
        """Create a job to add CIDRs.

        Validation of CIDRs is performed asynchronously.

        - CIDRs from the non-routable address space are discarded automatically if
        the server side environment variable `ONLY_GLOBAL_CIDRS` is `True` (which is by default).

        - If a CIDR already exist in the list its `ttl` will be updated.

        - If the `list_type` is `SAFE` another job will delete all the matching CIDRs from lists of type `DENY`.
        """
        if data.ttl is not None and data.ttl <= 0:
            raise HTTPException(status_code=HTTP_400_BAD_REQUEST, detail="TTL must be greater than 0.")

        list_record = await conn.fetchrow("select * from list where id = $1 and user_id = $2", id, request.user.id)
        if not list_record:
            raise NotFoundException(f"List {id} not found.")

        cidr_job = CidrJob(
            action=ActionEnum.ADD,
            list_id=list_record["id"],
            list_type=list_record["list_type"],
            list_enabled=list_record["enabled"],
            user_id=request.user.id,
            cidrs=data.cidrs,
            ttl=data.ttl,
        )

        async with conn.transaction():
            await conn.execute(
                INSERT_JOB,
                cidr_job.job_id,
                json_enc.encode(cidr_job).decode(),
            )
        return Response(cidr_job)

    @post("/{id:str}/cidr/delete")
    async def delete_cidrs(
        self, request: Request[User, Token, State], conn: PoolConnectionProxy, id: str, data: CidrDelete
    ) -> Response[CidrJob]:
        """Create a job to delete CIDRs.

        Validation of CIDRs is performed asynchronously.
        """
        list_record = await conn.fetchrow("select * from list where id = $1 and user_id = $2", id, request.user.id)
        if not list_record:
            raise NotFoundException(f"List {id} not found.")

        cidr_job = CidrJob(
            action=ActionEnum.DELETE,
            list_id=list_record["id"],
            list_type=list_record["list_type"],
            list_enabled=list_record["enabled"],
            user_id=request.user.id,
            cidrs=data.cidrs,
            ttl=None,
        )

        async with conn.transaction():
            await conn.execute(
                INSERT_JOB,
                cidr_job.job_id,
                json_enc.encode(cidr_job).decode(),
            )
        return Response(cidr_job)
