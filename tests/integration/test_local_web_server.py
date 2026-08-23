from __future__ import annotations

import re
import socket
import threading
import time
from pathlib import Path

import httpx
import pytest
import uvicorn
from fastapi.testclient import TestClient

from doc_generator import DocGenerator, open_doc_manifest_store

from ._chat_api_support import build_test_app, parse_sse_events
from ._doc_generator_support import build_indexed_repo


def _build_wiki(tmp_path: Path):
    root, store, graph = build_indexed_repo(tmp_path)
    docs_root = tmp_path / "docs"
    manifest_store = open_doc_manifest_store(tmp_path / "doc-manifest.sqlite")
    generator = DocGenerator(
        metadataStore=store,
        dependencyGraph=graph,
        manifestStore=manifest_store,
        outputRoot=docs_root,
        repositoryRoot=root,
    )
    doc_set = generator.generateRepositoryDocumentation(root, incremental=False)
    return docs_root, doc_set


def test_wiki_home_and_module_pages_serve_through_the_server(tmp_path):
    docs_root, doc_set = _build_wiki(tmp_path)
    app, index = build_test_app(tmp_path, docs_root=docs_root)
    client = TestClient(app)

    home_response = client.get("/")

    module_page = next(page for page in doc_set.pages if page.kind == "module")
    module_response = client.get(f"/{module_page.outputPathHtml}")
    index.close()

    assert home_response.status_code == 200
    assert module_response.status_code == 200
    assert module_page.title in module_response.text

    link_hrefs = re.findall(r'href="([^"]+\.html)"', home_response.text)
    assert link_hrefs, "expected at least one in-wiki link on the home page"
    followed_response = client.get(f"/{link_hrefs[0]}")
    assert followed_response.status_code == 200


def test_diagram_page_and_static_asset_serve_through_the_server(tmp_path):
    docs_root, doc_set = _build_wiki(tmp_path)
    app, index = build_test_app(tmp_path, docs_root=docs_root)
    client = TestClient(app)

    diagram_page = next(page for page in doc_set.pages if page.kind == "diagram")
    diagram_response = client.get(f"/{diagram_page.outputPathHtml}")
    asset_response = client.get("/assets/mermaid.min.js")
    index.close()

    assert diagram_response.status_code == 200
    assert diagram_page.title in diagram_response.text
    assert asset_response.status_code == 200
    assert len(asset_response.content) > 0


def test_missing_wiki_page_returns_404(tmp_path):
    docs_root, _ = _build_wiki(tmp_path)
    app, index = build_test_app(tmp_path, docs_root=docs_root)
    client = TestClient(app)

    response = client.get("/modules/does-not-exist.html")
    index.close()

    assert response.status_code == 404


def test_chat_api_still_works_alongside_the_wiki_mount(tmp_path):
    docs_root, _ = _build_wiki(tmp_path)
    app, index = build_test_app(tmp_path, docs_root=docs_root)
    client = TestClient(app)

    session_id = client.post("/sessions").json()["sessionId"]
    ask_response = client.post(
        f"/sessions/{session_id}/messages",
        json={"question": "where is authentication handled?"},
    )
    history_response = client.get(f"/sessions/{session_id}/messages")
    index.close()

    assert ask_response.status_code == 200
    events = parse_sse_events(ask_response.text)
    _final_name, body = events[-1]
    assert "citedSymbolIds" in body and "citedFilePaths" in body
    assert history_response.status_code == 200
    assert len(history_response.json()["messages"]) == 2


def _discover_local_lan_ip() -> str | None:
    """Best-effort discovery of this machine's LAN-facing IP address.

    Uses a UDP "connect" (a local routing-table lookup; no packet is sent on
    the wire) so it works even without real internet connectivity. Returns
    None if no non-loopback route can be determined.
    """
    probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        probe.connect(("8.8.8.8", 80))
        local_ip = probe.getsockname()[0]
    except OSError:
        return None
    finally:
        probe.close()
    if local_ip.startswith("127."):
        return None
    return local_ip


class _RunningServer:
    def __init__(self, app) -> None:
        listen_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        listen_socket.bind(("127.0.0.1", 0))
        listen_socket.listen()
        self.port = listen_socket.getsockname()[1]

        config = uvicorn.Config(app, host="127.0.0.1", log_level="critical")
        self.server = uvicorn.Server(config)
        self._thread = threading.Thread(target=self.server.run, kwargs={"sockets": [listen_socket]}, daemon=True)
        self._thread.start()

        deadline = time.monotonic() + 5.0
        while not self.server.started and time.monotonic() < deadline:
            time.sleep(0.05)
        if not self.server.started:
            raise RuntimeError("uvicorn server did not start within the timeout")

    def stop(self) -> None:
        self.server.should_exit = True
        self._thread.join(timeout=5.0)


def test_combined_server_accepts_on_loopback_but_refuses_on_lan_interface(tmp_path):
    docs_root, _ = _build_wiki(tmp_path)
    app, index = build_test_app(tmp_path, docs_root=docs_root)
    running = _RunningServer(app)
    try:
        home_response = httpx.get(f"http://127.0.0.1:{running.port}/", timeout=5.0)
        session_response = httpx.post(f"http://127.0.0.1:{running.port}/sessions", timeout=5.0)
        assert home_response.status_code == 200
        assert session_response.status_code == 201

        lan_ip = _discover_local_lan_ip()
        if lan_ip is None:
            pytest.skip("no non-loopback network interface available to test refusal against")

        with pytest.raises(httpx.TransportError):
            httpx.get(f"http://{lan_ip}:{running.port}/", timeout=2.0)
    finally:
        running.stop()
        index.close()


def test_server_starts_and_chat_api_works_before_wiki_is_generated(tmp_path):
    docs_root = tmp_path / "docs-not-generated-yet"
    app, index = build_test_app(tmp_path, docs_root=docs_root)
    client = TestClient(app)

    home_response = client.get("/")
    session_response = client.post("/sessions")
    index.close()

    assert home_response.status_code == 404
    assert session_response.status_code == 201
