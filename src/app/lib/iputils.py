from collections.abc import Generator
from ipaddress import (
    IPv4Address,
    IPv4Network,
    IPv6Address,
    IPv6Network,
    collapse_addresses,
    summarize_address_range,
)


def exclude_address_raw(
    base_range: tuple[int, int],
    exclude_range: tuple[int, int],
) -> Generator[tuple[int, int], None, None]:
    """Excludes a network from another.

    The range can be obtained from an ipaddress.IPv[4|6]Network object by casting it
    to an integer or accessing the protected field ``_ip``, i.e.:

        ```
        ipn = IPv4Network("10.10.0.0/24")
        ipn.network_address._ip, ipn.broadcast_address._ip
        (168427520, 168427775)
        ```

    Both ranges must be of the same IP version.

    Args:
    ----
        base_range (tuple[int, int]): IP Range to be excluded
        exclude_range(tuple[int, int]): IP Range that tries to exclude base_range

    Returns:
    -------
        Generator[tuple[int, int], None, None]: IP Ranges left after the exclusion
    """
    # --x--x-|--|-----
    # -------|--|-x-x-
    if base_range[0] > exclude_range[1] or base_range[1] < exclude_range[0]:
        # exclude_range does not overlap with base_range, we return the full base_range
        yield base_range
    # ---x-|------|-x-
    # -----X------|-x-
    # ---x-|------X---
    # -----X------X---
    elif base_range[0] >= exclude_range[0] and base_range[1] <= exclude_range[1]:
        # exclude_range fully overlaps base_range, we return nothing
        return
    # ---x--|---x--|--
    elif base_range[0] > exclude_range[0] and base_range[1] > exclude_range[1]:
        yield exclude_range[1] + 1, base_range[1]
    # ---|--x---|--x--
    elif base_range[0] < exclude_range[0] and base_range[1] < exclude_range[1]:
        yield base_range[0], exclude_range[0] - 1
    # -----X---x--|---
    elif base_range[0] == exclude_range[0]:
        # exclude range starts together with base_range and ends before base_range
        yield exclude_range[1] + 1, base_range[1]
    # -----|--x---X---
    elif base_range[1] == exclude_range[1]:
        # exclude range ends together with base_range and starts after base_range
        yield base_range[0], exclude_range[0] - 1
    # ---|--x---x--|--
    else:
        # exclude range creates two new ranges
        yield base_range[0], exclude_range[0] - 1
        yield exclude_range[1] + 1, base_range[1]


def exclude_address(
    base_net: IPv4Network,
    exclude_net: IPv6Network,
    base_class,
) -> Generator[IPv4Network | IPv6Network, None, None]:
    """Excludes a network from another.

    Accepts and returns ipaddress network objects.
    """
    base_range = base_net.network_address._ip, base_net.broadcast_address._ip  # type: ignore
    exclude_range = exclude_net.network_address._ip, exclude_net.broadcast_address._ip  # type: ignore

    for subn_range in exclude_address_raw(base_range=base_range, exclude_range=exclude_range):
        yield from summarize_address_range(base_class(subn_range[0]), base_class(subn_range[1]))


async def address_exclude_many(
    cidr: IPv4Network | IPv6Network, exclusion_cidrs: set[IPv4Network | IPv6Network]
) -> set[IPv4Network | IPv6Network]:
    """Excludes addresses from ``cidr`` present in any ``exclusion_cidrs``, subnetting if necessary."""

    async def _exclude_from_subnets(_subnet_ranges, _exclusion):
        exclude_range = _exclusion.network_address._ip, _exclusion.broadcast_address._ip
        new_subnet_ranges = set()
        for isub_range in _subnet_ranges:
            for _subnet_range in exclude_address_raw(base_range=isub_range, exclude_range=exclude_range):
                new_subnet_ranges.add(_subnet_range)
        return new_subnet_ranges

    base_class = IPv4Address if cidr.version == 4 else IPv6Address

    subnet_ranges = {(cidr.network_address._ip, cidr.broadcast_address._ip)}  # type:ignore
    for exclusion_cidr in (x for x in exclusion_cidrs if x.version == cidr.version):
        subnet_ranges = await _exclude_from_subnets(subnet_ranges, exclusion_cidr)
        if not subnet_ranges:
            break

    final_subnets = set()
    for subnet_range in subnet_ranges:
        for subn in summarize_address_range(base_class(subnet_range[0]), base_class(subnet_range[1])):
            final_subnets.add(subn)

    return set(collapse_addresses(iter(final_subnets)))  # type: ignore


async def address_exclude_many_2(
    cidr: IPv4Network | IPv6Network, exclusion_cidrs: set[IPv4Network | IPv6Network]
) -> set[IPv4Network | IPv6Network]:
    """Excludes addresses from ``cidr`` present in any ``exclusion_cidrs``, subnetting if necessary.

    Slower than address_exclude_many
    """

    def _exclude_from_subnets(_subnets, _exclusion):
        new_subnets = set()
        for isub in _subnets:
            if not isub.subnet_of(_exclusion):
                try:
                    for isub2 in isub.address_exclude(_exclusion):
                        new_subnets.add(isub2)
                except ValueError:
                    new_subnets.add(isub)
                    continue
        return new_subnets

    subnets = {cidr}
    for exclusion_cidr in (x for x in exclusion_cidrs if x.version == cidr.version):
        if not subnets:
            break
        subnets = _exclude_from_subnets(subnets, exclusion_cidr)
    return set(collapse_addresses(iter(subnets)))  # type: ignore
