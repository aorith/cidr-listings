import asyncio
from datetime import datetime, timezone
from pathlib import Path

from asyncpg import Connection

from app.lib.db.base import get_connection

MIGRATIONS_DIR = Path(__file__).parent.resolve() / "migrations"

CHECK_MIGRATIONS_TABLE = """
SELECT EXISTS (
    SELECT FROM
        pg_tables
    WHERE
        schemaname = 'public' AND
        tablename  = '_migrations'
    );
"""

MIGRATIONS_TABLE_DDL = """
BEGIN;
CREATE TABLE _migrations (
    version INTEGER NOT NULL PRIMARY KEY,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
INSERT INTO _migrations (version) VALUES (-1);
COMMIT;
"""


async def create_migrations_table(conn: Connection) -> None:
    """Create migrations table."""
    print(">>> Creating migrations table ...")
    await conn.execute(MIGRATIONS_TABLE_DDL)


async def get_current_version(conn: Connection) -> int | None:
    """Get current DB version."""
    print("- Retrieving current version ...")
    ver = await conn.fetchval("select version from _migrations")
    return int(ver) if ver else None


async def run_migration(conn: Connection, migrations_dir: Path, sql: str, sql_ver: int) -> None:
    """Run migration."""
    print(f">>> Executing SQL migration = {sql}")
    with (migrations_dir / Path(sql)).open("r") as fd:
        data = fd.read().encode()
    await conn.execute(data.decode())
    await conn.execute("update _migrations set version = $1, updated_at = $2", sql_ver, datetime.now(tz=timezone.utc))
    print(f"- Current version is now = {sql_ver}")


async def run_migrations() -> int:
    """Run migrations."""
    async for conn in get_connection():
        async with conn.transaction():
            if await conn.fetchval(CHECK_MIGRATIONS_TABLE):  # returns True or False directly
                curr_ver = await get_current_version(conn)
            else:
                await create_migrations_table(conn)
                curr_ver = -1

            print(f"- Current version = {curr_ver}")
            if curr_ver is None:
                raise ValueError("Current version cannot be None, _migrations table wasn't created successfully.")
            print("- Reading migration files ...")
            migration_sqls = sorted([x.name for x in MIGRATIONS_DIR.glob("*.sql")])
            for sql in migration_sqls:
                sql_ver = int(sql.split("_")[0])
                if sql_ver > curr_ver:
                    await run_migration(conn, MIGRATIONS_DIR, sql, sql_ver)
                print(f"- {sql}  ... OK")
    return 0


async def run_migrations_from_cli() -> None:
    """Run migrations from cli."""
    await run_migrations()


async def main() -> int:
    """Run migrations."""
    return await run_migrations()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
