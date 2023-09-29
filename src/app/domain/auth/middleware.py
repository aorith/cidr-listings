import msgspec
from litestar.connection import ASGIConnection
from litestar.exceptions import NotAuthorizedException
from litestar.middleware import AbstractAuthenticationMiddleware, AuthenticationResult
from litestar.stores.memory import MemoryStore

from app.domain.auth.jwt import decode_jwt_token
from app.domain.auth.schemas import TokenUser, User
from app.lib.db.base import get_dbmanager
from app.lib.settings import get_settings

settings = get_settings()

store_encoder = msgspec.msgpack.Encoder()
store_decoder = msgspec.msgpack.Decoder(type=TokenUser)
store = MemoryStore()


class JWTAuthenticationMiddleware(AbstractAuthenticationMiddleware):
    async def authenticate_request(self, connection: ASGIConnection) -> AuthenticationResult:
        """Parse the request api key stored in the header and retrieve the user correlating to the token from the DB."""
        if not (auth_header := connection.headers.get("Authorization")):
            if not (cookie_header := connection.cookies.get(settings.API_KEY_COOKIE)):
                raise NotAuthorizedException()
            auth_header = f"Bearer {cookie_header}"

        auth_header = auth_header.strip()
        if not auth_header.startswith("Bearer"):
            raise NotAuthorizedException("Invalid token, should be: 'Bearer <TOKEN>'")
        try:
            auth_header = auth_header.split(" ", 1)[1]
        except IndexError:
            raise NotAuthorizedException(  # noqa: B904
                "Invalid token, should be: 'Bearer <TOKEN>' without extra spaces between 'Bearer' and '<TOKEN>'"
            )

        # try to get a cached token_user pair to avoid a trip to the DB
        if cached_token := await store.get(auth_header):
            token_user = store_decoder.decode(cached_token)
            return AuthenticationResult(user=token_user.user, auth=token_user.token)

        token = decode_jwt_token(encoded_token=auth_header)

        user_record = None
        dbmngr = get_dbmanager()
        async for conn in dbmngr.get_connection():
            user_record = await conn.fetchrow("select * from user_login where id = $1", token.sub)

        if not user_record:
            raise NotAuthorizedException()

        user = User(**user_record)
        token_user = TokenUser(token=token, user=user)
        await store.set(auth_header, store_encoder.encode(token_user), expires_in=settings.AUTH_CACHE_SECONDS)
        return AuthenticationResult(user=user, auth=token)
