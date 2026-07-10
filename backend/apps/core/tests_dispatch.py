"""Resilient dispatch: a broker/Channels (Redis) outage must not raise into the
request path — the primary DB write already succeeded (apps.core.dispatch)."""
from unittest.mock import MagicMock

from django.test import SimpleTestCase

from apps.core.dispatch import safe_enqueue, safe_group_send


class SafeEnqueueTests(SimpleTestCase):
    def test_enqueues_with_args_kwargs_and_options(self):
        task = MagicMock()
        self.assertTrue(safe_enqueue(task, 7, foo="bar", options={"queue": "payments"}))
        task.apply_async.assert_called_once_with(
            args=(7,), kwargs={"foo": "bar"}, queue="payments")

    def test_broker_outage_is_swallowed(self):
        task = MagicMock(name="mytask")
        task.apply_async.side_effect = ConnectionError("max number of clients reached")
        # Must not raise — returns False so the caller knows it was not queued.
        self.assertFalse(safe_enqueue(task, 1, critical=True))

    def test_returns_true_on_success(self):
        task = MagicMock()
        self.assertTrue(safe_enqueue(task, 1))


class SafeGroupSendTests(SimpleTestCase):
    def test_channel_outage_is_swallowed(self):
        # get_channel_layer resolves a real layer; force its group_send to blow up
        # and assert we degrade to False rather than raising into the view.
        import apps.core.dispatch as dispatch

        class _BoomLayer:
            async def group_send(self, *a, **k):
                raise ConnectionError("channels backend down")

        orig = dispatch.safe_group_send
        # Patch get_channel_layer via the lazy import path used inside the helper.
        import channels.layers as layers
        real = layers.get_channel_layer
        layers.get_channel_layer = lambda *a, **k: _BoomLayer()
        try:
            self.assertFalse(orig("grp", {"type": "x"}))
        finally:
            layers.get_channel_layer = real

    def test_no_channel_layer_returns_false(self):
        import channels.layers as layers
        real = layers.get_channel_layer
        layers.get_channel_layer = lambda *a, **k: None
        try:
            self.assertFalse(safe_group_send("grp", {"type": "x"}))
        finally:
            layers.get_channel_layer = real
