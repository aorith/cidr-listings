from conftest import get_api_token_header
from litestar.status_codes import (
    HTTP_200_OK,
    HTTP_201_CREATED,
    HTTP_204_NO_CONTENT,
    HTTP_400_BAD_REQUEST,
    HTTP_404_NOT_FOUND,
)
from litestar.testing import AsyncTestClient

from app.domain.lists.schemas import (
    MAX_DESCRIPTION_LEN,
    MAX_LIST_ID_LEN,
    MAX_TAG_LEN,
    ListTypeEnum,
)
from app.lib.settings import get_settings

settings = get_settings()


async def test_list(test_client: AsyncTestClient) -> None:
    async with test_client as client:
        api_token_header = await get_api_token_header(client)

        response = await client.get("/v1/list", headers=api_token_header)
        assert response.status_code == HTTP_200_OK
        assert len(response.json()) >= 0

        response = await client.get("/v1/list/NONEXISTENT", headers=api_token_header)
        assert response.status_code == HTTP_404_NOT_FOUND

        response = await client.delete("/v1/list/NONEXISTENT", headers=api_token_header)
        assert response.status_code == HTTP_404_NOT_FOUND


async def test_create_modify(test_client: AsyncTestClient) -> None:
    async with test_client as client:
        api_token_header = await get_api_token_header(client)

        test_list = {"id": "MYTESTLIST1", "list_type": "DENY"}

        response = await client.post("/v1/list", json=test_list, headers=api_token_header)
        assert response.status_code == HTTP_201_CREATED
        assert response.json()["id"] == test_list["id"]
        assert response.json()["list_type"] == test_list["list_type"]

        response = await client.get(f"/v1/list/{test_list['id']}", headers=api_token_header)
        assert response.status_code == HTTP_200_OK
        assert response.json()["id"] == test_list["id"]
        assert response.json()["list_type"] == test_list["list_type"]
        assert "DEFAULT" in response.json()["tags"]

        response = await client.delete(f"/v1/list/{test_list['id']}", headers=api_token_header)
        assert response.status_code == HTTP_204_NO_CONTENT

        response = await client.get(f"/v1/list/{test_list['id']}", headers=api_token_header)
        assert response.status_code == HTTP_404_NOT_FOUND

        test_list2 = {"id": "MYTESTLIST2", "list_type": "SAFE", "tags": ["AA", "BB"]}
        response = await client.post("/v1/list", json=test_list2, headers=api_token_header)
        assert response.status_code == HTTP_201_CREATED
        assert response.json()["id"] == test_list2["id"]
        assert response.json()["list_type"] == test_list2["list_type"]
        for t in test_list2["tags"] + ["DEFAULT"]:
            assert t in response.json()["tags"]

        test_list3 = {"id": "MYTESTLIST3", "list_type": "DENY", "tags": ["AA", "BB"]}
        response = await client.post("/v1/list", json=test_list3, headers=api_token_header)
        assert response.status_code == HTTP_201_CREATED
        response = await client.get(f"/v1/list/{test_list3['id']}", headers=api_token_header)
        assert response.status_code == HTTP_200_OK
        old_created_at = response.json()["created_at"]

        # Assert we cannot modify created_at field or id
        update_list = {"id": "BB", "tags": ["OK"]}
        response = await client.put(f"/v1/list/{test_list3['id']}", json=update_list, headers=api_token_header)
        assert response.status_code == HTTP_200_OK
        assert sorted(response.json()["tags"]) == sorted(update_list["tags"] + ["DEFAULT"])
        assert response.json()["id"] == test_list3["id"]
        assert response.json()["created_at"] == old_created_at


async def test_list_user_scope(test_client: AsyncTestClient) -> None:
    async with test_client as client:
        api_token_header = await get_api_token_header(client)

        payload1 = {"login": "testuser01", "password": "abcdefgH1bbcc"}
        response = await client.post("/v1/admin/signup", json=payload1, headers=api_token_header)
        assert response.status_code == HTTP_201_CREATED
        payload2 = {"login": "testuser02", "password": "abcdefgH1bbcc"}
        response = await client.post("/v1/admin/signup", json=payload2, headers=api_token_header)
        assert response.status_code == HTTP_201_CREATED

        response = await client.post("/v1/auth/token", json=payload1)
        assert response.status_code == HTTP_200_OK
        token1 = f"{response.json()['token_type']} {response.json()['access_token']}"

        response = await client.post("/v1/auth/token", json=payload2)
        assert response.status_code == HTTP_200_OK
        token2 = f"{response.json()['token_type']} {response.json()['access_token']}"

        # Create a list with user1
        response = await client.post(
            "/v1/list", json={"id": "USER1", "list_type": ListTypeEnum.DENY}, headers={settings.API_KEY_HEADER: token1}
        )
        assert response.status_code == HTTP_201_CREATED
        # Create a list with user2
        response = await client.post(
            "/v1/list", json={"id": "USER2", "list_type": ListTypeEnum.DENY}, headers={settings.API_KEY_HEADER: token2}
        )
        assert response.status_code == HTTP_201_CREATED

        # Ensure each user only has their list
        response = await client.get("/v1/list", headers={settings.API_KEY_HEADER: token1})
        assert response.status_code == HTTP_200_OK
        assert len(response.json()) == 1
        assert response.json()[0]["id"] == "USER1"
        response = await client.get("/v1/list", headers={settings.API_KEY_HEADER: token2})
        assert response.status_code == HTTP_200_OK
        assert len(response.json()) == 1
        assert response.json()[0]["id"] == "USER2"


async def test_bad_payloads(test_client: AsyncTestClient) -> None:
    async with test_client as client:
        api_token_header = await get_api_token_header(client)

        for payload in [
            {"id": "asdf", "list_type": "DENY"},
            {"id": "A" * (MAX_LIST_ID_LEN + 1), "list_type": "DENY"},
            {"id": "AA", "list_type": "DENY", "tags": ["A" * (MAX_TAG_LEN + 1)]},
            {"id": "AAA", "list_type": "DENY", "description": "A" * (MAX_DESCRIPTION_LEN + 1)},
            {"id": "ABC", "list_type": "OOPS"},
            {"id": "1ABC", "list_type": "DENY"},
        ]:
            response = await client.post("/v1/list", json=payload, headers=api_token_header)
            assert response.status_code == HTTP_400_BAD_REQUEST


async def test_cidr_list(test_client: AsyncTestClient) -> None:
    async with test_client as client:
        api_token_header = await get_api_token_header(client)

        payload = {"login": "testcidrlist01", "password": "abcdefgH1bbcc"}
        response = await client.post("/v1/admin/signup", json=payload, headers=api_token_header)
        assert response.status_code == HTTP_201_CREATED

        response = await client.post("/v1/auth/token", json=payload)
        assert response.status_code == HTTP_200_OK
        token = {settings.API_KEY_HEADER: f"Bearer {response.json()['access_token']}"}

        list_payload = {"id": "TEST_LIST_CIDR", "list_type": "DENY"}
        response = await client.post("/v1/list", json=list_payload, headers=token)
        assert response.status_code == HTTP_201_CREATED

        response = await client.get(f"/v1/list/{list_payload['id']}/cidr", headers=token)
        assert response.status_code == HTTP_200_OK
        assert "cidrs" in response.json()
        assert len(response.json()["cidrs"]) == 0
        assert response.json()["tags"] == ["DEFAULT"]
