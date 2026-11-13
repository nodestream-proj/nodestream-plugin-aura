from typing import Any, AsyncGenerator, Dict, List

from ..api_client import DEFAULT_BASE_URL
from .base import AuraExtractor

# The spec marks both `page_limit` and `page_token` as required query params,
# which can't be literally true for the first page (there is no token yet).
# This extractor sends only page_limit on the first request, then follows
# `links.next`. NOT yet verified against a real account -- if the API rejects
# a first request without page_token, this is the place to adjust.
PAGE_LIMIT = "100"


class AuraVirtualGraphExtractor(AuraExtractor):
    """Extracts every virtual graph across one or more projects.

    Takes `project_scopes`, a list of `{"organization_id", "project_id"}`
    dicts -- both keys are required, since the endpoint is nested under the
    organization.

    GET /v2beta1/organizations/{org}/projects/{project}/virtual-graphs
    -> {"data": [{"id", "name", "status", "memory", "cloud_provider",
                  "region", "bolt_url", "private_bolt_url",
                  "public_access_enabled", "private_access_enabled",
                  "data_source_id", "data_source_type",
                  "maximum_bytes_billed", "created_at", "error_detail"}, ...],
        "links": {"first", "self", "next"}}

    Unlike every other list endpoint in this plugin, this one is
    cursor-paginated, so it goes through AuraApiClient.get_data_paginated.
    The list items already carry the full record (the per-id GET returns the
    same VirtualGraph schema), so no detail call is made.
    """

    def __init__(
        self,
        client_id: str,
        client_secret: str,
        project_scopes: List[Dict[str, str]],
        base_url: str = DEFAULT_BASE_URL,
    ):
        super().__init__(client_id, client_secret, base_url)
        self.project_scopes = project_scopes

    async def extract_records(self) -> AsyncGenerator[Any, Any]:
        for scope in self.project_scopes:
            organization_id = scope["organization_id"]
            project_id = scope["project_id"]
            virtual_graphs = await self.client.get_data_paginated(
                "v2beta1",
                f"/organizations/{organization_id}/projects/{project_id}/virtual-graphs",
                params={"page_limit": PAGE_LIMIT},
            )
            for virtual_graph in virtual_graphs:
                virtual_graph["project_id"] = project_id
                yield virtual_graph
