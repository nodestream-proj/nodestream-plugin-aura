import pytest
from hamcrest import assert_that, equal_to, has_length

from nodestream_plugin_aura.api_client import AuraApiClient, AuraApiError

BASE_URL = "https://api.neo4j.io"
TOKEN_URL = f"{BASE_URL}/oauth/token"


def mock_token(httpx_mock, access_token="fake-token", expires_in=3600):
    httpx_mock.add_response(
        url=TOKEN_URL,
        json={
            "access_token": access_token,
            "expires_in": expires_in,
            "token_type": "bearer",
        },
    )


@pytest.mark.asyncio
async def test_get_data_fetches_token_then_resource(httpx_mock):
    mock_token(httpx_mock)
    httpx_mock.add_response(
        url=f"{BASE_URL}/v2beta1/organizations",
        json={"data": [{"id": "org-1", "name": "My Org"}]},
    )

    subject = AuraApiClient("client-id", "client-secret", BASE_URL)
    result = await subject.get_data("v2beta1", "/organizations")

    assert_that(result, equal_to([{"id": "org-1", "name": "My Org"}]))

    requests = httpx_mock.get_requests()
    assert_that(requests, has_length(2))
    assert_that(requests[0].url, equal_to(TOKEN_URL))
    auth_header = requests[1].headers["Authorization"]
    assert_that(auth_header, equal_to("Bearer fake-token"))


@pytest.mark.asyncio
async def test_token_is_cached_across_multiple_calls(httpx_mock):
    mock_token(httpx_mock)
    httpx_mock.add_response(url=f"{BASE_URL}/v2beta1/organizations", json={"data": []})
    httpx_mock.add_response(url=f"{BASE_URL}/v2beta1/organizations", json={"data": []})

    subject = AuraApiClient("client-id", "client-secret", BASE_URL)
    await subject.get_data("v2beta1", "/organizations")
    await subject.get_data("v2beta1", "/organizations")

    token_requests = [r for r in httpx_mock.get_requests() if r.url == TOKEN_URL]
    assert_that(token_requests, has_length(1))


@pytest.mark.asyncio
async def test_expired_token_is_refetched(httpx_mock):
    mock_token(httpx_mock, access_token="first-token", expires_in=0)
    mock_token(httpx_mock, access_token="second-token", expires_in=3600)
    httpx_mock.add_response(url=f"{BASE_URL}/v2beta1/organizations", json={"data": []})
    httpx_mock.add_response(url=f"{BASE_URL}/v2beta1/organizations", json={"data": []})

    subject = AuraApiClient("client-id", "client-secret", BASE_URL)
    await subject.get_data("v2beta1", "/organizations")
    await subject.get_data("v2beta1", "/organizations")

    token_requests = [r for r in httpx_mock.get_requests() if r.url == TOKEN_URL]
    assert_that(token_requests, has_length(2))


@pytest.mark.asyncio
async def test_get_data_wraps_single_object_in_a_list(httpx_mock):
    mock_token(httpx_mock)
    httpx_mock.add_response(
        url=f"{BASE_URL}/v2beta1/organizations/org-1",
        json={"data": {"id": "org-1", "name": "My Org"}},
    )

    subject = AuraApiClient("client-id", "client-secret", BASE_URL)
    result = await subject.get_data("v2beta1", "/organizations/org-1")

    assert_that(result, equal_to([{"id": "org-1", "name": "My Org"}]))


@pytest.mark.asyncio
async def test_get_data_handles_a_bare_list_response_with_no_data_envelope(httpx_mock):
    # Confirmed against a real Aura account: the agents endpoint returns a
    # bare JSON array instead of the {"data": [...]} envelope every other
    # endpoint uses.
    mock_token(httpx_mock)
    httpx_mock.add_response(
        url=f"{BASE_URL}/v2beta1/organizations/org-1/projects/proj-1/agents",
        json=[{"id": "agent-1", "name": "my-agent"}],
    )

    subject = AuraApiClient("client-id", "client-secret", BASE_URL)
    result = await subject.get_data(
        "v2beta1", "/organizations/org-1/projects/proj-1/agents"
    )

    assert_that(result, equal_to([{"id": "agent-1", "name": "my-agent"}]))


