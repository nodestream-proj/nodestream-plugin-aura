from typing import Any, AsyncGenerator

from .base import AuraExtractor


class AuraOrganizationExtractor(AuraExtractor):
    """Extracts every organization the credential can see.

    GET /v2beta1/organizations -> {"data": [{"id", "name"}, ...]}
    """

    async def extract_records(self) -> AsyncGenerator[Any, Any]:
        organizations = await self.client.get_data("v2beta1", "/organizations")
        for organization in organizations:
            yield organization
