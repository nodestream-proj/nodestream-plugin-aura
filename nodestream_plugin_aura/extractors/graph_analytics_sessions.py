from typing import Any, AsyncGenerator, Dict, List

from ..api_client import DEFAULT_BASE_URL
from .base import AuraExtractor


class AuraGraphAnalyticsSessionExtractor(AuraExtractor):
    """Extracts every Graph Analytics Serverless session across one or more
    projects, with full session detail.

    Takes `project_scopes` (see AuraInstanceExtractor's docstring for the
    shared `{"organization_id"?, "project_id"}` shape) so several projects
    can be swept in one pass. A scope may also carry an optional
    `"instance_id"` key to filter that project's sessions to one instance.

    GET /v1/graph-analytics/sessions?tenantId={projectId}[&instanceId=...]
    only returns a summary (confirmed: id, name, status, project_id,
    cloud_provider, ttl in neo4j-cli's list.go), so this extractor uses it
    only to discover which session ids exist, then calls
    GET /v1/graph-analytics/sessions/{sessionId} per id for the full record
    (memory, created_at, user_id, region, host, expiry_date, instance_id,
    ...).
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
            params = {"tenantId": project_id}
            instance_id = scope.get("instance_id")
            if instance_id:
                params["instanceId"] = instance_id

            summaries = await self.client.get_data(
                "v1", "/graph-analytics/sessions", params=params
            )
            for summary in summaries:
                details = await self.client.get_data(
                    "v1", f"/graph-analytics/sessions/{summary['id']}"
                )
                session = details[0]
                session["project_id"] = session.pop("tenant_id", project_id)
                yield session
