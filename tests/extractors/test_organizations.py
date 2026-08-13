import pytest
from hamcrest import assert_that, equal_to

from nodestream_plugin_aura.extractors.organizations import (
    AuraOrganizationExtractor,
)

BASE_URL = "https://api.neo4j.io"


@pytest.mark.asyncio
async def test_extract_records_yields_each_organization(httpx_mock, mock_token):
    mock_token()
    httpx_mock.add_response(
        url=f"{BASE_URL}/v2beta1/organizations",
        json={
            "data": [
                {"id": "org-1", "name": "Org One"},
                {"id": "org-2", "name": "Org Two"},
            ]
        },
    )

    subject = AuraOrganizationExtractor("client-id", "client-secret", BASE_URL)
    results = [r async for r in subject.extract_records()]

    assert_that(
        results,
        equal_to(
            [{"id": "org-1", "name": "Org One"}, {"id": "org-2", "name": "Org Two"}]
        ),
    )
