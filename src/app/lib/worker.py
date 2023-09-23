import asyncio
import ipaddress
import threading
import time
from collections import Counter
from datetime import datetime, timedelta, timezone
from ipaddress import IPv4Network, IPv6Network, collapse_addresses, ip_network
from uuid import UUID

import msgspec
from asyncpg import Connection

from app.domain.lists.schemas import ActionEnum, CidrJob, ListTypeEnum
from app.lib.db.base import get_connection
from app.lib.iputils import address_exclude_many
from app.lib.settings import get_settings

settings = get_settings()

cidrjob_dec = msgspec.json.Decoder(type=CidrJob)

CONSUME_JOB_QUERY = """
DELETE FROM
    job_queue
USING (
    SELECT * FROM job_queue ORDER BY id FOR UPDATE SKIP LOCKED
) q
WHERE q.id = job_queue.id RETURNING job_queue.*;
"""

UPSERT_CIDR = """
INSERT INTO cidr
    (address, list_id, expires_at)
VALUES
    ($1, $2, $3)
ON CONFLICT (address, list_id)
DO
    UPDATE SET expires_at = $3
"""


SELECT_ENABLED_CIDRS_BY_LIST_TYPE = """
SELECT
    address, list_id, expires_at
FROM
    cidr
WHERE
    list_id IN (
            SELECT id FROM list WHERE
                enabled = true
            AND
                user_id = $1
            AND
                list_type = $2
        )
"""

SELECT_ENABLED_CIDRS_BY_LIST_ID = """
SELECT
    address, list_id, expires_at
FROM
    cidr
WHERE
    list_id = (
            SELECT id FROM list WHERE
                enabled = true
            AND
                id = $1
        )
"""

SELECT_ALL_CIDRS_BY_LIST_ID = """
SELECT
    address, list_id, expires_at
FROM
    cidr
WHERE
    list_id = (
            SELECT id FROM list WHERE
                id = $1
        )
"""


async def parse_raw_cidrs(
    cidrs: list[str], only_global: bool = True
) -> tuple[Counter, set[IPv4Network], set[IPv6Network]]:
    """Parse the initial list of CIDRs coming from a job.

    1. Converts the str representation to an IPv4Network/IPv6Network object, filtering malformed
    2. Filters non routable/non global addresses if ``only_global`` is True
    3. Splits IPv4Network and IPv6Network is two sets
    4. Collapses the two sets
    5. Returns a counter with the parsing information a set of IPv4Networks and another of IPv6Networks
    """
    result = Counter(total_job=0, malformed=0, non_global=0)
    ipv4_cidrs: set[IPv4Network] = set()
    ipv6_cidrs: set[IPv6Network] = set()

    for cidr in cidrs:
        result["total_job"] += 1
        try:
            ipn = ipaddress.ip_network(cidr)
            if not ipn.is_global and only_global:
                result["not_global"] += 1
                continue
        except ValueError:
            result["malformed"] += 1
            continue

        if ipn.version == 4:
            ipv4_cidrs.add(ipn)
        elif ipn.version == 6:
            ipv6_cidrs.add(ipn)
        else:
            raise ValueError(f"Unknown IP Version {ipn.version}")

    ipv4_cidrs = set(collapse_addresses(iter(ipv4_cidrs)))
    ipv6_cidrs = set(collapse_addresses(iter(ipv6_cidrs)))

    return result, ipv4_cidrs, ipv6_cidrs


async def filter_safe_cidrs(
    conn: Connection,
    user_id: UUID,
    cidrs: set[IPv4Network | IPv6Network],
) -> tuple[set[IPv4Network], set[IPv6Network]]:
    """Filter input ``cidrs`` that are present on enabled lists of type SAFE for ``user_id``."""
    safe_cidrs = set()
    for safe_cidr_record in await conn.fetch(
        "select address from cidr where list_id in (select id from list where enabled = true and list_type = $1 and user_id = $2)",
        ListTypeEnum.SAFE,
        user_id,
    ):
        safe_cidrs.add(safe_cidr_record["address"])

    safe_cidr_ipv4 = {x for x in safe_cidrs if x.version == 4}
    safe_cidr_ipv6 = {x for x in safe_cidrs if x.version == 6}

    deny_subnets = set()
    for deny_cidr in cidrs:
        for subnet in await address_exclude_many(
            cidr=deny_cidr,
            exclusion_cidrs=safe_cidr_ipv4 if deny_cidr.version == 4 else safe_cidr_ipv6,  # type: ignore
        ):
            deny_subnets.add(subnet)

    return (
        set(collapse_addresses(x for x in deny_subnets if x.version == 4)),
        set(collapse_addresses(x for x in deny_subnets if x.version == 6)),
    )


