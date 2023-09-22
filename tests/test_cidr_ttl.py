import asyncio

import pytest
from conftest import get_api_token_header
from litestar.status_codes import HTTP_200_OK, HTTP_201_CREATED, HTTP_400_BAD_REQUEST
from litestar.testing import AsyncTestClient

from app.domain.lists.schemas import ListTypeEnum
from app.lib.scheduled_tasks import TaskDeleteExpired
from app.lib.worker import CidrWorker


@pytest.mark.asyncio
async def test_cidr_ttl(test_client: AsyncTestClient) -> None:
    async with test_client as client:
        api_token_header = await get_api_token_header(client)
        task_delete_expired = TaskDeleteExpired()
        worker = CidrWorker()

        # Create a Deny list
        list_deny = {"enabled": True, "id": "TEST_CIDR_TTL_DENY1", "list_type": ListTypeEnum.DENY}
        response = await client.post("/v1/list", json=list_deny, headers=api_token_header)
        assert response.status_code == HTTP_201_CREATED
        assert response.json()["id"] == list_deny["id"]
        assert response.json()["list_type"] == list_deny["list_type"]

        # Try to add an incorrect TTL
        payload = {"cidrs": ["13.1.1.0/24"], "ttl": 0}
        response = await client.post(f"/v1/list/{list_deny['id']}/cidr/add", json=payload, headers=api_token_header)
        assert response.status_code == HTTP_400_BAD_REQUEST
        payload = {"cidrs": ["13.1.1.0/24"], "ttl": -1}
        response = await client.post(f"/v1/list/{list_deny['id']}/cidr/add", json=payload, headers=api_token_header)
        assert response.status_code == HTTP_400_BAD_REQUEST

        # 1. Add a CIDR with 10 TTL
        payload = {"cidrs": ["77.0.1.0/24"], "ttl": 7}
        response = await client.post(f"/v1/list/{list_deny['id']}/cidr/add", json=payload, headers=api_token_header)
        assert response.status_code == HTTP_201_CREATED

        # 2. Run worker and delete task
        await worker.run_once()
        await task_delete_expired.run_once()

        # 3. Ensure the CIDR is still in the list
        response = await client.get(
            f"/v1/cidr/collapsed?list_type={ListTypeEnum.DENY}&list_id={list_deny['id']}", headers=api_token_header
        )
        assert response.status_code == HTTP_200_OK
        assert len(response.json()) > 0
        assert response.json()[0] == payload["cidrs"][0]

        # 4. Wait longer, until the ttl is expired and then run delete task
        await asyncio.sleep(payload["ttl"] + 1)
        await task_delete_expired.run_once()

        # 5. Ensure the CIDR has been deleted
        response = await client.get(
            f"/v1/cidr/collapsed?list_type={ListTypeEnum.DENY}&list_id={list_deny['id']}", headers=api_token_header
        )
        assert response.status_code == HTTP_200_OK
        assert len(response.json()) == 0
