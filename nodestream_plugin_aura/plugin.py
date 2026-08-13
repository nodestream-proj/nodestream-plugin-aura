from nodestream.project import Project, ProjectPlugin


class AuraPlugin(ProjectPlugin):
    def activate(self, project: Project) -> None:
        project.add_plugin_scope_from_pipeline_resources(
            name="aura",
            package="nodestream_plugin_aura",
        )
