"""Empirically proves the merge-key design of the redesigned graph schema
(roles/MFA-methods/cloud-provider/region as shared nodes) against
nodestream's REAL Interpretation classes -- not just asserted in a YAML
comment.

Each pipeline YAML's interpretations are re-constructed here in Python using
the exact same classes nodestream loads them into (RelationshipInterpretation,
SourceNodeInterpretation, JmespathValueProvider), so this tests the real
mechanics, not a hand-written approximation of them.

Two things specifically needed proving, both surfaced by reading
nodestream/model/graph_objects.py's Relationship docstring rather than
guessing:

1. `find_many: true` + a list-valued jmespath expression really does fan out
   into one relationship per list item (not one relationship with a list
   property).
2. Without an explicit `relationship_key`, nodestream merges relationships of
   the same type between the same two nodes into ONE edge -- so a user with
   the same role in two different orgs needs organization_id in
   `relationship_key` (not `relationship_properties`), or one of the two
   grants silently disappears. Each "would this design lose data" claim below
   has a matching negative-control test proving the naive alternative really
   does lose data.
"""

import pytest
from hamcrest import assert_that, contains_inanyorder, equal_to, has_length
from nodestream.interpreting.interpretations.relationship_interpretation import (
    RelationshipInterpretation,
)
from nodestream.interpreting.interpretations.source_node_interpretation import (
    SourceNodeInterpretation,
)
from nodestream.pipeline.value_providers.context import ProviderContext
from nodestream.pipeline.value_providers.jmespath_value_provider import (
    JmespathValueProvider,
)


def jp(expression):
    return JmespathValueProvider.from_string_expression(expression)


def context_for(record):
    return ProviderContext.fresh(record)


# --- organization_users.yaml: HAS_ORG_ROLE -> AuraRole ---


def has_org_role_interpretation():
    return RelationshipInterpretation(
        node_type="AuraRole",
        relationship_type="HAS_ORG_ROLE",
        find_many=True,
        node_key={"name": jp("organization_roles")},
        key_normalization={"do_lowercase_strings": False},
        relationship_key={"organization_id": jp("organization_id")},
    )


def test_has_org_role_fans_out_one_relationship_per_role_with_exact_casing():
    context = context_for(
        {
            "organization_id": "org-1",
            "organization_roles": ["ORG_ADMIN", "ORG_BILLING_ADMIN"],
        }
    )
    has_org_role_interpretation().interpret(context)

    relationships = context.desired_ingest.relationships
    assert_that(relationships, has_length(2))
    role_names = [r.to_node.key_values["name"] for r in relationships]
    assert_that(role_names, contains_inanyorder("ORG_ADMIN", "ORG_BILLING_ADMIN"))
    for r in relationships:
        assert_that(r.relationship.key_values, equal_to({"organization_id": "org-1"}))


def test_has_org_role_discriminates_same_role_across_different_orgs():
    # Same user, same role, two different orgs -- these must produce
    # relationships whose key_values differ, or nodestream (per its own
    # Relationship docstring) would treat them as the same edge.
    context_org1 = context_for(
        {"organization_id": "org-1", "organization_roles": ["ORG_ADMIN"]}
    )
    context_org2 = context_for(
        {"organization_id": "org-2", "organization_roles": ["ORG_ADMIN"]}
    )
    has_org_role_interpretation().interpret(context_org1)
    has_org_role_interpretation().interpret(context_org2)

    rel1 = context_org1.desired_ingest.relationships[0].relationship
    rel2 = context_org2.desired_ingest.relationships[0].relationship
    assert_that(rel1.key_values, equal_to({"organization_id": "org-1"}))
    assert_that(rel2.key_values, equal_to({"organization_id": "org-2"}))


def test_relationship_properties_alone_would_not_have_discriminated_by_org():
    # Negative control: this is what organization_users.yaml would have
    # looked like using relationship_properties instead of relationship_key.
    # Proves the bug this design avoids -- both orgs produce an EMPTY,
    # therefore identical, relationship key, so the second grant would
    # silently overwrite the first at the database layer.
    naive_interpretation = RelationshipInterpretation(
        node_type="AuraRole",
        relationship_type="HAS_ORG_ROLE",
        find_many=True,
        node_key={"name": jp("organization_roles")},
        key_normalization={"do_lowercase_strings": False},
        relationship_properties={"organization_id": jp("organization_id")},
    )
    context_org1 = context_for(
        {"organization_id": "org-1", "organization_roles": ["ORG_ADMIN"]}
    )
    context_org2 = context_for(
        {"organization_id": "org-2", "organization_roles": ["ORG_ADMIN"]}
    )
    naive_interpretation.interpret(context_org1)
    naive_interpretation.interpret(context_org2)

    rel1 = context_org1.desired_ingest.relationships[0].relationship
    rel2 = context_org2.desired_ingest.relationships[0].relationship
    assert_that(rel1.key_values, equal_to({}))
    assert_that(rel2.key_values, equal_to({}))


