import pytest
from hamcrest import assert_that, equal_to

from nodestream_plugin_aura.extractors.ip_filters import AuraIpFilterExtractor

BASE_URL = "https://api.neo4j.io"


@pytest.mark.asyncio
async def test_extract_records_yields_each_filter_with_derived_cidr(
    httpx_mock, mock_token
):
    # The list endpoint returns a bare JSON array (per the v2beta1 spec) and
    # already includes allow_list and filtered_entities, so exactly one
    # request is made after the token exchange.
    mock_token()
    httpx_mock.add_response(
        url=f"{BASE_URL}/v2beta1/organizations/org-1/ip-filters",
        json=[
            {
                "id": "filter-1",
                "name": "office",
                "organization_id": "org-1",
                "filtering_disabled": False,
                "allow_list": [
                    {"address": "10.0.0.0", "prefix_len": 8, "description": "vpn"},
                    {"address": "203.0.113.7", "prefix_len": 32},
                ],
                "filtered_entities": {"instances": ["inst-1"], "projects": []},
            }
        ],
    )

    subject = AuraIpFilterExtractor("client-id", "client-secret", "org-1", BASE_URL)
    results = [r async for r in subject.extract_records()]

    assert_that(
        results,
        equal_to(
            [
                {
                    "id": "filter-1",
                    "name": "office",
                    "organization_id": "org-1",
                    "filtering_disabled": False,
                    "allow_list": [
                        {
                            "address": "10.0.0.0",
                            "prefix_len": 8,
                            "description": "vpn",
                            "cidr": "10.0.0.0/8",
                        },
                        {
                            "address": "203.0.113.7",
                            "prefix_len": 32,
                            "cidr": "203.0.113.7/32",
                        },
                    ],
                    "filtered_entities": {"instances": ["inst-1"], "projects": []},
                }
            ]
        ),
    )


@pytest.mark.asyncio
async def test_extract_records_stamps_organization_id_when_response_omits_it(
    httpx_mock, mock_token
):
    mock_token()
    httpx_mock.add_response(
        url=f"{BASE_URL}/v2beta1/organizations/org-1/ip-filters",
        json=[{"id": "filter-1", "name": "no-entries"}],
    )

    subject = AuraIpFilterExtractor("client-id", "client-secret", "org-1", BASE_URL)
    results = [r async for r in subject.extract_records()]

    assert_that(
        results,
        equal_to(
            [{"id": "filter-1", "name": "no-entries", "organization_id": "org-1"}]
        ),
    )


@pytest.mark.asyncio
async def test_duplicate_cidrs_in_one_filter_are_merged_keeping_every_description(
    httpx_mock, mock_token
):
    # nodestream collapses same-type edges between the same two nodes into
    # one, so without merging, the second entry's description would silently
    # replace the first's on the single ALLOWS edge.
    mock_token()
    httpx_mock.add_response(
        url=f"{BASE_URL}/v2beta1/organizations/org-1/ip-filters",
        json=[
            {
                "id": "filter-1",
                "allow_list": [
                    {"address": "10.0.0.0", "prefix_len": 8, "description": "vpn"},
                    {"address": "10.0.0.0", "prefix_len": 8, "description": "office"},
                    {"address": "10.0.0.0", "prefix_len": 8, "description": "vpn"},
                    {"address": "10.0.0.0", "prefix_len": 8},
                    {"address": "192.0.2.1", "prefix_len": 32},
                ],
            }
        ],
    )

    subject = AuraIpFilterExtractor("client-id", "client-secret", "org-1", BASE_URL)
    (result,) = [r async for r in subject.extract_records()]

    assert_that(
        result["allow_list"],
        equal_to(
            [
                {
                    "address": "10.0.0.0",
                    "prefix_len": 8,
                    "description": "vpn; office",
                    "cidr": "10.0.0.0/8",
                },
                {"address": "192.0.2.1", "prefix_len": 32, "cidr": "192.0.2.1/32"},
            ]
        ),
    )
