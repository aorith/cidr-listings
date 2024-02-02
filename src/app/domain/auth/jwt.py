from datetime import datetime, timedelta, timezone
from uuid import UUID

import jwt
from jwt import PyJWTError
from litestar.exceptions import NotAuthorizedException
from msgspec import to_builtins

from app.domain.auth.schemas import Token, TokenResponse
from app.lib.settings import get_settings

settings = get_settings()


def decode_jwt_token(encoded_token: str) -> Token:
    """Decode JWT token and return ``sub`` value.

    If the token is invalid or expired (i.e. the value stored under the exp key is in the past)
    an exception is raised.
    """
    try:
        payload = jwt.decode(jwt=encoded_token, key=settings.JWT_SECRET, algorithms=[settings.ALGORITHM])
        return Token(**payload)
    except PyJWTError as e:
        raise NotAuthorizedException("Invalid token") from e


def encode_jwt_token(user_id: UUID, login: str, expiration: int = settings.DEFAULT_TOKEN_TTL_SECONDS) -> TokenResponse:
    """Encode JWT token with expiration and a given user_id."""
    expires_at = datetime.now(tz=timezone.utc) + timedelta(seconds=expiration)
    token = Token(
        exp=expires_at,
        iat=datetime.now(tz=timezone.utc),
        sub=user_id,
        login=login,
    )
    token_encoded_str = jwt.encode(to_builtins(token), settings.JWT_SECRET, algorithm=settings.ALGORITHM)
    return TokenResponse(access_token=token_encoded_str, expires_in=expiration, expires_at=expires_at)
