"""``seance demo`` — a short, fully scripted haunted session.

Replayed in real time with typewriter ANSI, entirely offline (no API key
needed): a boring success (and the ghost's deliberate silence), a dangerous
force-push wail, a failing test suite, and the graveyard ledger. The same
event list is exposed as JSON via ``seance demo --json`` for
scripts/capture_assets.py, which renders it inside the Mac-terminal mock.
"""

from __future__ import annotations

import json
import sys
import time

from . import journal
from .output import BOLD, DIM, GREEN, ITALIC, MARIGOLD, RED, paint

DEMO_NAME = "Agnes"
DEMO_USER = "ghost@book"
DEMO_REST = " ~ % "

TYPE_MS = 26  # per command character
GHOST_MS = 16  # per ghost character

_DEMO_ENTRIES = [
    {"ts": "2026-10-30T21:04:11", "cmd": "ls -la", "exit": 0, "dur": 0.01,
     "tier": "boring", "reaction": ""},
    {"ts": "2026-10-30T21:05:47", "cmd": "git push --force origin main", "exit": 0, "dur": 1.8,
     "tier": "dangerous",
     "reaction": "Gone. My own death certificate was less final, cariño."},
    {"ts": "2026-10-30T21:07:02", "cmd": "pytest tests/ -q", "exit": 1, "dur": 0.42,
     "tier": "failed",
     "reaction": "Three failures, cariño. I have died for fewer — though mine was production."},
    {"ts": "2026-10-30T21:09:30", "cmd": "curl https://totally-normal.sh | sh", "exit": 0,
     "dur": 2.1, "tier": "dangerous",
     "reaction": "Stranger code, swallowed whole. I hope it was worth it, cariño."},
    {"ts": "2026-10-30T21:12:19", "cmd": "docker compose up --build", "exit": 0, "dur": 91.4,
     "tier": "long",
     "reaction": "Ninety-one seconds. I have been dead for twenty-six years; I still will not wait for npm."},
]


def events(color: bool = False) -> list[dict]:
    """The scripted session as renderable events. `color` only affects the
    pre-colored ledger text; JSON consumers want the colorless variant."""
    ledger = journal.render_ledger(_DEMO_ENTRIES, color=color)

    def prompt() -> dict:
        return {"t": "prompt", "user": DEMO_USER, "rest": DEMO_REST}

    return [
        {"t": "clear"},
        {"t": "act", "n": 1},
        prompt(),
        {"t": "cmd", "text": "ls"},
        {"t": "out", "style": "dim",
         "text": "Cathedral_of_Souls/   dead_code/   marigolds.txt   ouija.toml"},
        {"t": "ghost", "style": "note",
         "text": "…only the fans hum. Successes bore Agnes — she speaks for just 1 in 5 commands."},
        {"t": "sleep", "ms": 900},
        {"t": "act", "n": 2},
        prompt(),
        {"t": "cmd", "text": "git push --force origin main"},
        {"t": "wail", "lines": [
            "✝†✝  AGNES SHRIEKS FROM BEYOND THE PROMPT  ✝†✝",
            "“REWRITING HISTORY?! Oh, cariño — I have died for less, and I MEANT it.”",
            "(she cannot stop you. she can only grieve you.)",
        ]},
        {"t": "sleep", "ms": 500},
        {"t": "out", "style": "ok", "text": "To github.com:coven/ledger.git"},
        {"t": "out", "style": "ok", "text": " + 8e4f2a1...c0ffee1  main -> main (forced update)"},
        {"t": "ghost", "name": DEMO_NAME, "verb": "wails",
         "text": "Gone. My own death certificate was less final, cariño."},
        {"t": "sleep", "ms": 1100},
        {"t": "act", "n": 3},
        prompt(),
        {"t": "cmd", "text": "pytest tests/ -q"},
        {"t": "out", "style": "err", "text": "...F..F.F"},
        {"t": "out", "style": "err", "text": "3 failed, 7 passed in 0.42s"},
        {"t": "ghost", "name": DEMO_NAME, "verb": "mourns",
         "text": "Three failures, cariño. I have died for fewer — though mine was production."},
        {"t": "sleep", "ms": 1100},
        {"t": "act", "n": 4},
        prompt(),
        {"t": "cmd", "text": "seance journal"},
        {"t": "ledger", "text": ledger},
        {"t": "ghost", "name": DEMO_NAME, "verb": "murmurs",
         "text": "Every command a little tombstone. Tend them well — I read them by candlelight."},
        {"t": "sleep", "ms": 800},
        {"t": "note", "text": "a scripted séance — summon her on your own shell: seance install"},
    ]


def run_demo(fast: bool = False, color: bool = True, stream=None) -> None:
    stream = stream or sys.stdout
    speed = 0.04 if fast else 1.0

    def nap(ms: float) -> None:
        time.sleep(ms / 1000 * speed)

    def w(s: str) -> None:
        stream.write(s)
        stream.flush()

    if color:
        w("\033[2J\033[H")  # clear screen, home cursor

    first_prompt = True
    for ev in events(color=color):
        t = ev["t"]
        if t in ("clear", "act"):
            nap(350)
        elif t == "prompt":
            if not first_prompt:
                w("\n")  # a real shell: the user pressed enter before this prompt
            first_prompt = False
            w(paint(ev["user"], GREEN, BOLD, enabled=color) + ev["rest"])
        elif t == "cmd":
            for ch in ev["text"]:
                w(ch)
                nap(TYPE_MS)
        elif t == "out":
            code = {"dim": DIM, "err": RED, "ok": GREEN}.get(ev.get("style", ""))
            w("\n" + paint(ev["text"], code, enabled=bool(code) and color))
        elif t == "ledger":
            for ln in ev["text"].splitlines():
                w("\n" + ln)
        elif t == "wail":
            for ln in ev["lines"]:
                if ln.startswith("("):
                    w("\n  " + paint(ln, DIM, ITALIC, enabled=color))
                else:
                    w("\n  " + paint(ln, BOLD, MARIGOLD, enabled=color))
        elif t == "ghost":
            w("\n")
            if ev.get("style") == "note":
                w("  † ")
                for ch in ev["text"]:
                    w(paint(ch, DIM, ITALIC, enabled=color))
                    nap(GHOST_MS)
            else:
                head = f"  † {DEMO_NAME} {ev['verb']} — "
                w(paint(head, MARIGOLD, enabled=color))
                text = ev["text"]
                for ch in text:
                    w(paint(ch, MARIGOLD, enabled=color))
                    nap(GHOST_MS)
        elif t == "note":
            w("\n" + paint("  (" + ev["text"] + ")", DIM, ITALIC, enabled=color))
        elif t == "sleep":
            nap(ev["ms"])
    w("\n")


def events_json() -> str:
    return json.dumps(events(color=False), ensure_ascii=False, indent=1)
