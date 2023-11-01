import asyncio

from app.domain.auth.services import create_user
from app.lib.db.base import get_connection
from app.lib.settings import get_settings

settings = get_settings()


async def create_default_admin_user() -> None:
    """Initialize default admin user if the environment variables are present."""
    if not (settings.DEFAULT_ADMIN_USER and settings.DEFAULT_ADMIN_USER_PASSWORD):
        return

    await asyncio.sleep(2)

    async for conn in get_connection():
        async with conn.transaction():
            if await conn.fetchval("select login from user_login where login = $1", settings.DEFAULT_ADMIN_USER):
                return  # Login already exists

    await create_user(login=settings.DEFAULT_ADMIN_USER, password=settings.DEFAULT_ADMIN_USER_PASSWORD, superuser=True)
