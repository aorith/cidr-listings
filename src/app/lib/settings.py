from functools import lru_cache

from pydantic import Field, ValidationError
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Pydantic class to manage environment variables.

    Default values are overridden by the environment
    variables with the same name but in uppercase.
    """

    # DB
    DB_USERNAME: str = "test"
    DB_PASSWORD: str = "test1234"
    DB_HOST: str = "127.0.0.1"
    DB_PORT: int = 5432
    DB_NAME: str = "cidr"
    DB_POOL_MIN_SIZE: int = 5
    """Minimal number of connections that a pool starts with."""
    DB_POOL_MAX_SIZE: int = 10
    """Maximum number of connections that a pool can allocate."""
    DB_POOL_MAX_IDLE_TIMEOUT: int = Field(default=300, ge=30)
    """Maximum time a connection can be idle."""
    DB_POOL_ACQUIRE_CONN_TIMEOUT: int = 5
    """Maximum time allowed to get a connection from the pool."""
    DB_POOL_CLOSE_TIMEOUT: int = 10
    """Timeout to close the pool."""

    # Worker
    JOB_QUEUE_QUERY_INTERVAL: int = 5
    """Interval between the DB query that fetches the jobs from the 'job_queue' table."""

    # Scheduler tasks
    SCHEDULER_DELETE_EXPIRED_INTERVAL: int = 30
    """Interval between the task that deletes expired CIDRs."""

    # APP
    VERSION: str = "1.0"
    DEBUG: bool = False

    # DEFAULT_USER
    DEFAULT_ADMIN_USER: str | None = None
    DEFAULT_ADMIN_USER_PASSWORD: str | None = None

    # JWT
    JWT_SECRET: str
    ALGORITHM: str = "HS256"
    API_KEY_COOKIE: str = "apisessionkey"

    DEFAULT_TOKEN_TTL_SECONDS: int = 60 * 60 * 24
    """Expiration time for the token"""

    AUTH_CACHE_SECONDS: int = 120
    """Internal TTL for the cached authentication results"""

    # OpenAPI
    OPENAPI_TITLE: str = "CIDR Listings"
    OPENAPI_CONTACT_NAME: str = "Manuel Sanchez Pinar"
    OPENAPI_CONTACT_EMAIL: str = "aomanu@gmail.com"
    OPENAPI_PATH: str = "/docs"


@lru_cache
def get_settings():
    """Return cached settings so it's the same instance everywhere."""
    try:
        return Settings()  # type: ignore
    except ValidationError as err:
        print("Could not load settings.", err)  # noqa: T201
        raise
