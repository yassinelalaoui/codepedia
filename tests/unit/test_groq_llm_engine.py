from __future__ import annotations

import asyncio
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from local_llm import GroqLLMEngine, MissingApiKeyError, RateLimitedError, RemoteServiceUnavailableError, create_groq_llm_engine
from local_llm.groq_transport import API_KEY_ENV_VAR


class _GroqHandler(BaseHTTPRequestHandler):
    models = ("llama-3.3-70b-versatile",)
    require_key = "test-key"
    chunks = ("Hello", " from Groq.")

    def log_message(self, format, *args):  # pragma: no cover
        return

    def _authorized(self) -> bool:
        return self.headers.get("Authorization") == f"Bearer {self.require_key}"

    def _write_json(self, payload, status=200):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path != "/models":
            self._write_json({"error": "not found"}, status=404)
            return
        if not self._authorized():
            self._write_json({"error": "invalid api key"}, status=401)
            return
        self._write_json({"data": [{"id": name} for name in self.models]})

    def do_POST(self):
        if self.path != "/chat/completions":
            self._write_json({"error": "not found"}, status=404)
            return
        if not self._authorized():
            self._write_json({"error": "invalid api key"}, status=401)
            return
        length = int(self.headers.get("Content-Length", "0"))
        self.rfile.read(length) if length else b""
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Transfer-Encoding", "chunked")
        self.end_headers()
        for fragment in self.chunks:
            chunk = {"choices": [{"delta": {"content": fragment}}]}
            body = (f"data: {json.dumps(chunk)}\n\n").encode("utf-8")
            self.wfile.write(f"{len(body):x}\r\n".encode("ascii"))
            self.wfile.write(body)
            self.wfile.write(b"\r\n")
        done = b"data: [DONE]\n\n"
        self.wfile.write(f"{len(done):x}\r\n".encode("ascii"))
        self.wfile.write(done)
        self.wfile.write(b"\r\n")
        self.wfile.write(b"0\r\n\r\n")


class _RateLimitedHandler(_GroqHandler):
    def do_GET(self):
        if self.path != "/models":
            self._write_json({"error": "not found"}, status=404)
            return
        self._write_json({"error": "rate limited"}, status=429)

    def do_POST(self):
        if self.path != "/chat/completions":
            self._write_json({"error": "not found"}, status=404)
            return
        self._write_json({"error": "rate limited"}, status=429)


def _start_server(handler=_GroqHandler):
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server


def test_generate_stream_yields_fragments_parsed_from_groq_sse(monkeypatch):
    monkeypatch.setenv(API_KEY_ENV_VAR, "test-key")
    server = _start_server()
    try:
        endpoint = f"http://127.0.0.1:{server.server_port}"
        engine = create_groq_llm_engine("llama-3.3-70b-versatile", endpoint, timeout=1.0, generate_timeout=2.0)

        async def _collect():
            return [fragment async for fragment in engine.generateStream("hello")]

        fragments = asyncio.run(_collect())
        assert fragments == ["Hello", " from Groq."]
        assert engine.generate("hello") == "Hello from Groq."
    finally:
        server.shutdown()
        server.server_close()


def test_check_availability_reports_missing_api_key_clearly(monkeypatch):
    monkeypatch.delenv(API_KEY_ENV_VAR, raising=False)
    engine = create_groq_llm_engine("llama-3.3-70b-versatile", "http://127.0.0.1:6553")

    status = engine.checkAvailability()

    assert status.available is False
    assert API_KEY_ENV_VAR in status.message
    with pytest.raises(MissingApiKeyError):
        engine.generate("hello")


def test_check_availability_reports_unreachable_endpoint_clearly(monkeypatch):
    monkeypatch.setenv(API_KEY_ENV_VAR, "test-key")
    engine = create_groq_llm_engine("llama-3.3-70b-versatile", "http://127.0.0.1:6553", timeout=0.2)

    status = engine.checkAvailability()

    assert status.available is False
    assert status.serviceReachable is False
    with pytest.raises(RemoteServiceUnavailableError):
        engine.generate("hello")


def test_availability_and_generate_stream_classify_http_429_as_rate_limited(monkeypatch):
    monkeypatch.setenv(API_KEY_ENV_VAR, "test-key")
    server = _start_server(_RateLimitedHandler)
    try:
        endpoint = f"http://127.0.0.1:{server.server_port}"
        engine = create_groq_llm_engine("llama-3.3-70b-versatile", endpoint, timeout=1.0, generate_timeout=2.0)

        status = engine.checkAvailability()
        assert status.available is False
        assert status.rateLimited is True

        with pytest.raises(RateLimitedError):
            engine.generate("hello")
    finally:
        server.shutdown()
        server.server_close()


def test_transport_generate_stream_classifies_http_429_directly(monkeypatch):
    """Exercises `GroqLLMTransport.generate_stream`'s own 429 branch
    directly, bypassing `GroqLLMEngine.checkAvailability`'s upfront guard so
    the transport-level classification (not just the availability-probe
    one) is covered independently."""
    from local_llm.groq_transport import GroqLLMTransport
    from local_llm.models import PromptEnvelope

    monkeypatch.setenv(API_KEY_ENV_VAR, "test-key")
    server = _start_server(_RateLimitedHandler)
    try:
        endpoint = f"http://127.0.0.1:{server.server_port}"
        transport = GroqLLMTransport(endpoint, timeout=1.0, generateTimeout=2.0)

        async def _drain():
            return [
                fragment
                async for fragment in transport.generate_stream(
                    "llama-3.3-70b-versatile", PromptEnvelope.from_prompt("hello")
                )
            ]

        with pytest.raises(RateLimitedError):
            asyncio.run(_drain())
    finally:
        server.shutdown()
        server.server_close()


def test_check_availability_rejects_an_invalid_api_key(monkeypatch):
    monkeypatch.setenv(API_KEY_ENV_VAR, "wrong-key")
    server = _start_server()
    try:
        endpoint = f"http://127.0.0.1:{server.server_port}"
        engine = create_groq_llm_engine("llama-3.3-70b-versatile", endpoint, timeout=1.0)

        status = engine.checkAvailability()

        assert status.available is False
        assert status.serviceReachable is True
    finally:
        server.shutdown()
        server.server_close()
