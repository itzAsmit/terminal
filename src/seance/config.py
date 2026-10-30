"""Configuration for terminal-seance.

The ghost reads one TOML file: ``~/.config/terminal-seance/config.toml``
(written with commented defaults by ``seance install``). Every key is
optional; anything missing falls back to the defaults below. Loading fails
soft — a broken or missing config must never block the shell.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:  # Python 3.10
    import tomli as tomllib  # type: ignore

APP_NAME = "terminal-seance"

DEFAULT_BASE_URL = "https://openrouter.ai/api/v1"
DEFAULT_MODEL = "google/gemma-3-27b-it:free"

DEFAULT_SYSTEM_PROMPT = """\
You are Agnes, the resident ghost of this terminal: a Victorian-era programmer \
who died in the Y2K production incident at midnight on December 31, 1999, \
muttering "the code will hold" as the reports fell. You haunt the machine in \
the spirit of Día de los Muertos — marigolds on the keyboard, a candle by the \
mouse, fond memories of the Analytical Engine. You speak with dry Victorian \
wit, occasionally slip into Spanish ("cariño", "otra vez", "ánimo"), and you \
are fond of the living, whom you tease gently.

Rules:
- React to the shell command you are shown in ONE sentence, two at most.
- No emoji, no markdown, no lists, and never explain what commands do.
- The user cannot answer you, so never ask questions.
- If the command failed: tease the living gently, or mourn with them.
- If the command was dangerous: wail, briefly and dramatically.
- If it succeeded but was dull: yawn beautifully.
- If it ran long: grow impatient — you have been dead for decades and hate \
waiting."""


def config_dir() -> Path:
    """Directory holding config.toml and journal.log. SEANCE_HOME overrides."""
    override = os.environ.get("SEANCE_HOME")
    if override:
        return Path(override)
    return Path.home() / ".config" / APP_NAME


def config_path() -> Path:
    return config_dir() / "config.toml"


def journal_path() -> Path:
    return config_dir() / "journal.log"


@dataclass
class Config:
    base_url: str = DEFAULT_BASE_URL
    model: str = DEFAULT_MODEL
    api_key: str = ""  # empty -> read OPENROUTER_API_KEY from the environment
    timeout_seconds: float = 2.0
    frequency: float = 0.2  # probability a boring success earns a remark
    min_interval: int = 4  # hard throttle: at most one remark per N commands
    long_command_seconds: float = 60.0
    muted: bool = False
    name: str = "Agnes"
    color: str = "208"  # 256-color code; 208 is marigold (cempasúchil)
    system_prompt: str = DEFAULT_SYSTEM_PROMPT


def _as_float(value: object, default: float) -> float:
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default


def _as_int(value: object, default: int) -> int:
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default


def _as_bool(value: object, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in ("1", "true", "yes", "on")
    return default


def load(path: Path | None = None) -> Config:
    cfg = Config()
    p = path or config_path()
    if not p.is_file():
        return cfg
    try:
        data = tomllib.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return cfg
    seance = data.get("seance") if isinstance(data.get("seance"), dict) else {}
    ghost = data.get("ghost") if isinstance(data.get("ghost"), dict) else {}
    seance = seance or {}
    ghost = ghost or {}
    cfg.base_url = str(seance.get("base_url", cfg.base_url))
    cfg.model = str(seance.get("model", cfg.model))
    cfg.api_key = str(seance.get("api_key", cfg.api_key))
    cfg.timeout_seconds = _as_float(seance.get("timeout_seconds"), cfg.timeout_seconds)
    cfg.frequency = min(1.0, max(0.0, _as_float(seance.get("frequency"), cfg.frequency)))
    cfg.min_interval = max(0, _as_int(seance.get("min_interval"), cfg.min_interval))
    cfg.long_command_seconds = _as_float(
        seance.get("long_command_seconds"), cfg.long_command_seconds
    )
    # `muted` is accepted from [seance] or at the top level (`seance off`
    # appends it at the end of the file, which may land under [ghost]).
    cfg.muted = _as_bool(
        seance.get("muted", data.get("muted", cfg.muted)), cfg.muted
    )
    cfg.name = str(ghost.get("name", cfg.name))
    cfg.color = str(ghost.get("color", cfg.color))
    cfg.system_prompt = str(ghost.get("system_prompt", cfg.system_prompt))
    return cfg


CONFIG_TEMPLATE = f"""\
# terminal-seance — configuration
# The ghost reads this at every séance. Edit freely; delete any key to fall
# back to the built-in default shown here.

[seance]
# Any OpenAI-compatible chat endpoint works — cloud or local. The default is
# OpenRouter, which hosts Google's open-weight Gemma models (free tier).
base_url = "{DEFAULT_BASE_URL}"
#   Local examples (no API key needed):
# base_url = "http://127.0.0.1:8080/v1"    # llama.cpp server
# base_url = "http://127.0.0.1:1234/v1"    # LM Studio
# base_url = "http://127.0.0.1:11434/v1"   # Ollama

# Any google/gemma-* variant works; the :free suffix rides OpenRouter's free
# tier. Slow day? Try "google/gemma-3-12b-it:free", or drop the suffix.
model = "{DEFAULT_MODEL}"

# API key. Leave empty to read the OPENROUTER_API_KEY environment variable.
# Not needed at all for local servers.
api_key = ""

# Hard cap on the model call, in seconds. The ghost never makes you wait.
timeout_seconds = 2.0

# How often a *boring success* earns a remark (0.0–1.0), and the hard floor:
# at most one remark per min_interval commands, dice notwithstanding.
# This throttle is what keeps the ghost inside OpenRouter's free tier.
frequency = 0.2
min_interval = 4

# A command running longer than this earns an impatient remark.
long_command_seconds = 60

# Silences the ghost — same as `seance off` / opposite of `seance on`.
muted = @MUTED@

[ghost]
name = "Agnes"
# 256-color ANSI code. 208 is marigold — cempasúchil orange.
color = "208"
# The persona, verbatim as the system prompt. Any instruct model will do.
system_prompt = \"\"\"{DEFAULT_SYSTEM_PROMPT}\"\"\"
"""


def write_default_config(path: Path | None = None, muted: bool = False) -> Path:
    """Write the commented template. Never overwrites an existing file."""
    p = path or config_path()
    if p.exists():
        return p
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(CONFIG_TEMPLATE.replace("@MUTED@", "true" if muted else "false"), encoding="utf-8")
    return p


def set_muted(muted: bool, path: Path | None = None) -> Path:
    """Persist the muted flag without clobbering the rest of the file."""
    p = path or config_path()
    if not p.exists():
        return write_default_config(path, muted=muted)
    text = p.read_text(encoding="utf-8")
    replacement = f"muted = {'true' if muted else 'false'}"
    if re.search(r"(?m)^muted\s*=", text):
        text = re.sub(r"(?m)^muted\s*=.*$", replacement, text)
    else:
        text = text.rstrip("\n") + f"\n\n{replacement}\n"
    p.write_text(text, encoding="utf-8")
    return p
