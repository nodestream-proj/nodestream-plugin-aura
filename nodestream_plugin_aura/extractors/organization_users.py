from typing import Any, AsyncGenerator

from ..api_client import DEFAULT_BASE_URL
from .base import AuraExtractor


class AuraOrganizationUserExtractor(AuraExtractor):
    """Extracts every user and their org-level role for one organization.

    GET /v2beta1/organizations/{organizationId}/users
    -> {"data": [{"user_id", "email"?, "organization_roles": [str, ...],
    "mfa_enrolled_methods": [{"id", "enrolled_at"}, ...], ...}, ...]}

    Confirmed against a real account: `organization_roles` is a list of
    plain, lowercase-hyphenated strings (e.g. "organization-owner" -- NOT the
    upper-snake-case "ORG_OWNER"-style format originally assumed here).
    `mfa_enrolled_methods` is a list of *objects*, not strings -- each has an
    "id" (the method name, e.g. "totp") and an "enrolled_at" timestamp. This
    object shape crashed a real `nodestream run organization_users` with
    `TypeError: unhashable type: 'dict'` before organization_users.yaml's
    ENROLLED_IN relationship was switched from `find_many` to `iterate_on`
    (which decomposes the record per-item before extracting fields, rather
    than handing the whole object to a relationship key).
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
        users = await self.client.get_data(
            "v2beta1", f"/organizations/{self.organization_id}/users"
        )
        for user in users:
            user["organization_id"] = self.organization_id
            yield user
