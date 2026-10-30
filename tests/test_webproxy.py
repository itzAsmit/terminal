"""Tests for the key-safe ghost proxy (seance serve / webproxy)."""

import json
import threading
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from seance import webproxy


class Upstream(BaseHTTPRequestHandler):
    """A pretend OpenRouter: configurable status/content/delay."""
    behavior = {"status": 200, "content": "Upstream sentence one. Upstream sentence two. Three four.", "delay": 0.0}
    hits = 0
    seen = {}

    def log_message(self, *a):
        pass

    def do_POST(self):
        type(self).hits += 1
        n = int(self.headers.get("Content-Length", "0") or 0)
        type(self).seen["auth"] = self.headers.get("Authorization")
        type(self).seen["model"] = json.loads(self.rfile.read(n)).get("model")
        if self.behavior["delay"]:
            time.sleep(self.behavior["delay"])
        if self.behavior["status"] != 200:
            self.send_response(self.behavior["status"])
            self.send_header("Content-Length", "2")
            self.end_headers()
            self.wfile.write(b"{}")
            return
        body = json.dumps({"choices": [{"message": {"content": self.behavior["content"]}}]}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


@pytest.fixture
def proxy(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.setenv("SEANCE_MODEL", "google/gemma-3-27b-it:free")
    up = ThreadingHTTPServer(("127.0.0.1", 0), Upstream)
    threading.Thread(target=up.serve_forever, daemon=True).start()
    monkeypatch.setenv("SEANCE_BASE_URL", f"http://127.0.0.1:{up.server_port}/v1")

    webproxy._state["cooldown_until"] = 0.0
    webproxy._state["upstream_hits"] = 0
    Upstream.hits = 0

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), webproxy.Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    try:
        yield f"http://127.0.0.1:{httpd.server_port}", Upstream
    finally:
        httpd.shutdown()
        up.shutdown()


def _get(base, path):
    with urllib.request.urlopen(base + path, timeout=5) as r:
        return r.status, json.loads(r.read().decode())


def _post(base, path, payload):
    req = urllib.request.Request(
        base + path, data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"}, method="POST",
    )
    with urllib.request.urlopen(req, timeout=5) as r:
        return r.status, json.loads(r.read().decode())


def test_health_reports_live_and_model(proxy):
    base, _ = proxy
    status, data = _get(base, "/api/ghost/health")
    assert status == 200
    assert data["live"] is True
    assert data["model"] == "google/gemma-3-27b-it:free"
    assert "test-key" not in json.dumps(data)  # the key never leaves the process


def test_health_without_key_is_not_live(proxy, monkeypatch):
    base, _ = proxy
    monkeypatch.delenv("OPENROUTER_API_KEY")
    _, data = _get(base, "/api/ghost/health")
    assert data["live"] is False


def test_proxy_returns_trimmed_upstream_reply(proxy):
    base, up = proxy
    status, data = _post(base, "/api/ghost",
                         {"cmd": "pytest tests/ -q", "exit": 1, "dur": 0.42, "tier": "failed"})
    assert status == 200
    assert data["content"] == "Upstream sentence one. Upstream sentence two."
    assert up.seen["auth"] == "Bearer test-key"
    assert up.seen["model"] == "google/gemma-3-27b-it:free"


def test_429_sets_server_side_cooldown(proxy):
    base, up = proxy
    Upstream.behavior["status"] = 429
    _, first = _post(base, "/api/ghost", {"cmd": "ls", "exit": 0, "tier": "boring"})
    _, second = _post(base, "/api/ghost", {"cmd": "ls", "exit": 0, "tier": "boring"})
    assert first["content"] is None and second["content"] is None
    assert up.hits == 1  # the second ask never reached the upstream


def test_upstream_timeout_returns_null(proxy, monkeypatch):
    base, _ = proxy
    monkeypatch.setattr(webproxy, "TIMEOUT", 0.2)
    Upstream.behavior["delay"] = 0.6
    _, data = _post(base, "/api/ghost", {"cmd": "ls", "exit": 0, "tier": "boring"})
    assert data["content"] is None


def test_malformed_body_is_400(proxy):
    base, _ = proxy
    with pytest.raises(urllib.error.HTTPError) as e:
        req = urllib.request.Request(base + "/api/ghost", data=b"not json{",
                                     headers={"Content-Type": "application/json"}, method="POST")
        urllib.request.urlopen(req, timeout=5)
    assert e.value.code == 400


def test_empty_cmd_returns_null_content(proxy):
    base, _ = proxy
    _, data = _post(base, "/api/ghost", {"cmd": "   ", "exit": 0, "tier": "boring"})
    assert data["content"] is None


def test_unknown_post_path_is_404(proxy):
    base, _ = proxy
    with pytest.raises(urllib.error.HTTPError) as e:
        _post(base, "/api/other", {"cmd": "ls"})
    assert e.value.code == 404


def test_serves_static_site(proxy):
    base, _ = proxy
    with urllib.request.urlopen(base + "/", timeout=5) as r:
        html = r.read().decode("utf-8")
    assert "terminal-seance" in html


def test_config_js_stub_when_no_injected_file(tmp_path, monkeypatch):
    """On the proxy host there is no build-time config.js — serve a stub so
    the page has no 404 and no injected-key confusion."""
    (tmp_path / "index.html").write_text("hello", encoding="utf-8")
    monkeypatch.setattr(webproxy, "SITE_DIR", tmp_path)
    monkeypatch.setenv("OPENROUTER_API_KEY", "")  # no key either
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), webproxy.Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{httpd.server_port}/config.js", timeout=5) as r:
            body = r.read().decode()
        assert "SEANCE_WEB_CFG" in body
    finally:
        httpd.shutdown()
