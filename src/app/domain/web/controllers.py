import ipaddress
import re
from typing import Annotated
from uuid import UUID

import msgspec
from asyncpg.pool import PoolConnectionProxy
from litestar import Request, Response, delete, get, post, put
from litestar.controller import Controller
from litestar.datastructures import Cookie, State
from litestar.enums import RequestEncodingType
from litestar.exceptions import HTTPException, NotFoundException, ValidationException
from litestar.params import Body
from litestar.response import Template
from litestar.status_codes import HTTP_200_OK, HTTP_204_NO_CONTENT
from msgspec import ValidationError

from app.domain.auth.schemas import Token, User, UserLoginOrCreate
from app.domain.auth.services import generate_token
from app.domain.cidr.services import get_cidr_records_paginated
from app.domain.lists.controllers import INSERT_LIST, UPDATE_LIST
from app.domain.lists.schemas import ActionEnum, CidrJob, ListFull, ListTypeEnum
from app.domain.lists.services import insert_cidr_job, parse_raw_cidrs_input, parse_raw_cidrs_input_as_str
from app.lib.settings import get_settings

settings = get_settings()


SELECT_LISTS_WITH_CIDR_COUNT = """
select l.id, coalesce(c1.networks, 0) as networks, l.list_type, l.enabled, l.tags, l.description, l.updated_at
from list l
left join
    (
        select c.list_id, count(c.address) as networks from
        cidr c
        group by c.list_id
    ) c1
on l.id = c1.list_id
where l.user_id = $1
order by l.updated_at desc
"""

SELECT_LIST_WITH_CIDR_COUNT = """
select l.id, coalesce(c1.networks, 0) as networks, l.list_type, l.enabled, l.tags, l.description, l.updated_at
from list l
left join
    (
        select c.list_id, count(c.address) as networks from
        cidr c
        group by c.list_id
    ) c1
on l.id = c1.list_id
where l.user_id = $1
and l.id = $2
order by l.updated_at desc
"""


async def get_network_info(address: str | None, conn: PoolConnectionProxy, user_id: UUID) -> Template:
    """Get network info."""
    error = None
    ipn = None
    usable = None
    subnets = None
    supernet = None
    if address:
        try:
            ipn = ipaddress.ip_network(address)
            usable = max(ipn.num_addresses - 2, 1)
            subnets = ipn.subnets()
            supernet = ipn.supernet()
        except ValueError as err:
            error = str(err)

    lists = [
        x["id"]
        for x in await conn.fetch(
            "select id from list where user_id = $1 and id in (select list_id from cidr where address >>= $2)",
            user_id,
            ipn,
        )
    ]

    return Template(
        template_name="partials/network-info.html.j2",
        context={"error": error, "usable": usable, "ip": ipn, "subnets": subnets, "supernet": supernet, "lists": lists},
    )


class WebController(Controller):
    tags = ["Web"]

    @get("/", include_in_schema=False)
    async def home(self, request: Request[User, Token, State]) -> Template:
        """Home."""
        return Template(template_name="base.html.j2", context={"login": request.user.login})

    @get(path="/login", include_in_schema=False)
    async def login(self) -> Template:
        """Login."""
        return Template(template_name="login.html.j2", context={})

    @get(path="/logout", include_in_schema=False)
    async def logout(self) -> Response:
        """Logout."""
        return Response(
            None,
            headers={"HX-Push": "/", "HX-Redirect": "/"},
            cookies=[Cookie(key=settings.API_KEY_COOKIE, value="", samesite="strict", max_age=-1)],
            status_code=HTTP_204_NO_CONTENT,
        )

    @post("/login", include_in_schema=False)
    async def post_login(
        self,
        conn: PoolConnectionProxy,
        data: Annotated[UserLoginOrCreate, Body(media_type=RequestEncodingType.URL_ENCODED)],
    ) -> Response:
        """Login."""
        token = await generate_token(conn=conn, data=data)
        return Response(
            None,
            headers={"HX-Push": "/", "HX-Redirect": "/"},
            cookies=[
                Cookie(
                    key=settings.API_KEY_COOKIE, value=token.access_token, samesite="strict", max_age=token.expires_in
                )
            ],
            status_code=HTTP_204_NO_CONTENT,
        )


