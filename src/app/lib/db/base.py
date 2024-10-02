import asyncio
from collections.abc import AsyncGenerator
from functools import lru_cache

import asyncpg

from app.lib.settings import get_settings

settings = get_settings()

dsn = (
    f"postgres://{settings.DB_USERNAME}:{settings.DB_PASSWORD}@{settings.DB_HOST}:{settings.DB_PORT}/{settings.DB_NAME}"
)


async def get_connection() -> AsyncGenerator[asyncpg.Connection, None]:
    """Get a connection to the DB."""
    conn = await asyncpg.connect(dsn=dsn)
    try:
        yield conn
    finally:
        await conn.close()


class DBManager:
    pool: asyncpg.Pool

    async def setup(self) -> None:
        """Initialize the DB pool."""
        pool = await asyncpg.create_pool(
            dsn=dsn,
            timeout=30,
            min_size=settings.DB_POOL_MIN_SIZE,
            max_size=settings.DB_POOL_MAX_SIZE,
            max_inactive_connection_lifetime=settings.DB_POOL_MAX_IDLE_TIMEOUT,
        )
        if not isinstance(pool, asyncpg.Pool):
            raise Exception("Pool is not initialized")
        self.pool = pool

    async def get_connection(self) -> AsyncGenerator[asyncpg.pool.PoolConnectionProxy, None]:
        """Get a connection from the pool."""
        conn = await self.pool.acquire(timeout=settings.DB_POOL_ACQUIRE_CONN_TIMEOUT)
        try:
            yield conn
        finally:
            await self.pool.release(conn)

    async def stop(self) -> None:
        """Close the pool."""
        try:
            if hasattr(self, "pool") and isinstance(self.pool, asyncpg.Pool) and not self.pool.is_closing():
                await asyncio.wait_for(self.pool.close(), timeout=settings.DB_POOL_CLOSE_TIMEOUT)
        except asyncio.TimeoutError:
            pass


@lru_cache
def get_dbmanager() -> DBManager:
    """Get DBManager singleton."""
    return DBManager()