@pytest.mark.asyncio
async def test_non_2xx_response_raises_aura_api_error(httpx_mock):
    mock_token(httpx_mock)
    httpx_mock.add_response(
        url=f"{BASE_URL}/v2beta1/organizations", status_code=403, text="forbidden"
    )

    subject = AuraApiClient("client-id", "client-secret", BASE_URL)
    try:
        await subject.get_data("v2beta1", "/organizations")
        assert False, "expected AuraApiError"
    except AuraApiError as e:
        assert_that(e.status_code, equal_to(403))


@pytest.mark.asyncio
async def test_failed_token_exchange_raises_aura_api_error(httpx_mock):
    httpx_mock.add_response(url=TOKEN_URL, status_code=401, text="invalid credentials")

    subject = AuraApiClient("client-id", "client-secret", BASE_URL)
    try:
        await subject.get_data("v2beta1", "/organizations")
        assert False, "expected AuraApiError"
    except AuraApiError as e:
        assert_that(e.status_code, equal_to(401))


@pytest.mark.parametrize("status_code", [403, 404])
def test_is_permission_denied_true_for_403_and_404(status_code):
    error = AuraApiError(status_code, "https://api.neo4j.io/v2beta1/organizations", "")
    assert_that(error.is_permission_denied, equal_to(True))


@pytest.mark.parametrize("status_code", [401, 429, 500])
def test_is_permission_denied_false_for_other_status_codes(status_code):
    error = AuraApiError(status_code, "https://api.neo4j.io/v2beta1/organizations", "")
    assert_that(error.is_permission_denied, equal_to(False))


def test_reason_is_parsed_from_error_body():
    body = '{"errors":[{"message":"This project is not capable of configuring encryption keys","reason":"tenant-incapable-of-action"}]}'
    error = AuraApiError(400, "https://api.neo4j.io/v1/customer-managed-keys", body)
    assert_that(error.reason, equal_to("tenant-incapable-of-action"))


@pytest.mark.parametrize("body", ["", "not json", "{}", '{"errors": []}'])
def test_reason_is_none_when_body_has_no_parseable_reason(body):
    error = AuraApiError(400, "https://api.neo4j.io/v1/customer-managed-keys", body)
    assert_that(error.reason, equal_to(None))


def test_is_skippable_true_for_known_capability_gap_reason():
    body = '{"errors":[{"reason":"tenant-incapable-of-action"}]}'
    error = AuraApiError(400, "https://api.neo4j.io/v1/customer-managed-keys", body)
    assert_that(error.is_skippable, equal_to(True))


def test_is_skippable_false_for_400_with_unrecognized_reason():
    body = '{"errors":[{"reason":"something-we-have-not-seen-before"}]}'
    error = AuraApiError(400, "https://api.neo4j.io/v1/customer-managed-keys", body)
    assert_that(error.is_skippable, equal_to(False))


def test_is_skippable_false_for_400_with_no_body():
    error = AuraApiError(400, "https://api.neo4j.io/v1/customer-managed-keys", "")
    assert_that(error.is_skippable, equal_to(False))


@pytest.mark.parametrize("status_code", [403, 404])
def test_is_skippable_true_for_permission_denied_status_codes(status_code):
    error = AuraApiError(status_code, "https://api.neo4j.io/v2beta1/organizations", "")
    assert_that(error.is_skippable, equal_to(True))


def test_is_capability_gap_true_for_known_capability_gap_reason():
    body = '{"errors":[{"reason":"tenant-incapable-of-action"}]}'
    error = AuraApiError(400, "https://api.neo4j.io/v1/customer-managed-keys", body)
    assert_that(error.is_capability_gap, equal_to(True))


@pytest.mark.parametrize("status_code", [403, 404])
def test_is_capability_gap_false_for_bare_permission_denied(status_code):
    # A permission-denied status with no capability-gap reason is
    # is_skippable but NOT is_capability_gap -- that distinction is the
    # whole point: extractors should auto-recover from a capability gap but
    # still raise on a bare permission error.
    error = AuraApiError(status_code, "https://api.neo4j.io/v2beta1/organizations", "")
    assert_that(error.is_capability_gap, equal_to(False))


def test_is_capability_gap_false_for_400_with_unrecognized_reason():
    body = '{"errors":[{"reason":"something-we-have-not-seen-before"}]}'
    error = AuraApiError(400, "https://api.neo4j.io/v1/customer-managed-keys", body)
    assert_that(error.is_capability_gap, equal_to(False))
