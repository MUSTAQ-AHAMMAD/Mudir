"""Unit tests for :class:`orchestra.whatsapp.client.WATIClient`.

An injectable async ``transport`` (``RecordingTransport``) stands in for
``httpx`` so no real network calls are made. Covers message sending, templates,
retry logic, rate limiting and media download.
"""

from __future__ import annotations

import dataclasses
import unittest

from orchestra.whatsapp.client import SlidingWindowRateLimiter, WATIClient
from orchestra.whatsapp.config import WhatsAppConfig
from orchestra.whatsapp.exceptions import (
    MediaDownloadError,
    RateLimitError,
    WhatsAppAPIError,
)


# ---------------------------------------------------------------------------
# Test doubles for the HTTP transport
# ---------------------------------------------------------------------------
class FakeResponse:
    """Minimal stand-in for an ``httpx.Response``."""

    def __init__(self, status_code=200, json_body=None, content=b""):
        self.status_code = status_code
        self._json = json_body if json_body is not None else {"ok": True}
        self.content = content
        self.text = ""

    def json(self):
        return self._json


class RecordingTransport:
    """Async transport that records calls and returns queued responses."""

    def __init__(self, responses=None):
        self.calls = []
        self._responses = list(responses or [])

    async def __call__(self, method, url, *, params=None, json=None, headers=None):
        self.calls.append({"method": method, "url": url, "params": params, "json": json})
        if self._responses:
            item = self._responses.pop(0)
            if isinstance(item, Exception):
                raise item
            return item
        return FakeResponse()


def _fast_retry_config(cfg, max_retries=3):
    return dataclasses.replace(
        cfg, max_retries=max_retries, retry_backoff_base=0.0, retry_backoff_max=0.0
    )


def _test_config(**overrides):
    base = WhatsAppConfig(wati_api_url="https://test.wati.io", wati_api_key="key")
    return dataclasses.replace(base, **overrides) if overrides else base


# ---------------------------------------------------------------------------
# Sending
# ---------------------------------------------------------------------------
class SendMessageTests(unittest.IsolatedAsyncioTestCase):
    async def test_send_message_hits_expected_endpoint(self):
        transport = RecordingTransport([FakeResponse(json_body={"result": "sent"})])
        client = WATIClient(config=_test_config(), transport=transport)
        result = await client.send_message("group123", "hello")
        self.assertEqual(result, {"result": "sent"})
        self.assertEqual(transport.calls[0]["method"], "POST")
        self.assertIn("sendSessionMessage/group123", transport.calls[0]["url"])

    async def test_send_direct_message(self):
        transport = RecordingTransport([FakeResponse(json_body={"result": "sent"})])
        client = WATIClient(config=_test_config(), transport=transport)
        await client.send_direct_message("+966500000000", "hi")
        self.assertIn("sendSessionMessage/+966500000000", transport.calls[0]["url"])

    async def test_send_template_builds_parameters(self):
        transport = RecordingTransport([FakeResponse()])
        client = WATIClient(config=_test_config(), transport=transport)
        await client.send_template("g1", "mudir_overdue_alert", {"1": "Design"})
        body = transport.calls[0]["json"]
        self.assertEqual(body["template_name"], "mudir_overdue_alert")
        self.assertEqual(body["parameters"], [{"name": "1", "value": "Design"}])


# ---------------------------------------------------------------------------
# Retry logic
# ---------------------------------------------------------------------------
class RetryTests(unittest.IsolatedAsyncioTestCase):
    async def test_retries_on_503_then_succeeds(self):
        transport = RecordingTransport(
            [FakeResponse(status_code=503), FakeResponse(json_body={"ok": 1})]
        )
        client = WATIClient(config=_fast_retry_config(_test_config()), transport=transport)
        result = await client.send_message("g1", "hi")
        self.assertEqual(result, {"ok": 1})
        self.assertEqual(len(transport.calls), 2)

    async def test_retries_exhausted_raises(self):
        transport = RecordingTransport([FakeResponse(status_code=500)] * 6)
        client = WATIClient(config=_fast_retry_config(_test_config(), max_retries=2), transport=transport)
        with self.assertRaises(WhatsAppAPIError):
            await client.send_message("g1", "hi")

    async def test_retries_on_connection_error(self):
        transport = RecordingTransport([RuntimeError("boom"), FakeResponse(json_body={"ok": 2})])
        client = WATIClient(config=_fast_retry_config(_test_config()), transport=transport)
        result = await client.send_message("g1", "hi")
        self.assertEqual(result, {"ok": 2})

    async def test_no_retry_on_4xx(self):
        transport = RecordingTransport([FakeResponse(status_code=400)])
        client = WATIClient(config=_fast_retry_config(_test_config()), transport=transport)
        with self.assertRaises(WhatsAppAPIError):
            await client.send_message("g1", "hi")
        self.assertEqual(len(transport.calls), 1)  # not retried


# ---------------------------------------------------------------------------
# Rate limiting
# ---------------------------------------------------------------------------
class RateLimitTests(unittest.IsolatedAsyncioTestCase):
    async def test_group_rate_limit_enforced(self):
        cfg = _test_config(rate_limit_per_group=2, rate_limit_window=60.0)
        transport = RecordingTransport([FakeResponse() for _ in range(5)])
        client = WATIClient(config=cfg, transport=transport)
        await client.send_message("g1", "1")
        await client.send_message("g1", "2")
        with self.assertRaises(RateLimitError):
            await client.send_message("g1", "3")

    async def test_sliding_window_limiter_directly(self):
        limiter = SlidingWindowRateLimiter(max_events=1, window=60.0)
        await limiter.acquire("k")
        with self.assertRaises(RateLimitError):
            await limiter.acquire("k")


# ---------------------------------------------------------------------------
# Media download
# ---------------------------------------------------------------------------
class MediaDownloadTests(unittest.IsolatedAsyncioTestCase):
    async def test_download_media_returns_bytes(self):
        transport = RecordingTransport([FakeResponse(content=b"audio-bytes")])
        client = WATIClient(config=_test_config(), transport=transport)
        data = await client.download_media("https://cdn.example/voice.ogg")
        self.assertEqual(data, b"audio-bytes")

    async def test_download_media_too_large_raises(self):
        cfg = _test_config(media_max_bytes=4)
        transport = RecordingTransport([FakeResponse(content=b"way-too-large")])
        client = WATIClient(config=cfg, transport=transport)
        with self.assertRaises(MediaDownloadError):
            await client.download_media("https://cdn.example/big.bin")


# ---------------------------------------------------------------------------
# Config helpers
# ---------------------------------------------------------------------------
class ConfigTests(unittest.TestCase):
    def test_is_configured(self):
        self.assertTrue(_test_config().is_configured)
        self.assertFalse(WhatsAppConfig(wati_api_url="", wati_api_key="").is_configured)

    def test_auth_header(self):
        header = _test_config().auth_header
        self.assertEqual(header, {"Authorization": "Bearer " + "key"})

    def test_summary_redacts_secrets(self):
        summary = _test_config(webhook_secret="s3cr3t").summary()
        self.assertNotIn("s3cr3t", str(summary))


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
