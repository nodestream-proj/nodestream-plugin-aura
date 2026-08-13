from typing import Any, AsyncGenerator

from ..api_client import DEFAULT_BASE_URL
from .base import AuraExtractor


class AuraProjectExtractor(AuraExtractor):
    """Extracts every project in one organization.

    GET /v2beta1/organizations/{organizationId}/projects -> {"data": [{"id", "name"}, ...]}
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
        projects = await self.client.get_data(
            "v2beta1", f"/organizations/{self.organization_id}/projects"
        )
        for project in projects:
            project["organization_id"] = self.organization_id
            yield project
