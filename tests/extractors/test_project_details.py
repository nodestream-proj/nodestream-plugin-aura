import pytest
from hamcrest import assert_that, equal_to

from nodestream_plugin_aura.extractors.project_details import (
    AuraProjectDetailExtractor,
)

BASE_URL = "https://api.neo4j.io"


@pytest.mark.asyncio
async def test_extract_records_fetches_each_project_directly_and_stamps_organization_id(
    httpx_mock, mock_token
):
    # Confirmed against a real account: GET /v1/tenants/{id} works for a
    # credential that can only administer specific projects and cannot list
    # every project in the org (unlike AuraProjectExtractor's endpoint).
    mock_token()
    httpx_mock.add_response(
        url=f"{BASE_URL}/v1/tenants/proj-1",
        json={
            "data": {
                "id": "proj-1",
                "name": "Neo4j Sales Eng. America (GCP)",
                "instance_configurations": [{"cloud_provider": "gcp"}],
            }
        },
    )
    httpx_mock.add_response(
        url=f"{BASE_URL}/v1/tenants/proj-2",
        json={"data": {"id": "proj-2", "name": "cotality-tax-poc-db"}},
    )

    subject = AuraProjectDetailExtractor(
        "client-id",
        "client-secret",
        [
            {"organization_id": "org-1", "project_id": "proj-1"},
            {"organization_id": "org-2", "project_id": "proj-2"},
        ],
        BASE_URL,
    )
    results = [r async for r in subject.extract_records()]

    assert_that(
        results,
        equal_to(
            [
                {
                    "id": "proj-1",
                    "name": "Neo4j Sales Eng. America (GCP)",
                    "instance_configurations": [{"cloud_provider": "gcp"}],
                    "organization_id": "org-1",
                },
                {
                    "id": "proj-2",
                    "name": "cotality-tax-poc-db",
                    "organization_id": "org-2",
                },
            ]
        ),
    )
