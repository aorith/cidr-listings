from datetime import datetime

from msgspec import Struct, field

from app.lib.default_factories import datetime_no_microseconds


class Cidr(Struct):
    address: str
    list_id: str
    expires_at: datetime | None = None
    created_at: datetime = field(default_factory=datetime_no_microseconds)
    updated_at: datetime = field(default_factory=datetime_no_microseconds)
    id: int | None = None


class CidrNL(Struct):
    """Same as Cidr but without list_id.

    for /v1/list/<id>/cidr.
    """

    address: str
    expires_at: datetime
    created_at: datetime
    updated_at: datetime


class CidrByVersion(Struct):
    ipv4: list[str]
    ipv6: list[str]
