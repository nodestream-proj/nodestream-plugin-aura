"""Walks the real Aura hierarchy and prints raw records as JSON.

Bypasses nodestream pipelines entirely -- calls each Extractor's
extract_records() directly. Use this first, before wiring up a full
nodestream.yaml run, to confirm auth works and to see the *actual* JSON
shape Aura returns (especially for AuraOrganizationUserExtractor /
AuraProjectUserExtractor / AuraOrganizationInviteExtractor, whose field
names are unverified guesses -- the invites endpoint most of all, since
it's not confirmed to even exist yet, only announced).

Also cross-checks every returned record against MAPPED_FIELDS below (the
field set each nodestream_plugin_aura/aura_*.yaml actually maps into the graph) and
reports any field the live API returns that isn't mapped anywhere yet --
this is the only fully reliable way to confirm schema completeness, since
neo4j-cli's Go structs (used to derive several of these field lists) can
silently under-declare fields the real API returns.

Usage:
    export AURA_CLIENT_ID=...
    export AURA_CLIENT_SECRET=...
    python scripts/smoke_test.py
"""

import asyncio
import json
import os
import sys
from typing import Optional

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from nodestream_plugin_aura.api_client import AuraApiError  # noqa: E402
from nodestream_plugin_aura.extractors import (  # noqa: E402
    AuraAgentExtractor,
    AuraCustomerManagedKeyExtractor,
    AuraGraphAnalyticsSessionExtractor,
    AuraInstanceExtractor,
    AuraOrganizationExtractor,
    AuraOrganizationInviteExtractor,
    AuraOrganizationUserExtractor,
    AuraProjectExtractor,
    AuraProjectUserExtractor,
)

# Fields each nodestream_plugin_aura/aura_*.yaml currently maps into the graph, keyed
# by the same resource_key passed to drain() below. Confirmed against
# neo4j-cli source + (for instances) a real account, except
# organization_users/project_users, which are still an unverified guess --
# see AuraOrganizationUserExtractor's docstring.
MAPPED_FIELDS = {
    "organizations": {"id", "name"},
    "projects": {"id", "name", "organization_id"},
    "instances": {
        "id",
        "name",
        "status",
        "cloud_provider",
        "region",
        "type",
        "memory",
        "storage",
        "connection_url",
        "metrics_integration_url",
        "created_at",
        "vector_optimized",
        "cdc_enrichment_mode",
        "graph_analytics_plugin",
        "secondaries_count",
        "customer_managed_key_id",
        "graph_nodes",
        "graph_relationships",
        "project_id",
    },
    # "id"/"role" were the original (wrong) guess at these two resources'
    # field names; "user_id"/"organization_roles"/"project_roles" are
    # confirmed against a real account. Left both in so the "possibly
    # phantom" check below can empirically settle whether "id"/"role" ever
    # actually appear, rather than deleting them on another guess.
    "organization_users": {
        "id",
        "email",
        "role",
        "user_id",
        "organization_roles",
        "organization_id",
        "exempt_from_automatic_removal",
        "last_activity_at",
        "mfa_enrolled_methods",
        "mfa_enrollment_status",
    },
    "project_users": {
        "id",
        "email",
        "role",
        "user_id",
        "project_roles",
        "project_id",
    },
    # Least-confirmed resource in this plugin -- see
    # AuraOrganizationInviteExtractor's docstring. Guessed to follow
    # organization_users' confirmed email/organization_roles naming.
    "organization_invites": {
        "email",
        "organization_roles",
        "status",
        "organization_id",
    },
    "customer_managed_keys": {
        "id",
        "name",
        "project_id",
        "status",
        "created",
        "cloud_provider",
        "key_id",
        "region",
        "type",
        "instance_type",
    },
    "graph_analytics_sessions": {
        "id",
        "name",
        "project_id",
        "memory",
        "status",
        "created_at",
        "user_id",
        "cloud_provider",
        "region",
        "host",
        "expiry_date",
        "instance_id",
    },
    "agents": {
        "id",
        "name",
        "description",
        "dbid",
        "is_private",
        "is_mcp_enabled",
        "enabled",
        "project_id",
    },
}

# (label, detail) for every resource skipped (permission gap or a confirmed
# project-capability gap), reported as a summary at the end of the run.
skipped: list = []

# (label, resource_key, sorted list of unmapped field names) for every record
# that had a field not in MAPPED_FIELDS, reported as a summary at the end.
schema_gaps: list = []

# resource_key -> union of every field name actually seen on any record of
# that type across the whole run. Used at the end to flag MAPPED_FIELDS
# entries that were assumed but never once observed -- catching a wrong
# guess (like the original "id"/"role" for the two user endpoints) even
# though it never shows up as a SCHEMA GAP, since a gap only fires for
# fields present-but-unmapped, not for mapped-but-absent fields.
observed_fields: dict = {}


