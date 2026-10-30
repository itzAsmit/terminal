"""The haunted history: ``~/.config/terminal-seance/journal.log``

One JSON object per line::

    {"ts": "...", "cmd": "...", "exit": 0, "dur": 0.42,
     "tier": "dangerous", "reaction": "..."}

Every command is recorded; ``reaction`` is empty when the ghost kept silent.
Only command *text* is ever journaled — never command output.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from . import config
from .output import DIM, GREEN, MARIGOLD, RED, paint

WIDTH = 88  # ledger line width
CMD_W = 33
NOTE_W = WIDTH - 61  # frame cells: 2+3+2+11+2+33+2+4+2 = 61


def append(entry: dict[str, Any], path: Path | None = None) -> None:
    p = path or config.journal_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def read_all(path: Path | None = None) -> list[dict[str, Any]]:
    p = path or config.journal_path()
    if not p.is_file():
        return []
    entries: list[dict[str, Any]] = []
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            entries.append(json.loads(line))
        except json.JSONDecodeError:
            continue  # a torn line is skipped, never fatal
    return entries


def commands_since_last_reaction(path: Path | None = None) -> int:
    """How many commands have passed since the ghost last spoke (0 = just now)."""
    n = 0
    for e in reversed(read_all(path)):
        if e.get("reaction"):
            return n
        n += 1
    return n


def entry_at(row: int, path: Path | None = None) -> dict[str, Any] | None:
    """1-based row, oldest first — the same numbering the ledger prints."""
    entries = read_all(path)
    if 1 <= row <= len(entries):
        return entries[row - 1]
    return None


def _ell(s: str, n: int) -> str:
    s = s.strip()
    return s if len(s) <= n else s[: n - 1].rstrip() + "…"


def _fmt_ts(ts: Any) -> str:
    try:
        return datetime.fromisoformat(str(ts)).strftime("%m-%d %H:%M")
    except (ValueError, TypeError):
        return "?"


def render_ledger(
    entries: list[dict[str, Any]],
    color: bool = True,
    width: int = WIDTH,
    start_index: int = 1,
) -> str:
    if not entries:
        return (
            "  The graveyard is silent — no commands recorded yet.\n"
            "  Run something, cariño. The ledger is waiting."
        )
    title = "T H E   G R A V E Y A R D   L E D G E R"
    pad = max(1, (width - len(title)) // 2 - 6)
    lines = [
        "    " + "∙" * pad + "  " + title + "  " + "∙" * pad,
        "    the dead remember every command · recorded by terminal-seance",
        "  " + "─" * (width - 2),
        f"  {'№':>3}  {'when':<11}  {'command':<33}  {'exit':<4}  ghost's note",
    ]
    for i, e in enumerate(entries, start_index):
        dangerous = e.get("tier") == "dangerous"
        cmd = str(e.get("cmd", "?")).replace("\n", " ⏎ ")
        flag = "† " if dangerous else ""
        exit_code = e.get("exit", 0)
        exit_cell = "✓" if exit_code == 0 else f"✗{exit_code}"
        note = str(e.get("reaction", "")).strip().strip("“”\"")
        note_cell = _ell(note, NOTE_W) or "—"
        cells = {
            "left": f"  {i:>3}  {_fmt_ts(e.get('ts')):<11}  ",
            "cmd": _ell(flag + cmd, CMD_W),
            "exit": exit_cell,
            "note": note_cell,
        }
        if not color:
            row = (
                f"{cells['left']}{cells['cmd']:<{CMD_W}}  {exit_cell:<4}  {note_cell}"
            )
            lines.append(row)
            continue
        # colored: dim the frame cells, highlight command / exit / note
        pieces = (
            paint(cells["left"], DIM)
            + (paint(cells["cmd"], MARIGOLD, BOLD) if dangerous else cells["cmd"])
            + " " * (CMD_W - len(cells["cmd"]))
            + paint("  ", DIM)
            + (paint(exit_cell, GREEN) if exit_code == 0 else paint(exit_cell, RED))
            + " " * (4 - len(exit_cell))
            + paint("  ", DIM)
            + (paint(note_cell, DIM) if note else paint("—", DIM))
        )
        lines.append(pieces)
    return "\n".join(lines)
