from typing import Any, AsyncGenerator

from ..api_client import DEFAULT_BASE_URL
from .base import AuraExtractor


class AuraIpFilterExtractor(AuraExtractor):
    """Extracts every IP filter (network allow-list) in one organization.

    GET /v2beta1/organizations/{organizationId}/ip-filters
    -> [{"id", "name", "description", "organization_id", "filtering_disabled",
         "updated_at",
         "allow_list": [{"address", "prefix_len", "description"}, ...],
         "filtered_entities": {"organizations": [...], "projects": [...],
                               "instances": [...]}}, ...]

    The list response already carries `filtered_entities` and `allow_list`
    in full, so no per-filter detail call is needed (the per-id GET returns
    the identical shape). That's also why this extractor does not call the
    per-instance `.../instances/{id}/ip-filters` endpoint: it would only add
    a `status` field, at the cost of one request per instance.

    Each allow-list entry gets a derived `cidr` ("10.0.0.0/8") so the
    pipeline can key shared AuraIpRange nodes on a single string instead of
    a composite of address + prefix length.
    """

    def __init__(
        self,
        client_id: str,
        client_secret: str,
        organization_id: str,
        base_url: str = DEFAULT_BASE_URL,
    ):
        super().__init__(client_id, client_secret, base_url)
        self.organization_id = organization_id

    async def extract_records(self) -> AsyncGenerator[Any, Any]:
        ip_filters = await self.client.get_data(
            "v2beta1", f"/organizations/{self.organization_id}/ip-filters"
        )
        for ip_filter in ip_filters:
            ip_filter.setdefault("organization_id", self.organization_id)
            for entry in ip_filter.get("allow_list") or []:
                entry["cidr"] = f"{entry['address']}/{entry['prefix_len']}"
            yield ip_filter
