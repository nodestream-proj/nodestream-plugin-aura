import asyncio
import json
import time
from typing import Any, Dict, List, Optional

import httpx

DEFAULT_BASE_URL = "https://api.neo4j.io"

# How many seconds before the token's real expiry we treat it as stale, so a
# request started just before expiry doesn't get a token that dies mid-flight.
TOKEN_EXPIRY_BUFFER_SECONDS = 60

# Generous per-request timeout -- matches neo4j-cli's own httpClientTimeout
# (internal/api/api.go, 60s), since the Aura API can be slow under load and
# a request that legitimately just needs more time shouldn't be treated the
# same as a hung connection.
HTTP_TIMEOUT_SECONDS = 60.0

# Retry policy for transient failures: rate limiting (429) and 5xx/network
# errors. Aura's own rate limits are 25 req/min (free/trial) or 125 req/min
# (paid tiers) -- this plugin's list-then-detail-per-item pattern means a
# full multi-org/multi-project sweep can plausibly issue hundreds of
# requests, so hitting 429 on a real run is expected, not exceptional.
MAX_RETRIES = 5
RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}
BASE_BACKOFF_SECONDS = 2.0
BACKOFF_MULTIPLIER = 2.0
MAX_BACKOFF_SECONDS = 60.0


def _capped_exponential_backoff(attempt: int) -> float:
    """attempt is 1-indexed (the Nth retry, not the Nth request)."""
    return min(
        BASE_BACKOFF_SECONDS * (BACKOFF_MULTIPLIER ** (attempt - 1)),
        MAX_BACKOFF_SECONDS,
    )


def _backoff_seconds(response: httpx.Response, attempt: int) -> float:
    """How long to wait before retrying `attempt` (1-indexed).

    Honors the server's Retry-After header when present (Aura may send one
    on 429s) rather than guessing, falling back to capped exponential
    backoff otherwise.
    """
    retry_after = response.headers.get("Retry-After")
    if retry_after is not None:
        try:
            return max(float(retry_after), 0.0)
        except ValueError:
            pass
    return _capped_exponential_backoff(attempt)


# Status codes that mean "this credential can't see this specific resource"
# rather than "something is broken." Aura returns 404 (not just 403) for
# resources a credential lacks visibility into, to avoid confirming they
# exist. 401 is deliberately excluded -- that means the credential/token
# itself is invalid, which no amount of skipping-and-continuing will fix.
PERMISSION_DENIED_STATUS_CODES = {403, 404}

# Aura's `{"errors": [{"reason": "..."}]}` values that mean "this org/project
# doesn't support this feature at all" -- a project-capability gap, not a
# malformed request. Confirmed so far: customer-managed keys return 400 +
# this reason on projects whose plan tier/cloud provider doesn't support CMK.
# Deliberately a narrow, explicit allowlist -- an unrecognized `reason` on a
# 400 still raises, since that's much more likely to mean our request is
# genuinely wrong than a new capability gap we haven't seen yet.
SKIPPABLE_REASONS = {"tenant-incapable-of-action"}


def _extract_reason(body: str) -> Optional[str]:
    try:
        errors = json.loads(body).get("errors") or []
    except (ValueError, AttributeError):
        return None
    return errors[0].get("reason") if errors else None


class AuraApiError(RuntimeError):
    """Raised when the Aura API returns a non-2xx response."""

    def __init__(self, status_code: int, url: str, body: str):
        super().__init__(f"Aura API request to {url} failed with {status_code}: {body}")
        self.status_code = status_code
        self.url = url
        self.body = body
        self.reason = _extract_reason(body)

    @property
    def is_permission_denied(self) -> bool:
        return self.status_code in PERMISSION_DENIED_STATUS_CODES

    @property
    def is_capability_gap(self) -> bool:
        """True only for a confirmed "this resource can't exist here" reason.

        Deliberately narrower than is_skippable: a project genuinely being
        incapable of a feature (e.g. CMK) is unambiguous -- there are zero
        of that resource, full stop, regardless of who's asking. That makes
        it safe for an Extractor to catch this itself and yield nothing,
        even inside a single deliberately-scoped production pipeline run.
        A bare permission-denied response carries no such guarantee (it
        might mean "there are some, you just can't see them"), so it's
        intentionally excluded here -- see is_skippable for where that
        ambiguity is accepted anyway (best-effort multi-org discovery).
        """
        return self.reason in SKIPPABLE_REASONS

    @property
    def is_skippable(self) -> bool:
        """True for errors safe to log-and-continue past during discovery.

        Broader than is_capability_gap -- also treats permission-denied as
        skippable, accepting the "no access" vs "genuinely none" ambiguity.
        Appropriate for a best-effort walk across many orgs/projects (see
        scripts/smoke_test.py), not for a single-project production pipeline
        run, where that ambiguity is worth surfacing rather than hiding.
        """
        return self.is_permission_denied or self.is_capability_gap


