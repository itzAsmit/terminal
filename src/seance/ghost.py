"""The ghost herself: tier decisions, throttling, and the one HTTPS call.

One law governs everything here: the ghost may NEVER make the user wait.
The model call is attempted exactly once, capped (default 2 s), and any
failure — timeout, missing key, rate limit, outage — falls back to a random
line from the bundled whispers list below. No retries, ever: a rate-limited
ghost stays quiet rather than hammering the API.
"""

from __future__ import annotations

import enum
import json
import os
import random
import re
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

from . import config


class Tier(enum.Enum):
    DANGEROUS = "dangerous"
    FAILED = "failed"
    LONG = "long"
    BORING = "boring"


VERBS = {
    Tier.DANGEROUS: "wails",
    Tier.FAILED: "mourns",
    Tier.LONG: "taps the hourglass",
    Tier.BORING: "murmurs",
}


def classify_tier(
    exit_code: int,
    duration: float | None,
    dangerous_label: str | None,
    long_seconds: float,
) -> Tier:
    """Pure tier logic. Precedence: dangerous > failed > long > boring."""
    if dangerous_label:
        return Tier.DANGEROUS
    if exit_code != 0:
        return Tier.FAILED
    if duration is not None and duration >= long_seconds:
        return Tier.LONG
    return Tier.BORING


@dataclass
class Reactor:
    """Decides whether the ghost speaks.

    Boring successes are throttled hard: at most one remark per
    ``min_interval`` commands (a hard cap, whatever the dice say), and even
    then only with probability ``frequency``. This is what keeps the ghost
    inside OpenRouter's free tier — and keeps her interesting.
    """

    frequency: float = 0.2
    min_interval: int = 4
    rng: random.Random = field(default_factory=random.Random)

    def should_speak(self, tier: Tier, commands_since_last: int) -> bool:
        if tier is not Tier.BORING:
            return True
        if commands_since_last < self.min_interval:
            return False
        return self.rng.random() < self.frequency


def build_context(
    cmd: str,
    exit_code: int,
    duration: float | None,
    tier: Tier,
    dangerous_label: str | None,
) -> str:
    dur = f"{duration:.1f}s" if duration is not None else "unknown"
    lines = [f"command: {cmd}", f"exit code: {exit_code}", f"duration: {dur}"]
    if tier is Tier.DANGEROUS:
        lines.append(f"(dangerous: {dangerous_label} — wail, briefly)")
    elif tier is Tier.FAILED:
        lines.append("(it failed — tease gently or mourn)")
    elif tier is Tier.LONG:
        lines.append(f"(it ran {dur} — be impatient)")
    else:
        lines.append("(a dull success — yawn beautifully, or stay cryptic)")
    return "\n".join(lines)


# Local fallback one-liners, bundled so the ghost always has a voice — no
# key, no network, no quota. Tier-agnostic by design.
WHISPERS: list[str] = [
    "The fans hum a requiem, cariño. I have haunted slower machines — and loved them still.",
    "Another command crosses the veil. The marigolds on the keyboard tremble, delighted.",
    "I knew a boy who piped like that. Lovely manners. Terrible backups.",
    "The cursor blinks like a votive candle. I could watch it for another century.",
    "Otra vez, cariño? The dead have infinite patience. You, less so.",
    "Even my séance table ran warmer than this machine. I miss the candlelight.",
    "Somewhere, a mainframe dreams of you. It, too, wonders what you are typing.",
    "I died at midnight, December 31st, 1999. Since then, every prompt is a small resurrection.",
    "Type on, cariño. The veil is thin and the terminal is thinner.",
    "I knew COBOL before it was vintage. Now everything is vintage. I am thrilled.",
    "Ánimo! The ghosts of failed builds past stand behind you. Politely.",
    "Your shell history is a graveyard of intentions. Beautiful, really.",
    "The marigolds say a command is coming. They are rarely wrong.",
    "I have watched ten thousand prompts. Yours blinks the brightest.",
    "Dios mío, the uptime. Even I do not rest that little.",
    "I keep the candles lit by the mouse. You never notice. That is how I like it.",
    "Babbage would have adored this. He would also have billed you for it.",
    "A quiet success, cariño. The best kind — like a funeral nobody attends.",
    "The dead envy you your Ctrl+C. We could have used one, back in '99.",
    "Hush now. The terminal is listening. It learned that from me.",
]

_SENTINEL_RNG = random.Random()


def random_whisper(rng: random.Random | None = None) -> str:
    return (rng or _SENTINEL_RNG).choice(WHISPERS)


# --- the one HTTP call -----------------------------------------------------

RATELIMIT_FILE = ".ratelimit"
RATELIMIT_COOLDOWN = 120.0  # seconds of silence after a 429/5xx


def _ratelimit_path() -> Path:
    return config.config_dir() / RATELIMIT_FILE


def _rate_limited(now: float | None = None) -> bool:
    try:
        stamp = float(_ratelimit_path().read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return False
    return (now if now is not None else time.time()) - stamp < RATELIMIT_COOLDOWN


def _mark_rate_limited() -> None:
    try:
        p = _ratelimit_path()
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(str(time.time()), encoding="utf-8")
    except OSError:
        pass


def _post_json(url: str, payload: dict, headers: dict, timeout: float) -> dict:
    """Single HTTP POST. Kept as a module-level function so tests can stub it."""
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def ask_ghost(cfg: config.Config, context: str, post=None) -> str | None:
    """One attempt, hard-capped. Returns the ghost's line, or None.

    None means "stay silent or whisper locally" — the caller decides. There
    are no retries: 429/5xx also set a cooldown stamp so subsequent commands
    skip the API entirely for a while (never retry-flood).
    """
    key = cfg.api_key or os.environ.get("OPENROUTER_API_KEY", "")
    if not key:
        return None
    if _rate_limited():
        return None
    url = cfg.base_url.rstrip("/") + "/chat/completions"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {key}",
        "HTTP-Referer": "https://github.com/terminal-seance/terminal-seance",
        "X-Title": "terminal-seance",
    }
    payload = {
        "model": cfg.model,
        "temperature": 0.9,
        "max_tokens": 90,
        "messages": [
            {"role": "system", "content": cfg.system_prompt},
            {"role": "user", "content": context},
        ],
    }
    try:
        data = (post or _post_json)(url, payload, headers, cfg.timeout_seconds)
    except urllib.error.HTTPError as e:
        if e.code in (429, 500, 502, 503):
            _mark_rate_limited()
        return None
    except Exception:
        return None
    try:
        text = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError):
        return None
    if not isinstance(text, str):
        return None
    return trim_reply(text)


def trim_reply(text: str, max_sentences: int = 2, max_chars: int = 240) -> str:
    """Keep the ghost terse: 1–2 sentences, bounded length, no markdown fences."""
    text = " ".join(str(text).split()).strip("`").strip()
    parts = re.split(r"(?<=[.!?…])\s+", text)
    out = " ".join(parts[:max_sentences]).strip()
    out = re.sub(r"^(?:agnes|the ghost)\s*[:—-]\s*", "", out, flags=re.IGNORECASE)
    if len(out) > max_chars:
        out = out[: max_chars - 1].rstrip() + "…"
    return out or "…"
