import pytest
from hamcrest import assert_that, equal_to

from nodestream_plugin_aura.extractors.organization_users import (
    AuraOrganizationUserExtractor,
)

BASE_URL = "https://api.neo4j.io"


@pytest.mark.asyncio
async def test_extract_records_stamps_organization_id(httpx_mock, mock_token):
    mock_token()
    httpx_mock.add_response(
        url=f"{BASE_URL}/v2beta1/organizations/org-1/users",
        json={"data": [{"id": "user-1", "role": "ORG_ADMIN"}]},
    )

    subject = AuraOrganizationUserExtractor(
        "client-id", "client-secret", "org-1", BASE_URL
    )
    results = [r async for r in subject.extract_records()]

    assert_that(
        results,
        equal_to([{"id": "user-1", "role": "ORG_ADMIN", "organization_id": "org-1"}]),
    )
