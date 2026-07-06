"""Integration tests for the self-hosted AI services.

The heavy backends (Ollama HTTP API, whisper.cpp, SentenceTransformers and the
HuggingFace ``transformers`` models) are all replaced with lightweight fakes so
the service *wiring* — request shaping, response parsing, normalisation and
error handling — is exercised without any model download or network access.

These are marked ``integration`` because they cross the service boundary, but
they run anywhere (no GPU, no models, no server required).
"""

from __future__ import annotations

import unittest

import pytest

pytestmark = pytest.mark.integration


# ---------------------------------------------------------------------------
# Shared HTTP fakes for the Ollama-backed LLM service
# ---------------------------------------------------------------------------
class FakeHTTPResponse:
    def __init__(self, json_body, status_ok=True):
        self._json = json_body
        self._status_ok = status_ok

    def raise_for_status(self):
        if not self._status_ok:
            import requests

            raise requests.HTTPError("boom")

    def json(self):
        return self._json


class FakeSession:
    """Stand-in for a ``requests.Session`` that returns queued responses."""

    def __init__(self, responses):
        self._responses = list(responses)
        self.posts = []

    def post(self, url, json=None, timeout=None):  # noqa: A002 - mirror requests API
        self.posts.append({"url": url, "json": json})
        return self._responses.pop(0)


def _llm_with(reply_content):
    from orchestra.services.llm_service import LLMService

    service = LLMService(model="test-model", base_url="http://localhost:11434")
    service.max_retries = 1
    service._session = FakeSession([FakeHTTPResponse({"message": {"content": reply_content}})])
    return service


# ---------------------------------------------------------------------------
# LLM service
# ---------------------------------------------------------------------------
class LLMChatTests(unittest.TestCase):
    def test_chat_returns_message_content(self):
        service = _llm_with("Hello from the model")
        self.assertEqual(service.chat("hi"), "Hello from the model")
        # The request targeted the /api/chat endpoint with the model + prompt.
        sent = service._session.posts[0]
        self.assertTrue(sent["url"].endswith("/api/chat"))
        self.assertEqual(sent["json"]["model"], "test-model")

    def test_chat_includes_system_prompt(self):
        service = _llm_with("ok")
        service.chat("question", system="You are helpful")
        messages = service._session.posts[0]["json"]["messages"]
        self.assertEqual(messages[0], {"role": "system", "content": "You are helpful"})

    def test_understand_intent_normalises_shape(self):
        service = _llm_with('{"intent": "create_project", "confidence": 0.9}')
        result = service.understand_intent("open a store")
        self.assertEqual(result["intent"], "create_project")
        # Missing keys are backfilled with defaults.
        self.assertIn("entities", result)
        self.assertIn("sentiment", result)

    def test_extract_workflow_parses_stages(self):
        body = '{"workflow_name": "wf", "stages": [{"name": "A"}, {"name": "B"}]}'
        service = _llm_with(body)
        wf = service.extract_workflow("do A then B")
        self.assertEqual(wf["workflow_name"], "wf")
        self.assertEqual(len(wf["stages"]), 2)

    def test_chat_json_tolerates_surrounding_prose(self):
        service = _llm_with('Sure! Here is the result:\n{"ok": true}\nThanks.')
        result = service._chat_json("x", system="y")
        self.assertEqual(result, {"ok": True})

    def test_chat_retries_then_raises(self):
        from orchestra.services.llm_service import LLMService, LLMServiceError

        service = LLMService(base_url="http://localhost:11434")
        service.max_retries = 2
        service._session = FakeSession([
            FakeHTTPResponse({}, status_ok=False),
            FakeHTTPResponse({}, status_ok=False),
        ])
        with self.assertRaises(LLMServiceError):
            service.chat("hi")


# ---------------------------------------------------------------------------
# Whisper transcription
# ---------------------------------------------------------------------------
class WhisperTests(unittest.TestCase):
    def test_transcribe_returns_text(self):
        from orchestra.services.whisper_service import WhisperService

        service = WhisperService(binary="whisper-cli", model_path="/models/ggml.bin")
        service._run = lambda audio_path, language=None, with_timestamps=False: {"text": "مرحبا"}
        self.assertEqual(service.transcribe("/tmp/a.ogg"), "مرحبا")

    def test_transcribe_missing_file_raises(self):
        from orchestra.services.whisper_service import WhisperService, WhisperServiceError

        service = WhisperService(binary="whisper-cli", model_path="/models/ggml.bin")
        with self.assertRaises(WhisperServiceError):
            service.transcribe("/nonexistent/does-not-exist.ogg")

    def test_transcribe_with_timestamps_returns_segments(self):
        from orchestra.services.whisper_service import WhisperService

        service = WhisperService(binary="whisper-cli", model_path="/models/ggml.bin")
        payload = {"text": "hello", "segments": [{"start": 0.0, "end": 1.0, "text": "hello"}]}
        service._run = lambda audio_path, language=None, with_timestamps=False: payload
        result = service.transcribe_with_timestamps("/tmp/a.ogg")
        self.assertEqual(result["segments"][0]["text"], "hello")


