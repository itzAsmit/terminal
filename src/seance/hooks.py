"""Shell integration: the marked hook blocks appended to ~/.bashrc / ~/.zshrc.

Design notes
------------
* zsh: native ``preexec``/``precmd`` — clean before/after hooks.
* bash: there is no preexec, so two cooperating pieces are used:
    - a **DEBUG trap** runs before every top-level command: it records the
      start time and does a cheap local prefilter so truly risky commands
      get their pre-exec wail *before* running. (Our own PROMPT_COMMAND
      plumbing is excluded by marker, so the start time stays pinned to the
      user's command.)
    - **PROMPT_COMMAND** (prepended, so ``$?`` is still fresh) reads the last
      history entry — the full command line — and fires ``seance hear`` in a
      disowned background job, so the prompt is never delayed.
* The ``seance hear`` call passes command text / exit code / timing via
  environment variables — never command output — and is backgrounded so the
  ghost may arrive late but never early.

Both blocks are idempotent (markers) and removable (``seance uninstall``).
"""

from __future__ import annotations

import os
from pathlib import Path

MARK_BEGIN = "# >>> terminal-seance >>>"
MARK_END = "# <<< terminal-seance <<<"

# Cheap shell-side prefilter, so `seance guard` (a Python startup) only runs
# for plausibly dangerous commands. Python re-checks precisely; a miss there
# costs nothing but a few milliseconds.
_CASE_PATTERNS = """\
"rm "*|*" rm "*|"git push"*|*" git push"*|"chmod "*|*" chmod "*|\\
      "curl "*|*" curl "*|"wget "*|*" wget "*|"DROP "*|*" DROP "*|"mkfs"*|*" mkfs"*|\\
      "dd "*|*" dd "*|"shutdown"*|*" shutdown"*|"reboot"*|*" reboot"*"""

ZSH_BLOCK = """\
# >>> terminal-seance >>>
# haunted by terminal-seance — regenerate with: seance install
if [[ -o interactive ]]; then

  __seance_preexec() {
    __SEANCE_T0="${EPOCHREALTIME:-$SECONDS}"
    __SEANCE_FRESH=1
    __SEANCE_CMD_LINE="$1"
    case "$__SEANCE_CMD_LINE" in
      @CASE_PATTERNS@)
        SEANCE_CMD="$__SEANCE_CMD_LINE" command seance guard 2>/dev/null ;;
    esac
  }

  __seance_precmd() {
    local ec=$?
    if [[ -n "${__SEANCE_FRESH:-}" ]]; then
      __SEANCE_FRESH=""
      __SEANCE_T1="${EPOCHREALTIME:-$SECONDS}"
      SEANCE_CMD="$__SEANCE_CMD_LINE" SEANCE_EXIT="$ec" \\
        SEANCE_START="${__SEANCE_T0:-}" SEANCE_END="${__SEANCE_T1:-}" \\
        command seance hear 2>/dev/null &!
    fi
  }

  preexec_functions=(__seance_preexec $preexec_functions)
  precmd_functions=(__seance_precmd $precmd_functions)
fi
# <<< terminal-seance <<<
"""

