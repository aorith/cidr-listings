import pytest
from conftest import get_api_token_header
from litestar.status_codes import HTTP_200_OK, HTTP_201_CREATED
from litestar.testing import AsyncTestClient

from app.domain.lists.schemas import ListTypeEnum
from app.lib.worker import CidrWorker


@pytest.mark.asyncio
async def test_cidr_filters(test_client: AsyncTestClient) -> None:
    async with test_client as client:
        api_token_header = await get_api_token_header(client)
        worker = CidrWorker()

        list_safe_1 = {
            "enabled": True,
            "id": "TEST_TAGS_SAFE1",
            "list_type": ListTypeEnum.SAFE,
            "tags": ["TAG1", "COMMON"],
        }
        list_safe_2 = {
            "enabled": True,
            "id": "TEST_TAGS_SAFE2",
            "list_type": ListTypeEnum.SAFE,
            "tags": ["TAG2", "OK", "COMMON"],
        }

        # Safe list 1
        response = await client.post("/v1/list", json=list_safe_1, headers=api_token_header)
        assert response.status_code == HTTP_201_CREATED
        assert response.json()["id"] == list_safe_1["id"]
        assert response.json()["list_type"] == list_safe_1["list_type"]

        # Safe list 2
        response = await client.post("/v1/list", json=list_safe_2, headers=api_token_header)
        assert response.status_code == HTTP_201_CREATED
        assert response.json()["id"] == list_safe_2["id"]
        assert response.json()["list_type"] == list_safe_2["list_type"]

        # Add some CIDRs to the SAFE list 1
        safe_cidrs_payload_1 = {"cidrs": ["6.5.4.0/24", "3.2.1.0/24"]}
        response = await client.post(
            f"/v1/list/{list_safe_1['id']}/cidr/add", json=safe_cidrs_payload_1, headers=api_token_header
        )
        assert response.status_code == HTTP_201_CREATED

        # Add some CIDRs to the SAFE list 2
        safe_cidrs_payload_2 = {"cidrs": ["60.50.40.0/24", "30.20.10.0/24", "33.22.11.1/32"]}
        response = await client.post(
            f"/v1/list/{list_safe_2['id']}/cidr/add", json=safe_cidrs_payload_2, headers=api_token_header
        )
        assert response.status_code == HTTP_201_CREATED

        # Run worker to consume the job_queue
        await worker.run_once()

        # Query the list 1
        response = await client.get(
            f"/v1/cidr/?list_type={ListTypeEnum.SAFE}&list_id={list_safe_1['id']}", headers=api_token_header
        )
        assert response.status_code == HTTP_200_OK
        assert len(response.json()) == 2

        # Query the list 2
        response = await client.get(
            f"/v1/cidr/?list_type={ListTypeEnum.SAFE}&list_id={list_safe_2['id']}", headers=api_token_header
        )
        assert response.status_code == HTTP_200_OK
        assert len(response.json()) == 3

        # Filter by tags of list 1
        response = await client.get(
            f"/v1/cidr/collapsed/?list_type={ListTypeEnum.SAFE}&tags=TAG1",
            headers=api_token_header,
        )
        assert response.status_code == HTTP_200_OK
        assert len(response.json()) == 2
        assert sorted(response.json()) == sorted(safe_cidrs_payload_1["cidrs"])

        # Filter by tags of list 2
        response = await client.get(
            f"/v1/cidr/collapsed/?list_type={ListTypeEnum.SAFE}&tags=TAG2",
            headers=api_token_header,
        )
        assert response.status_code == HTTP_200_OK
        assert len(response.json()) == 3
        assert sorted(response.json()) == sorted(safe_cidrs_payload_2["cidrs"])

        # Filter by common tag 'COMMON'
        response = await client.get(
            f"/v1/cidr/collapsed/?list_type={ListTypeEnum.SAFE}&tags=COMMON",
            headers=api_token_header,
        )
        assert response.status_code == HTTP_200_OK
        assert len(response.json()) == 5
        assert sorted(response.json()) == sorted(safe_cidrs_payload_1["cidrs"] + safe_cidrs_payload_2["cidrs"])

        # Filter tag XXX1, no addresses should be returned
        response = await client.get(
            f"/v1/cidr/collapsed/?list_type={ListTypeEnum.SAFE}&tags=XXX1",
            headers=api_token_header,
        )
        assert response.status_code == HTTP_200_OK
        assert len(response.json()) == 0

        # Filter tag TAG1
        response = await client.get(
            f"/v1/cidr/collapsed/?list_type={ListTypeEnum.SAFE}&tags=TAG1",
            headers=api_token_header,
        )
        assert response.status_code == HTTP_200_OK
        assert len(response.json()) == 2

        # Filter tag OK
        response = await client.get(
            f"/v1/cidr/collapsed/?list_type={ListTypeEnum.SAFE}&tags=OK",
            headers=api_token_header,
        )
        assert response.status_code == HTTP_200_OK
        assert len(response.json()) == 3

        # Filter by common tag 'COMMON' and by-ip-version
        response = await client.get(
            f"/v1/cidr/collapsed/by-ip-version/?list_type={ListTypeEnum.SAFE}&tags=COMMON",
            headers=api_token_header,
        )
        assert response.status_code == HTTP_200_OK
        assert len(response.json()["ipv4"]) == 5
        assert sorted(response.json()["ipv4"]) == sorted(safe_cidrs_payload_1["cidrs"] + safe_cidrs_payload_2["cidrs"])

        # Disable the list1
        list_safe_1_disabled = list_safe_1.copy()
        list_safe_1_disabled["enabled"] = False
        response = await client.put(
            f"/v1/list/{list_safe_1_disabled['id']}", json=list_safe_1_disabled, headers=api_token_header
        )
        assert response.status_code == HTTP_200_OK

        # Filter by common tag 'COMMON', only the second list should return content
        response = await client.get(
            f"/v1/cidr/collapsed/?list_type={ListTypeEnum.SAFE}&tags=COMMON",
            headers=api_token_header,
        )
        assert response.status_code == HTTP_200_OK
        assert len(response.json()) == 3
        assert sorted(response.json()) == sorted(safe_cidrs_payload_2["cidrs"])
