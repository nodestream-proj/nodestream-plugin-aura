"""Unit tests for smoke_test.py's schema-completeness checker."""

import importlib.util
from pathlib import Path

from hamcrest import assert_that, equal_to

SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "smoke_test.py"


def load_smoke_test_module():
    spec = importlib.util.spec_from_file_location("smoke_test_under_test", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_no_gap_reported_when_every_field_is_mapped():
    module = load_smoke_test_module()

    module.check_schema_completeness(
        "Organizations", "organizations", [{"id": "org-1", "name": "My Org"}]
    )

    assert_that(module.schema_gaps, equal_to([]))


def test_gap_reported_for_a_field_not_in_mapped_fields():
    module = load_smoke_test_module()

    module.check_schema_completeness(
        "Organizations",
        "organizations",
        [{"id": "org-1", "name": "My Org", "tier": "enterprise"}],
    )

    assert_that(
        module.schema_gaps, equal_to([("Organizations", "organizations", ["tier"])])
    )


def test_gaps_are_deduplicated_and_sorted_across_multiple_records():
    module = load_smoke_test_module()

    module.check_schema_completeness(
        "Organizations",
        "organizations",
        [
            {"id": "org-1", "name": "One", "tier": "enterprise"},
            {"id": "org-2", "name": "Two", "created_at": "2023-01-01"},
        ],
    )

    assert_that(
        module.schema_gaps,
        equal_to([("Organizations", "organizations", ["created_at", "tier"])]),
    )


def test_unrecognized_resource_key_is_a_silent_no_op():
    module = load_smoke_test_module()

    module.check_schema_completeness(
        "Something new", "not_a_known_resource", [{"anything": "goes"}]
    )

    assert_that(module.schema_gaps, equal_to([]))


def test_no_phantom_fields_reported_when_nothing_was_observed():
    module = load_smoke_test_module()

    assert_that(module.find_phantom_fields(), equal_to({}))


def test_no_phantom_fields_reported_when_every_mapped_field_was_seen():
    module = load_smoke_test_module()

    module.check_schema_completeness(
        "Organizations", "organizations", [{"id": "org-1", "name": "My Org"}]
    )

    assert_that(module.find_phantom_fields(), equal_to({}))


def test_phantom_fields_reported_for_mapped_fields_never_observed():
    module = load_smoke_test_module()

    # organization_users' MAPPED_FIELDS includes the original ("id", "role")
    # guess alongside the confirmed ("user_id", "organization_roles", ...)
    # real fields -- a record using only the confirmed real fields should
    # surface "id"/"role" as phantom.
    module.check_schema_completeness(
        "Org users (org-1)",
        "organization_users",
        [
            {
                "user_id": "user-1",
                "email": "a@example.com",
                "organization_roles": ["ORG_ADMIN"],
                "organization_id": "org-1",
                "exempt_from_automatic_removal": False,
                "last_activity_at": "2026-01-01T00:00:00Z",
                "mfa_enrolled_methods": ["totp"],
                "mfa_enrollment_status": "ENROLLED",
            }
        ],
    )

    assert_that(
        module.find_phantom_fields(),
        equal_to({"organization_users": ["id", "role"]}),
    )
