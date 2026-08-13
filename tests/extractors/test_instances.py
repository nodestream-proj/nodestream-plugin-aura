import pytest
from hamcrest import assert_that, equal_to

from nodestream_plugin_aura.extractors.instances import AuraInstanceExtractor

BASE_URL = "https://api.neo4j.io"


@pytest.mark.asyncio
async def test_extract_records_fetches_full_details_and_renames_tenant_id(
    httpx_mock, mock_token
):
    mock_token()
    httpx_mock.add_response(
        url=f"{BASE_URL}/v1/instances?tenantId=proj-1",
        json={
            "data": [
                {
                    "id": "inst-1",
                    "name": "instance-one",
                    "tenant_id": "proj-1",
                    "cloud_provider": "gcp",
                }
            ]
        },
    )
    httpx_mock.add_response(
        url=f"{BASE_URL}/v1/instances/inst-1",
        json={
            "data": {
                "id": "inst-1",
                "name": "instance-one",
                "status": "running",
                "tenant_id": "proj-1",
                "cloud_provider": "gcp",
                "connection_url": "neo4j+s://inst-1.databases.neo4j.io",
                "metrics_integration_url": "https://metrics.example/inst-1",
                "region": "europe-west1",
                "type": "enterprise-db",
                "memory": "8GB",
                "storage": "16GB",
                "created_at": "2023-01-20T13:44:42Z",
                "vector_optimized": False,
            }
        },
    )

    subject = AuraInstanceExtractor(
        "client-id", "client-secret", [{"project_id": "proj-1"}], BASE_URL
    )
    results = [r async for r in subject.extract_records()]

    assert_that(
        results,
        equal_to(
            [
                {
                    "id": "inst-1",
                    "name": "instance-one",
                    "status": "running",
                    "project_id": "proj-1",
                    "cloud_provider": "gcp",
                    "connection_url": "neo4j+s://inst-1.databases.neo4j.io",
                    "metrics_integration_url": "https://metrics.example/inst-1",
                    "region": "europe-west1",
                    "type": "enterprise-db",
                    "memory": "8GB",
                    "storage": "16GB",
                    "created_at": "2023-01-20T13:44:42Z",
                    "vector_optimized": False,
                }
            ]
        ),
    )


@pytest.mark.asyncio
async def test_extract_records_falls_back_to_requested_project_id_when_tenant_id_missing(
    httpx_mock, mock_token
):
    mock_token()
    httpx_mock.add_response(
        url=f"{BASE_URL}/v1/instances?tenantId=proj-1",
        json={"data": [{"id": "inst-1", "name": "instance-one"}]},
    )
    httpx_mock.add_response(
        url=f"{BASE_URL}/v1/instances/inst-1",
        json={"data": {"id": "inst-1", "name": "instance-one"}},
    )

    subject = AuraInstanceExtractor(
        "client-id", "client-secret", [{"project_id": "proj-1"}], BASE_URL
    )
    results = [r async for r in subject.extract_records()]

    assert_that(
        results,
        equal_to([{"id": "inst-1", "name": "instance-one", "project_id": "proj-1"}]),
    )


@pytest.mark.asyncio
async def test_extract_records_fetches_details_for_every_instance_in_the_list(
    httpx_mock, mock_token
):
    mock_token()
    httpx_mock.add_response(
        url=f"{BASE_URL}/v1/instances?tenantId=proj-1",
        json={
            "data": [
                {"id": "inst-1", "name": "one", "tenant_id": "proj-1"},
                {"id": "inst-2", "name": "two", "tenant_id": "proj-1"},
            ]
        },
    )
    httpx_mock.add_response(
        url=f"{BASE_URL}/v1/instances/inst-1",
        json={"data": {"id": "inst-1", "name": "one", "tenant_id": "proj-1"}},
    )
    httpx_mock.add_response(
        url=f"{BASE_URL}/v1/instances/inst-2",
        json={"data": {"id": "inst-2", "name": "two", "tenant_id": "proj-1"}},
    )

    subject = AuraInstanceExtractor(
        "client-id", "client-secret", [{"project_id": "proj-1"}], BASE_URL
    )
    results = [r async for r in subject.extract_records()]

    assert_that(
        results,
        equal_to(
            [
                {"id": "inst-1", "name": "one", "project_id": "proj-1"},
                {"id": "inst-2", "name": "two", "project_id": "proj-1"},
            ]
        ),
    )


@pytest.mark.asyncio
async def test_extract_records_sweeps_every_project_scope_in_one_pass(
    httpx_mock, mock_token
):
    mock_token()
    httpx_mock.add_response(
        url=f"{BASE_URL}/v1/instances?tenantId=proj-1",
        json={"data": [{"id": "inst-1", "name": "one", "tenant_id": "proj-1"}]},
    )
    httpx_mock.add_response(
        url=f"{BASE_URL}/v1/instances/inst-1",
        json={"data": {"id": "inst-1", "name": "one", "tenant_id": "proj-1"}},
    )
    httpx_mock.add_response(
        url=f"{BASE_URL}/v1/instances?tenantId=proj-2",
        json={"data": [{"id": "inst-2", "name": "two", "tenant_id": "proj-2"}]},
    )
    httpx_mock.add_response(
        url=f"{BASE_URL}/v1/instances/inst-2",
        json={"data": {"id": "inst-2", "name": "two", "tenant_id": "proj-2"}},
    )

    subject = AuraInstanceExtractor(
        "client-id",
        "client-secret",
        [{"project_id": "proj-1"}, {"project_id": "proj-2"}],
        BASE_URL,
    )
    results = [r async for r in subject.extract_records()]

    assert_that(
        results,
        equal_to(
            [
                {"id": "inst-1", "name": "one", "project_id": "proj-1"},
                {"id": "inst-2", "name": "two", "project_id": "proj-2"},
            ]
        ),
    )
