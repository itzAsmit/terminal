"""Ghost proxy + static server — the hosting backend for the web séance.

Run with ``seance serve`` (or ``python -m seance.webproxy``); designed for
Render's free web-service tier but works anywhere:

    GET  /api/ghost/health -> {"live": bool, "model": str}   (never the key)
    POST /api/ghost        {"cmd","exit","dur","tier","label"}
                           -> {"content": str | null}
    everything else        -> the plain files in site/

The key lives ONLY in the OPENROUTER_API_KEY environment variable on the
host (Render dashboard, local shell). It is never sent to the browser, which
makes this the privacy-correct way to host: visitors bring no key and can
never read yours. The 429/5xx cooldown from the CLI applies server-side, so
a misbehaving internet cannot hammer the upstream either.

Pure standard library — no install-time dependencies.
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from . import config, ghost


def _find_site_dir() -> Path:
    """site/ next to the working directory (repo checkout, Render's
    ``pip install .`` runs from the repo root) or beside the package in a
    dev tree. Override with SEANCE_SITE_DIR."""
    env = os.environ.get("SEANCE_SITE_DIR", "").strip()
    if env:
        return Path(env)
    cwd = Path.cwd() / "site"
    if (cwd / "index.html").exists():
        return cwd
    return Path(__file__).resolve().parents[2] / "site"


SITE_DIR = _find_site_dir()

TIMEOUT = 2.5  # the 2-second law, hosting edition
COOLDOWN = 120.0
MAX_BODY = 4096
MAX_CMD = 500
TIERS = {"dangerous", "failed", "long", "boring", "chat"}

_state = {"cooldown_until": 0.0, "upstream_hits": 0}


def base_url() -> str:
    return os.environ.get("SEANCE_BASE_URL", "").strip() or config.DEFAULT_BASE_URL


def model() -> str:
    return os.environ.get("SEANCE_MODEL", "").strip() or config.DEFAULT_MODEL


def key_present() -> bool:
    return bool(os.environ.get("OPENROUTER_API_KEY", "").strip())


def ask_upstream(context: str) -> str | None:
    """One upstream attempt, hard-capped. Returns trimmed text or None.
    Mirrors ghost.ask_ghost, but the key never leaves this process."""
    key = os.environ.get("OPENROUTER_API_KEY", "").strip()
    if not key:
        return None
    if time.time() < _state["cooldown_until"]:
        return None
    _state["upstream_hits"] += 1
    url = base_url().rstrip("/") + "/chat/completions"
    req = urllib.request.Request(
        url,
        data=json.dumps({
            "model": model(),
            "temperature": 0.9,
            "max_tokens": 90,
            "messages": [
                {"role": "system", "content": config.DEFAULT_SYSTEM_PROMPT},
                {"role": "user", "content": context},
            ],
        }).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {key}",
            "HTTP-Referer": "https://terminal-seance",
            "X-Title": "terminal-seance-web",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        text = data["choices"][0]["message"]["content"]
        return ghost.trim_reply(text) if isinstance(text, str) else None
    except urllib.error.HTTPError as e:
        if e.code in (429, 500, 502, 503):
            _state["cooldown_until"] = time.time() + COOLDOWN
        return None
    except Exception:
        return None


class Handler(SimpleHTTPRequestHandler):
    server_version = "terminal-seance"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(SITE_DIR), **kwargs)

    def log_message(self, fmt, *args):  # keep host logs quiet-ish
        line = str(fmt) + " " + " ".join(str(a) for a in args)
        if "/api/ghost" in line:
            return
        super().log_message(fmt, *args)

    def _json(self, code: int, obj: dict) -> None:
        body = json.dumps(obj).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = self.path.split("?")[0]
        if path == "/api/ghost/health":
            return self._json(200, {"live": key_present(), "model": model()})
        if path == "/config.js" and not (SITE_DIR / "config.js").exists():
            # no build-time injection on this host — the proxy holds the key
            body = b"window.SEANCE_WEB_CFG = null;\n"
            self.send_response(200)
            self.send_header("Content-Type", "application/javascript")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            return self.wfile.write(body)
        super().do_GET()

    def do_POST(self):
        path = self.path.split("?")[0]
        if path != "/api/ghost":
            return self._json(404, {"error": "not found"})
        try:
            n = int(self.headers.get("Content-Length", "0") or 0)
        except ValueError:
            n = 0
        if n <= 0 or n > MAX_BODY:
            return self._json(400, {"content": None})
        try:
            req = json.loads(self.rfile.read(n).decode("utf-8"))
        except Exception:
            return self._json(400, {"content": None})
        if not isinstance(req, dict):
            return self._json(400, {"content": None})

        cmd = str(req.get("cmd", ""))[:MAX_CMD].strip()
        try:
            exit_code = int(req.get("exit", 0))
        except (TypeError, ValueError):
            exit_code = 0
        raw_dur = req.get("dur")
        try:
            dur = float(raw_dur) if raw_dur is not None else None
        except (TypeError, ValueError):
            dur = None
        tier = req.get("tier") if req.get("tier") in TIERS else "boring"
        label = str(req.get("label") or "").strip() or None

        if not cmd:
            return self._json(200, {"content": None})
        if tier == "chat":
            # speech, not a shell command — a conversational context instead
            # of the command-reaction one
            context = (
                f'the living one is speaking to you — this is not a shell command. '
                f'they said: "{cmd}"\n'
                "(answer in character as Agnes: ONE short sentence or two, dry "
                "Victorian wit, occasional Spanish)"
            )
        else:
            context = ghost.build_context(cmd, exit_code, dur, ghost.Tier(tier), label)
        return self._json(200, {"content": ask_upstream(context)})


def main(port: int | None = None) -> int:
    port = port or int(os.environ.get("PORT", "8080") or 8080)
    httpd = ThreadingHTTPServer(("0.0.0.0", port), Handler)
    print(
        f"† the séance is open on http://0.0.0.0:{port} — "
        f"live: {key_present()} · model: {model()}",
        flush=True,
    )
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