def test_default_key_normalization_would_have_lowercased_role_names():
    # Negative control: proves key_normalization: {do_lowercase_strings:
    # false} is load-bearing, not decorative. nodestream lowercases node
    # keys by default (DEFAULT_KEY_NORMALIZATION_ARGUMENTS in
    # relationship_interpretation.py); without the override, "ORG_ADMIN"
    # silently becomes "org_admin", diverging from the real Aura API value.
    interpretation_without_override = RelationshipInterpretation(
        node_type="AuraRole",
        relationship_type="HAS_ORG_ROLE",
        find_many=True,
        node_key={"name": jp("organization_roles")},
    )
    context = context_for({"organization_roles": ["ORG_ADMIN"]})
    interpretation_without_override.interpret(context)

    assert_that(
        context.desired_ingest.relationships[0].to_node.key_values,
        equal_to({"name": "org_admin"}),
    )


# --- organization_users.yaml: ENROLLED_IN -> MfaMethod ---
#
# mfa_enrolled_methods is a list of OBJECTS on the real API
# ([{"id": "totp", "enrolled_at": "..."}]), confirmed after find_many crashed
# a real `nodestream run organization_users` with `TypeError: unhashable
# type: 'dict'` -- find_many's node_key hands each raw list item to the key
# as-is, which is correct for a list of strings (organization_roles) but
# wrong for a list of objects. iterate_on is the fix: it decomposes the
# record into one sub-record per list item first, so node_key/
# relationship_properties resolve against each individual object.


def enrolled_in_interpretation():
    return RelationshipInterpretation(
        node_type="MfaMethod",
        relationship_type="ENROLLED_IN",
        iterate_on=jp("mfa_enrolled_methods"),
        node_key={"name": jp("id")},
        key_normalization={"do_lowercase_strings": False},
        relationship_properties={"enrolled_at": jp("enrolled_at")},
    )


def test_enrolled_in_iterates_one_relationship_per_mfa_method_object():
    context = context_for(
        {
            "mfa_enrolled_methods": [
                {"id": "totp", "enrolled_at": "2025-09-09T21:10:57.225000Z"},
                {"id": "webauthn", "enrolled_at": "2025-10-01T00:00:00.000000Z"},
            ]
        }
    )
    enrolled_in_interpretation().interpret(context)

    relationships = context.desired_ingest.relationships
    assert_that(relationships, has_length(2))
    method_names = [r.to_node.key_values["name"] for r in relationships]
    assert_that(method_names, contains_inanyorder("totp", "webauthn"))


def test_enrolled_in_pairs_each_methods_own_enrolled_at_not_the_first_ones():
    # The bug find_many's relationship_properties would have caused here:
    # find_relationship() computes relationship_properties ONCE per record
    # using single_value() semantics, so every fanned-out relationship would
    # get the FIRST item's enrolled_at, silently misattributing the second
    # method's enrollment date. iterate_on avoids this by giving each
    # sub-record its own single-item document before relationship_properties
    # is evaluated.
    context = context_for(
        {
            "mfa_enrolled_methods": [
                {"id": "totp", "enrolled_at": "2025-09-09T21:10:57.225000Z"},
                {"id": "webauthn", "enrolled_at": "2025-10-01T00:00:00.000000Z"},
            ]
        }
    )
    enrolled_in_interpretation().interpret(context)

    by_method = {
        r.to_node.key_values["name"]: r.relationship.properties["enrolled_at"]
        for r in context.desired_ingest.relationships
    }
    assert_that(by_method["totp"], equal_to("2025-09-09T21:10:57.225000Z"))
    assert_that(by_method["webauthn"], equal_to("2025-10-01T00:00:00.000000Z"))


