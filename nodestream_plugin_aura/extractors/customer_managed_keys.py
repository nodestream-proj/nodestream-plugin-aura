from logging import getLogger
from typing import Any, AsyncGenerator, Dict, List

from ..api_client import DEFAULT_BASE_URL, AuraApiError
from .base import AuraExtractor


class AuraCustomerManagedKeyExtractor(AuraExtractor):
    """Extracts every customer-managed key across one or more projects, with
    full detail.

    Takes `project_scopes` (see AuraInstanceExtractor's docstring for the
    shared `{"organization_id"?, "project_id"}` shape) so several projects
    can be swept in one pass.

    GET /v1/customer-managed-keys?tenantId={projectId} only returns a summary
    per Aura's own docs (confirmed: just {"id", "name", "tenant_id"} in
    neo4j-cli's list.go), so this extractor uses it only to discover which
    key ids exist, then calls GET /v1/customer-managed-keys/{keyId} per id
    for the full record (status, created, cloud_provider, key_id, region,
    type, ...).

    Projects whose plan tier/cloud provider doesn't support CMK at all get
    400 tenant-incapable-of-action on the list call -- confirmed against a
    real Aura Free instance, where this crashed a real `nodestream run`
    (there's no discovery-walk wrapper to catch it there, unlike
    scripts/smoke_test.py). That specific reason is unambiguous ("this
    project cannot have CMKs, full stop") so it's caught here per project and
    treated as zero records for that project rather than a pipeline failure
    -- the loop continues to the next project scope rather than aborting the
    whole extractor. A bare permission-denied error (403/404,
    is_permission_denied but not is_capability_gap) still propagates -- that
    ambiguity ("no access" vs "genuinely none") is worth a loud failure in a
    single deliberately-scoped production run.
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
        self.logger = getLogger(self.__class__.__name__)

    async def extract_records(self) -> AsyncGenerator[Any, Any]:
        for scope in self.project_scopes:
            project_id = scope["project_id"]
            try:
                summaries = await self.client.get_data(
                    "v1", "/customer-managed-keys", params={"tenantId": project_id}
                )
            except AuraApiError as e:
                if not e.is_capability_gap:
                    raise
                self.logger.warning(
                    "Project %s does not support customer-managed keys (%s); "
                    "yielding zero records.",
                    project_id,
                    e.reason,
                )
                continue

            for summary in summaries:
                details = await self.client.get_data(
                    "v1", f"/customer-managed-keys/{summary['id']}"
                )
                key = details[0]
                key["project_id"] = key.pop("tenant_id", project_id)
                yield key
