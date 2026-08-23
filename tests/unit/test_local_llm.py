from __future__ import annotations

import asyncio
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import httpx
import pytest

from local_llm import (
    GenerationFailedError,
    GroqLLMEngine,
    InvalidResponseError,
    LocalLLMEngine,
    ModelMissingError,
    PromptEnvelope,
    ServiceUnavailableError,
    create_llm_engine,
    create_local_llm_engine,
)


class _OllamaHandler(BaseHTTPRequestHandler):
    models = ("llama3:latest", "qwen2.5-coder:latest")
    response_text = "Generated locally."
    malformed_generate_response = False
    version_status = 200
    tags_status = 200
    generate_status = 200

    def log_message(self, format, *args):  # pragma: no cover
        return

    def _write_json(self, payload, status=200):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/api/version":
            self._write_json({"version": "0.1.0"}, status=self.version_status)
        elif self.path == "/api/tags":
            self._write_json({"models": [{"name": name} for name in self.models]}, status=self.tags_status)
        else:
            self._write_json({"error": "not found"}, status=404)

    def do_POST(self):
        if self.path != "/api/generate":
            self._write_json({"error": "not found"}, status=404)
            return
        length = int(self.headers.get("Content-Length", "0"))
        payload = json.loads(self.rfile.read(length).decode("utf-8")) if length else {}
        self.server.last_payload = payload  # type: ignore[attr-defined]
        if self.malformed_generate_response:
            body = b"not-json"
            self.send_response(self.generate_status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        self._write_json(
            {
                "model": payload.get("model", "llama3"),
                "response": self.response_text,
                "done": True,
            },
            status=self.generate_status,
        )


def _start_server(handler=_OllamaHandler):
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server


def _write_chunk(wfile, payload: dict) -> None:
    body = (json.dumps(payload) + "\n").encode("utf-8")
    wfile.write(f"{len(body):x}\r\n".encode("ascii"))
    wfile.write(body)
    wfile.write(b"\r\n")


def _make_streaming_handler(trailing_count: int, *, chunk_delay: float = 0.05):
    """A handler class whose /api/generate response is chunked-transfer-encoded
    NDJSON: one "first" fragment immediately, then `trailing_count` more
    fragments each after `chunk_delay`, then a final done=true fragment."""

    class StreamingHandler(_OllamaHandler):
        def do_POST(self):
            if self.path != "/api/generate":
                super().do_POST()
                return
            length = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(length).decode("utf-8")) if length else {}
            self.server.last_payload = payload  # type: ignore[attr-defined]
            self.send_response(200)
            self.send_header("Content-Type", "application/x-ndjson")
            self.send_header("Transfer-Encoding", "chunked")
            self.end_headers()
            _write_chunk(self.wfile, {"model": payload.get("model", "llama3"), "response": "first", "done": False})
            for index in range(trailing_count):
                time.sleep(chunk_delay)
                _write_chunk(self.wfile, {"model": "llama3", "response": f" more{index}", "done": False})
            _write_chunk(self.wfile, {"model": "llama3", "response": "", "done": True})
            self.wfile.write(b"0\r\n\r\n")

    return StreamingHandler


def test_engine_reports_service_unavailable_when_endpoint_is_down():
    engine = create_local_llm_engine("llama3", "http://127.0.0.1:6553", timeout=0.2)

    assert engine.isAvailableLocally() is False
    with pytest.raises(ServiceUnavailableError):
        engine.generate("hello")


def test_engine_reports_missing_model_without_generating():
    class MissingModelHandler(_OllamaHandler):
        models = ("qwen2.5-coder:latest",)

    server = _start_server(MissingModelHandler)
    try:
        endpoint = f"http://127.0.0.1:{server.server_port}"
        engine = create_local_llm_engine("llama3", endpoint, timeout=1.0)

        assert engine.isAvailableLocally() is False
        with pytest.raises(ModelMissingError):
            engine.generate("hello")
    finally:
        server.shutdown()
        server.server_close()


def test_engine_generates_text_from_local_backend():
    server = _start_server(_OllamaHandler)
    try:
        endpoint = f"http://127.0.0.1:{server.server_port}"
        engine = create_local_llm_engine("llama3", endpoint, timeout=1.0)
        prompt = PromptEnvelope.from_prompt(
            "Summarize this code.",
            context=("def add(a, b): return a + b",),
            system_prompt="You are a helpful code assistant.",
        )

        assert engine.isAvailableLocally() is True
        text = engine.generate(prompt)

        assert text == "Generated locally."
        assert server.last_payload["model"] == "llama3"
        assert "System:" in server.last_payload["prompt"]
        assert "Context:" in server.last_payload["prompt"]
    finally:
        server.shutdown()
        server.server_close()