def test_find_many_on_a_list_of_objects_would_have_crashed():
    # Negative control: reproduces the exact TypeError seen in production,
    # proving find_many is the wrong tool for a list of objects rather than
    # asserting it.
    naive_interpretation = RelationshipInterpretation(
        node_type="MfaMethod",
        relationship_type="ENROLLED_IN",
        find_many=True,
        node_key={"name": jp("mfa_enrolled_methods")},
        key_normalization={"do_lowercase_strings": False},
    )
    context = context_for(
        {
            "mfa_enrolled_methods": [
                {"id": "totp", "enrolled_at": "2025-09-09T21:10:57.225000Z"}
            ]
        }
    )
    naive_interpretation.interpret(context)

    # The node_key resolved to a dict, not a string -- constructing it didn't
    # raise, but it produced an unhashable key_values entry. This is exactly
    # what later blows up in nodestream's operation debouncer
    # (bucket.get(key) on a tuple containing a dict).
    key_values = context.desired_ingest.relationships[0].to_node.key_values
    assert_that(isinstance(key_values["name"], dict), equal_to(True))
    with pytest.raises(TypeError):
        hash(tuple(sorted(key_values.items())))


# --- instances.yaml / customer_managed_keys.yaml / graph_analytics_sessions.yaml:
#     HOSTED_IN -> AuraRegion (composite key), HOSTED_BY -> AuraCloudProvider ---


def test_hosted_in_region_uses_composite_name_and_cloud_provider_key():
    interpretation = RelationshipInterpretation(
        node_type="AuraRegion",
        relationship_type="HOSTED_IN",
        node_key={"name": jp("region"), "cloud_provider": jp("cloud_provider")},
    )
    context = context_for({"region": "europe-west1", "cloud_provider": "gcp"})
    interpretation.interpret(context)

    assert_that(
        context.desired_ingest.relationships[0].to_node.key_values,
        equal_to({"name": "europe-west1", "cloud_provider": "gcp"}),
    )


def test_hosted_by_cloud_provider_uses_name_alone():
    interpretation = RelationshipInterpretation(
        node_type="AuraCloudProvider",
        relationship_type="HOSTED_BY",
        node_key={"name": jp("cloud_provider")},
    )
    context = context_for({"cloud_provider": "gcp"})
    interpretation.interpret(context)

    assert_that(
        context.desired_ingest.relationships[0].to_node.key_values,
        equal_to({"name": "gcp"}),
    )


# --- graph_analytics_sessions.yaml: CREATED_BY -> AuraUser ---


def test_created_by_targets_aura_user_via_user_id():
    interpretation = RelationshipInterpretation(
        node_type="AuraUser",
        relationship_type="CREATED_BY",
        node_key={"user_id": jp("user_id")},
    )
    context = context_for({"user_id": "user-1"})
    interpretation.interpret(context)

    assert_that(
        context.desired_ingest.relationships[0].to_node.key_values,
        equal_to({"user_id": "user-1"}),
    )


# --- agents.yaml: QUERIES -> AuraInstance via dbid (speculative) ---


def test_queries_targets_aura_instance_via_dbid():
    interpretation = RelationshipInterpretation(
        node_type="AuraInstance",
        relationship_type="QUERIES",
        node_key={"id": jp("dbid")},
    )
    context = context_for({"dbid": "inst-1"})
    interpretation.interpret(context)

    assert_that(
        context.desired_ingest.relationships[0].to_node.key_values,
        equal_to({"id": "inst-1"}),
    )


# --- organization_invites.yaml: AuraInvite keyed on (email, organization_id) ---


def test_invite_source_node_uses_composite_email_and_organization_id_key():
    interpretation = SourceNodeInterpretation(
        node_type="AuraInvite",
        key={"email": jp("email"), "organization_id": jp("organization_id")},
    )
    context = context_for({"email": "person@example.com", "organization_id": "org-1"})
    interpretation.interpret(context)

    assert_that(
        context.desired_ingest.source.key_values,
        equal_to({"email": "person@example.com", "organization_id": "org-1"}),
    )


def test_invite_keyed_on_email_alone_would_have_collided_across_orgs():
    # Negative control: proves the latent bug in the original single-field
    # key. The same email invited to two different orgs produces the SAME
    # key under an email-only scheme, so the second invite would silently
    # overwrite the first's status/organization_id.
    naive_interpretation = SourceNodeInterpretation(
        node_type="AuraInvite",
        key={"email": jp("email")},
    )
    context_org1 = context_for(
        {"email": "person@example.com", "organization_id": "org-1"}
    )
    context_org2 = context_for(
        {"email": "person@example.com", "organization_id": "org-2"}
    )
    naive_interpretation.interpret(context_org1)
    naive_interpretation.interpret(context_org2)

    assert_that(
        context_org1.desired_ingest.source.key_values,
        equal_to(context_org2.desired_ingest.source.key_values),
    )
