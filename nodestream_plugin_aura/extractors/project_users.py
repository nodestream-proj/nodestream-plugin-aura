from typing import Any, AsyncGenerator, Dict, List

from ..api_client import DEFAULT_BASE_URL
from .base import AuraExtractor


class AuraProjectUserExtractor(AuraExtractor):
    """Extracts every user and their project-level role across one or more
    projects.

    Takes `project_scopes`, a list of `{"organization_id", "project_id"}`
    dicts -- unlike AuraInstanceExtractor, both keys are required here since
    the endpoint URL itself is nested under the organization.

    GET /v2beta1/organizations/{organizationId}/projects/{projectId}/users
    -> {"data": [{"user_id", "email"?, "project_roles": [str, ...], ...}, ...]}

    `user_id`/`project_roles` (field names and plurality) are confirmed
    against a real account, matching AuraOrganizationUserExtractor's
    `organization_roles`. The exact *value format* of each role string is
    NOT independently confirmed here, though -- organization_roles turned
    out to be lowercase-hyphenated (e.g. "organization-owner") rather than
    the upper-snake-case originally assumed, so project_roles' values should
    be checked against a real project rather than assumed to match either
    format.
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
            users = await self.client.get_data(
                "v2beta1",
                f"/organizations/{organization_id}/projects/{project_id}/users",
            )
            for user in users:
                user["project_id"] = project_id
                yield user