class WebPartListController(Controller):
    tags = ["Web"]
    path = "/parts/list"

    @get("/", include_in_schema=False)
    async def get_lists(self, request: Request[User, Token, State], conn: PoolConnectionProxy) -> Template:
        """Get lists."""
        records = await conn.fetch(SELECT_LISTS_WITH_CIDR_COUNT, request.user.id)
        return Template(template_name="partials/lists.html.j2", context={"items": records})

    @post("/", include_in_schema=False)
    async def create_list(
        self,
        request: Request[User, Token, State],
        conn: PoolConnectionProxy,
        data: Annotated[dict, Body(media_type=RequestEncodingType.URL_ENCODED)],
    ) -> Response:
        """Create list."""
        tags = {x.strip() for x in re.split(",| |\n", data["tags"]) if x}
        tags.add("DEFAULT")
        data.update(
            {
                "enabled": data.get("enabled", "false").lower() in ["true", "on"],
                "tags": list(tags),
                "user_id": UUID(
                    str(request.user.id),
                ),
            }
        )
        try:
            new_list = msgspec.convert(data, ListFull)
        except ValidationError as err:
            raise ValidationException(str(err))  # noqa: B904

        async with conn.transaction():
            record = await conn.fetchrow(
                INSERT_LIST,
                new_list.id,
                request.user.id,
                new_list.list_type,
                new_list.enabled,
                new_list.tags,
                new_list.description,
            )
        if not record:
            raise HTTPException(status_code=409, detail=f"List {new_list.id} already exists.")

        return Template(template_name="partials/list-item.html.j2", context={"item": record, "new_item": True})

    @get("/{id:str}", include_in_schema=False)
    async def get_list_detail(self, conn: PoolConnectionProxy, id: str, last_cidr_id: int | None = None) -> Template:
        """Get list detail."""
        if last_cidr_id:
            records = await get_cidr_records_paginated(conn=conn, list_id=id, address_id=last_cidr_id)
            if len(records) > 0:
                last_cidr_id = records[-1]["id"]
            return Template(
                template_name="partials/cidr-detail.html.j2",
                context={"list_id": id, "items": records, "last_cidr_id": last_cidr_id},
            )

        records = await get_cidr_records_paginated(conn=conn, list_id=id)
        if len(records) > 0:
            last_cidr_id = records[-1]["id"]
        return Template(
            template_name="partials/list-cidrs.html.j2",
            context={"list_id": id, "items": records, "last_cidr_id": last_cidr_id},
        )

    @put("/{id:str}", include_in_schema=False)
    async def edit_list(
        self,
        request: Request[User, Token, State],
        conn: PoolConnectionProxy,
        id: str,
        data: Annotated[dict, Body(media_type=RequestEncodingType.URL_ENCODED)],
    ) -> Template:
        """Edit list."""
        tags = {x.strip() for x in re.split(",| |\n", data["tags"]) if x}
        tags.add("DEFAULT")
        data.update(
            {
                "id": id,
                "list_type": data["list_type"],
                "user_id": request.user.id,
                "enabled": data.get("enabled", "false").lower() in ["true", "on"],
                "tags": list(tags),
                "description": data["description"],
            }
        )
        try:
            updated_list = msgspec.convert(data, ListFull)
        except ValidationError as err:
            raise ValidationException(str(err))  # noqa: B904

        async with conn.transaction():
            record = await conn.fetchrow(
                "select id, enabled from list where id = $1 and user_id = $2", id, request.user.id
            )
            if not record:
                raise NotFoundException(f"List {id} not found.")

            # force deny cidrs cleanup if the list is safe and goes from disabled to enabled
            if data["list_type"] == ListTypeEnum.SAFE and not record["enabled"] and data.get("enabled", False):
                cidr_job = CidrJob(
                    action=ActionEnum.UPDATE,
                    list_id=id,
                    list_type=data["list_type"],
                    list_enabled=data["enabled"],
                    user_id=request.user.id,
                    cidrs=[],
                    ttl=None,
                )
                await insert_cidr_job(job=cidr_job, conn=conn)

            record = await conn.fetchrow(
                UPDATE_LIST,
                updated_list.list_type,
                updated_list.enabled,
                updated_list.tags,
                updated_list.description,
                id,
                request.user.id,
            )

        records = await conn.fetch(SELECT_LIST_WITH_CIDR_COUNT, request.user.id, id)
        if not records:
            raise NotFoundException(f"List {id} not found.")
        item = dict(records[0])

        return Template(template_name="partials/list-item.html.j2", context={"new_item": True, "item": item})

    @get("/edit/{id:str}", include_in_schema=False)
    async def edit_list_view(
        self, request: Request[User, Token, State], conn: PoolConnectionProxy, id: str
    ) -> Template:
        """Get edit list view."""
        records = await conn.fetch(SELECT_LIST_WITH_CIDR_COUNT, request.user.id, id)
        if not records:
            raise NotFoundException(f"List {id} not found.")
        item = dict(records[0])
        item["tags"] = ",".join(item["tags"])
        return Template(template_name="partials/list-edit.html.j2", context={"list_id": id, "item": item})

    @delete("/{id:str}", include_in_schema=False, status_code=HTTP_200_OK)
    async def delete_list(self, request: Request[User, Token, State], conn: PoolConnectionProxy, id: str) -> Response:
        """Delete list."""
        async with conn.transaction():
            record = await conn.fetch(
                "delete from list where user_id = $1 and id = $2 returning id", request.user.id, id
            )
            if not record:
                raise NotFoundException(f"List {id} not found.")
        return Response("", status_code=HTTP_200_OK)


