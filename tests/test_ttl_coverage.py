"""Guards the data-expiry (TTL) pipelines against drift.

nodestream only upserts, so any node or relationship type that a pipeline
writes but the TTL pipelines don't list would live in the graph forever
(revoked access never disappearing). This test builds the plugin's real
project schema and fails if a type is missing from the TTL lists -- or if the
TTL lists name a type no pipeline writes any more.
"""

import asyncio

from hamcrest import assert_that, empty, greater_than
from nodestream.pipeline.extractors.ttls import TimeToLiveConfigurationExtractor
from nodestream.project import Project
from nodestream.project.plugin import PluginConfiguration
from nodestream.schema import GraphObjectType

from nodestream_plugin_aura.plugin import AuraPlugin


def build_project():
    # The plugin's pipelines only attach to a project that lists the plugin in
    # its `plugins:` config (as a real nodestream.yaml does) -- without this
    # entry the scope is silently empty and every check below passes vacuously.
    project = Project(
        scopes_by_name={},
        plugins_by_name={
            "aura": PluginConfiguration.from_file_data(
                {"name": "aura", "targets": ["neo4j"], "config": {}}
            )
        },
    )
    AuraPlugin().activate(project)
    return project


def schema_types(project, graph_object_type):
    return {
        type_def.name
        for (kind, _), type_def in project.get_schema().type_schemas.items()
        if kind == graph_object_type
    }


def ttl_types(project, graph_object_type):
    async def collect():
        found = set()
        for _, _, extractor in project.dig_for_step_of_type(
            TimeToLiveConfigurationExtractor
        ):
            async for config in extractor.extract_records():
                if config.graph_object_type == graph_object_type:
                    found.add(config.object_type)
        return found

    return asyncio.run(collect())


def test_every_node_type_written_by_a_pipeline_has_a_ttl_entry():
    project = build_project()
    missing = schema_types(project, GraphObjectType.NODE) - ttl_types(
        project, GraphObjectType.NODE
    )
    assert_that(sorted(missing), empty())


def test_every_relationship_type_written_by_a_pipeline_has_a_ttl_entry():
    project = build_project()
    missing = schema_types(project, GraphObjectType.RELATIONSHIP) - ttl_types(
        project, GraphObjectType.RELATIONSHIP
    )
    assert_that(sorted(missing), empty())


def test_ttl_entries_only_name_types_some_pipeline_actually_writes():
    project = build_project()
    stale_nodes = ttl_types(project, GraphObjectType.NODE) - schema_types(
        project, GraphObjectType.NODE
    )
    stale_rels = ttl_types(project, GraphObjectType.RELATIONSHIP) - schema_types(
        project, GraphObjectType.RELATIONSHIP
    )
    assert_that(sorted(stale_nodes | stale_rels), empty())


def test_the_checks_above_are_not_vacuous():
    # If the plugin scope failed to load, the schema (and so every "missing"
    # set above) would be empty and the coverage tests would pass trivially.
    project = build_project()
    assert_that(len(schema_types(project, GraphObjectType.NODE)), greater_than(10))
    assert_that(
        len(schema_types(project, GraphObjectType.RELATIONSHIP)), greater_than(10)
    )
    assert_that(len(ttl_types(project, GraphObjectType.NODE)), greater_than(10))