async def delete_excluded_cidrs(
    conn: Connection,
    user_id: UUID,
    exclusion_cidrs: set[IPv4Network | IPv6Network],
    list_id: str | None = None,
    list_type: ListTypeEnum | None = None,
) -> None:
    """Delete CIDRs matching ``exclusion_cidrs``.

    This function cleans the DB from the excluded addresses preserving
    the ones not excluded instead of deleting the whole subnet.

    Use case example:
    When adding new CIDRs to a safelist we need to clean existing
    denylists to honor the new additions to the safelist.
    If a CIDR from the safelist is a subnet of a CIDR from a
    denylist, the CIDR from the denylist will be split into
    subnets that do not contain the one in the safelist.
    """
    if list_id:
        exclusion_record = await conn.fetch(SELECT_ALL_CIDRS_BY_LIST_ID, list_id)
    elif list_type:
        exclusion_record = await conn.fetch(SELECT_ENABLED_CIDRS_BY_LIST_TYPE, user_id, list_type)
    else:
        raise NotImplementedError("Either `list_id` or `list_type` is needed.")
    if not exclusion_record:
        return

    exclusion_cidr_ipv4 = {x for x in exclusion_cidrs if x.version == 4}
    exclusion_cidr_ipv6 = {x for x in exclusion_cidrs if x.version == 6}
    new_subnets = []
    to_delete = set()

    for record in exclusion_record:
        exclusion_cidr = ipaddress.ip_network(str(record["address"]))
        exclusion_subnets = await address_exclude_many(
            cidr=exclusion_cidr,
            exclusion_cidrs=exclusion_cidr_ipv4 if exclusion_cidr.version == 4 else exclusion_cidr_ipv6,  # type: ignore
        )

        if len(exclusion_subnets) == 1:
            subnet = exclusion_subnets.pop()
            if subnet == exclusion_cidr:
                # the same address has been returned so no filtering was needed, we
                # upsert to update expires_at
                new_subnets.append((subnet, record["list_id"], record["expires_at"]))
            else:
                # one subnet left which isn't the original, upsert the new and delete the old
                to_delete.add((exclusion_cidr, record["list_id"]))
                new_subnets.append((subnet, record["list_id"], record["expires_at"]))
        else:
            # either no subnets returned or many which means the original needs to be deleted
            to_delete.add((exclusion_cidr, record["list_id"]))
            for exc_subnet in exclusion_subnets:
                new_subnets.append((exc_subnet, record["list_id"], record["expires_at"]))

    # Execute the queries
    await conn.executemany("delete from cidr where address = $1 and list_id = $2", list(to_delete))
    await conn.executemany(UPSERT_CIDR, new_subnets)


async def add_cidrs(conn: Connection, cidr_job: CidrJob) -> None:
    """Add the CIDRs included in the job."""
    stime = time.perf_counter()

    # Initial parsing
    result, ipv4_cidrs, ipv6_cidrs = await parse_raw_cidrs(cidrs=cidr_job.cidrs)
    if not ipv4_cidrs and not ipv6_cidrs:
        print(f"Add({cidr_job.list_type}): {result}")
        return

    if cidr_job.list_type == ListTypeEnum.DENY:
        # When adding CIDRs to a deny list, we only need to filter out CIDRs in current safe lists
        ipv4_cidrs, ipv6_cidrs = await filter_safe_cidrs(
            conn=conn, user_id=cidr_job.user_id, cidrs=ipv4_cidrs | ipv6_cidrs
        )
    else:
        # When adding CIDRs to a safe list, we must delete matching CIDRs in current deny lists
        # if the target safe list is enabled
        if cidr_job.list_enabled:
            await delete_excluded_cidrs(
                conn=conn,
                user_id=cidr_job.user_id,
                exclusion_cidrs=ipv4_cidrs | ipv6_cidrs,
                list_type=ListTypeEnum.DENY,
            )

    sql_params = []
    for cidr in ipv4_cidrs | ipv6_cidrs:
        result["total_final"] += 1
        expires_at = datetime.now(tz=timezone.utc) + timedelta(seconds=cidr_job.ttl) if cidr_job.ttl else None
        sql_params.append((cidr, cidr_job.list_id, expires_at))

    await conn.executemany(UPSERT_CIDR, sql_params)
    print(f"Add({cidr_job.list_type}): {result} - took {time.perf_counter() - stime} seconds")


