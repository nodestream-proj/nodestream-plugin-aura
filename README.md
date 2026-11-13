# nodestream-plugin-aura

Pulls a Neo4j Aura account's organization → project → instance / user /
permission hierarchy (plus customer-managed keys, Graph Analytics sessions,
and Agents) into a graph, for compliance and access-attribution use cases:
who has access to what, where it's hosted, and what would be affected if a
credential, region, or cloud provider were compromised.

## Installation

```bash
pip install nodestream-plugin-aura nodestream-plugin-neo4j
```

`nodestream-plugin-neo4j` provides the `neo4j` database target; install
whichever database connector plugin matches where you want the graph
written.

## Configuration

Create an Aura API client credential in the Aura Console under **Account
Settings → Client credentials** (OAuth2 client-credentials grant).

In your own nodestream project's `nodestream.yaml`, add:

```yaml
plugins:
  - name: aura
    targets:
      - neo4j
    config:
      ClientId: !env AURA_CLIENT_ID
      ClientSecret: !env AURA_CLIENT_SECRET
      OrganizationId: !env AURA_ORGANIZATION_ID
      ProjectScopes:
        - organization_id: !env AURA_ORGANIZATION_ID
          project_id: !env AURA_PROJECT_ID

targets:
  neo4j:
    database: neo4j
    uri: !env NEO4J_URI
    username: !env NEO4J_USERNAME
    password: !env NEO4J_PASSWORD
    database_name: !env NEO4J_DATABASE
```

`ProjectScopes` is a list, not a single id — add one `{organization_id,
project_id}` entry per project you want to pull, across as many orgs as
your credential can reach, and every project-scoped pipeline sweeps all of
them in one `nodestream run`. It's read directly from `nodestream.yaml`
rather than an env var, since org/project ids aren't secrets and a
variable-length list can't come from one flat environment variable.

**One org, several projects** — the same `organization_id` repeats, one
entry per project:

```yaml
      ProjectScopes:
        - organization_id: org-1
          project_id: proj-a
        - organization_id: org-1
          project_id: proj-b
        - organization_id: org-1
          project_id: proj-c
```

This list is **not** auto-populated from `aura_organizations`/`aura_projects`
discovering projects under an org — those two pipelines list everything
they can see on their own, but the eight project-scoped pipelines
(`aura_project_details`, `aura_instances`, `aura_project_users`,
`aura_customer_managed_keys`, `aura_graph_analytics_sessions`,
`aura_agents`, `aura_databases`, `aura_virtual_graphs`) only ever process what's explicitly listed in
`ProjectScopes`. There's no automatic "run this for every project
`aura_projects` just found" chaining — if your org has 10 projects and you
want instances/keys/sessions/agents for all 10, list all 10 here yourself.

To find the project ids to list, either check the Aura Console, or run
`python scripts/smoke_test.py` (see Development below) with just
`AURA_CLIENT_ID`/`AURA_CLIENT_SECRET` set — it prints every project's real
`id` under any org your credential can see, before you've configured
anything else.

Avoid typing secrets directly into an interactive shell (`export
AURA_CLIENT_SECRET=...`) — it lands in shell history and is readable via
`/proc/<pid>/environ` on Linux for that shell's lifetime. A gitignored
`.env` file (`chmod 600`, loaded with `source .env`) or your OS keychain are
both safer. See `playground_project/.env.example` for a template.

## Usage

```bash
nodestream show   # confirms every pipeline resolves under the `aura` scope
nodestream run aura_organizations aura_projects aura_instances \
  aura_organization_users aura_organization_invites aura_ip_filters \
  aura_project_users aura_customer_managed_keys aura_graph_analytics_sessions \
  aura_agents aura_databases aura_virtual_graphs -v
```

Not every pipeline needs the same level of access:

- **Org Admin** (full org visibility): run `aura_organizations`,
  `aura_projects`, `aura_organization_users`, `aura_organization_invites`,
  `aura_ip_filters` for the org's full contents, plus `aura_instances`,
  `aura_project_users`, `aura_customer_managed_keys`,
  `aura_graph_analytics_sessions`, `aura_agents`, `aura_databases`, and
  `aura_virtual_graphs` for whichever projects you listed in `ProjectScopes`. Skip
  `aura_project_details` — it's redundant here, since `aura_projects`
  already gives every project a real `name`.
