import ipaddress

import pytest
from conftest import get_api_token_header
from litestar.status_codes import HTTP_200_OK, HTTP_201_CREATED
from litestar.testing import AsyncTestClient

from app.domain.lists.schemas import ListTypeEnum
from app.lib.worker import CidrWorker


@pytest.mark.asyncio
async def test_job_tasks(test_client: AsyncTestClient) -> None:
    async with test_client as client:
        api_token_header = await get_api_token_header(client)
        worker = CidrWorker()

        # Deny list
        list_deny = {"enabled": True, "id": "TEST_CIDRJOB_DENY1", "list_type": ListTypeEnum.DENY}
        response = await client.post("/v1/list", json=list_deny, headers=api_token_header)
        assert response.status_code == HTTP_201_CREATED
        assert response.json()["id"] == list_deny["id"]
        assert response.json()["list_type"] == list_deny["list_type"]

        # Safe list
        list_safe = {"enabled": True, "id": "TEST_CIDRJOB_SAFE1", "list_type": ListTypeEnum.SAFE}
        response = await client.post("/v1/list", json=list_safe, headers=api_token_header)
        assert response.status_code == HTTP_201_CREATED
        assert response.json()["id"] == list_safe["id"]
        assert response.json()["list_type"] == list_safe["list_type"]

        # Add some CIDRs to the SAFE list
        safe_cidrs_payload = {"cidrs": ["13.1.0.0/16", "13.1.1.33"]}
        response = await client.post(
            f"/v1/list/{list_safe['id']}/cidr/add", json=safe_cidrs_payload, headers=api_token_header
        )
        assert response.status_code == HTTP_201_CREATED

        # Run worker to consume the job_queue
        await worker.run_once()

        # Query the list
        response = await client.get(
            f"/v1/cidr/?list_type={ListTypeEnum.SAFE}&list_id={list_safe['id']}", headers=api_token_header
        )
        assert response.status_code == HTTP_200_OK
        # ["13.1.0.0/16", "13.1.1.33"] must be collapsed into 13.1.0.0/16
        assert response.json()[0]["address"] == "13.1.0.0/16"

        # Try to add a network excluded in that range...
        payload = {"cidrs": ["13.1.1.0/24"]}
        response = await client.post(f"/v1/list/{list_deny['id']}/cidr/add", json=payload, headers=api_token_header)
        assert response.status_code == HTTP_201_CREATED

        # Run worker to consume the job_queue
        await worker.run_once()

        # The network should have been filtered
        response = await client.get(
            f"/v1/cidr/?list_type={ListTypeEnum.DENY}&list_id={list_deny['id']}", headers=api_token_header
        )
        assert response.status_code == HTTP_200_OK
        assert len(response.json()) == 0

        # Add non safe deny IPs
        payload = {"cidrs": ["1.2.3.4/32", "111.22.33.0/24", "4.3.2.1/32"]}
        response = await client.post(f"/v1/list/{list_deny['id']}/cidr/add", json=payload, headers=api_token_header)
        assert response.status_code == HTTP_201_CREATED

        # Run worker to consume the job_queue
        await worker.run_once()

        # Deny networks should be present
        response = await client.get(
            f"/v1/cidr/collapsed?list_type={ListTypeEnum.DENY}&list_id={list_deny['id']}", headers=api_token_header
        )
        assert response.status_code == HTTP_200_OK
        assert len(response.json()) == 3
        assert sorted(response.json()) == sorted(payload["cidrs"])

        # Test that exclusions happen automatically when adding IPs to enabled safelists
        safe_cidrs_payload = {"cidrs": ["111.22.0.0/16", "4.3.0.0/16"]}
        response = await client.post(
            f"/v1/list/{list_safe['id']}/cidr/add", json=safe_cidrs_payload, headers=api_token_header
        )
        assert response.status_code == HTTP_201_CREATED

        # Run worker to consume the job_queue
        await worker.run_once()

        # Safe networks should have been removed automatically from deny lists
        response = await client.get(
            f"/v1/cidr/collapsed?list_type={ListTypeEnum.DENY}&list_id={list_deny['id']}", headers=api_token_header
        )
        assert response.status_code == HTTP_200_OK
        assert len(response.json()) == 1
        assert response.json() == ["1.2.3.4/32"]

        # Test deletion
        # 1. ensure the IP is on the list
        payload = {"cidrs": ["111.22.0.0/16"]}
        response = await client.get(
            f"/v1/cidr/collapsed?list_type={ListTypeEnum.SAFE}&list_id={list_safe['id']}", headers=api_token_header
        )
        assert response.status_code == HTTP_200_OK
        assert payload["cidrs"][0] in response.json()
        # 2. delete it
        response = await client.post(f"/v1/list/{list_safe['id']}/cidr/delete", json=payload, headers=api_token_header)
        assert response.status_code == HTTP_201_CREATED
        # 3. Run worker to consume the job_queue
        await worker.run_once()
        # 4. Ensure the IP was deleted
        payload = {"cidrs": ["111.22.0.0/16"]}
        response = await client.get(
            f"/v1/cidr/collapsed?list_type={ListTypeEnum.SAFE}&list_id={list_safe['id']}", headers=api_token_header
        )
        assert response.status_code == HTTP_200_OK
        assert payload["cidrs"][0] not in response.json()

        # test that adding a IPv4Network to a denylist splits it in subnets when
        # an enabled safelists is present
        # safe: 66.66.1.0/26
        # deny: 66.66.1.0/24
        # after exclusions: 66.66.1.128/25, 66.66.1.64/26

        # 1. Delete current cidrs
        response = await client.get(
            f"/v1/cidr/collapsed?list_type={ListTypeEnum.DENY}&list_id={list_deny['id']}", headers=api_token_header
        )
        assert response.status_code == HTTP_200_OK
        delete_payload = {"cidrs": response.json()}
        response = await client.post(
            f"/v1/list/{list_deny['id']}/cidr/delete", json=delete_payload, headers=api_token_header
        )
        assert response.status_code == HTTP_201_CREATED

        # 2. Run worker to consume the job_queue
        await worker.run_once()

        # 3. Add the safe cidr
        safe_cidrs_payload = {"cidrs": ["66.66.1.0/26"]}
        response = await client.post(
            f"/v1/list/{list_safe['id']}/cidr/add", json=safe_cidrs_payload, headers=api_token_header
        )
        assert response.status_code == HTTP_201_CREATED

        # 4. Add the deny cidr
        deny_cidrs_payload = {"cidrs": ["66.66.1.0/24"]}
        response = await client.post(
            f"/v1/list/{list_deny['id']}/cidr/add", json=deny_cidrs_payload, headers=api_token_header
        )
        assert response.status_code == HTTP_201_CREATED

        # 5. Run worker to consume the job_queue
        await worker.run_once()

        # 6. Get the cidrs in the denylist and ensure they've been split accordingly
        response = await client.get(
            f"/v1/cidr/collapsed?list_type={ListTypeEnum.DENY}&list_id={list_deny['id']}", headers=api_token_header
        )
        assert response.status_code == HTTP_200_OK
        cidrs_in_denylist = response.json()
        safe_cidr = ipaddress.IPv4Network("66.66.1.0/26")
        deny_cidr = ipaddress.IPv4Network("66.66.1.0/24")
        after_exclusion = sorted([x.compressed for x in deny_cidr.address_exclude(safe_cidr)])
        assert sorted(cidrs_in_denylist) == after_exclusion

        # test that disabled safelists do not affect the result when adding IPs to the denylist
        # 1. Disable the safelist
        list_safe_disabled = list_safe.copy()
        list_safe_disabled["enabled"] = False
        response = await client.put(f"/v1/list/{list_safe['id']}", json=list_safe_disabled, headers=api_token_header)
        assert response.status_code == HTTP_200_OK

        # 2. Add back the deny ip
        deny_cidrs_payload = {"cidrs": ["66.66.1.0/24"]}
        response = await client.post(
            f"/v1/list/{list_deny['id']}/cidr/add", json=deny_cidrs_payload, headers=api_token_header
        )
        assert response.status_code == HTTP_201_CREATED

        # 3. Run worker to consume the job_queue
        await worker.run_once()

        # 4. Get the cidrs in the denylist, now the network didn't split
        response = await client.get(
            f"/v1/cidr/collapsed?list_type={ListTypeEnum.DENY}&list_id={list_deny['id']}", headers=api_token_header
        )
        assert response.status_code == HTTP_200_OK
        assert response.json()[0] == "66.66.1.0/24"

        # 1. Test that the denylist cidrs are split again when we re-enable the list
        response = await client.put(f"/v1/list/{list_safe['id']}", json=list_safe, headers=api_token_header)
        assert response.status_code == HTTP_200_OK

        # 2. Run worker to consume the job_queue
        await worker.run_once()

        # 3. Get the cidrs in the denylist and ensure they've been split accordingly
        response = await client.get(
            f"/v1/cidr/collapsed?list_type={ListTypeEnum.DENY}&list_id={list_deny['id']}", headers=api_token_header
        )
        assert response.status_code == HTTP_200_OK
        cidrs_in_denylist = response.json()
        safe_cidr = ipaddress.IPv4Network("66.66.1.0/26")
        deny_cidr = ipaddress.IPv4Network("66.66.1.0/24")
        after_exclusion = sorted([x.compressed for x in deny_cidr.address_exclude(safe_cidr)])
        assert sorted(cidrs_in_denylist) == after_exclusion

        # Disable the denylist and test that nothing is returned
        list_deny_disabled = list_deny.copy()
        list_deny_disabled["enabled"] = False
        response = await client.put(f"/v1/list/{list_deny['id']}", json=list_deny_disabled, headers=api_token_header)
        assert response.status_code == HTTP_200_OK
        response = await client.get(
            f"/v1/cidr/collapsed?list_type={ListTypeEnum.DENY}&list_id={list_deny['id']}", headers=api_token_header
        )
        assert response.status_code == HTTP_200_OK
        assert len(response.json()) == 0

        # re-enable and test that cidrs are returned again
        response = await client.put(f"/v1/list/{list_deny['id']}", json=list_deny, headers=api_token_header)
        assert response.status_code == HTTP_200_OK
        # run worker (not required but might catch bugs with update_cleanup
        await worker.run_once()

        response = await client.get(
            f"/v1/cidr/collapsed?list_type={ListTypeEnum.DENY}&list_id={list_deny['id']}", headers=api_token_header
        )
        assert response.status_code == HTTP_200_OK
        assert len(response.json()) == 2
        assert sorted(response.json()) == sorted(["66.66.1.128/25", "66.66.1.64/26"])

        # TEST ADD AND DELETE RAW
        # test delete raw
        delete_raw_cidrs = {
            "cidrs": "hello this is a raw input, I want to delete: 66.66.1.64/26, the following are invalid addresses 32.0 3.2 1.1.1.1/33"
        }
        response = await client.post(
            f"/v1/list/{list_deny['id']}/cidr/delete/raw", json=delete_raw_cidrs, headers=api_token_header
        )
        assert response.status_code == HTTP_201_CREATED
        await worker.run_once()

        response = await client.get(
            f"/v1/cidr/collapsed?list_type={ListTypeEnum.DENY}&list_id={list_deny['id']}", headers=api_token_header
        )
        assert response.status_code == HTTP_200_OK
        assert len(response.json()) == 1
        assert sorted(response.json()) == sorted(["66.66.1.128/25"])

        # test add raw
        add_raw_cidrs = {
            "cidrs": "hello this is a raw input, I want to add again: 66.66.1.64/26, the following are invalid addresses 32.0 3.2 1.1.1.1/33 fasd::dsf:bf"
        }
        response = await client.post(
            f"/v1/list/{list_deny['id']}/cidr/add/raw", json=add_raw_cidrs, headers=api_token_header
        )
        assert response.status_code == HTTP_201_CREATED
        await worker.run_once()

        response = await client.get(
            f"/v1/cidr/collapsed?list_type={ListTypeEnum.DENY}&list_id={list_deny['id']}", headers=api_token_header
        )
        assert response.status_code == HTTP_200_OK
        assert len(response.json()) == 2
        assert sorted(response.json()) == sorted(["66.66.1.128/25", "66.66.1.64/26"])

        # test IP regex
        add_raw_cidrs2 = {
            "cidrs": """
            Invalid addresses:

            12.12.12.1299
            1212.12.12.1299
            hello1.1.1.1bye
            fasd::dsf:bf
            1.1.1.1/33
            2c0f:fb50::/129

            Valid addresses:
            23.23.23.23/32
            13.14.15.16/24 --> raw input is not strict with hosts bits set, this transforns into: 13.14.15.0/24
            2c0f:fb50::/128
            """
        }
        response = await client.post(
            f"/v1/list/{list_deny['id']}/cidr/add/raw", json=add_raw_cidrs2, headers=api_token_header
        )
        assert response.status_code == HTTP_201_CREATED
        await worker.run_once()

        response = await client.get(
            f"/v1/cidr/collapsed?list_type={ListTypeEnum.DENY}&list_id={list_deny['id']}", headers=api_token_header
        )
        assert response.status_code == HTTP_200_OK
        assert len(response.json()) == 5
        assert sorted(response.json()) == sorted(
            ["66.66.1.128/25", "66.66.1.64/26", "23.23.23.23/32", "13.14.15.0/24", "2c0f:fb50::/128"]
        )

        # TEST THAT SPECIAL ADDRESSES NEVER TOUCH THE DB
        list_safe_empty = {"enabled": True, "id": "TEST_CIDRJOB_EMPTY_SAFE1", "list_type": ListTypeEnum.SAFE}
        response = await client.post("/v1/list", json=list_safe_empty, headers=api_token_header)
        assert response.status_code == HTTP_201_CREATED
        assert response.json()["id"] == list_safe_empty["id"]
        assert response.json()["list_type"] == list_safe_empty["list_type"]

        invalid_addresses = {"cidrs": ["0.0.0.0", "0.0.0.0/0"]}
        response = await client.post(
            f"/v1/list/{list_safe_empty['id']}/cidr/add", json=invalid_addresses, headers=api_token_header
        )
        assert response.status_code == HTTP_201_CREATED
        await worker.run_once()

        response = await client.get(
            f"/v1/cidr/collapsed?list_type={ListTypeEnum.SAFE}&list_id={list_safe_empty['id']}",
            headers=api_token_header,
        )
        assert response.status_code == HTTP_200_OK
        assert len(response.json()) == 0
