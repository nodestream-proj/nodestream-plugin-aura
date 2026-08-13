import pytest

BASE_URL = "https://api.neo4j.io"
TOKEN_URL = f"{BASE_URL}/oauth/token"


@pytest.fixture
def mock_token(httpx_mock):
    def _mock():
        httpx_mock.add_response(
            url=TOKEN_URL,
            json={
                "access_token": "fake-token",
                "expires_in": 3600,
                "token_type": "bearer",
            },
        )

    return _mock
