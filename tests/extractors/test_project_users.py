import pytest
from hamcrest import assert_that, equal_to

from nodestream_plugin_aura.extractors.project_users import (
    AuraProjectUserExtractor,
)

BASE_URL = "https://api.neo4j.io"


@pytest.mark.asyncio
async def test_extract_records_stamps_project_id(httpx_mock, mock_token):
    mock_token()
    httpx_mock.add_response(
        url=f"{BASE_URL}/v2beta1/organizations/org-1/projects/proj-1/users",
        json={"data": [{"id": "user-1", "role": "PROJECT_ADMIN"}]},
    )

    subject = AuraProjectUserExtractor(
        "client-id",
        "client-secret",
        [{"organization_id": "org-1", "project_id": "proj-1"}],
        BASE_URL,
    )
    results = [r async for r in subject.extract_records()]

    assert_that(
        results,
        equal_to([{"id": "user-1", "role": "PROJECT_ADMIN", "project_id": "proj-1"}]),
    )


@pytest.mark.asyncio
async def test_extract_records_sweeps_every_project_scope_across_different_orgs(
    httpx_mock, mock_token
):
    mock_token()
    httpx_mock.add_response(
        url=f"{BASE_URL}/v2beta1/organizations/org-1/projects/proj-1/users",
        json={"data": [{"id": "user-1", "role": "PROJECT_ADMIN"}]},
    )
    httpx_mock.add_response(
        url=f"{BASE_URL}/v2beta1/organizations/org-2/projects/proj-2/users",
        json={"data": [{"id": "user-2", "role": "PROJECT_MEMBER"}]},
    )

    subject = AuraProjectUserExtractor(
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
                {"id": "user-1", "role": "PROJECT_ADMIN", "project_id": "proj-1"},
                {"id": "user-2", "role": "PROJECT_MEMBER", "project_id": "proj-2"},
            ]
        ),
    )
