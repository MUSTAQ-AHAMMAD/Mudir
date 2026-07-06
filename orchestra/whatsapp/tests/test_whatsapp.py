"""Tests for the ORCHESTRA WhatsApp integration layer.

These use the stdlib :mod:`unittest` (``IsolatedAsyncioTestCase``) so they run
without any extra dependencies::

    python -m unittest discover -s orchestra/whatsapp/tests

They are also discoverable by ``pytest`` if it is installed.
"""

from __future__ import annotations

import unittest

from orchestra.whatsapp import templates
from orchestra.whatsapp.client import SlidingWindowRateLimiter, WATIClient
from orchestra.whatsapp.exceptions import (
    MediaDownloadError,
    RateLimitError,
    WhatsAppAPIError,
)
from orchestra.whatsapp.webhook import WebhookReceiver, parse_message


# ---------------------------------------------------------------------------
# Test doubles
# ---------------------------------------------------------------------------
class FakeResponse:
    """Minimal stand-in for an httpx.Response."""

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


def _client(responses=None, **kwargs):
    return WATIClient(transport=RecordingTransport(responses), **kwargs)


# ---------------------------------------------------------------------------
# Templates
# ---------------------------------------------------------------------------
class TemplateTests(unittest.TestCase):
    def test_render_arabic(self):
        msg = templates.render(
            "PROJECT_CREATED",
            {"project_name": "Riyadh Mall", "team": "Property"},
            lang="ar",
        )
        self.assertIn("Riyadh Mall", msg)
        self.assertIn("مدير", msg)
        self.assertNotIn("I'm Mudir", msg)

    def test_render_english(self):
        msg = templates.render(
            "PROJECT_CREATED",
            {"project_name": "Riyadh Mall", "team": "Property"},
            lang="en",
        )
        self.assertIn("I'm Mudir", msg)
        self.assertNotIn("مدير", msg)

    def test_render_both(self):
        msg = templates.render(
            "OVERDUE_ALERT",
            {"team": "Design", "days": 3, "project_name": "P-1"},
            lang="both",
        )
        self.assertIn("تنبيه", msg)
        self.assertIn("Alert", msg)
        self.assertIn("3", msg)

    def test_missing_variable_is_blank_not_error(self):
        # No variables passed: should not raise and placeholders become blank.
        msg = templates.render("TASK_ASSIGNED", {}, lang="en")
        self.assertIn("New task", msg)

    def test_unknown_template_raises(self):
        from orchestra.whatsapp.exceptions import TemplateNotFoundError

        with self.assertRaises(TemplateNotFoundError):
            templates.render("NOPE", {})

    def test_meta_names_present(self):
        self.assertEqual(
            templates.META_TEMPLATE_NAMES["OVERDUE_ALERT"], "mudir_overdue_alert"
        )


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------
class ClientSendTests(unittest.IsolatedAsyncioTestCase):
    async def test_send_message_hits_expected_endpoint(self):
        transport = RecordingTransport([FakeResponse(json_body={"result": "sent"})])
        client = WATIClient(transport=transport)
        result = await client.send_message("group123", "hello")
        self.assertEqual(result, {"result": "sent"})
        self.assertEqual(transport.calls[0]["method"], "POST")
        self.assertIn("sendSessionMessage/group123", transport.calls[0]["url"])

    async def test_send_template_builds_parameters(self):
        transport = RecordingTransport([FakeResponse()])
        client = WATIClient(transport=transport)
        await client.send_template("g1", "mudir_overdue_alert", {"1": "Design"})
        body = transport.calls[0]["json"]
        self.assertEqual(body["template_name"], "mudir_overdue_alert")
        self.assertEqual(body["parameters"], [{"name": "1", "value": "Design"}])

    async def test_api_error_on_4xx(self):
        transport = RecordingTransport([FakeResponse(status_code=400)])
        client = WATIClient(transport=transport)
        with self.assertRaises(WhatsAppAPIError) as ctx:
            await client.send_message("g1", "x")
        self.assertEqual(ctx.exception.status_code, 400)

    async def test_health_check_false_when_unconfigured(self):
        client = WATIClient(transport=RecordingTransport([FakeResponse()]))
        # Default config has no API key in the test environment.
        self.assertFalse(await client.health_check())


