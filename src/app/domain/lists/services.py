import itertools
import re
from ipaddress import IPv4Network, IPv6Network, ip_network

import msgspec
from asyncpg.pool import PoolConnectionProxy

from app.domain.lists.schemas import CidrJob

INSERT_JOB = """
INSERT INTO job_queue
    (job_id, payload)
VALUES
    ($1, $2::jsonb)
"""


IPV4_RE = re.compile(r"((?:[0-9]{1,3}\.){3}[0-9]{1,3}(?:\/[0-9]{1,2})?)")
IPV6_RE = re.compile(r"([A-Fa-f0-9:]+:[A-Fa-f0-9]*(?:\/[0-9]{1,3})?)")

json_enc = msgspec.json.Encoder()


def parse_raw_cidrs_input(raw_data: str) -> tuple[set[IPv4Network], set[IPv6Network]]:
    """Parse raw input string and return valid IPv4/IPv6 networks."""
    ipv4_valid: set[IPv4Network] = set()
    ipv6_valid: set[IPv6Network] = set()

    for i in itertools.chain(re.finditer(IPV4_RE, raw_data), re.finditer(IPV6_RE, raw_data)):
        try:
            ipn = ip_network(i.group(0), strict=False)
            if ipn.version == 4:
                ipv4_valid.add(ipn)
            else:
                ipv6_valid.add(ipn)
        except ValueError:
            continue

    return ipv4_valid, ipv6_valid


def parse_raw_cidrs_input_as_str(raw_data: str) -> tuple[set[str], set[str]]:
    """Parse raw input string and return valid IPv4/IPv6 networks as a string."""
    ipv4_valid, ipv6_valid = parse_raw_cidrs_input(raw_data=raw_data)
    return {x.compressed for x in ipv4_valid}, {x.compressed for x in ipv6_valid}


async def insert_cidr_job(job: CidrJob, conn: PoolConnectionProxy) -> None:
    """Insert a new CIDR Job."""
    cidr_job_json = json_enc.encode(job).decode()
    async with conn.transaction():
        await conn.execute(
            INSERT_JOB,
            job.job_id,
            cidr_job_json,
        )
