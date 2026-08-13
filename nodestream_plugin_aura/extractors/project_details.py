from typing import Any, AsyncGenerator, Dict, List

from ..api_client import DEFAULT_BASE_URL
from .base import AuraExtractor


class AuraProjectDetailExtractor(AuraExtractor):
    """Fetches one or more projects' own details directly by id, without
    listing every project in their organization first.

    GET /v1/tenants/{projectId} -> {"data": {"id", "name",
    "instance_configurations": [...]}}. `tenants` is the pre-Projects-rename
    name for what the rest of this API calls Projects (same as
    AuraInstanceExtractor's `tenant_id` field). Confirmed against a real
    account: this single-resource endpoint works for a credential that can
    only administer specific projects and cannot call
    `AuraProjectExtractor`'s `GET /v2beta1/organizations/{orgId}/projects`
    (which lists every project in the org and needs broader visibility).

    This is what backfills `name` for `AuraProject` nodes for a Project
    Admin credential, which can't use `AuraProjectExtractor`'s org-wide
    listing -- without it, those nodes only ever get created as id-only
    stubs via other pipelines' BELONGS_TO_PROJECT/MEMBER_OF_PROJECT
    relationships.
    `instance_configurations` (a static catalog of allowed instance
    sizes/types for the project's plan tier) isn't mapped -- it duplicates
    information already tracked per-instance on real `AuraInstance` nodes
    and isn't access/attribution-relevant.

    Takes `project_scopes`, the same `{"organization_id", "project_id"}`
    list shape as every other project-scoped extractor in this plugin.
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
            details = await self.client.get_data("v1", f"/tenants/{project_id}")
            project = details[0]
            project["organization_id"] = organization_id
            yield project