class ClientRetryTests(unittest.IsolatedAsyncioTestCase):
    async def test_retries_on_503_then_succeeds(self):
        transport = RecordingTransport(
            [FakeResponse(status_code=503), FakeResponse(json_body={"ok": 1})]
        )
        client = WATIClient(transport=transport)
        client.config = _fast_retry_config(client.config)
        result = await client.send_message("g1", "hi")
        self.assertEqual(result, {"ok": 1})
        self.assertEqual(len(transport.calls), 2)

    async def test_retries_exhausted_raises(self):
        transport = RecordingTransport(
            [FakeResponse(status_code=500) for _ in range(10)]
        )
        client = WATIClient(transport=transport)
        client.config = _fast_retry_config(client.config, max_retries=2)
        with self.assertRaises(WhatsAppAPIError):
            await client.send_message("g1", "hi")
        # initial + 2 retries = 3 calls
        self.assertEqual(len(transport.calls), 3)

    async def test_connection_error_is_retried(self):
        transport = RecordingTransport(
            [ConnectionError("boom"), FakeResponse(json_body={"ok": True})]
        )
        client = WATIClient(transport=transport)
        client.config = _fast_retry_config(client.config)
        result = await client.send_message("g1", "hi")
        self.assertEqual(result, {"ok": True})


class ClientMediaTests(unittest.IsolatedAsyncioTestCase):
    async def test_download_media_returns_bytes(self):
        transport = RecordingTransport([FakeResponse(content=b"BINARY")])
        client = WATIClient(transport=transport)
        data = await client.download_media("https://x/y.jpg")
        self.assertEqual(data, b"BINARY")

    async def test_download_media_too_large(self):
        transport = RecordingTransport([FakeResponse(content=b"x" * 100)])
        client = WATIClient(transport=transport)
        client.config = _tiny_media_config(client.config)
        with self.assertRaises(MediaDownloadError):
            await client.download_media("https://x/y.jpg")

    async def test_download_media_wraps_api_error(self):
        transport = RecordingTransport([FakeResponse(status_code=404)])
        client = WATIClient(transport=transport)
        with self.assertRaises(MediaDownloadError):
            await client.download_media("https://x/missing.jpg")


# ---------------------------------------------------------------------------
# Rate limiting
# ---------------------------------------------------------------------------
class RateLimitTests(unittest.IsolatedAsyncioTestCase):
    async def test_limiter_allows_then_blocks(self):
        limiter = SlidingWindowRateLimiter(max_events=2, window=100.0)
        await limiter.acquire("g1")
        await limiter.acquire("g1")
        with self.assertRaises(RateLimitError) as ctx:
            await limiter.acquire("g1")
        self.assertGreater(ctx.exception.retry_after, 0)

    async def test_limiter_is_per_key(self):
        limiter = SlidingWindowRateLimiter(max_events=1, window=100.0)
        await limiter.acquire("g1")
        # Different key not affected.
        await limiter.acquire("g2")

    async def test_window_expiry_allows_again(self):
        limiter = SlidingWindowRateLimiter(max_events=1, window=100.0)
        base = [1000.0]
        limiter._now = lambda: base[0]  # type: ignore[assignment]
        await limiter.acquire("g1")
        base[0] += 101  # advance past the window
        await limiter.acquire("g1")  # should not raise

    async def test_client_send_respects_group_limit(self):
        limiter = SlidingWindowRateLimiter(max_events=1, window=100.0)
        client = WATIClient(
            transport=RecordingTransport([FakeResponse(), FakeResponse()]),
            group_rate_limiter=limiter,
        )
        await client.send_message("g1", "one")
        with self.assertRaises(RateLimitError):
            await client.send_message("g1", "two")


