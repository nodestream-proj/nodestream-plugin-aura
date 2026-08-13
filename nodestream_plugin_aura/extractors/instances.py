from typing import Any, AsyncGenerator, Dict, List

from ..api_client import DEFAULT_BASE_URL
from .base import AuraExtractor


class AuraInstanceExtractor(AuraExtractor):
    """Extracts every instance across one or more projects, with full
    instance details.

    Takes `project_scopes`, a list of `{"organization_id"?, "project_id"}`
    dicts -- one entry per project to sweep, so a single credential covering
    several projects (e.g. a Project Admin on multiple projects, possibly
    across different orgs) can run in one pass instead of one run per
    project. `organization_id` isn't used by this extractor (instances are
    looked up by project alone), but the same dict shape is shared across
    every project-scoped extractor in this plugin so one `ProjectScopes`
    config list serves all of them.

    GET /v1/instances?tenantId={projectId} only returns a summary per Aura's
    own docs -- confirmed to be just {"id", "name", "tenant_id",
    "cloud_provider"} -- so this extractor uses it only to discover which
    instance ids exist in the project, then calls
    GET /v1/instances/{instanceId} for each one to get the full record
    (status, region, type, memory, storage, connection_url,
    metrics_integration_url, created_at, vector_optimized, ...).

    This means one list call plus one detail call per instance. Fine for the
    typical instance counts per project; if that ever becomes a real cost,
    the two calls could be parallelized with asyncio.gather.

    The API's `tenant_id` field is the pre-Projects-rename name for what is
    now called a Project; it's normalized to `project_id` here to match the
    rest of this plugin's field naming.
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
            project_id = scope["project_id"]
            summaries = await self.client.get_data(
                "v1", "/instances", params={"tenantId": project_id}
            )
            for summary in summaries:
                details = await self.client.get_data(
                    "v1", f"/instances/{summary['id']}"
                )
                instance = details[0]
                instance["project_id"] = instance.pop("tenant_id", project_id)
                yield instance
