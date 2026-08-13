import pytest
from hamcrest import assert_that, equal_to

from nodestream_plugin_aura.api_client import AuraApiError
from nodestream_plugin_aura.extractors.customer_managed_keys import (
    AuraCustomerManagedKeyExtractor,
)

BASE_URL = "https://api.neo4j.io"


@pytest.mark.asyncio
async def test_extract_records_fetches_full_details_and_renames_tenant_id(
    httpx_mock, mock_token
):
    mock_token()
    httpx_mock.add_response(
        url=f"{BASE_URL}/v1/customer-managed-keys?tenantId=proj-1",
        json={"data": [{"id": "cmk-1", "name": "my-key", "tenant_id": "proj-1"}]},
    )
    httpx_mock.add_response(
        url=f"{BASE_URL}/v1/customer-managed-keys/cmk-1",
        json={
            "data": {
                "id": "cmk-1",
                "name": "my-key",
                "tenant_id": "proj-1",
                "status": "active",
                "created": "2023-01-20T13:44:42Z",
                "cloud_provider": "gcp",
                "key_id": "projects/p/locations/l/keyRings/r/cryptoKeys/k",
                "region": "europe-west1",
                "type": "gcp-kms",
            }
        },
    )

    subject = AuraCustomerManagedKeyExtractor(
        "client-id", "client-secret", [{"project_id": "proj-1"}], BASE_URL
    )
    results = [r async for r in subject.extract_records()]

    assert_that(
        results,
        equal_to(
            [
                {
                    "id": "cmk-1",
                    "name": "my-key",
                    "project_id": "proj-1",
                    "status": "active",
                    "created": "2023-01-20T13:44:42Z",
                    "cloud_provider": "gcp",
                    "key_id": "projects/p/locations/l/keyRings/r/cryptoKeys/k",
                    "region": "europe-west1",
                    "type": "gcp-kms",
                }
            ]
        ),
    )


@pytest.mark.asyncio
async def test_extract_records_yields_nothing_when_project_is_cmk_incapable(
    httpx_mock, mock_token
):
    # Confirmed against a real Aura Free instance: this crashed a real
    # `nodestream run customer_managed_keys` before this recovery was added,
    # since nothing outside scripts/smoke_test.py's drain() wrapper caught it.
    mock_token()
    httpx_mock.add_response(
        url=f"{BASE_URL}/v1/customer-managed-keys?tenantId=proj-1",
        status_code=400,
        json={"errors": [{"reason": "tenant-incapable-of-action"}]},
    )

    subject = AuraCustomerManagedKeyExtractor(
        "client-id", "client-secret", [{"project_id": "proj-1"}], BASE_URL
    )
    results = [r async for r in subject.extract_records()]

    assert_that(results, equal_to([]))


@pytest.mark.asyncio
async def test_a_capability_gap_in_one_project_does_not_block_the_next_project(
    httpx_mock, mock_token
):
    # The loop over project_scopes must `continue` past a capability gap,
    # not abort the whole extractor -- otherwise a Project Admin sweeping
    # several projects in one run would silently lose every project listed
    # after the first CMK-incapable one.
    mock_token()
    httpx_mock.add_response(
        url=f"{BASE_URL}/v1/customer-managed-keys?tenantId=proj-1",
        status_code=400,
        json={"errors": [{"reason": "tenant-incapable-of-action"}]},
    )
    httpx_mock.add_response(
        url=f"{BASE_URL}/v1/customer-managed-keys?tenantId=proj-2",
        json={"data": [{"id": "cmk-2", "name": "key-two", "tenant_id": "proj-2"}]},
    )
    httpx_mock.add_response(
        url=f"{BASE_URL}/v1/customer-managed-keys/cmk-2",
        json={"data": {"id": "cmk-2", "name": "key-two", "tenant_id": "proj-2"}},
    )

    subject = AuraCustomerManagedKeyExtractor(
        "client-id",
        "client-secret",
        [{"project_id": "proj-1"}, {"project_id": "proj-2"}],
        BASE_URL,
    )
    results = [r async for r in subject.extract_records()]

    assert_that(
        results, equal_to([{"id": "cmk-2", "name": "key-two", "project_id": "proj-2"}])
    )


@pytest.mark.asyncio
async def test_extract_records_still_raises_on_bare_permission_denied(
    httpx_mock, mock_token
):
    # A permission-denied response with no capability-gap reason must NOT
    # be silently swallowed -- that ambiguity ("no access" vs "genuinely
    # none") is worth a loud failure in a real pipeline run.
    mock_token()
    httpx_mock.add_response(
        url=f"{BASE_URL}/v1/customer-managed-keys?tenantId=proj-1",
        status_code=403,
        text="forbidden",
    )

    subject = AuraCustomerManagedKeyExtractor(
        "client-id", "client-secret", [{"project_id": "proj-1"}], BASE_URL
    )
    try:
        [r async for r in subject.extract_records()]
        assert False, "expected AuraApiError"
    except AuraApiError as e:
        assert_that(e.status_code, equal_to(403))
