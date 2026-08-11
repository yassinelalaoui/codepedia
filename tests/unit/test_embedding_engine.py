from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from embedding_engine import (
    EmbeddingEngine,
    InvalidResponseError,
    ModelMissingError,
    ServiceUnavailableError,
    create_embedding_engine,
)


class _EmbeddingHandler(BaseHTTPRequestHandler):
    models = ("nomic-embed-text:latest",)
    malformed_embed_response = False
    version_status = 200
    tags_status = 200
    embed_status = 200
    vector = [0.1, 0.2, 0.3]

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
        if self.path != "/api/embed":
            self._write_json({"error": "not found"}, status=404)
            return
        length = int(self.headers.get("Content-Length", "0"))
        payload = json.loads(self.rfile.read(length).decode("utf-8")) if length else {}
        self.server.last_payload = payload  # type: ignore[attr-defined]
        if self.malformed_embed_response:
            body = b"not-json"
            self.send_response(self.embed_status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        self._write_json(
            {
                "model": payload.get("model", "nomic-embed-text"),
                "embeddings": [self.vector],
            },
            status=self.embed_status,
        )


def _start_server(handler=_EmbeddingHandler):
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server


def test_engine_reports_service_unavailable_when_endpoint_is_down():
    engine = create_embedding_engine("nomic-embed-text", "http://127.0.0.1:6553", timeout=0.2)

    assert engine.isAvailableLocally() is False
    with pytest.raises(ServiceUnavailableError):
        engine.embed("hello world")


def test_engine_reports_missing_model_without_generating():
    class MissingModelHandler(_EmbeddingHandler):
        models = ("another-model:latest",)

    server = _start_server(MissingModelHandler)
    try:
        endpoint = f"http://127.0.0.1:{server.server_port}"
        engine = create_embedding_engine("nomic-embed-text", endpoint, timeout=1.0)

        assert engine.isAvailableLocally() is False
        with pytest.raises(ModelMissingError):
            engine.embed("hello world")
    finally:
        server.shutdown()
        server.server_close()


def test_engine_generates_vectors_from_local_backend():
    server = _start_server(_EmbeddingHandler)
    try:
        endpoint = f"http://127.0.0.1:{server.server_port}"
        engine = create_embedding_engine("nomic-embed-text", endpoint, timeout=1.0)

        assert engine.isAvailableLocally() is True
        vector = engine.embed("classify this code")

        assert tuple(vector) == tuple(_EmbeddingHandler.vector)
        assert server.last_payload["model"] == "nomic-embed-text"
        assert server.last_payload["input"] == "classify this code"
    finally:
        server.shutdown()
        server.server_close()


def test_engine_raises_on_invalid_generate_response():
    class MalformedHandler(_EmbeddingHandler):
        malformed_embed_response = True

    server = _start_server(MalformedHandler)
    try:
        endpoint = f"http://127.0.0.1:{server.server_port}"
        engine = EmbeddingEngine("nomic-embed-text", endpoint, timeout=1.0)

        with pytest.raises(InvalidResponseError):
            engine.embed("hello world")
    finally:
        server.shutdown()
        server.server_close()
