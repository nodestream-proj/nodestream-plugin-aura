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
            if ip_filter.get("allow_list"):
                ip_filter["allow_list"] = _merge_duplicate_cidrs(
                    ip_filter["allow_list"]
                )
            yield ip_filter


def _merge_duplicate_cidrs(allow_list):
    """Adds a derived `cidr` to each entry and merges entries sharing one.

    The pipeline writes one (:AuraIpFilter)-[:ALLOWS]->(:AuraIpRange) edge per
    entry, and nodestream collapses same-type edges between the same two nodes
    into one -- so two entries for the same CIDR with different descriptions
    would otherwise keep only whichever was written last. Merging here keeps
    every distinct description (joined with "; ") on the single edge instead.
    """
    merged = {}
    descriptions = {}
    for entry in allow_list:
        cidr = f"{entry['address']}/{entry['prefix_len']}"
        merged.setdefault(cidr, {**entry, "cidr": cidr})
        seen = descriptions.setdefault(cidr, [])
        description = entry.get("description")
        if description and description not in seen:
            seen.append(description)

    for cidr, entry in merged.items():
        if descriptions[cidr]:
            entry["description"] = "; ".join(descriptions[cidr])
    return list(merged.values())
