from __future__ import annotations

import socket
import threading
import time

import httpx
import pytest
import uvicorn

from chat_api.security import TOKEN_HEADER

from ._chat_api_support import build_test_app


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


def test_server_accepts_on_loopback_but_refuses_on_lan_interface(tmp_path):
    app, index = build_test_app(tmp_path)
    running = _RunningServer(app)
    try:
        token = {TOKEN_HEADER: app.state.authToken}
        loopback_response = httpx.post(
            f"http://127.0.0.1:{running.port}/sessions", headers=token, timeout=5.0
        )
        assert loopback_response.status_code == 201

        lan_ip = _discover_local_lan_ip()
        if lan_ip is None:
            pytest.skip("no non-loopback network interface available to test refusal against")

        # A connection attempt to a non-loopback interface the server never bound to
        # must not succeed: depending on the platform/firewall it surfaces as either
        # an immediate refusal or a timeout waiting for a response, never a 2xx.
        with pytest.raises(httpx.TransportError):
            httpx.post(f"http://{lan_ip}:{running.port}/sessions", headers=token, timeout=2.0)
    finally:
        running.stop()
        index.close()