# ---------------------------------------------------------------------------
# Embeddings
# ---------------------------------------------------------------------------
class _FakeVector:
    def __init__(self, values):
        self._values = values

    def tolist(self):
        return list(self._values)


class EmbeddingsTests(unittest.TestCase):
    def _service(self):
        from orchestra.services.embeddings_service import EmbeddingsService

        service = EmbeddingsService(model_path="/models/bge", device="cpu")

        class FakeModel:
            def encode(self, texts, **kwargs):
                return [_FakeVector([0.1, 0.2, 0.3]) for _ in texts]

        service._model = FakeModel()
        return service

    def test_generate_embedding(self):
        vec = self._service().generate_embedding("hello")
        self.assertEqual(vec, [0.1, 0.2, 0.3])

    def test_batch_generate_embeddings(self):
        vecs = self._service().batch_generate_embeddings(["a", "b"])
        self.assertEqual(len(vecs), 2)

    def test_empty_text_raises(self):
        from orchestra.services.embeddings_service import EmbeddingsServiceError

        with self.assertRaises(EmbeddingsServiceError):
            self._service().generate_embedding("   ")

    def test_cosine_similarity_identical(self):
        from orchestra.services.embeddings_service import EmbeddingsService

        self.assertAlmostEqual(EmbeddingsService.cosine_similarity([1, 0], [1, 0]), 1.0)

    def test_cosine_similarity_orthogonal(self):
        from orchestra.services.embeddings_service import EmbeddingsService

        self.assertAlmostEqual(EmbeddingsService.cosine_similarity([1, 0], [0, 1]), 0.0)


# ---------------------------------------------------------------------------
# Sentiment
# ---------------------------------------------------------------------------
class SentimentTests(unittest.TestCase):
    def _service(self, predictions):
        from orchestra.services.sentiment_service import SentimentService

        service = SentimentService(model_path="/models/sent", device="cpu")
        service._pipeline = lambda texts: list(predictions)
        return service

    def test_analyze_positive(self):
        service = self._service([{"label": "positive", "score": 0.98}])
        result = service.analyze("رائع")
        self.assertEqual(result["sentiment"], "positive")
        self.assertAlmostEqual(result["score"], 0.98)

    def test_analyze_batch(self):
        service = self._service([
            {"label": "positive", "score": 0.9},
            {"label": "negative", "score": 0.8},
        ])
        results = service.analyze_batch(["good", "bad"])
        self.assertEqual([r["sentiment"] for r in results], ["positive", "negative"])

    def test_empty_text_raises(self):
        from orchestra.services.sentiment_service import SentimentServiceError

        with self.assertRaises(SentimentServiceError):
            self._service([]).analyze("")


# ---------------------------------------------------------------------------
# Translation
# ---------------------------------------------------------------------------
class _FakeTensor:
    def to(self, device):
        return self


class _FakeTokenizer:
    def __init__(self):
        self.src_lang = None

    def __call__(self, text, return_tensors=None, truncation=None):
        return {"input_ids": _FakeTensor()}

    def convert_tokens_to_ids(self, token):
        return 42

    def batch_decode(self, generated, skip_special_tokens=True):
        return ["translated text"]


class _FakeModel:
    def generate(self, **kwargs):
        return _FakeTensor()


class TranslationTests(unittest.TestCase):
    def test_detect_language_arabic(self):
        from orchestra.services.translation_service import TranslationService

        self.assertEqual(TranslationService().detect_language("مرحبا بالعالم"), "ar")

    def test_detect_language_english(self):
        from orchestra.services.translation_service import TranslationService

        self.assertEqual(TranslationService().detect_language("hello world"), "en")

    def test_translate_uses_model(self):
        from orchestra.services.translation_service import TranslationService

        service = TranslationService(device="cpu")
        service._tokenizer = _FakeTokenizer()
        service._model = _FakeModel()
        result = service.translate("مرحبا", target_lang="en")
        self.assertEqual(result, "translated text")

    def test_translate_empty_returns_empty(self):
        from orchestra.services.translation_service import TranslationService

        self.assertEqual(TranslationService().translate("   ", "en"), "")

    def test_translate_unsupported_pair_raises(self):
        from orchestra.services.translation_service import TranslationService, TranslationServiceError

        service = TranslationService(device="cpu")
        service._tokenizer = _FakeTokenizer()
        service._model = _FakeModel()
        with self.assertRaises(TranslationServiceError):
            service.translate("hello", target_lang="klingon")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
