import pytest
from hamcrest import assert_that, equal_to

from nodestream_plugin_aura.extractors.graph_analytics_sessions import (
    AuraGraphAnalyticsSessionExtractor,
)

BASE_URL = "https://api.neo4j.io"

DETAIL_RESPONSE = {
    "data": {
        "id": "session-1",
        "name": "my-session",
        "tenant_id": "proj-1",
        "memory": "8GB",
        "status": "ready",
        "created_at": "2023-01-20T13:44:42Z",
        "user_id": "user-1",
        "cloud_provider": "gcp",
        "region": "europe-west1",
        "host": "session-1.neo4j.io",
        "expiry_date": "2023-01-21T13:44:42Z",
        "instance_id": "inst-1",
    }
}

EXPECTED_RECORD = {
    "id": "session-1",
    "name": "my-session",
    "project_id": "proj-1",
    "memory": "8GB",
    "status": "ready",
    "created_at": "2023-01-20T13:44:42Z",
    "user_id": "user-1",
    "cloud_provider": "gcp",
    "region": "europe-west1",
    "host": "session-1.neo4j.io",
    "expiry_date": "2023-01-21T13:44:42Z",
    "instance_id": "inst-1",
}


@pytest.mark.asyncio
async def test_extract_records_without_instance_filter_fetches_full_details(
    httpx_mock, mock_token
):
    mock_token()
    httpx_mock.add_response(
        url=f"{BASE_URL}/v1/graph-analytics/sessions?tenantId=proj-1",
        json={"data": [{"id": "session-1", "tenant_id": "proj-1"}]},
    )
    httpx_mock.add_response(
        url=f"{BASE_URL}/v1/graph-analytics/sessions/session-1", json=DETAIL_RESPONSE
    )

    subject = AuraGraphAnalyticsSessionExtractor(
        "client-id", "client-secret", [{"project_id": "proj-1"}], base_url=BASE_URL
    )
    results = [r async for r in subject.extract_records()]

    assert_that(results, equal_to([EXPECTED_RECORD]))


@pytest.mark.asyncio
async def test_extract_records_with_instance_filter_fetches_full_details(
    httpx_mock, mock_token
):
    mock_token()
    httpx_mock.add_response(
        url=f"{BASE_URL}/v1/graph-analytics/sessions?tenantId=proj-1&instanceId=inst-1",
        json={"data": [{"id": "session-1", "tenant_id": "proj-1"}]},
    )
    httpx_mock.add_response(
        url=f"{BASE_URL}/v1/graph-analytics/sessions/session-1", json=DETAIL_RESPONSE
    )

    subject = AuraGraphAnalyticsSessionExtractor(
        "client-id",
        "client-secret",
        [{"project_id": "proj-1", "instance_id": "inst-1"}],
        base_url=BASE_URL,
    )
    results = [r async for r in subject.extract_records()]

    assert_that(results, equal_to([EXPECTED_RECORD]))


@pytest.mark.asyncio
async def test_extract_records_sweeps_every_project_scope_in_one_pass(
    httpx_mock, mock_token
):
    mock_token()
    httpx_mock.add_response(
        url=f"{BASE_URL}/v1/graph-analytics/sessions?tenantId=proj-1",
        json={"data": [{"id": "session-1", "tenant_id": "proj-1"}]},
    )
    httpx_mock.add_response(
        url=f"{BASE_URL}/v1/graph-analytics/sessions/session-1", json=DETAIL_RESPONSE
    )
    httpx_mock.add_response(
        url=f"{BASE_URL}/v1/graph-analytics/sessions?tenantId=proj-2",
        json={"data": []},
    )

    subject = AuraGraphAnalyticsSessionExtractor(
        "client-id",
        "client-secret",
        [{"project_id": "proj-1"}, {"project_id": "proj-2"}],
        base_url=BASE_URL,
    )
    results = [r async for r in subject.extract_records()]

    assert_that(results, equal_to([EXPECTED_RECORD]))
