import pytest
from hamcrest import assert_that, equal_to

from nodestream_plugin_aura.extractors.databases import AuraDatabaseExtractor

BASE_URL = "https://api.neo4j.io"
PROJECT_PATH = f"{BASE_URL}/v2beta1/organizations/org-1/projects/proj-1"


@pytest.mark.asyncio
async def test_extract_records_lists_databases_per_instance_and_stamps_ids(
    httpx_mock, mock_token
):
    mock_token()
    httpx_mock.add_response(
        url=f"{PROJECT_PATH}/instances",
        json={"data": [{"id": "inst-1"}, {"id": "inst-2"}]},
    )
    httpx_mock.add_response(
        url=f"{PROJECT_PATH}/instances/inst-1/databases",
        json={"data": [{"id": "db-a", "name": "neo4j"}]},
    )
    httpx_mock.add_response(
        url=f"{PROJECT_PATH}/instances/inst-2/databases",
        json={"data": [{"id": "db-a", "name": "neo4j"}, {"id": "db-b", "name": "x"}]},
    )

    subject = AuraDatabaseExtractor(
        "client-id",
        "client-secret",
        [{"organization_id": "org-1", "project_id": "proj-1"}],
        BASE_URL,
    )
    results = [r async for r in subject.extract_records()]

    # Same database id on two instances stays two distinct records, each
    # carrying its own instance_id (the pipeline keys on both).
    assert_that(
        results,
        equal_to(
            [
                {
                    "id": "db-a",
                    "name": "neo4j",
                    "instance_id": "inst-1",
                    "project_id": "proj-1",
                },
                {
                    "id": "db-a",
                    "name": "neo4j",
                    "instance_id": "inst-2",
                    "project_id": "proj-1",
                },
                {
                    "id": "db-b",
                    "name": "x",
                    "instance_id": "inst-2",
                    "project_id": "proj-1",
                },
            ]
        ),
    )


@pytest.mark.asyncio
async def test_extract_records_yields_nothing_for_a_project_with_no_instances(
    httpx_mock, mock_token
):
    mock_token()
    httpx_mock.add_response(url=f"{PROJECT_PATH}/instances", json={"data": []})

    subject = AuraDatabaseExtractor(
        "client-id",
        "client-secret",
        [{"organization_id": "org-1", "project_id": "proj-1"}],
        BASE_URL,
    )
    results = [r async for r in subject.extract_records()]

    assert_that(results, equal_to([]))
