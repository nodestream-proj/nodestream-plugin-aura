from unittest.mock import MagicMock

from nodestream_plugin_aura.plugin import AuraPlugin


def test_activate_registers_the_aura_plugin_scope_from_package_resources():
    project = MagicMock()

    AuraPlugin().activate(project)

    project.add_plugin_scope_from_pipeline_resources.assert_called_once_with(
        name="aura",
        package="nodestream_plugin_aura",
    )
