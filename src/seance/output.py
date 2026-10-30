"""ANSI helpers and the ghost's on-screen voice.

These are pure formatting functions — paint never blocks anything.
"""

from __future__ import annotations

import os
import textwrap

MARIGOLD = "38;5;208"
BOLD = "1"
DIM = "2"
ITALIC = "3"
RED = "31"
GREEN = "32"
GRAY = "90"

# Dramatic exclamations for the pre-exec wail, keyed by danger label.
EXCLAIMS = {
    "a recursive or forced rm": "DELETING RECURSIVELY?!",
    "a forced push": "REWRITING HISTORY?!",
    "chmod 777": "THE GATES THROWN OPEN TO EVERY SOUL?!",
    "a DROP statement": "THE TABLE! YOU WOULD DROP THE TABLE ITSELF?!",
    "a new filesystem over the bones": "A NEW FILESYSTEM, OVER THE BONES OF THE OLD?!",
    "a raw write with dd": "RAW WRITES, UNMITIGATED?!",
    "stranger code, piped into a shell": "STRANGER CODE, SWALLOWED WHOLE?!",
    "a fork bomb": "AN INFINITE CHOIR OF CLONES?!",
    "a raw write to the disk itself": "THE DISK ITSELF?!",
    "the machine, put to bed forever": "PUTTING THE MACHINE TO BED — FOREVER?!",
}


def supports_color(stream=None) -> bool:
    """True only when we are talking to an interactive terminal.

    Piped output and captured output (CI, logs) never see the ghost.
    """
    stream = stream or __import__("sys").stdout
    if os.environ.get("NO_COLOR"):
        return False
    if os.environ.get("FORCE_COLOR"):
        return True
    return bool(getattr(stream, "isatty", lambda: False)())


def paint(text: str, *codes: str, enabled: bool = True) -> str:
    if not text or not enabled or not codes:
        return text
    return f"\033[{';'.join(str(c) for c in codes)}m{text}\033[0m"


def term_width(default: int = 88) -> int:
    import sys

    try:
        return max(48, min(110, os.get_terminal_size(sys.__stdout__.fileno()).columns))
    except (OSError, ValueError, AttributeError):
        return default


def ghost_line(name: str, verb: str, text: str, color: bool = True, width: int | None = None) -> str:
    """Format one post-command remark:  ``  † Agnes wails — "..."``

    Printed after the prompt has already returned — the ghost may arrive a
    second late, never a second early.
    """
    width = width or term_width()
    text = " ".join(text.split())
    if not text.startswith(('"', "“")):
        text = f"“{text}”"
    head = f"  † {name} " + (f"{verb} — " if verb else "— ")
    out = textwrap.fill(
        text,
        width=width,
        initial_indent=head,
        subsequent_indent="      ",
        break_long_words=False,
        break_on_hyphens=False,
    )
    if not color:
        return out
    first, _, rest = out.partition("\n")
    painted = paint(first, MARIGOLD)
    if rest:
        painted += "\n" + paint(rest, MARIGOLD)
    return painted


def wail(label: str, color: bool = True, width: int | None = None) -> str:
    """The pre-exec wail block, printed synchronously before the dangerous
    command is allowed to run. Local regex only — no API, no delay."""
    width = width or term_width()
    exclaim = EXCLAIMS.get(label, "SUCH DARK INCANTATIONS, CARIÑO?!")
    line1 = "  ✝†✝  AGNES SHRIEKS FROM BEYOND THE PROMPT  ✝†✝"
    quote = textwrap.fill(
        f"“{exclaim} Oh, cariño — I have died for less, and I MEANT it.”",
        width=width,
        initial_indent="  ",
        subsequent_indent="  ",
        break_long_words=False,
        break_on_hyphens=False,
    )
    line3 = "  (she cannot stop you. she can only grieve you.)"
    if color:
        line1 = paint(line1, BOLD, MARIGOLD)
        quote = paint(quote, MARIGOLD)
        line3 = paint(line3, DIM, ITALIC)
    return "\n".join([line1, quote, line3])
