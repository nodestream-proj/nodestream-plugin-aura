from typing import Any, AsyncGenerator, Dict, List

from ..api_client import DEFAULT_BASE_URL
from .base import AuraExtractor


class AuraAgentExtractor(AuraExtractor):
    """Extracts every Aura Agent across one or more projects, with full
    agent detail.

    Takes `project_scopes`, a list of `{"organization_id", "project_id"}`
    dicts -- unlike AuraInstanceExtractor, both keys are required here since
    the endpoint URL itself is nested under the organization.

    GET /v2beta1/organizations/{organizationId}/projects/{projectId}/agents
    -> [{"id", "name", ...}, ...] -- a bare JSON array, unlike every other
    endpoint in this plugin, which wrap their list in {"data": [...]}.
    Confirmed against a real Aura account. This list only returns a summary
    (id, name, description, dbid, enabled per neo4j-cli's list.go), so this
    extractor uses it only to discover which agent ids exist, then calls
    GET .../agents/{agentId} per id for the full record (adds is_private,
    is_mcp_enabled).
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
            base_path = f"/organizations/{organization_id}/projects/{project_id}/agents"
            summaries = await self.client.get_data("v2beta1", base_path)
            for summary in summaries:
                details = await self.client.get_data(
                    "v2beta1", f"{base_path}/{summary['id']}"
                )
                agent = details[0]
                agent["project_id"] = project_id
                yield agent
