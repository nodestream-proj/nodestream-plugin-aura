from nodestream.pipeline.extractors import Extractor

from ..api_client import DEFAULT_BASE_URL, AuraApiClient


class AuraExtractor(Extractor):
    """Shared constructor plumbing for every Aura-API-backed extractor."""

    def __init__(
        self,
        client_id: str,
        client_secret: str,
        base_url: str = DEFAULT_BASE_URL,
    ):
        self.client = AuraApiClient(client_id, client_secret, base_url)