class WebPartCidrController(Controller):
    tags = ["Web"]
    path = "/parts/cidr"

    @get("/", include_in_schema=False)
    async def cidrs(
        self,
    ) -> Template:
        """CIDRs add/delete view."""
        return Template(template_name="partials/cidrs/cidrs.html.j2")

    @post("/", include_in_schema=False)
    async def parse_raw_cidrs(
        self,
        request: Request[User, Token, State],
        conn: PoolConnectionProxy,
        data: Annotated[dict, Body(media_type=RequestEncodingType.URL_ENCODED)],
    ) -> Template:
        """Parse raw CIDRs."""
        ipv4_valid = set()
        ipv6_valid = set()

        ipv4_valid, ipv6_valid = parse_raw_cidrs_input_as_str(raw_data=data["cidrs-raw"])

        ipv4_string = "\n".join(ipv4_valid)
        ipv6_string = "\n".join(ipv6_valid)
        total_ipv4 = len(ipv4_valid)
        total_ipv6 = len(ipv6_valid)

        lists = await conn.fetch("select id, list_type from list where user_id = $1", request.user.id)

        return Template(
            template_name="partials/cidrs/cidrs-parsed.html.j2",
            headers={"HX-Trigger-After-Swap": "scrollToBottom"},
            context={
                "ipv4_cidrs": ipv4_string,
                "ipv6_cidrs": ipv6_string,
                "total_ipv4": total_ipv4,
                "total_ipv6": total_ipv6,
                "lists": lists,
            },
        )

    @put("/", include_in_schema=False)
    async def submit_parsed_cidrs(
        self,
        request: Request[User, Token, State],
        conn: PoolConnectionProxy,
        data: Annotated[dict, Body(media_type=RequestEncodingType.URL_ENCODED)],
    ) -> Template:
        """Submit parsed CIDRs as a Job."""
        ipv4_valid, ipv6_valid = parse_raw_cidrs_input(raw_data=data["ipv4-cidrs"] + " " + data["ipv6-cidrs"])

        cidrs = [x.compressed for x in ipaddress.collapse_addresses(iter(ipv4_valid))] + [
            x.compressed for x in ipaddress.collapse_addresses(iter(ipv6_valid))
        ]

        list_record = await conn.fetchrow(
            "select * from list where id = $1 and user_id = $2", data["list_id"], request.user.id
        )
        if not list_record:
            raise NotFoundException(f"List {id} not found.")

        cidr_job = CidrJob(
            action=ActionEnum.DELETE if data["action"] == "delete" else ActionEnum.ADD,
            list_id=list_record["id"],
            list_type=list_record["list_type"],
            list_enabled=list_record["enabled"],
            user_id=request.user.id,
            cidrs=cidrs,
            ttl=None if int(data["ttl"]) == 0 else int(data["ttl"]),
        )

        await insert_cidr_job(job=cidr_job, conn=conn)

        return Template(
            template_name="partials/cidrs/cidrs-job.html.j2",
            headers={"HX-Trigger-After-Swap": "scrollToBottom"},
            context={"job": cidr_job},
        )

    @get("/ni", include_in_schema=False)
    async def get_ni(self, request: Request[User, Token, State], conn: PoolConnectionProxy) -> Template:
        """Get cidr."""
        return await get_network_info(conn=conn, address=None, user_id=request.user.id)

    @get("/ni/{ip:str}/{prefix:str}", include_in_schema=False)
    async def get_cidr(
        self, request: Request[User, Token, State], conn: PoolConnectionProxy, ip: str, prefix: str
    ) -> Template:
        """Get cidr."""
        address = ip + "/" + prefix
        return await get_network_info(conn=conn, address=address, user_id=request.user.id)

    @post("/ni", include_in_schema=False)
    async def get_ni_cidr(
        self,
        request: Request[User, Token, State],
        conn: PoolConnectionProxy,
        data: Annotated[dict, Body(media_type=RequestEncodingType.URL_ENCODED)],
    ) -> Template:
        """Get network info for CIDR."""
        return await get_network_info(conn=conn, address=data.get("address", ""), user_id=request.user.id)

    @delete("/{list_id:str}/{ip:str}/{prefix:str}", include_in_schema=False, status_code=HTTP_200_OK)
    async def delete_cidr(
        self,
        conn: PoolConnectionProxy,
        list_id: str,
        ip: str,
        prefix: str,
    ) -> Response:
        """Delete CIDR."""
        address = ip + "/" + prefix
        async with conn.transaction():
            record = await conn.fetch(
                "delete from cidr where list_id = $1 and address = $2 returning address", list_id, address
            )
            if not record:
                raise NotFoundException(f"CIDR {address} not found.")
        return Response("", status_code=HTTP_200_OK)
