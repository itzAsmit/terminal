"""The ``seance`` command line.

Public commands: install, uninstall, off/on, journal, summon, demo.
Hook-internal commands: hear (after every command), guard (before risky ones).
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from datetime import datetime

from . import __version__
from . import config, danger, demo, ghost, hooks, journal, output


# --- shared env plumbing (set by the shell hook) ---------------------------

def _int_env(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, "") or default)
    except ValueError:
        return default


def _duration_from_env() -> float | None:
    """SEANCE_START / SEANCE_END come from the same shell-side clock, so the
    difference is valid whether the shell used EPOCHREALTIME or SECONDS."""
    raw0 = os.environ.get("SEANCE_START", "")
    raw1 = os.environ.get("SEANCE_END", "")
    if not raw0 or not raw1:
        return None
    try:
        t0, t1 = float(raw0), float(raw1)
    except ValueError:
        return None
    if (t0 > 1e9) != (t1 > 1e9):  # mixed clock bases — don't guess
        return None
    d = t1 - t0
    return d if 0.0 <= d < 86400 else None


def _is_muted(cfg: config.Config) -> bool:
    return cfg.muted or os.environ.get("SEANCE_MUTE", "") not in ("", "0")


# --- hook-internal commands ------------------------------------------------

def cmd_hear(args: argparse.Namespace) -> int:
    """Called (backgrounded) after every shell command. Never raises, never
    blocks for more than the configured cap, never prints unless interactive."""
    cmd = (os.environ.get("SEANCE_CMD") or "").strip()
    if not cmd or len(cmd) > 500:
        return 0
    cfg = config.load()
    exit_code = _int_env("SEANCE_EXIT", 0)
    duration = _duration_from_env()
    dangerous_label = danger.classify(cmd)
    tier = ghost.classify_tier(exit_code, duration, dangerous_label, cfg.long_command_seconds)

    speak = False
    if not _is_muted(cfg):
        reactor = ghost.Reactor(cfg.frequency, cfg.min_interval)
        speak = reactor.should_speak(tier, journal.commands_since_last_reaction())

    reaction = ""
    if speak:
        context = ghost.build_context(cmd, exit_code, duration, tier, dangerous_label)
        reply = ghost.ask_ghost(cfg, context)
        reaction = reply if reply is not None else ghost.random_whisper()

    journal.append({
        "ts": datetime.now().isoformat(timespec="seconds"),
        "cmd": cmd,
        "exit": exit_code,
        "dur": round(duration, 3) if duration is not None else None,
        "tier": tier.value,
        "reaction": reaction,
    })

    if speak and reaction and output.supports_color():
        print(output.ghost_line(cfg.name, ghost.VERBS[tier], reaction, color=True), flush=True)
    return 0


def cmd_guard(args: argparse.Namespace) -> int:
    """Called (synchronously) before a command that looked dangerous.
    Local regex only — microseconds, no API."""
    cmd = os.environ.get("SEANCE_CMD") or ""
    label = danger.classify(cmd)
    if not label or not output.supports_color():
        return 0
    print(output.wail(label, color=True), flush=True)
    return 0


# --- public commands -------------------------------------------------------

def cmd_install(args: argparse.Namespace) -> int:
    try:
        rc = hooks.install(shell=args.shell)
    except ValueError as e:
        print(str(e), file=sys.stderr)
        return 2
    conf = config.write_default_config()
    c = output.supports_color()
    print(output.paint(f"† Agnes has moved into {rc}", output.BOLD, output.MARIGOLD, enabled=c))
    print(f"  1. restart your shell — or:  source {rc.name}")
    print("  2. export OPENROUTER_API_KEY=sk-or-...   (or point base_url at a local model)")
    print("  3. run something. she is watching, cariño.")
    print(f"  config: {conf}")
    print("  silence her anytime:  seance off  ·  SEANCE_MUTE=1")
    return 0


def cmd_uninstall(args: argparse.Namespace) -> int:
    removed = hooks.uninstall(shell=args.shell)
    c = output.supports_color()
    if removed:
        rc = hooks.rc_path(args.shell or hooks.detect_shell())
        print(output.paint(f"† Agnes lifts the candle from {rc}. The shell is yours alone again.",
                           output.MARIGOLD, enabled=c))
    else:
        print("No hook block found — the ghost was never here.")
    print("  (the journal is kept; delete ~/.config/terminal-seance/ to forget everything)")
    return 0


def cmd_off(args: argparse.Namespace) -> int:
    config.set_muted(True)
    c = output.supports_color()
    print(output.paint("† Agnes bows and dims her candle. (muted — `seance on` to wake her)",
                       output.MARIGOLD, enabled=c))
    return 0


def cmd_on(args: argparse.Namespace) -> int:
    config.set_muted(False)
    c = output.supports_color()
    print(output.paint("† Agnes trims the wick. She is listening again, cariño.",
                       output.MARIGOLD, enabled=c))
    return 0


def cmd_journal(args: argparse.Namespace) -> int:
    entries = journal.read_all()
    color = output.supports_color() and not args.no_color
    start = 1
    if args.tail:
        shown = entries[-args.tail:]
        start = len(entries) - len(shown) + 1  # keep the global ledger numbers
        entries = shown
    print(journal.render_ledger(entries, color=color, start_index=start))
    if entries:
        print(output.paint("  † `seance summon <№>` re-runs a row — she remembers everything.",
                           output.DIM, enabled=color))
    return 0


def cmd_summon(args: argparse.Namespace) -> int:
    e = journal.entry_at(args.row)
    if e is None:
        print(f"No soul rests at row {args.row} — try `seance journal` first.")
        return 1
    cmd = str(e.get("cmd", ""))
    print(f"† re-summoning row {args.row}: {cmd}")
    label = danger.classify(cmd)
    if label and output.supports_color():
        print(output.wail(label, color=True))
    return subprocess.call(cmd, shell=True)


def cmd_demo(args: argparse.Namespace) -> int:
    if args.json:
        print(demo.events_json())
        return 0
    try:
        demo.run_demo(fast=args.fast, color=not args.no_color)
    except OSError:
        pass  # the reader hung up early (e.g. piped into head) — that's fine
    return 0


def cmd_serve(args: argparse.Namespace) -> int:
    """Host the web séance: site/ + a key-safe /api/ghost proxy.

    The key comes from OPENROUTER_API_KEY in the environment (Render
    dashboard, local shell) and is never sent to the browser."""
    from . import webproxy

    return webproxy.main(port=args.port)


# --- parser ----------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="seance",
        description=(
            "A haunted CLI companion: Agnes, a Victorian ghost who died in the Y2K "
            "incident, reacts to your shell commands. Powered by open-weight Gemma "
            "via OpenRouter — or any OpenAI-compatible endpoint, cloud or local."
        ),
    )
    p.add_argument("--version", action="version", version=f"seance {__version__}")
    sub = p.add_subparsers(dest="command", metavar="<command>")

    g = sub.add_parser("install", help="append the ghost's hook block to ~/.bashrc or ~/.zshrc")
    g.add_argument("--shell", choices=["bash", "zsh"], default=None, help="default: auto-detect")
    g.set_defaults(fn=cmd_install)

    g = sub.add_parser("uninstall", help="remove the hook block cleanly")
    g.add_argument("--shell", choices=["bash", "zsh"], default=None, help="default: auto-detect")
    g.set_defaults(fn=cmd_uninstall)

    g = sub.add_parser("off", help="silence the ghost (persists; SEANCE_MUTE=1 for one session)")
    g.set_defaults(fn=cmd_off)

    g = sub.add_parser("on", help="wake the ghost again")
    g.set_defaults(fn=cmd_on)

    g = sub.add_parser("journal", help="print the graveyard ledger of everything recorded")
    g.add_argument("--tail", type=int, default=None, metavar="N", help="only the last N rows")
    g.add_argument("--no-color", action="store_true")
    g.set_defaults(fn=cmd_journal)

    g = sub.add_parser("summon", help="re-run a past command by its ledger row number")
    g.add_argument("row", type=int)
    g.set_defaults(fn=cmd_summon)

    g = sub.add_parser("demo", help="replay a short scripted haunted session (offline)")
    g.add_argument("--fast", action="store_true", help="typewriter at test speed")
    g.add_argument("--json", action="store_true", help="emit the event script as JSON (for scripts/)")
    g.add_argument("--no-color", action="store_true")
    g.set_defaults(fn=cmd_demo)

    g = sub.add_parser("serve", help="host the web séance — site/ + key-safe ghost proxy (see render.yaml)")
    g.add_argument("--port", type=int, default=None, help="default: $PORT or 8080")
    g.set_defaults(fn=cmd_serve)

    g = sub.add_parser("hear", help="(internal) called by the shell hook after each command")
    g.set_defaults(fn=cmd_hear)

    g = sub.add_parser("guard", help="(internal) called by the shell hook before risky commands")
    g.set_defaults(fn=cmd_guard)

    return p


def main(argv: list[str] | None = None) -> int:
    if os.name == "nt":
        os.system("")  # enable ANSI escape codes on Windows terminals
    parser = build_parser()
    args = parser.parse_args(argv)
    fn = getattr(args, "fn", None)
    if fn is None:
        parser.print_help()
        return 0
    try:
        return fn(args)
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    sys.exit(main())
