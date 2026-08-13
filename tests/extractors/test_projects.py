import pytest
from hamcrest import assert_that, equal_to

from nodestream_plugin_aura.extractors.projects import AuraProjectExtractor

BASE_URL = "https://api.neo4j.io"


@pytest.mark.asyncio
async def test_extract_records_stamps_organization_id(httpx_mock, mock_token):
    mock_token()
    httpx_mock.add_response(
        url=f"{BASE_URL}/v2beta1/organizations/org-1/projects",
        json={"data": [{"id": "proj-1", "name": "Project One"}]},
    )

    subject = AuraProjectExtractor("client-id", "client-secret", "org-1", BASE_URL)
    results = [r async for r in subject.extract_records()]

    assert_that(
        results,
        equal_to([{"id": "proj-1", "name": "Project One", "organization_id": "org-1"}]),
    )