# ---------------------------------------------------------------------------
# Webhook signature validation
# ---------------------------------------------------------------------------
class WebhookSignatureTests(unittest.TestCase):
    def _receiver(self, secret="s3cr3t", allow_unsigned=False):
        from orchestra.whatsapp.config import WhatsAppConfig

        cfg = WhatsAppConfig(webhook_secret=secret, webhook_allow_unsigned=allow_unsigned)
        return WebhookReceiver(config=cfg)

    def test_valid_signature(self):
        import hashlib
        import hmac

        receiver = self._receiver()
        body = b'{"hello":"world"}'
        sig = hmac.new(b"s3cr3t", body, hashlib.sha256).hexdigest()
        self.assertTrue(receiver.verify_signature(body, sig))
        self.assertTrue(receiver.verify_signature(body, "sha256=" + sig))

    def test_invalid_signature(self):
        receiver = self._receiver()
        self.assertFalse(receiver.verify_signature(b"{}", "deadbeef"))

    def test_missing_signature_rejected(self):
        receiver = self._receiver()
        self.assertFalse(receiver.verify_signature(b"{}", None))

    def test_unsigned_allowed_when_no_secret(self):
        receiver = self._receiver(secret="", allow_unsigned=True)
        self.assertTrue(receiver.verify_signature(b"{}", None))

    def test_unsigned_blocked_when_not_allowed(self):
        receiver = self._receiver(secret="", allow_unsigned=False)
        self.assertFalse(receiver.verify_signature(b"{}", None))


# ---------------------------------------------------------------------------
# Webhook parsing + routing
# ---------------------------------------------------------------------------
class FakeOrchestrator:
    def __init__(self):
        self.calls = []

    async def handle_incoming_message(self, message, sender, group_id):
        self.calls.append({"message": message, "sender": sender, "group_id": group_id})
        return {"reply": "ok", "echo": message}


class FakeHandlers:
    """Records which handler was invoked and with what content."""

    def __init__(self):
        self.invoked = []

    def _make(self, name):
        async def _handler(content, sender, group_id):
            self.invoked.append((name, content, sender, group_id))
            return {"handler": name}
        return _handler

    def __getattr__(self, name):
        if name.startswith("handle_"):
            return self._make(name)
        raise AttributeError(name)


class WebhookParseTests(unittest.TestCase):
    def test_parse_text_message(self):
        parsed = parse_message(
            {"type": "text", "text": "New store", "waId": "g1", "senderName": "Ali"}
        )
        self.assertEqual(parsed["type"], "text")
        self.assertEqual(parsed["group_id"], "g1")
        self.assertEqual(parsed["content"]["text"], "New store")

    def test_parse_marks_from_me(self):
        parsed = parse_message({"type": "text", "text": "hi", "fromMe": True})
        self.assertTrue(parsed["from_me"])


class WebhookRoutingTests(unittest.IsolatedAsyncioTestCase):
    async def test_text_routes_to_orchestrator(self):
        orch = FakeOrchestrator()
        from orchestra.whatsapp.handlers import MessageHandlers

        handlers = MessageHandlers(orchestrator=orch)
        receiver = WebhookReceiver(handlers=handlers)
        result = await receiver.handle_incoming_message(
            {"type": "text", "text": "We are opening a store", "waId": "grp"}
        )
        self.assertEqual(result["status"], "ok")
        self.assertEqual(orch.calls[0]["group_id"], "grp")
        self.assertEqual(orch.calls[0]["message"], "We are opening a store")

    async def test_image_routes_to_image_handler(self):
        fake = FakeHandlers()
        receiver = WebhookReceiver(handlers=fake)
        await receiver.handle_incoming_message(
            {"type": "image", "data": "http://x/i.jpg", "waId": "grp", "caption": "c"}
        )
        self.assertEqual(fake.invoked[0][0], "handle_image")

    async def test_from_me_is_ignored(self):
        orch = FakeOrchestrator()
        from orchestra.whatsapp.handlers import MessageHandlers

        receiver = WebhookReceiver(handlers=MessageHandlers(orchestrator=orch))
        result = await receiver.handle_incoming_message(
            {"type": "text", "text": "echo", "waId": "grp", "fromMe": True}
        )
        self.assertEqual(result["status"], "ignored")
        self.assertEqual(orch.calls, [])

    async def test_missing_group_id_ignored(self):
        fake = FakeHandlers()
        receiver = WebhookReceiver(handlers=fake)
        result = await receiver.handle_incoming_message({"type": "text", "text": "x"})
        self.assertEqual(result["status"], "ignored")

    async def test_route_request_health(self):
        receiver = WebhookReceiver()
        status, body = await receiver.route_request("GET", "/webhook/health")
        self.assertEqual(status, 200)
        self.assertEqual(body["status"], "healthy")

    async def test_route_request_rejects_bad_signature(self):
        from orchestra.whatsapp.config import WhatsAppConfig

        cfg = WhatsAppConfig(webhook_secret="k", webhook_allow_unsigned=False)
        fake = FakeHandlers()
        receiver = WebhookReceiver(config=cfg, handlers=fake)
        status, body = await receiver.route_request(
            "POST",
            "/webhook/wati",
            body={"type": "text", "text": "hi", "waId": "g"},
            raw_body=b"{}",
            signature="wrong",
        )
        self.assertEqual(status, 401)


