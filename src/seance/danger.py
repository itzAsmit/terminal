"""Local, instant dangerous-command detection — no API, no waiting.

Heuristics by design: the pre-exec guard must answer in microseconds, so it
runs a fixed list of regexes over the command text. They lean toward over-
matching on quoted text (``echo "rm -rf"`` will be mourned); in a haunted
shell that is a feature, not a bug.
"""

from __future__ import annotations

import re

# (pattern, label) — matched case-insensitively against the whole command line.
PATTERNS: list[tuple[str, str]] = [
    (r"\brm\s+(?:-{1,2}[\w-]+\s+)*-\w*[rfR]", "a recursive or forced rm"),
    (r"\brm\b[^|;&]*(?:--recursive|--force)", "a recursive or forced rm"),
    (r"\bgit\s+push\b[^\n]*\s(?:-f\b|--force)", "a forced push"),
    (r"\bchmod\b[^\n;&|]*\b777\b", "chmod 777"),
    (r"\bDROP\s+(?:TABLE|DATABASE|SCHEMA)\b", "a DROP statement"),
    (r"\bmkfs", "a new filesystem over the bones"),
    (r"\bdd\b[^|;&]*\bof\s*=", "a raw write with dd"),
    (
        r"\b(?:curl|wget)\b[^|;&]*\|\s*(?:sudo\s+)?(?:ba|z|da|fi|k|)sh\b",
        "stranger code, piped into a shell",
    ),
    (r":\s*\(\s*\)\s*\{[^}]*:\s*\|[^}]*&", "a fork bomb"),
    (r">\s*/dev/(?:sd[a-z]|nvme\d|hd[a-z]|disk\d)", "a raw write to the disk itself"),
    (r"\b(?:shutdown|reboot|halt|poweroff)\b", "the machine, put to bed forever"),
]

_COMPILED = [(re.compile(p, re.IGNORECASE), label) for p, label in PATTERNS]


def classify(command: str) -> str | None:
    """Return a short label if the command line looks dangerous, else None."""
    for rx, label in _COMPILED:
        if rx.search(command):
            return label
    return None
