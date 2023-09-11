import uuid
from datetime import datetime
from enum import StrEnum
from typing import Annotated

from msgspec import Meta, Struct, field

from app.lib.default_factories import datetime_no_microseconds
from litestar.dto import DTOConfig, MsgspecDTO

MIN_PLAIN_PASSWORD_LENGTH = 10
MAX_PLAIN_PASSWORD_LENGTH = 64
MIN_LOGIN_LENGTH = 3
MAX_LOGIN_LENGTH = 64


class UserRoleEnum(StrEnum):
    USER = "USER"
    SUPERUSER = "SUPERUSER"


LoginStr = Annotated[
    str,
    Meta(
        min_length=MIN_LOGIN_LENGTH,
        max_length=MAX_LOGIN_LENGTH,
        pattern="^[a-z][a-z0-9_]*$",
        description="Only lowercase letters numbers and '_' allowed, must start with a letter.",
    ),
]

PasswordStr = Annotated[
    str,
    Meta(
        min_length=MIN_PLAIN_PASSWORD_LENGTH,
        max_length=MAX_PLAIN_PASSWORD_LENGTH,
        pattern="(?=.*[0-9])(?=.*[a-z])(?=.*[A-Z]).*",
        description="Minimum ten characters, at least one uppercase letter, one lowercase letter and one number.",
    ),
]


class User(Struct):
    login: LoginStr
    salt: str
    hashed_password: str
    id: uuid.UUID = field(default_factory=uuid.uuid4)  # noqa: A003
    role: UserRoleEnum = UserRoleEnum.USER
    created_at: datetime = field(default_factory=datetime_no_microseconds)
    updated_at: datetime = field(default_factory=datetime_no_microseconds)


class UserLoginOrCreate(Struct):
    login: LoginStr
    password: PasswordStr


class UserChangePassword(UserLoginOrCreate):
    new_password: PasswordStr


class UserReadDTO(MsgspecDTO[User]):
    config = DTOConfig(exclude={"salt", "hashed_password"})


class Token(Struct):
    """Token payload.

    exp: time at which the JWT will expire
    iat: time when the JWT was created
    sub: user/login identification
    """

    exp: datetime | int
    iat: datetime | int
    sub: uuid.UUID
    login: str

    def __post_init__(self) -> None:  # noqa: D105
        if isinstance(self.exp, datetime):
            self.exp = int(self.exp.timestamp())
        if isinstance(self.iat, datetime):
            self.iat = int(self.iat.timestamp())


class TokenResponse(Struct):
    access_token: str
    expires_at: datetime
    expires_in: int
    token_type: str = "Bearer"


class TokenUser(Struct):
    """To cache the middleware response."""

    token: Token
    user: User