BASH_BLOCK = """\
# >>> terminal-seance >>>
# haunted by terminal-seance — regenerate with: seance install
if [[ $- == *i* ]]; then

  # Pre-exec hook: records the command's start time and wails before risky
  # commands run. The PROMPT_COMMAND plumbing itself is excluded by marker,
  # so the start time stays pinned to the user's own command. Stateless on
  # purpose — it cannot corrupt any other DEBUG-trap state.
  __seance_debug() {
    [[ -n "${COMP_LINE:-}" ]] && return 0
    case "$BASH_COMMAND" in
      *__seance_precmd*) return 0 ;;
    esac
    __SEANCE_T0="${EPOCHREALTIME:-$SECONDS}"
    case "$BASH_COMMAND" in
      @CASE_PATTERNS@)
        SEANCE_CMD="$BASH_COMMAND" command seance guard 2>/dev/null ;;
    esac
  }
  trap '__seance_debug' DEBUG

  __seance_precmd() {
    local ec=$? h n c
    h="$(HISTTIMEFORMAT= history 1)"
    h="${h#"${h%%[![:space:]]*}"}"
    n="${h%%[!0-9]*}"
    c="${h#"$n"}"
    c="${c#"${c%%[![:space:]]*}"}"
    # __SEANCE_T0 is only set by the DEBUG trap for a command that actually
    # ran in THIS session — this skips the last entry of a previous session,
    # which ~/.bash_history loads at startup.
    if [[ -n "$c" && -n "${__SEANCE_T0:-}" && "$n" != "${__SEANCE_N:-}" ]]; then
      __SEANCE_N="$n"
      __SEANCE_T1="${EPOCHREALTIME:-$SECONDS}"
      SEANCE_CMD="$c" SEANCE_EXIT="$ec" \\
        SEANCE_START="${__SEANCE_T0:-}" SEANCE_END="${__SEANCE_T1:-}" \\
        command seance hear 2>/dev/null & disown 2>/dev/null || true
    fi
    __SEANCE_T0=""
  }

  if [[ "$(declare -p PROMPT_COMMAND 2>/dev/null)" == "declare -a"* ]]; then
    PROMPT_COMMAND=(__seance_precmd "${PROMPT_COMMAND[@]}")
  else
    PROMPT_COMMAND="__seance_precmd${PROMPT_COMMAND:+;$PROMPT_COMMAND}"
  fi
  __SEANCE_T0=""   # DEBUG fired while sourcing this block — drop the stale stamp
fi
# <<< terminal-seance <<<
"""


def _render(block: str) -> str:
    return block.replace("@CASE_PATTERNS@", _CASE_PATTERNS)


def detect_shell() -> str:
    shell = os.environ.get("SHELL", "")
    if shell.endswith("zsh"):
        return "zsh"
    if shell.endswith("bash"):
        return "bash"
    home = Path.home()
    if (home / ".zshrc").exists() and not (home / ".bashrc").exists():
        return "zsh"
    return "bash"


def rc_path(shell: str, home: Path | None = None) -> Path:
    base = Path(home) if home is not None else Path.home()
    return base / (".zshrc" if shell == "zsh" else ".bashrc")


def _strip_block(text: str) -> str:
    """Remove the marked block (handles a missing end marker, too)."""
    out: list[str] = []
    skip = False
    for line in text.splitlines():
        if MARK_BEGIN in line:
            skip = True
            continue
        if MARK_END in line:
            skip = False
            continue
        if not skip:
            out.append(line)
    return "\n".join(out) + ("\n" if out else "")


def install(shell: str | None = None, home: Path | None = None) -> Path:
    """Append the hook block (idempotent). Returns the rc file path."""
    shell = shell or detect_shell()
    if shell not in ("bash", "zsh"):
        raise ValueError(f"unsupported shell: {shell!r} (use 'bash' or 'zsh')")
    rc = rc_path(shell, home)
    existing = rc.read_text(encoding="utf-8") if rc.exists() else ""
    text = _strip_block(existing)
    if text and not text.endswith("\n"):
        text += "\n"
    if text.strip():
        text += "\n"
    text += _render(ZSH_BLOCK if shell == "zsh" else BASH_BLOCK)
    rc.write_text(text, encoding="utf-8")
    return rc


def uninstall(shell: str | None = None, home: Path | None = None) -> bool:
    """Remove the hook block. Returns True if anything was removed."""
    shell = shell or detect_shell()
    rc = rc_path(shell, home)
    if not rc.exists():
        return False
    text = rc.read_text(encoding="utf-8")
    stripped = _strip_block(text)
    if stripped == text and MARK_BEGIN not in text:
        return False
    rc.write_text(stripped, encoding="utf-8")
    return True
