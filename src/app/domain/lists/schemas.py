import uuid
from datetime import datetime
from enum import StrEnum
from typing import Annotated

from litestar.dto import DTOConfig, MsgspecDTO
from msgspec import Meta, Struct, field

from app.domain.cidr.schemas import CidrNL
from app.lib.default_factories import datetime_no_microseconds

MAX_LIST_ID_LEN = 64
MAX_TAG_LEN = 16
MAX_DESCRIPTION_LEN = 256

LIST_ID_PATTERN = "^[A-Z][A-Z0-9_]*$"
TAG_PATTERN = "^[A-Z][A-Z0-9]*$"
TAG_PARAMS_PATTERN = "^([A-Z][A-Z0-9]*,?)+$"

CidrType = Annotated[str, Meta(description="IP address or network in CIDR notation.")]

CidrTTL = Annotated[
    int | None,
    Meta(
        description="Time to live (TTL) of each CIDR in seconds, after that they'll beremoved from the list, when this field is not set CIDRs won't be removed."
    ),
]

TagStr = Annotated[
    str,
    Meta(
        max_length=MAX_TAG_LEN,
        pattern=TAG_PATTERN,
        description="Uppercase letters and numbers, starting with a letter. The 'DEFAULT' tag will be always present.",
    ),
]


def default_tag_factory() -> list[TagStr]:
    return ["DEFAULT"]


class ListTypeEnum(StrEnum):
    DENY = "DENY"
    SAFE = "SAFE"


class ActionEnum(StrEnum):
    ADD = "add"
    DELETE = "delete"
    UPDATE = "update"


class ListBase(Struct):
    id: Annotated[
        str,
        Meta(
            max_length=MAX_LIST_ID_LEN,
            pattern=LIST_ID_PATTERN,
            description="Uppercase letters, numbers and underscores (`_`) allowed, must start with a letter.",
        ),
    ]
    list_type: ListTypeEnum
    tags: list[TagStr] = field(default_factory=default_tag_factory)
    enabled: bool = False
    description: Annotated[str, Meta(max_length=MAX_DESCRIPTION_LEN)] = field(default="")


class ListFull(ListBase):
    user_id: uuid.UUID = field(default_factory=uuid.uuid4)
    created_at: datetime = field(default_factory=datetime_no_microseconds)
    updated_at: datetime = field(default_factory=datetime_no_microseconds)


class ListCreateDTO(MsgspecDTO[ListFull]):
    config = DTOConfig(exclude={"user_id", "created_at", "updated_at"})


class ListUpdateDTO(MsgspecDTO[ListFull]):
    config = DTOConfig(partial=True, exclude={"id", "user_id", "created_at", "updated_at"})


class CidrList(ListFull):
    cidrs: list[CidrNL] = field(default_factory=list)


class CidrDelete(Struct):
    cidrs: list[CidrType]


class CidrAdd(CidrDelete):
    cidrs: list[CidrType]
    ttl: CidrTTL = None


class CidrJob(Struct):
    list_id: str
    list_type: ListTypeEnum
    list_enabled: bool
    user_id: uuid.UUID
    action: ActionEnum
    cidrs: list[str]
    ttl: CidrTTL = None
    job_id: uuid.UUID = field(default_factory=uuid.uuid4)
