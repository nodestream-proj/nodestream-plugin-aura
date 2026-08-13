import pytest
from hamcrest import assert_that, equal_to

from nodestream_plugin_aura.extractors.agents import AuraAgentExtractor

BASE_URL = "https://api.neo4j.io"


@pytest.mark.asyncio
async def test_extract_records_fetches_full_details_and_stamps_project_id(
    httpx_mock, mock_token
):
    # Confirmed against a real Aura account: the list endpoint returns a bare
    # JSON array, not the {"data": [...]} envelope other list endpoints use.
    # The per-agent detail response's envelope is NOT independently confirmed
    # -- assumed here to match every other confirmed detail endpoint
    # ({"data": {...}}), since get_data() handles both shapes regardless.
    mock_token()
    httpx_mock.add_response(
        url=f"{BASE_URL}/v2beta1/organizations/org-1/projects/proj-1/agents",
        json=[{"id": "agent-1", "name": "my-agent"}],
    )
    httpx_mock.add_response(
        url=f"{BASE_URL}/v2beta1/organizations/org-1/projects/proj-1/agents/agent-1",
        json={
            "data": {
                "id": "agent-1",
                "name": "my-agent",
                "description": "does things",
                "dbid": "db-1",
                "is_private": True,
                "is_mcp_enabled": False,
                "enabled": True,
            }
        },
    )

    subject = AuraAgentExtractor(
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
                {
                    "id": "agent-1",
                    "name": "my-agent",
                    "description": "does things",
                    "dbid": "db-1",
                    "is_private": True,
                    "is_mcp_enabled": False,
                    "enabled": True,
                    "project_id": "proj-1",
                }
            ]
        ),
    )


@pytest.mark.asyncio
async def test_extract_records_sweeps_every_project_scope_across_different_orgs(
    httpx_mock, mock_token
):
    mock_token()
    httpx_mock.add_response(
        url=f"{BASE_URL}/v2beta1/organizations/org-1/projects/proj-1/agents",
        json=[{"id": "agent-1", "name": "one"}],
    )
    httpx_mock.add_response(
        url=f"{BASE_URL}/v2beta1/organizations/org-1/projects/proj-1/agents/agent-1",
        json={"data": {"id": "agent-1", "name": "one"}},
    )
    httpx_mock.add_response(
        url=f"{BASE_URL}/v2beta1/organizations/org-2/projects/proj-2/agents",
        json=[{"id": "agent-2", "name": "two"}],
    )
    httpx_mock.add_response(
        url=f"{BASE_URL}/v2beta1/organizations/org-2/projects/proj-2/agents/agent-2",
        json={"data": {"id": "agent-2", "name": "two"}},
    )

    subject = AuraAgentExtractor(
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
                {"id": "agent-1", "name": "one", "project_id": "proj-1"},
                {"id": "agent-2", "name": "two", "project_id": "proj-2"},
            ]
        ),
    )
