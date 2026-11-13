from typing import Any, AsyncGenerator, Dict, List

from ..api_client import DEFAULT_BASE_URL
from .base import AuraExtractor


class AuraDatabaseExtractor(AuraExtractor):
    """Extracts every database on every instance across one or more projects.

    Takes `project_scopes`, a list of `{"organization_id", "project_id"}`
    dicts -- both keys are required, since the v2beta1 endpoints are nested
    under the organization.

    GET /v2beta1/organizations/{org}/projects/{project}/instances
    -> {"data": [{"id", ...}, ...]} is used only to discover which instance
    ids exist. Then, per instance,
    GET .../instances/{instanceId}/databases
    -> {"data": [{"id", "name"}, ...]}.

    The per-database detail endpoint (`.../databases/{databaseId}`) returns
    the same two fields as the list (`DatabaseSummary`), so it is not called.

    Each record is stamped with `instance_id` and `project_id`. Database ids
    are keyed together with `instance_id` in the pipeline, since nothing in
    the spec promises they're unique across instances.
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
            project_path = f"/organizations/{organization_id}/projects/{project_id}"
            instances = await self.client.get_data(
                "v2beta1", f"{project_path}/instances"
            )
            for instance in instances:
                instance_id = instance["id"]
                databases = await self.client.get_data(
                    "v2beta1", f"{project_path}/instances/{instance_id}/databases"
                )
                for database in databases:
                    database["instance_id"] = instance_id
                    database["project_id"] = project_id
                    yield database
