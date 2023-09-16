from ipaddress import collapse_addresses, ip_network
from itertools import chain

from asyncpg.pool import PoolConnectionProxy
from litestar import Request, Response
from litestar.controller import Controller
from litestar.datastructures import State
from litestar.handlers import get
from litestar.params import Parameter
from litestar.status_codes import HTTP_200_OK

from app.domain.auth.schemas import Token, User
from app.domain.cidr.schemas import Cidr, CidrByVersion
from app.domain.cidr.services import get_cidr_records
from app.domain.lists.schemas import (
    LIST_ID_PATTERN,
    MAX_LIST_ID_LEN,
    TAG_PARAMS_PATTERN,
    ListTypeEnum,
)


class CidrController(Controller):
    path = "/v1/cidr"
    tags = ["CIDRs"]
    parameters = {
        "list_type": Parameter(ListTypeEnum, description="Required parameter list_type.", required=True),
        "list_id": Parameter(
            str,
            max_length=MAX_LIST_ID_LEN,
            pattern=LIST_ID_PATTERN,
            description="A concrete list_id.",
            required=False,
        ),
        "tags": Parameter(
            str | None,
            description="A tag or multiple tags separated by commas.",
            pattern=TAG_PARAMS_PATTERN,
            required=False,
        ),
    }

    @get("/")
    async def get_cidrs(self, request: Request[User, Token, State], conn: PoolConnectionProxy) -> Response[list[Cidr]]:
        """Get CIDRs from **enabled** lists.

        - The parameter `list_type` is required.

        - If the parameter `list_id` is specified, `tags` filter has no effect
        and if `list_type` doesn't match nothing will be returned.
        """
        records = await get_cidr_records(
            conn=conn,
            user_id=request.user.id,
            list_type=request.query_params["list_type"],
            list_id=request.query_params.get("list_id", None),
            tags=request.query_params.get("tags", None),
        )
        return Response([Cidr(**x) for x in records], status_code=HTTP_200_OK)

    @get("/collapsed")
    async def get_collapsed_cidrs(
        self, request: Request[User, Token, State], conn: PoolConnectionProxy
    ) -> Response[list[str]]:
        """Get CIDRs from **enabled** lists with all the networks collapsed if possible.

        - The parameter `list_type` is required.

        - If the parameter `list_id` is specified, `tags` filter has no effect
        and if `list_type` doesn't match nothing will be returned.
        """
        all_addresses = set()
        for record in await get_cidr_records(
            conn=conn,
            user_id=request.user.id,
            list_type=request.query_params["list_type"],
            list_id=request.query_params.get("list_id", None),
            tags=request.query_params.get("tags", None),
        ):
            all_addresses.add(ip_network(record["address"]))

        ipv4_collapsed = collapse_addresses(x for x in all_addresses if x.version == 4)
        ipv6_collapsed = collapse_addresses(x for x in all_addresses if x.version == 6)
        return Response([x.compressed for x in chain(ipv4_collapsed, ipv6_collapsed)])

    @get("/collapsed/by-ip-version")
    async def get_collapsed_by_version_cidrs(
        self, request: Request[User, Token, State], conn: PoolConnectionProxy
    ) -> Response[CidrByVersion]:
        """Get CIDRs from **enabled** lists, collapsed by ip version.

        - The parameter `list_type` is required.

        - If the parameter `list_id` is specified, `tags` filter has no effect
        and if `list_type` doesn't match nothing will be returned.
        """
        all_addresses = set()
        for record in await get_cidr_records(
            conn=conn,
            user_id=request.user.id,
            list_type=request.query_params["list_type"],
            list_id=request.query_params.get("list_id", None),
            tags=request.query_params.get("tags", None),
        ):
            all_addresses.add(ip_network(record["address"]))

        ipv4_collapsed = collapse_addresses(x for x in all_addresses if x.version == 4)
        ipv6_collapsed = collapse_addresses(x for x in all_addresses if x.version == 6)
        return Response(CidrByVersion(ipv4=list(ipv4_collapsed), ipv6=list(ipv6_collapsed)))
