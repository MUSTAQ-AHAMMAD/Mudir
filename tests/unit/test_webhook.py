"""Unit tests for :class:`orchestra.whatsapp.webhook.WebhookReceiver`.

Covers HMAC-SHA256 signature validation, message parsing, status updates,
media handling and error handling. No network is used — the handler layer is
replaced with a recording fake.
"""

from __future__ import annotations

import dataclasses
import hashlib
import hmac
import unittest

from orchestra.whatsapp.config import WhatsAppConfig
from orchestra.whatsapp.webhook import WebhookReceiver, parse_message


class RecordingHandlers:
    """A stand-in for :class:`MessageHandlers` that records dispatched calls."""

    def __init__(self):
        self.calls = []

    async def handle_text(self, content, sender, group_id):
        self.calls.append(("text", content, sender, group_id))
        return {"ok": True, "handler": "text"}

    async def handle_voice(self, content, sender, group_id):
        self.calls.append(("voice", content, sender, group_id))
        return {"ok": True, "handler": "voice"}

    async def handle_image(self, content, sender, group_id):
        self.calls.append(("image", content, sender, group_id))
        return {"ok": True, "handler": "image"}

    async def handle_document(self, content, sender, group_id):
        self.calls.append(("document", content, sender, group_id))
        return {"ok": True, "handler": "document"}


def _receiver(secret="s3cr3t", allow_unsigned=False, handlers=None):
    cfg = WhatsAppConfig(webhook_secret=secret, webhook_allow_unsigned=allow_unsigned)
    return WebhookReceiver(config=cfg, handlers=handlers)


def _sign(body: bytes, secret: str = "s3cr3t") -> str:
    return hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


# ---------------------------------------------------------------------------
# Signature validation
# ---------------------------------------------------------------------------
class SignatureTests(unittest.TestCase):
    def test_valid_signature_accepted(self):
        receiver = _receiver()
        body = b'{"hello":"world"}'
        sig = _sign(body)
        self.assertTrue(receiver.verify_signature(body, sig))
        self.assertTrue(receiver.verify_signature(body, "sha256=" + sig))

    def test_invalid_signature_rejected(self):
        receiver = _receiver()
        self.assertFalse(receiver.verify_signature(b"{}", "deadbeef"))

    def test_missing_signature_rejected_when_secret_set(self):
        receiver = _receiver()
        self.assertFalse(receiver.verify_signature(b"{}", None))

    def test_unsigned_allowed_in_dev_mode(self):
        receiver = _receiver(secret="", allow_unsigned=True)
        self.assertTrue(receiver.verify_signature(b"{}", None))

    def test_unsigned_rejected_when_not_allowed(self):
        receiver = _receiver(secret="", allow_unsigned=False)
        self.assertFalse(receiver.verify_signature(b"{}", None))

    def test_string_payload_accepted(self):
        receiver = _receiver()
        body = '{"a":1}'
        sig = _sign(body.encode())
        self.assertTrue(receiver.verify_signature(body, sig))


# ---------------------------------------------------------------------------
# Message parsing
# ---------------------------------------------------------------------------
class ParseMessageTests(unittest.TestCase):
    def test_parses_text_message_fields(self):
        parsed = parse_message({"type": "text", "text": "hi", "waId": "grp", "senderName": "Ali"})
        self.assertEqual(parsed["group_id"], "grp")
        self.assertEqual(parsed["type"], "text")
        self.assertEqual(parsed["content"]["text"], "hi")

    def test_normalises_group_id_variants(self):
        parsed = parse_message({"type": "text", "groupId": "g99", "text": "x"})
        self.assertEqual(parsed["group_id"], "g99")

    def test_from_me_flag_preserved(self):
        parsed = parse_message({"type": "text", "text": "x", "waId": "g", "fromMe": True})
        self.assertTrue(parsed["from_me"])


# ---------------------------------------------------------------------------
# Incoming message routing
# ---------------------------------------------------------------------------
class IncomingMessageTests(unittest.IsolatedAsyncioTestCase):
    async def test_text_routes_to_text_handler(self):
        handlers = RecordingHandlers()
        receiver = _receiver(handlers=handlers)
        result = await receiver.handle_incoming_message(
            {"type": "text", "text": "opening a store", "waId": "grp"}
        )
        self.assertEqual(result["status"], "ok")
        self.assertEqual(handlers.calls[0][0], "text")

    async def test_voice_routes_to_voice_handler(self):
        handlers = RecordingHandlers()
        receiver = _receiver(handlers=handlers)
        await receiver.handle_incoming_message(
            {"type": "audio", "waId": "grp", "data": "https://cdn/voice.ogg"}
        )
        self.assertEqual(handlers.calls[0][0], "voice")

    async def test_from_me_message_ignored(self):
        handlers = RecordingHandlers()
        receiver = _receiver(handlers=handlers)
        result = await receiver.handle_incoming_message(
            {"type": "text", "text": "hi", "waId": "grp", "fromMe": True}
        )
        self.assertEqual(result["status"], "ignored")
        self.assertEqual(handlers.calls, [])


# ---------------------------------------------------------------------------
# Media handling
# ---------------------------------------------------------------------------
class MediaHandlingTests(unittest.IsolatedAsyncioTestCase):
    async def test_media_upload_delegates_to_image_handler(self):
        handlers = RecordingHandlers()
        receiver = _receiver(handlers=handlers)
        result = await receiver.handle_media_upload(
            {"type": "image", "waId": "grp", "data": "https://cdn/x.jpg"}
        )
        self.assertEqual(result["status"], "ok")
        self.assertEqual(handlers.calls[0][0], "image")


# ---------------------------------------------------------------------------
# Status updates
# ---------------------------------------------------------------------------
class StatusUpdateTests(unittest.IsolatedAsyncioTestCase):
    async def test_status_update_extracts_delivery_state(self):
        receiver = _receiver()
        result = await receiver.handle_status_update(
            {"type": "status", "id": "msg-1", "status": "delivered"}
        )
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["delivery_status"], "delivered")


# ---------------------------------------------------------------------------
# Event dispatch + error handling
# ---------------------------------------------------------------------------
class HandleEventTests(unittest.IsolatedAsyncioTestCase):
    async def test_handle_event_rejects_bad_signature(self):
        from orchestra.whatsapp.exceptions import WebhookValidationError

        handlers = RecordingHandlers()
        receiver = _receiver(handlers=handlers)
        payload = {"type": "text", "text": "hi", "waId": "g"}
        import json

        raw = json.dumps(payload).encode()
        with self.assertRaises(WebhookValidationError):
            await receiver.handle_event(payload, raw_body=raw, signature="bad")

    async def test_handle_event_accepts_valid_signature(self):
        handlers = RecordingHandlers()
        receiver = _receiver(handlers=handlers)
        payload = {"type": "text", "text": "hi", "waId": "g"}
        import json

        raw = json.dumps(payload).encode()
        result = await receiver.handle_event(payload, raw_body=raw, signature=_sign(raw))
        self.assertEqual(result["status"], "ok")

    async def test_route_request_health(self):
        receiver = _receiver(secret="", allow_unsigned=True)
        status, body = await receiver.route_request("GET", "/webhook/health")
        self.assertEqual(status, 200)

    async def test_route_request_missing_body(self):
        receiver = _receiver(secret="", allow_unsigned=True)
        status, body = await receiver.route_request("POST", "/webhook/wati", body=None)
        self.assertEqual(status, 400)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