# ---------------------------------------------------------------------------
# Sender
# ---------------------------------------------------------------------------
class SenderTests(unittest.IsolatedAsyncioTestCase):
    async def test_send_message_delivers_and_returns_result(self):
        from orchestra.whatsapp.sender import WhatsAppSender

        client = WATIClient(transport=RecordingTransport([FakeResponse()]))
        # Avoid DB access during context resolution.
        sender = WhatsAppSender(client=client)
        sender._resolve_context = _async_return((None, None))
        result = await sender.send_message("grp", "hello")
        self.assertTrue(result["delivered"])

    async def test_send_falls_back_to_log_on_api_error(self):
        from orchestra.whatsapp.sender import WhatsAppSender

        client = WATIClient(transport=RecordingTransport([FakeResponse(status_code=500)]))
        client.config = _fast_retry_config(client.config, max_retries=0)
        sender = WhatsAppSender(client=client)
        sender._resolve_context = _async_return((None, None))
        result = await sender.send_message("grp", "hello")
        self.assertFalse(result["delivered"])
        self.assertIn("error", result)


# ---------------------------------------------------------------------------
# Middleware
# ---------------------------------------------------------------------------
class MiddlewareTests(unittest.IsolatedAsyncioTestCase):
    async def test_rate_limit_middleware_blocks(self):
        from orchestra.whatsapp.client import SlidingWindowRateLimiter
        from orchestra.whatsapp.middleware import RateLimitMiddleware, WebhookRequest

        mw = RateLimitMiddleware(
            group_limiter=SlidingWindowRateLimiter(1, 100.0),
            user_limiter=SlidingWindowRateLimiter(99, 100.0),
        )
        req1 = WebhookRequest(body={"type": "text", "text": "a", "waId": "g"})
        self.assertIsNone(await mw(req1))
        req2 = WebhookRequest(body={"type": "text", "text": "b", "waId": "g"})
        result = await mw(req2)
        self.assertIsNotNone(result)
        self.assertEqual(result[0], 429)

    async def test_auth_middleware_rejects_bad_signature(self):
        from orchestra.whatsapp.config import WhatsAppConfig
        from orchestra.whatsapp.middleware import AuthMiddleware, WebhookRequest
        from orchestra.whatsapp.webhook import WebhookReceiver

        cfg = WhatsAppConfig(webhook_secret="k", webhook_allow_unsigned=False)
        mw = AuthMiddleware(receiver=WebhookReceiver(config=cfg))
        req = WebhookRequest(
            headers={"x-wati-signature": "bad"}, raw_body=b"{}", body={}
        )
        result = await mw(req)
        self.assertEqual(result[0], 401)

    async def test_timeout_middleware_runs_handler(self):
        from orchestra.whatsapp.middleware import TimeoutMiddleware

        async def handler(x):
            return x * 2

        mw = TimeoutMiddleware(timeout=5.0)
        self.assertEqual(await mw.run(handler, 21), 42)

    def test_error_middleware_maps_validation_error(self):
        from orchestra.whatsapp.exceptions import WebhookValidationError
        from orchestra.whatsapp.middleware import error_middleware

        status, _ = error_middleware(WebhookValidationError("bad"))
        self.assertEqual(status, 401)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _async_return(value):
    async def _fn(*_a, **_k):
        return value
    return _fn


def _fast_retry_config(cfg, max_retries=3):
    import dataclasses

    return dataclasses.replace(
        cfg, max_retries=max_retries, retry_backoff_base=0.0, retry_backoff_max=0.0
    )


def _tiny_media_config(cfg):
    import dataclasses

    return dataclasses.replace(cfg, media_max_bytes=10)


if __name__ == "__main__":
    unittest.main()
