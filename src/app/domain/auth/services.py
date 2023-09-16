from asyncpg.pool import PoolConnectionProxy
from litestar.exceptions import NotAuthorizedException

from app.domain.auth.jwt import encode_jwt_token
from app.domain.auth.schemas import TokenResponse, User, UserLoginOrCreate, UserRoleEnum
from app.lib.authcrypt import generate_salt_and_hashed_password, verify_password
from app.lib.db.base import get_connection

INSERT_USER = """
INSERT INTO user_login
    (id, login, salt, hashed_password, role)
VALUES
    ($1, $2, $3, $4, $5);
"""


async def create_user(login: str, password: str, superuser: bool = False) -> None:
    """Create a new user."""
    async for conn in get_connection():
        async with conn.transaction():
            if await conn.fetchval("select login from user_login where login = $1", login):
                print("Login name already taken.")
                # don't return here to avoid:
                # RuntimeWarning: coroutine 'PoolConnectionHolder.release' was never awaited
            else:
                salt, hashed_password = await generate_salt_and_hashed_password(plain_password=password)
                role = UserRoleEnum.SUPERUSER if superuser else UserRoleEnum.USER

                user = User(login=login, salt=salt, hashed_password=hashed_password, role=role)
                await conn.execute(INSERT_USER, user.id, user.login, user.salt, user.hashed_password, user.role)
                print(user)
                print("User created successfully.")


async def generate_token(conn: PoolConnectionProxy, data: UserLoginOrCreate) -> TokenResponse:
    """Generate JWT token from an user login."""
    if not (record := await conn.fetchrow("select * from user_login where login = $1", data.login)):
        raise NotAuthorizedException("Wrong login or password.")
    if not await verify_password(
        salt=record["salt"], hashed_password=record["hashed_password"], plain_password=data.password
    ):
        raise NotAuthorizedException("Wrong login or password.")
    return encode_jwt_token(user_id=record["id"], login=record["login"])