class AuraApiClient:
    """Thin async client for the Neo4j Aura API.

    Handles the OAuth2 client-credentials token exchange (with caching across
    calls) and versioned request routing (v1 / v1beta5 / v2beta1), mirroring
    the routing scheme used by neo4j-labs/neo4j-cli.
    """

    def __init__(
        self,
        client_id: str,
        client_secret: str,
        base_url: str = DEFAULT_BASE_URL,
    ):
        self.client_id = client_id
        self.client_secret = client_secret
        self.base_url = base_url.rstrip("/")
        self.auth_url = f"{self.base_url}/oauth/token"
        self._token: Optional[str] = None
        self._token_expires_at: float = 0.0
        self._token_lock = asyncio.Lock()

    async def _send_with_retry(self, send_request) -> httpx.Response:
        """Executes `send_request` (a zero-arg async callable returning an
        httpx.Response) with retry-with-backoff for transient failures:
        429/5xx responses and network-level errors (timeouts, connection
        failures). A non-retryable status (e.g. 400/401/403/404) or a
        successful response returns immediately on the first attempt.
        """
        attempt = 0
        while True:
            attempt += 1
            try:
                response = await send_request()
            except (httpx.TimeoutException, httpx.TransportError):
                if attempt > MAX_RETRIES:
                    raise
                await asyncio.sleep(_capped_exponential_backoff(attempt))
                continue

            if (
                attempt > MAX_RETRIES
                or response.status_code not in RETRYABLE_STATUS_CODES
            ):
                return response

            await asyncio.sleep(_backoff_seconds(response, attempt))

    async def _get_token(self) -> str:
        async with self._token_lock:
            if self._token is not None and time.monotonic() < self._token_expires_at:
                return self._token

            async def send_request() -> httpx.Response:
                async with httpx.AsyncClient(timeout=HTTP_TIMEOUT_SECONDS) as client:
                    return await client.post(
                        self.auth_url,
                        auth=(self.client_id, self.client_secret),
                        data={"grant_type": "client_credentials"},
                        headers={"Content-Type": "application/x-www-form-urlencoded"},
                    )

            response = await self._send_with_retry(send_request)
            if not response.is_success:
                raise AuraApiError(response.status_code, self.auth_url, response.text)

            grant = response.json()
            self._token = grant["access_token"]
            self._token_expires_at = (
                time.monotonic() + grant["expires_in"] - TOKEN_EXPIRY_BUFFER_SECONDS
            )
            return self._token

    async def get(
        self,
        version: str,
        path: str,
        params: Optional[Dict[str, str]] = None,
    ) -> Any:
        token = await self._get_token()
        url = f"{self.base_url}/{version}{path}"

        async def send_request() -> httpx.Response:
            async with httpx.AsyncClient(timeout=HTTP_TIMEOUT_SECONDS) as client:
                return await client.get(
                    url,
                    headers={"Authorization": f"Bearer {token}"},
                    params=params,
                )

        response = await self._send_with_retry(send_request)
        if not response.is_success:
            raise AuraApiError(response.status_code, url, response.text)
        return response.json()

    async def get_data(
        self,
        version: str,
        path: str,
        params: Optional[Dict[str, str]] = None,
    ) -> List[Dict[str, Any]]:
        """GET a resource and unwrap its `data` envelope, if it has one.

        Most confirmed Aura v1/v2beta1 list endpoints return `{"data": [...]}`,
        but at least one (agents) returns a bare JSON array instead -- so a
        list response is returned as-is rather than assumed to be a dict.
        No cursor-based pagination has been observed on any endpoint; if Aura
        adds it to one later, this is the seam to extend.
        """
        body = await self.get(version, path, params)
        if isinstance(body, list):
            return body
        data = body.get("data", body)
        return data if isinstance(data, list) else [data]
