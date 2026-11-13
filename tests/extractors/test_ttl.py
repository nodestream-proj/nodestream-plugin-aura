import logging

import pytest
from hamcrest import assert_that, contains_inanyorder, equal_to, has_length
from nodestream.pipeline.argument_resolvers.configuration_argument_resolver import (
    set_config,
)
from nodestream.pipeline.scope_config import ScopeConfig

from nodestream_plugin_aura.extractors.ttl import AuraTimeToLiveExtractor

CONFIGS = [{"object_type": "AuraUser"}, {"object_type": "AuraRole"}]


async def collect(subject):
    return [config async for config in subject.extract_records()]


@pytest.mark.asyncio
async def test_emits_enabled_configs_with_the_configured_window():
    results = await collect(AuraTimeToLiveExtractor("NODE", CONFIGS, 168))

    assert_that(results, has_length(2))
    assert_that(
        [c.object_type for c in results], contains_inanyorder("AuraUser", "AuraRole")
    )
    for config in results:
        assert_that(config.expiry_in_hours, equal_to(168))
        assert_that(config.enabled, equal_to(True))
        assert_that(config.graph_object_type.value, equal_to("NODE"))


@pytest.mark.asyncio
async def test_unset_window_emits_disabled_configs_not_nodestreams_24h_default(caplog):
    # `!config TtlExpiryHours` resolves to None when the key is missing from
    # nodestream.yaml. Falling through to nodestream's own 24-hour default
    # would silently delete everything older than a day, so every config must
    # come out disabled (ingest() skips disabled configs) -- yet still be
    # emitted so `nodestream audit ttls` can see which types are covered.
    with set_config(ScopeConfig({})), caplog.at_level(logging.WARNING):
        subject = AuraTimeToLiveExtractor("RELATIONSHIP", CONFIGS, None)
        results = await collect(subject)

    assert_that(results, has_length(2))
    for config in results:
        assert_that(config.enabled, equal_to(False))
        assert_that(config.expiry_in_hours, equal_to(None))
    assert_that("TtlExpiryHours is not set" in caplog.text, equal_to(True))


@pytest.mark.asyncio
async def test_disabled_config_does_not_touch_the_database():
    class Strategy:
        called = False

        async def perform_ttl_operation(self, config):
            Strategy.called = True

    (config, _) = await collect(AuraTimeToLiveExtractor("NODE", CONFIGS, None))
    await config.ingest(Strategy())

    assert_that(Strategy.called, equal_to(False))


@pytest.mark.asyncio
@pytest.mark.parametrize("bad_value", [0, -5, "168", 1.5, True])
async def test_an_explicit_but_invalid_window_raises(bad_value):
    subject = AuraTimeToLiveExtractor("NODE", CONFIGS, bad_value)

    with pytest.raises(ValueError, match="TtlExpiryHours"):
        await collect(subject)


@pytest.mark.asyncio
async def test_introspection_load_does_not_warn_but_still_emits_disabled_configs(
    caplog,
):
    # `nodestream audit ttls` loads pipelines with no config context, where
    # `!config TtlExpiryHours` is None even if the user HAS set it. Warning
    # there would be a false alarm; the audit only needs the covered types.
    with caplog.at_level(logging.WARNING):
        results = await collect(AuraTimeToLiveExtractor("NODE", CONFIGS, None))

    assert_that(results, has_length(2))
    assert_that(caplog.text, equal_to(""))