async def delete_cidrs(conn: Connection, cidr_job: CidrJob) -> None:
    """Delete the CIDRs included in the job."""
    stime = time.perf_counter()

    # Initial parsing
    result, ipv4_cidrs, ipv6_cidrs = await parse_raw_cidrs(cidrs=cidr_job.cidrs, only_global=False)
    if not ipv4_cidrs and not ipv6_cidrs:
        return

    await delete_excluded_cidrs(
        conn=conn, user_id=cidr_job.user_id, exclusion_cidrs=ipv4_cidrs | ipv6_cidrs, list_id=cidr_job.list_id
    )

    print(f"Delete({cidr_job.list_type}): {result} - took {time.perf_counter() - stime} seconds")


async def update_cleanup(conn: Connection, cidr_job: CidrJob) -> None:
    """Do a CIDR cleanup from denylists when a safelist is re-enabled."""
    stime = time.perf_counter()

    if cidr_job.list_type != ListTypeEnum.SAFE:
        raise ValueError("update_cleanup() should only process safe lists.")

    # This job doesn't actually carry the CIDRs from the safelist, we get them here
    num_addresses = 0
    all_addresses = set()
    for record in await conn.fetch(SELECT_ENABLED_CIDRS_BY_LIST_ID, cidr_job.list_id):
        num_addresses += 1
        all_addresses.add(ip_network(record["address"]))
    ipv4_collapsed = set(collapse_addresses(x for x in all_addresses if x.version == 4))
    ipv6_collapsed = set(collapse_addresses(x for x in all_addresses if x.version == 6))

    await delete_excluded_cidrs(
        conn=conn,
        user_id=cidr_job.user_id,
        exclusion_cidrs=ipv4_collapsed | ipv6_collapsed,
        list_type=ListTypeEnum.DENY,
    )
    print(f"UpdateCleanup({cidr_job.list_type}): for {num_addresses} cidrs took {time.perf_counter() - stime} seconds")


class CidrWorker:
    """Consumes the job queue that inserts and deletes CIDRs in/from lists."""

    keep_running: bool

    def __init__(self) -> None:
        self.keep_running = True

    def stop(self) -> None:
        """Stop CidrWorker consume_loop."""
        print("Stopping CidrWorker.")
        self.keep_running = False

    async def run(self) -> None:
        """Start the bg thread with consume_loop."""
        t = threading.Thread(
            target=asyncio.run, args=(self._consume_loop(),), name="job_queue_worker_thread", daemon=True
        )
        t.start()

    async def run_once(self) -> None:
        """Consume one batch of jobs and quit.

        Mostly used for testing.
        """
        await self._process_jobs()

    async def _consume_loop(self) -> None:
        """Consume jobs in a loop."""
        try:
            print(f"Starting CidrWorker.consume_loop() - {self.keep_running=}")
            while self.keep_running:
                await self._process_jobs()
                await asyncio.sleep(settings.JOB_QUEUE_QUERY_INTERVAL)
        except KeyboardInterrupt:
            self.keep_running = False

    async def _process_jobs(self) -> None:
        """Process one batch of jobs."""
        async for conn in get_connection():
            async with conn.transaction():
                for record in await conn.fetch(CONSUME_JOB_QUERY):
                    cidr_job = cidrjob_dec.decode(record["payload"])
                    if cidr_job.action == ActionEnum.ADD:
                        await add_cidrs(conn=conn, cidr_job=cidr_job)
                    elif cidr_job.action == ActionEnum.DELETE:
                        await delete_cidrs(conn=conn, cidr_job=cidr_job)
                    elif cidr_job.action == ActionEnum.UPDATE:
                        await update_cleanup(conn=conn, cidr_job=cidr_job)