- **Project Admin** (no org-level list access): skip the five org-wide
  pipelines above (they'll 403/404 — this credential can't list an org's
  full contents) and run `aura_project_details`, `aura_instances`,
  `aura_project_users`, `aura_customer_managed_keys`,
  `aura_graph_analytics_sessions`, `aura_agents`, `aura_databases`, and
  `aura_virtual_graphs` instead — these only
  need the specific projects listed in `ProjectScopes`, not org-wide
  visibility. Run `aura_project_details` alongside the others so
  `AuraProject` nodes get a real `name` instead of an id-only stub — it
  exists specifically because `aura_projects` isn't available to this
  credential.

Run `aura_organizations`/`aura_projects` before pipelines that reference
those nodes — relationships default to eager node creation, so an
out-of-order run won't error, but you'll get stub nodes with no properties
until the owning pipeline backfills them.

## Graph model

```text
(:AuraOrganization {id, name})
  <-[:BELONGS_TO_ORG]-(:AuraProject {id, name})
      <-[:BELONGS_TO_PROJECT]-(:AuraInstance {id, name, status, type, memory, storage,
                                       connection_url, metrics_integration_url,
                                       created_at, vector_optimized,
                                       cdc_enrichment_mode, graph_analytics_plugin,
                                       secondaries_count, graph_nodes,
                                       graph_relationships})
      <-[:BELONGS_TO_PROJECT]-(:AuraCustomerManagedKey {id, name, status, created,
                                                  key_id, type, instance_type})
      <-[:BELONGS_TO_PROJECT]-(:AuraGraphAnalyticsSession {id, name, memory, status,
                                                     created_at, host, expiry_date})
      <-[:BELONGS_TO_PROJECT]-(:AuraAgent {id, name, description, dbid, is_private,
                                     is_mcp_enabled, enabled})
      <-[:BELONGS_TO_PROJECT]-(:AuraVirtualGraph {id, name, status, memory, bolt_url,
                                            private_bolt_url, public_access_enabled,
                                            private_access_enabled, data_source_id,
                                            data_source_type, maximum_bytes_billed,
                                            created_at, error_detail})
(:AuraDatabase {instance_id, id, name})-[:BELONGS_TO_INSTANCE]->(:AuraInstance)
(:AuraInstance)-[:ENCRYPTED_WITH]->(:AuraCustomerManagedKey)   (only if the instance has one)
(:AuraGraphAnalyticsSession)-[:RUNS_ON]->(:AuraInstance)
(:AuraGraphAnalyticsSession)-[:CREATED_BY]->(:AuraUser {user_id})
(:AuraAgent)-[:QUERIES]->(:AuraInstance {id})   (best-effort -- see Known limitations)

# Shared dimension nodes, reached only via relationships from the resource
# types above:
(:AuraInstance | :AuraCustomerManagedKey | :AuraGraphAnalyticsSession | :AuraVirtualGraph)
  -[:HOSTED_IN]->(:AuraRegion {name, cloud_provider})
  -[:HOSTED_BY]->(:AuraCloudProvider {name})

# Network access (IP filters):
(:AuraIpFilter {id, name, description, filtering_disabled, updated_at})
  -[:BELONGS_TO_ORG]->(:AuraOrganization)
  -[:APPLIES_TO_ORG]->(:AuraOrganization)
  -[:APPLIES_TO_PROJECT]->(:AuraProject)
  -[:APPLIES_TO_INSTANCE]->(:AuraInstance)
  -[:ALLOWS {description}]->(:AuraIpRange {cidr, address, prefix_len})

# Users, roles, invites:
(:AuraUser {user_id, email, exempt_from_automatic_removal, last_activity_at,
            mfa_enrollment_status})
  -[:MEMBER_OF_ORG]->(:AuraOrganization)
  -[:HAS_ORG_ROLE {organization_id}]->(:AuraRole {name})
  -[:ENROLLED_IN {enrolled_at}]->(:MfaMethod {name})
(:AuraUser)-[:MEMBER_OF_PROJECT]->(:AuraProject)
(:AuraUser)-[:HAS_PROJECT_ROLE {project_id}]->(:AuraRole {name})
(:AuraInvite {email, organization_id, status})
  -[:INVITED_TO]->(:AuraOrganization)
  -[:INVITED_WITH_ROLE]->(:AuraRole {name})
```

