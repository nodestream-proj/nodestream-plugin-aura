import httpx
import pytest
from hamcrest import assert_that, equal_to, has_length

from nodestream_plugin_aura.api_client import (
    MAX_RETRIES,
    AuraApiClient,
    AuraApiError,
    _capped_exponential_backoff,
)

BASE_URL = "https://api.neo4j.io"
TOKEN_URL = f"{BASE_URL}/oauth/token"
ORGS_URL = f"{BASE_URL}/v2beta1/organizations"


def mock_token(httpx_mock):
    httpx_mock.add_response(
        url=TOKEN_URL,
        json={"access_token": "fake-token", "expires_in": 3600, "token_type": "bearer"},
    )


@pytest.fixture
def fake_sleep(monkeypatch):
    """Replaces asyncio.sleep with a no-op that records requested durations,
    so retry tests run instantly instead of actually waiting."""
    calls = []

    async def _fake_sleep(seconds):
        calls.append(seconds)

    monkeypatch.setattr("nodestream_plugin_aura.api_client.asyncio.sleep", _fake_sleep)
    return calls


@pytest.mark.asyncio
async def test_429_is_retried_and_eventually_succeeds(httpx_mock, fake_sleep):
    mock_token(httpx_mock)
    httpx_mock.add_response(url=ORGS_URL, status_code=429, text="rate limited")
    httpx_mock.add_response(url=ORGS_URL, json={"data": [{"id": "org-1"}]})

    subject = AuraApiClient("client-id", "client-secret", BASE_URL)
    result = await subject.get_data("v2beta1", "/organizations")

    assert_that(result, equal_to([{"id": "org-1"}]))
    assert_that(fake_sleep, has_length(1))


@pytest.mark.asyncio
async def test_429_honors_retry_after_header(httpx_mock, fake_sleep):
    mock_token(httpx_mock)
    httpx_mock.add_response(
        url=ORGS_URL, status_code=429, headers={"Retry-After": "3"}, text=""
    )
    httpx_mock.add_response(url=ORGS_URL, json={"data": []})

    subject = AuraApiClient("client-id", "client-secret", BASE_URL)
    await subject.get_data("v2beta1", "/organizations")

    assert_that(fake_sleep, equal_to([3.0]))


@pytest.mark.asyncio
async def test_429_without_retry_after_uses_exponential_backoff(httpx_mock, fake_sleep):
    mock_token(httpx_mock)
    httpx_mock.add_response(url=ORGS_URL, status_code=429, text="")
    httpx_mock.add_response(url=ORGS_URL, json={"data": []})

    subject = AuraApiClient("client-id", "client-secret", BASE_URL)
    await subject.get_data("v2beta1", "/organizations")

    assert_that(fake_sleep, equal_to([_capped_exponential_backoff(1)]))


@pytest.mark.asyncio
async def test_429_exceeding_max_retries_raises_aura_api_error(httpx_mock, fake_sleep):
    mock_token(httpx_mock)
    for _ in range(MAX_RETRIES + 1):
        httpx_mock.add_response(url=ORGS_URL, status_code=429, text="rate limited")

    subject = AuraApiClient("client-id", "client-secret", BASE_URL)
    try:
        await subject.get_data("v2beta1", "/organizations")
        assert False, "expected AuraApiError"
    except AuraApiError as e:
        assert_that(e.status_code, equal_to(429))

    # MAX_RETRIES retries were attempted (MAX_RETRIES + 1 total requests).
    assert_that(fake_sleep, has_length(MAX_RETRIES))


@pytest.mark.asyncio
async def test_5xx_is_retried_and_eventually_succeeds(httpx_mock, fake_sleep):
    mock_token(httpx_mock)
    httpx_mock.add_response(url=ORGS_URL, status_code=503, text="unavailable")
    httpx_mock.add_response(url=ORGS_URL, json={"data": []})

    subject = AuraApiClient("client-id", "client-secret", BASE_URL)
    result = await subject.get_data("v2beta1", "/organizations")

    assert_that(result, equal_to([]))
    assert_that(fake_sleep, has_length(1))


@pytest.mark.asyncio
async def test_non_retryable_status_is_not_retried(httpx_mock, fake_sleep):
    mock_token(httpx_mock)
    httpx_mock.add_response(url=ORGS_URL, status_code=403, text="forbidden")

    subject = AuraApiClient("client-id", "client-secret", BASE_URL)
    try:
        await subject.get_data("v2beta1", "/organizations")
        assert False, "expected AuraApiError"
    except AuraApiError as e:
        assert_that(e.status_code, equal_to(403))

    assert_that(fake_sleep, equal_to([]))
    assert_that(httpx_mock.get_requests(), has_length(2))  # token + one GET, no retry


@pytest.mark.asyncio
async def test_transient_network_error_is_retried_and_eventually_succeeds(
    httpx_mock, fake_sleep
):
    mock_token(httpx_mock)
    httpx_mock.add_exception(httpx.ReadTimeout("timed out"), url=ORGS_URL)
    httpx_mock.add_response(url=ORGS_URL, json={"data": []})

    subject = AuraApiClient("client-id", "client-secret", BASE_URL)
    result = await subject.get_data("v2beta1", "/organizations")

    assert_that(result, equal_to([]))
    assert_that(fake_sleep, has_length(1))


@pytest.mark.asyncio
async def test_transient_network_error_exceeding_max_retries_reraises(
    httpx_mock, fake_sleep
):
    mock_token(httpx_mock)
    for _ in range(MAX_RETRIES + 1):
        httpx_mock.add_exception(httpx.ConnectError("connection refused"), url=ORGS_URL)

    subject = AuraApiClient("client-id", "client-secret", BASE_URL)
    try:
        await subject.get_data("v2beta1", "/organizations")
        assert False, "expected httpx.ConnectError"
    except httpx.ConnectError:
        pass

    assert_that(fake_sleep, has_length(MAX_RETRIES))