def test_engine_raises_generation_failed_on_timeout_not_a_raw_timeout_error():
    """Regression test: a local model that is reachable and installed but too
    slow to respond within the generation timeout used to raise a raw
    built-in TimeoutError out of `generate()` - uncaught by both `local_llm`
    and the CLI's `index`/`serve` commands, crashing with a raw traceback
    instead of report_and_exit's clean, actionable message. See the real
    `repo-scanner index` run against a large repository that first
    surfaced this."""

    class SlowGenerateHandler(_OllamaHandler):
        def do_POST(self):
            if self.path == "/api/generate":
                time.sleep(0.5)
            super().do_POST()

    server = _start_server(SlowGenerateHandler)
    try:
        endpoint = f"http://127.0.0.1:{server.server_port}"
        engine = create_local_llm_engine("llama3", endpoint, timeout=1.0, generate_timeout=0.1)

        assert engine.isAvailableLocally() is True  # reachable - not a service-down case
        with pytest.raises(GenerationFailedError, match="did not respond within"):
            engine.generate("hello")
    finally:
        server.shutdown()
        server.server_close()


def test_engine_raises_on_invalid_generate_response():
    class MalformedHandler(_OllamaHandler):
        malformed_generate_response = True

    server = _start_server(MalformedHandler)
    try:
        endpoint = f"http://127.0.0.1:{server.server_port}"
        engine = create_local_llm_engine("llama3", endpoint, timeout=1.0)

        with pytest.raises(InvalidResponseError):
            engine.generate("hello")
    finally:
        server.shutdown()
        server.server_close()


def test_generate_stream_yields_fragments_in_order_and_generate_joins_them():
    server = _start_server(_make_streaming_handler(trailing_count=2, chunk_delay=0.01))
    try:
        endpoint = f"http://127.0.0.1:{server.server_port}"
        engine = create_local_llm_engine("llama3", endpoint, timeout=1.0, generate_timeout=2.0)

        async def _collect():
            return [fragment async for fragment in engine.generateStream("hello")]

        fragments = asyncio.run(_collect())
        assert fragments == ["first", " more0", " more1"]
        assert "".join(fragments) == engine.generate("hello")
    finally:
        server.shutdown()
        server.server_close()


def test_first_fragment_delay_does_not_grow_with_how_many_more_fragments_follow():
    """Structural check for SC-002: the delay to the first streamed fragment
    stays flat whether one or several more fragments will follow it - unlike
    a blocking call, where the caller sees nothing until every fragment has
    arrived."""

    async def _first_fragment_delay(trailing_count: int) -> float:
        server = _start_server(_make_streaming_handler(trailing_count, chunk_delay=0.05))
        try:
            endpoint = f"http://127.0.0.1:{server.server_port}"
            engine = create_local_llm_engine("llama3", endpoint, timeout=1.0, generate_timeout=5.0)
            start = time.monotonic()
            async for _fragment in engine.generateStream("hello"):
                return time.monotonic() - start
            raise AssertionError("expected at least one fragment")
        finally:
            server.shutdown()
            server.server_close()

    short_delay = asyncio.run(_first_fragment_delay(1))
    long_delay = asyncio.run(_first_fragment_delay(8))

    # Generous bound - the point is "doesn't scale with how many fragments
    # follow," not a tight timing assertion that would make this test flaky.
    assert long_delay < short_delay + 0.2


def test_create_llm_engine_builds_exactly_one_engine_per_provider():
    local_engine = create_llm_engine("local", "llama3", "http://127.0.0.1:6553")
    assert isinstance(local_engine, LocalLLMEngine)

    groq_engine = create_llm_engine("groq", "llama-3.3-70b-versatile")
    assert isinstance(groq_engine, GroqLLMEngine)

    # Never a composite/fallback engine, never chosen automatically -
    # requesting one provider never returns (or silently touches) the other.
    assert not isinstance(local_engine, GroqLLMEngine)
    assert not isinstance(groq_engine, LocalLLMEngine)

    with pytest.raises(ValueError):
        create_llm_engine("something-else", "llama3")


def test_create_llm_engine_never_consults_the_other_provider_when_one_is_unavailable(monkeypatch):
    from local_llm.groq_transport import API_KEY_ENV_VAR

    monkeypatch.delenv(API_KEY_ENV_VAR, raising=False)
    groq_engine = create_llm_engine("groq", "llama-3.3-70b-versatile")

    # The local engine is never configured/reachable in this test at all -
    # if create_llm_engine or the engine itself ever fell back to it, this
    # would either error differently or hang; instead it must fail exactly
    # as an unavailable Groq engine would, on its own.
    assert groq_engine.isAvailableLocally() is False
    status = groq_engine.checkAvailability()
    assert "GROQ_API_KEY" in status.message


def test_generate_stream_never_targets_a_host_other_than_the_configured_endpoint(monkeypatch):
    # A real local server answers the availability probe (/api/version,
    # /api/tags - urllib-based, unaffected by the httpx mock below) so the
    # streaming call itself is what gets reached and intercepted.
    server = _start_server(_OllamaHandler)
    try:
        endpoint = f"http://127.0.0.1:{server.server_port}"
        calls: list[str] = []

        def _recording_stream(self, method, url, **kwargs):
            calls.append(str(url))
            raise httpx.ConnectError("simulated - this stub never actually connects")

        monkeypatch.setattr(httpx.AsyncClient, "stream", _recording_stream)

        engine = create_local_llm_engine("llama3", endpoint, timeout=1.0, generate_timeout=1.0)

        async def _consume():
            with pytest.raises(GenerationFailedError):
                async for _fragment in engine.generateStream("hello"):
                    pass

        asyncio.run(_consume())
        assert calls == [f"{endpoint}/api/generate"]
    finally:
        server.shutdown()
        server.server_close()
