import pytest
from hamcrest import assert_that, equal_to

from nodestream_plugin_aura.extractors.virtual_graphs import (
    AuraVirtualGraphExtractor,
)

BASE_URL = "https://api.neo4j.io"
LIST_URL = f"{BASE_URL}/v2beta1/organizations/org-1/projects/proj-1/virtual-graphs"


@pytest.mark.asyncio
async def test_extract_records_follows_pagination_and_stamps_project_id(
    httpx_mock, mock_token
):
    mock_token()
    httpx_mock.add_response(
        url=f"{LIST_URL}?page_limit=100",
        json={
            "data": [{"id": "vg-1", "name": "one"}],
            "links": {"next": f"{LIST_URL}?page_limit=100&page_token=abc"},
        },
    )
    httpx_mock.add_response(
        url=f"{LIST_URL}?page_limit=100&page_token=abc",
        json={
            "data": [{"id": "vg-2", "name": "two"}],
            "links": {"next": None},
        },
    )

    subject = AuraVirtualGraphExtractor(
        "client-id",
        "client-secret",
        [{"organization_id": "org-1", "project_id": "proj-1"}],
        BASE_URL,
    )
    results = [r async for r in subject.extract_records()]

    assert_that(
        results,
        equal_to(
            [
                {"id": "vg-1", "name": "one", "project_id": "proj-1"},
                {"id": "vg-2", "name": "two", "project_id": "proj-1"},
            ]
        ),
    )
