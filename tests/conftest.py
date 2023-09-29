import os
import time

import pytest
from litestar.status_codes import HTTP_200_OK
from litestar.testing import AsyncTestClient

from app.lib.settings import get_settings
from app.main import app

settings = get_settings()

TEST_USER_PAYLOAD = {
    "login": os.getenv("TEST_USER", "test"),
    "password": os.getenv("TEST_USER_PASSWORD", "Ilovet3st!"),
}

# Scopes: function > class > module > package > session


async def get_api_token_header(client):
    response = await client.post("/v1/auth/token", json=TEST_USER_PAYLOAD)
    assert response.status_code == HTTP_200_OK
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


@pytest.fixture(scope="session")
def test_client() -> AsyncTestClient:
    settings.JOB_QUEUE_QUERY_INTERVAL = 1
    settings.SCHEDULER_DELETE_EXPIRED_INTERVAL = 1
    async_test_client = AsyncTestClient(app=app)
    time.sleep(1)  # wait for scheduler and worker to stop
    return async_test_client
