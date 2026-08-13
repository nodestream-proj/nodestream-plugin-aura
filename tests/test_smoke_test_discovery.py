"""Proves a skip in one project doesn't prevent the next project (or the
next resource within the same project) from being attempted independently.

Loads scripts/smoke_test.py as a module (it's a script, not part of the
installed package) so its main() can be exercised against mocked HTTP
responses instead of a real Aura account.
"""

import importlib.util
from pathlib import Path

import pytest
from hamcrest import assert_that, equal_to, has_item

BASE_URL = "https://api.neo4j.io"
SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "smoke_test.py"


def load_smoke_test_module():
    spec = importlib.util.spec_from_file_location("smoke_test_under_test", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def mock_empty_resources_for_project(httpx_mock, org_id, project_id):
    httpx_mock.add_response(
        url=f"{BASE_URL}/v1/instances?tenantId={project_id}", json={"data": []}
    )
    httpx_mock.add_response(
        url=f"{BASE_URL}/v2beta1/organizations/{org_id}/projects/{project_id}/users",
        json={"data": []},
    )
    httpx_mock.add_response(
        url=f"{BASE_URL}/v1/graph-analytics/sessions?tenantId={project_id}",
        json={"data": []},
    )
    httpx_mock.add_response(
        url=f"{BASE_URL}/v2beta1/organizations/{org_id}/projects/{project_id}/agents",
        json={"data": []},
    )


@pytest.mark.asyncio
async def test_a_skipped_projects_cmk_call_does_not_block_the_next_projects_cmk_call(
    httpx_mock, monkeypatch
):
    monkeypatch.setenv("AURA_CLIENT_ID", "client-id")
    monkeypatch.setenv("AURA_CLIENT_SECRET", "client-secret")

    # Every extractor builds its own AuraApiClient, so this run re-authenticates
    # once per resource fetched rather than sharing one token across the walk --
    # allow the mock to be reused for however many of those happen.
    httpx_mock.add_response(
        url=f"{BASE_URL}/oauth/token",
        json={"access_token": "tok", "expires_in": 3600, "token_type": "bearer"},
        is_reusable=True,
    )
    httpx_mock.add_response(
        url=f"{BASE_URL}/v2beta1/organizations",
        json={"data": [{"id": "org-1", "name": "Org One"}]},
    )
    httpx_mock.add_response(
        url=f"{BASE_URL}/v2beta1/organizations/org-1/users", json={"data": []}
    )
    httpx_mock.add_response(
        url=f"{BASE_URL}/v2beta1/organizations/org-1/invites", json={"data": []}
    )
    httpx_mock.add_response(
        url=f"{BASE_URL}/v2beta1/organizations/org-1/projects",
        json={"data": [{"id": "proj-1", "name": "P1"}, {"id": "proj-2", "name": "P2"}]},
    )
    mock_empty_resources_for_project(httpx_mock, "org-1", "proj-1")
    mock_empty_resources_for_project(httpx_mock, "org-1", "proj-2")

    # proj-1's customer-managed-keys call hits a capability gap...
    httpx_mock.add_response(
        url=f"{BASE_URL}/v1/customer-managed-keys?tenantId=proj-1",
        status_code=400,
        json={"errors": [{"reason": "tenant-incapable-of-action"}]},
    )
    # ...proj-2's own call must still be attempted, independently, and succeed.
    httpx_mock.add_response(
        url=f"{BASE_URL}/v1/customer-managed-keys?tenantId=proj-2",
        json={"data": [{"id": "cmk-2", "name": "key-two"}]},
    )
    httpx_mock.add_response(
        url=f"{BASE_URL}/v1/customer-managed-keys/cmk-2",
        json={"data": {"id": "cmk-2", "name": "key-two", "tenant_id": "proj-2"}},
    )

    module = load_smoke_test_module()
    await module.main()

    requested_urls = [str(request.url) for request in httpx_mock.get_requests()]

    assert_that(
        requested_urls,
        has_item(f"{BASE_URL}/v1/customer-managed-keys?tenantId=proj-1"),
    )
    assert_that(
        requested_urls,
        has_item(f"{BASE_URL}/v1/customer-managed-keys?tenantId=proj-2"),
    )
    # AuraCustomerManagedKeyExtractor itself now catches is_capability_gap
    # errors (see extract_records) and yields zero records instead of
    # raising, so drain() never sees an exception here -- skipped stays
    # empty. That's a stronger guarantee than the old "smoke-test-only
    # catch": a real `nodestream run customer_managed_keys` survives this
    # too, not just this discovery script.
    assert_that(module.skipped, equal_to([]))
