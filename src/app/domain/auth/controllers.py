from asyncpg.pool import PoolConnectionProxy

from app.domain.auth.schemas import (
    Token,
    TokenResponse,
    User,
    UserChangePassword,
    UserLoginOrCreate,
    UserReadDTO,
    UserRoleEnum,
)
from app.domain.auth.services import generate_token
from app.lib.authcrypt import generate_salt_and_hashed_password
from app.lib.settings import get_settings
from litestar import Request, Response, post, put
from litestar.controller import Controller
from litestar.datastructures import ResponseHeader, State
from litestar.exceptions import (
    HTTPException,
    InternalServerException,
    NotAuthorizedException,
    ValidationException,
)
from litestar.status_codes import HTTP_200_OK

settings = get_settings()

INSERT_USER = """
INSERT INTO user_login
    (id, login, salt, hashed_password)
VALUES
    ($1, $2, $3, $4);
"""


class AuthAdminController(Controller):
    path = "/v1/admin"
    tags = ["Admin"]

    @post("/signup", return_dto=UserReadDTO)
    async def create_user(
        self, request: Request[User, Token, State], conn: PoolConnectionProxy, data: UserLoginOrCreate
    ) -> User:
        """Create user."""
        current_user_record = await conn.fetchrow("select * from user_login where id = $1", request.user.id)
        if not current_user_record:
            raise NotAuthorizedException()
        if current_user_record["role"] != UserRoleEnum.SUPERUSER:
            raise NotAuthorizedException()

        if await conn.fetchval("select login from user_login where login = $1", data.login):
            raise HTTPException(status_code=409, detail="Login name already taken.")
        salt, hashed_password = await generate_salt_and_hashed_password(plain_password=data.password)
        user = User(login=data.login, salt=salt, hashed_password=hashed_password)
        await conn.execute(INSERT_USER, user.id, user.login, user.salt, user.hashed_password)
        return user


class AuthController(Controller):
    path = "/v1/auth"
    tags = ["Auth"]

    @put("/password", status_code=HTTP_200_OK)
    async def change_password(self, request: Request, conn: PoolConnectionProxy, data: UserChangePassword) -> None:
        """Change password."""
        if data.password == data.new_password:
            raise ValidationException("New password must be different.")
        # validate the user generatin a login token with the current password
        user_login = UserLoginOrCreate(login=data.login, password=data.password)
        _ = await generate_token(conn=conn, data=user_login)
        # change the password
        salt, hashed_password = await generate_salt_and_hashed_password(plain_password=data.new_password)
        _id = await conn.fetchval(
            "update user_login set salt = $1, hashed_password = $2 where login = $3 returning id",
            salt,
            hashed_password,
            data.login,
        )
        if not _id:
            raise InternalServerException("Password couldn't be updated.")

    @post(
        "/token",
        status_code=HTTP_200_OK,
        response_headers=[
            ResponseHeader(name=settings.API_KEY_HEADER, value="Bearer <TOKEN>", description="Token header")
        ],
    )
    async def generate_token(self, conn: PoolConnectionProxy, data: UserLoginOrCreate) -> Response[TokenResponse]:
        """Generate an API access token."""
        token = await generate_token(conn=conn, data=data)
        return Response(
            token,
            headers=[
                ResponseHeader(name=settings.API_KEY_HEADER, value=f"Bearer {token.access_token}", description="Token")
            ],
        )