Roles, MFA methods, cloud providers, and regions are modeled as shared nodes
rather than string/list properties, since each value repeats identically
across many users or resources — that's what turns "who holds this role
anywhere" or "what's affected if this cloud provider has an incident" into a
graph traversal instead of a property scan, and makes role/region
concentration usable as input to centrality algorithms.

Every node/relationship key is a minimal, genuinely unique identifier
(verified in `tests/test_graph_schema_interpretations.py`, including
negative-control tests that reproduce two real bugs this avoided: a
same-email invite to two orgs colliding on an email-only key, and a user
holding the same role in two orgs silently overwriting one grant when the
org id sits in `relationship_properties` instead of `relationship_key`).
`AuraRegion` is keyed on `(name, cloud_provider)`, not `name` alone, since a
region name is only meaningful within one provider's namespace.

## Known limitations

- **`AuraOrganizationInviteExtractor`** is the least-confirmed piece of this
  plugin — the endpoint is announced in Neo4j's Aura changelog but hasn't
  been exercised against a real org with pending invites.
- **`AuraAgent`'s `QUERIES` relationship** assumes `dbid` equals the target
  instance's own `id`. That's a reasonable guess (Aura instances are
  effectively single-database today) but not independently confirmed — the
  raw `dbid` is kept as a property on the node regardless, so it stays
  inspectable even if the relationship guess is wrong.
- **`aura_ip_filters`, `aura_databases`, `aura_virtual_graphs`** were added
  from the v2beta1 OpenAPI spec (`https://api.neo4j.io/v2beta1/spec.json`)
  and are covered by mocked tests, but have not yet been run against a real
  account. Two specifics are unverified: the virtual-graphs list endpoint
  marks both `page_limit` and `page_token` as required, so the first request
  (which sends only `page_limit`) may need adjusting; and not every instance
  type may expose the databases endpoint. `aura_ip_filters` is org-scoped
  and needs an Org Admin credential.
- **Rate limits and retries**: Aura's API allows 25 req/min (free/trial) or
  125 req/min (paid); a full sweep of many projects can plausibly exceed
  that. Requests retry with capped exponential backoff on `429`/`5xx`/
  network errors (honoring `Retry-After` when present), with a 60s timeout
  per request. Non-retryable statuses (`400`/`401`/`403`/`404`) fail
  immediately.
- **Permission errors fail loudly, on purpose**: a bare `403`/`404` could
  mean "this genuinely doesn't exist" or "your credential can't see it" —
  extractors don't guess which, so a pipeline run fails rather than writing
  a silently-incomplete graph. The one exception is a *confirmed* Aura
  capability gap (e.g. a project whose plan tier doesn't support
  customer-managed keys), which is unambiguous and is caught and yielded as
  zero records instead.

## Development

```bash
git clone https://github.com/nodestream-proj/nodestream-plugin-aura
cd nodestream-plugin-aura
poetry install

poetry run pytest --cov nodestream_plugin_aura   # 87 tests, all mocked -- no live Aura account touched
poetry run ruff nodestream_plugin_aura tests
poetry run black nodestream_plugin_aura tests --check
poetry run isort nodestream_plugin_aura tests --check-only
```

`scripts/smoke_test.py` is a standalone diagnostic that calls every
extractor directly against a real Aura account (bypassing nodestream
pipelines entirely) and cross-checks the raw JSON it gets back against the
fields each pipeline actually maps, flagging anything present-but-unmapped.
Useful before wiring up a full pipeline run, or after an Aura API change:

```bash
export AURA_CLIENT_ID=...
export AURA_CLIENT_SECRET=...
python scripts/smoke_test.py
```

`playground_project/` is a minimal nodestream project for exercising the
installed plugin end to end against a real account — see its
`.env.example`.

## Contributing

Review our Contributing Guide [in the Docs](https://nodestream-proj.github.io/nodestream/contributing).
