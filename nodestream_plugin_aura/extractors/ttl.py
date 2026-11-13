import logging
from typing import Any, AsyncGenerator, Dict, Iterable, Optional

from nodestream.model import TimeToLiveConfiguration
from nodestream.pipeline.argument_resolvers import get_config
from nodestream.pipeline.extractors.ttls import TimeToLiveConfigurationExtractor
from nodestream.schema import GraphObjectType

logger = logging.getLogger(__name__)


class AuraTimeToLiveExtractor(TimeToLiveConfigurationExtractor):
    """Emits TTL (data-expiry) configs for a list of node or relationship types,
    refusing to guess an expiry window.

    Why this exists instead of using nodestream's own
    TimeToLiveConfigurationExtractor directly: that class falls back to a
    24-hour window when none is given, and `!config TtlExpiryHours` resolves to
    `None` both when the key is missing from nodestream.yaml and when nodestream
    loads a pipeline for introspection (`nodestream audit ttls`, schema
    commands). So a user who forgot to set `TtlExpiryHours` would get a 24-hour
    window silently and, on a weekly run cadence, have the whole graph deleted.

    Behaviour here instead:
    - `expiry_in_hours` is None (not configured): every config is emitted with
      `enabled=False`. `nodestream audit ttls` still sees the covered types, but
      a real run is a no-op (TimeToLiveConfiguration.ingest skips disabled
      configs), and a warning says why -- but only when the pipeline was loaded
      with a config context, i.e. for a real run. Introspection loads
      (`nodestream audit ttls`, schema commands) have no config context, so
      `!config` is None there even when the setting IS present; warning in
      that case would be a false alarm.
    - `expiry_in_hours` is a positive int: every config is emitted enabled with
      that window.
    - Anything else (0, negative, a string, a bool): raises ValueError. An
      explicitly-set but wrong value is a config mistake worth failing on, not
      silently disabling.

    `configurations` is a list of `{"object_type": <label or relationship type>}`
    dicts, the same shape nodestream's own extractor takes, so the pipeline YAML
    reads the same.
    """

    def __init__(
        self,
        graph_object_type: str,
        configurations: Iterable[Dict[str, Any]],
        expiry_in_hours: Optional[int] = None,
    ) -> None:
        super().__init__(graph_object_type, [])
        self.graph_object_type = GraphObjectType(graph_object_type)
        self.object_types = [config["object_type"] for config in configurations]
        self.expiry_in_hours = expiry_in_hours
        # Captured at load time: nodestream sets the config context only while
        # building a pipeline for a real run, not for introspection.
        self._loaded_with_config = get_config() is not None

    async def extract_records(self) -> AsyncGenerator[Any, Any]:
        hours = self.expiry_in_hours
        enabled = True
        if hours is None:
            enabled = False
            if self._loaded_with_config:
                logger.warning(
                    "TtlExpiryHours is not set in the aura plugin config, so "
                    "the %s TTL pipeline will not delete anything. Set it in "
                    "nodestream.yaml to enable data expiry.",
                    self.graph_object_type.value,
                )
        elif isinstance(hours, bool) or not isinstance(hours, int) or hours <= 0:
            raise ValueError(
                f"TtlExpiryHours must be a positive integer number of hours, "
                f"got {hours!r}."
            )

        for object_type in self.object_types:
            yield TimeToLiveConfiguration(
                graph_object_type=self.graph_object_type,
                object_type=object_type,
                expiry_in_hours=hours,
                enabled=enabled,
            )
