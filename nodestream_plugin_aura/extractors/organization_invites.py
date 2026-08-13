from typing import Any, AsyncGenerator

from ..api_client import DEFAULT_BASE_URL
from .base import AuraExtractor


class AuraOrganizationInviteExtractor(AuraExtractor):
    """Extracts every pending/outstanding invitation for one organization.

    GET /v2beta1/organizations/{organizationId}/invites
    -> {"data": [{"email"?, "organization_roles"?, "status"?, ...}, ...]}

    NOTE: this is the least-confirmed endpoint in this plugin. Unlike
    AuraOrganizationUserExtractor/AuraProjectUserExtractor (also originally
    unverified, but since confirmed live via a real account -- see
    scripts/smoke_test.py's schema-gap history), this one hasn't been
    exercised against a real org at all. It's only known to exist from
    Neo4j's own Aura changelog announcement ("GET, POST, DELETE
    /organizations/{org_id}/invites"), with no field-shape confirmation from
    any source. Run scripts/smoke_test.py against a real org with pending
    invites before trusting field names here.
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
        invites = await self.client.get_data(
            "v2beta1", f"/organizations/{self.organization_id}/invites"
        )
        for invite in invites:
            invite["organization_id"] = self.organization_id
            yield invite
