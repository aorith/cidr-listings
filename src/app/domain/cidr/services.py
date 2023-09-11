from uuid import UUID

from asyncpg import Record
from asyncpg.pool import PoolConnectionProxy

from litestar.exceptions import ImproperlyConfiguredException

SELECT_ENABLED_BY_TYPE_AND_ID = """
select *
from cidr
where list_id
in
(select id
 from list
 where
 enabled = true
 and user_id = $1
 and list_type = $2
 and list_id = $3
)"""

SELECT_ENABLED_BY_TYPE_AND_TAGS = """
select *
from cidr
where list_id
in
(select id
 from list
 where
 enabled = true
 and user_id = $1
 and list_type = $2
 and tags && $3::text[]
)"""

SELECT_ENABLED_BY_ID = """
select *
from cidr
where list_id
in
(select id
 from list
 where
 enabled = true
 and user_id = $1
 and list_id = $2
)"""

SELECT_ENABLED_BY_TYPE = """
select *
from cidr
where
list_id in
(select id
 from list
 where
 enabled = true
 and user_id = $1
 and list_type = $2
)"""

SELECT_BY_ID_FIRST_PAGE = """
select *
from cidr
where
list_id = $1
order by id desc
limit $2
"""

SELECT_BY_ID_PAGINATED = """
select *
from cidr
where
id < $1
and
list_id = $2
order by id desc
limit $3
"""


async def get_cidr_records(
    conn: PoolConnectionProxy,
    user_id: UUID,
    list_type: str | None = None,
    list_id: str | None = None,
    tags: str | None = None,
) -> list[Record]:
    """Get CIDR records filtering by id, type and or tags."""
    if list_id and list_type:
        return await conn.fetch(
            SELECT_ENABLED_BY_TYPE_AND_ID,
            user_id,
            list_type,
            list_id,
        )

    if tags and list_type:
        tags_split = [x.strip() for x in tags.strip().split(",") if x]
        return await conn.fetch(
            SELECT_ENABLED_BY_TYPE_AND_TAGS,
            user_id,
            list_type,
            tags_split,
        )

    if list_id:
        return await conn.fetch(
            SELECT_ENABLED_BY_ID,
            user_id,
            list_id,
        )

    if not list_type:
        raise ImproperlyConfiguredException("list_type is mandatory if no other filters are used")

    return await conn.fetch(
        SELECT_ENABLED_BY_TYPE,
        user_id,
        list_type,
    )


async def get_cidr_records_paginated(
    conn: PoolConnectionProxy,
    list_id: str,
    address_id: int | None = None,
    limit: int = 100,
) -> list[Record]:
    """Get CIDR records paginating by id."""
    if address_id:
        return await conn.fetch(
            SELECT_BY_ID_PAGINATED,
            address_id,
            list_id,
            limit,
        )

    return await conn.fetch(
        SELECT_BY_ID_FIRST_PAGE,
        list_id,
        limit,
    )
