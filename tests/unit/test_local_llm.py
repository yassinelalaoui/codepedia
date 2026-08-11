from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from local_llm import (
    InvalidResponseError,
    LocalLLMEngine,
    ModelMissingError,
    PromptEnvelope,
    ServiceUnavailableError,
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