def print_section(title: str) -> None:
    print(f"\n{'=' * 10} {title} {'=' * 10}")


def check_schema_completeness(label: str, resource_key: str, records: list) -> None:
    mapped = MAPPED_FIELDS.get(resource_key)
    if mapped is None:
        return

    seen = observed_fields.setdefault(resource_key, set())
    unmapped = set()
    for record in records:
        seen.update(record.keys())
        unmapped.update(record.keys() - mapped)

    if unmapped:
        gap = sorted(unmapped)
        print(f"SCHEMA GAP: fields present but not mapped in the pipeline YAML: {gap}")
        schema_gaps.append((label, resource_key, gap))


def find_phantom_fields() -> dict:
    """Fields in MAPPED_FIELDS that were never seen on any drained record.

    Only considers resources with at least one record observed -- a
    resource with zero records this run (e.g. no instances in an empty
    project) says nothing about whether its mapped fields are real.
    """
    return {
        resource_key: sorted(MAPPED_FIELDS[resource_key] - seen)
        for resource_key, seen in observed_fields.items()
        if seen and MAPPED_FIELDS[resource_key] - seen
    }


async def drain(label: str, extractor, resource_key: Optional[str] = None) -> list:
    print_section(label)
    try:
        records = [record async for record in extractor.extract_records()]
    except AuraApiError as e:
        if not e.is_skippable:
            raise
        detail = e.reason or f"HTTP {e.status_code}"
        print(f"SKIPPED ({detail}): {label}")
        skipped.append((label, detail))
        return []

    print(f"{len(records)} record(s)")
    for record in records:
        print(json.dumps(record, indent=2, default=str))

    if resource_key:
        check_schema_completeness(label, resource_key, records)

    return records


async def main() -> None:
    client_id = os.environ["AURA_CLIENT_ID"]
    client_secret = os.environ["AURA_CLIENT_SECRET"]

    organizations = await drain(
        "Organizations",
        AuraOrganizationExtractor(client_id, client_secret),
        resource_key="organizations",
    )
    if not organizations:
        print("\nNo organizations visible to this credential -- stopping here.")
        return

    # Walk every org this credential can see, one level at a time, so a
    # single run confirms the whole hierarchy end to end.
    for org in organizations:
        org_id = org["id"]

        await drain(
            f"Org users ({org_id})",
            AuraOrganizationUserExtractor(client_id, client_secret, org_id),
            resource_key="organization_users",
        )
        await drain(
            f"Org invites ({org_id})",
            AuraOrganizationInviteExtractor(client_id, client_secret, org_id),
            resource_key="organization_invites",
        )

        projects = await drain(
            f"Projects ({org_id})",
            AuraProjectExtractor(client_id, client_secret, org_id),
            resource_key="projects",
        )

        for project in projects:
            project_id = project["id"]
            # Every project-scoped extractor now takes a *list* of
            # {organization_id, project_id} scopes (to support sweeping
            # several projects in one nodestream run -- see the `aura`
            # plugin scope's ProjectScopes config). This walk still
            # discovers and drains one project at a time, so each call just
            # wraps that single project in a one-item list.
            project_scope = [{"organization_id": org_id, "project_id": project_id}]

            await drain(
                f"Instances ({project_id})",
                AuraInstanceExtractor(client_id, client_secret, project_scope),
                resource_key="instances",
            )
            await drain(
                f"Project users ({project_id})",
                AuraProjectUserExtractor(client_id, client_secret, project_scope),
                resource_key="project_users",
            )
            await drain(
                f"Customer-managed keys ({project_id})",
                AuraCustomerManagedKeyExtractor(
                    client_id, client_secret, project_scope
                ),
                resource_key="customer_managed_keys",
            )
            await drain(
                f"Graph Analytics sessions ({project_id})",
                AuraGraphAnalyticsSessionExtractor(
                    client_id, client_secret, project_scope
                ),
                resource_key="graph_analytics_sessions",
            )
            await drain(
                f"Agents ({project_id})",
                AuraAgentExtractor(client_id, client_secret, project_scope),
                resource_key="agents",
            )

    if skipped:
        print_section("Skipped")
        for label, detail in skipped:
            print(f"  {detail}: {label}")

    if schema_gaps:
        print_section("Schema gaps")
        for label, resource_key, gap in schema_gaps:
            print(f"  {resource_key} ({label}): {gap}")

    phantom_by_resource = find_phantom_fields()
    if phantom_by_resource:
        print_section("Possibly phantom fields (mapped, never observed)")
        for resource_key, phantom in phantom_by_resource.items():
            print(f"  {resource_key}: {phantom}")


if __name__ == "__main__":
    asyncio.run(main())
