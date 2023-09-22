from conftest import get_api_token_header
from litestar.status_codes import (
    HTTP_200_OK,
    HTTP_201_CREATED,
    HTTP_400_BAD_REQUEST,
    HTTP_401_UNAUTHORIZED,
    HTTP_409_CONFLICT,
)
from litestar.testing import AsyncTestClient

from app.lib.settings import get_settings

settings = get_settings()


async def test_signup(test_client: AsyncTestClient) -> None:
    async with test_client as client:
        api_token_header = await get_api_token_header(client)

        payload = {"login": "test01", "password": "abcdefgHij1"}
        response = await client.post("/v1/admin/signup", json=payload, headers=api_token_header)
        assert response.status_code == HTTP_201_CREATED
        response = await client.post("/v1/admin/signup", json=payload, headers=api_token_header)
        assert response.status_code == HTTP_409_CONFLICT
        response = await client.post("/v1/admin/signup", json=payload, headers={})
        assert response.status_code == HTTP_401_UNAUTHORIZED

        response = await client.post("/v1/auth/token", json=payload)
        assert response.status_code == HTTP_200_OK
        resp_json = response.json()
        assert resp_json["token_type"] == "Bearer"
        assert resp_json["expires_in"] == settings.DEFAULT_TOKEN_TTL_SECONDS
        assert "access_token" in resp_json
        assert "expires_at" in resp_json

        response = await client.get(
            "/v1/list", headers={settings.API_KEY_HEADER: f"{resp_json['token_type']} {resp_json['access_token']}"}
        )
        assert response.status_code == HTTP_200_OK
        response = await client.get("/v1/list", headers={settings.API_KEY_HEADER: f"{resp_json['token_type']} ADFJ"})
        assert response.status_code == HTTP_401_UNAUTHORIZED
        response = await client.get(
            "/v1/list", headers={settings.API_KEY_HEADER: f"BeaRER {resp_json['access_token']}"}
        )
        assert response.status_code == HTTP_401_UNAUTHORIZED

        # Verify validations
        payload = {"login": "test0001", "password": "aaaaAF4"}
        response = await client.post("/v1/admin/signup", json=payload, headers=api_token_header)
        assert response.status_code == HTTP_400_BAD_REQUEST
        payload = {"login": "test0001", "password": "aaaabbbbcccddd1"}
        response = await client.post("/v1/admin/signup", json=payload, headers=api_token_header)
        assert response.status_code == HTTP_400_BAD_REQUEST

        # Create a new login for password change verification
        payload = {"login": "testc01", "password": "aaaaaaaaaAF40"}
        response = await client.post("/v1/admin/signup", json=payload, headers=api_token_header)
        assert response.status_code == HTTP_201_CREATED
        # New password cannot be equal to old
        payload = {"login": "testc01", "password": "aaaaaaaaaAF40", "new_password": "aaaaaaaaaAF40"}
        response = await client.put("/v1/auth/password", json=payload)
        assert response.status_code == HTTP_400_BAD_REQUEST
        # New password validations
        payload = {"login": "testc01", "password": "aaaaaaaaaAF40", "new_password": "aaaa0"}
        response = await client.put("/v1/auth/password", json=payload)
        assert response.status_code == HTTP_400_BAD_REQUEST
        # Correct new password
        payload = {"login": "testc01", "password": "aaaaaaaaaAF40", "new_password": "newPasssswordOK01"}
        response = await client.put("/v1/auth/password", json=payload)
        assert response.status_code == HTTP_200_OK
        # Login with the old password = 401
        payload = {"login": "testc01", "password": "aaaaaaaaaAF40"}
        response = await client.post("/v1/auth/token", json=payload, follow_redirects=False)
        assert response.status_code == HTTP_401_UNAUTHORIZED

        # Successful login with the new password
        payload = {"login": "testc01", "password": "newPasssswordOK01"}
        response = await client.post("/v1/auth/token", json=payload)
        assert response.status_code == HTTP_200_OK
        payload = {"login": "testc01", "password": "newPasssswordOK01"}
        response = await client.post("/v1/auth/token", json=payload, follow_redirects=False)
        assert response.status_code == HTTP_200_OK

        # Test that only the superuser can create other users
        payload = {"login": "testc01", "password": "newPasssswordOK01"}
        response = await client.post("/v1/auth/token", json=payload)
        assert response.status_code == HTTP_200_OK
        user_token_header = {settings.API_KEY_HEADER: f"Bearer {response.json()['access_token']}"}

        payload = {"login": "newuser001", "password": "abcdefgHij1"}
        response = await client.post("/v1/admin/signup", json=payload, headers=user_token_header)
        assert response.status_code == HTTP_401_UNAUTHORIZED
