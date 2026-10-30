import json

import pytest

from seance import cli, config, demo, journal


def test_version(capsys):
    with pytest.raises(SystemExit) as e:
        cli.main(["--version"])
    assert e.value.code == 0
    assert "seance" in capsys.readouterr().out


def test_no_args_prints_help(capsys):
    assert cli.main([]) == 0
    assert "usage" in capsys.readouterr().out.lower()


def test_demo_json_is_valid_event_script(capsys):
    rc = cli.main(["demo", "--json"])
    assert rc == 0
    events = json.loads(capsys.readouterr().out)
    kinds = {e["t"] for e in events}
    assert {"act", "prompt", "cmd", "out", "ghost", "wail", "ledger", "sleep"} <= kinds
    acts = [e["n"] for e in events if e["t"] == "act"]
    assert acts == [1, 2, 3, 4]
    # the wail act is present, with the danger made explicit
    wails = [e for e in events if e["t"] == "wail"]
    assert wails and "AGNES SHRIEKS" in wails[0]["lines"][0]


def test_demo_fast_runs_offline(capsys):
    rc = cli.main(["demo", "--fast", "--no-color"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "Agnes" in out
    assert "L E D G E R" in out
    assert "AGNES SHRIEKS" in out


def test_journal_empty_is_graceful(seance_home, capsys):
    assert cli.main(["journal", "--no-color"]) == 0
    assert "silent" in capsys.readouterr().out


def test_journal_tail_keeps_global_row_numbers(seance_home, capsys):
    for n in range(1, 7):
        journal.append({"ts": "2026-10-30T21:00:0%d" % n, "cmd": f"cmd-{n}",
                        "exit": 0, "dur": 0.1, "tier": "boring", "reaction": ""})
    assert cli.main(["journal", "--tail", "2", "--no-color"]) == 0
    out = capsys.readouterr().out
    assert "cmd-6" in out and "cmd-5" in out and "cmd-4" not in out
    assert "  6" in out  # global row number, not the tail-local one


def test_summon_unknown_row(seance_home, capsys):
    assert cli.main(["summon", "9"]) == 1
    assert "No soul rests at row 9" in capsys.readouterr().out


def test_summon_row_runs_the_command(seance_home, capsys):
    journal.append({"ts": "2026-10-30T21:00:00", "cmd": "echo haunted", "exit": 0,
                    "dur": 0.1, "tier": "boring", "reaction": ""})
    rc = cli.main(["summon", "1"])
    assert rc == 0
    assert "re-summoning row 1: echo haunted" in capsys.readouterr().out


def test_hear_journals_silently_when_piped(seance_home, capsys, monkeypatch):
    # capsys = stdout is a pipe -> the ghost must not speak, but must remember.
    monkeypatch.setenv("SEANCE_CMD", "ls -la")
    monkeypatch.setenv("SEANCE_EXIT", "0")
    monkeypatch.setenv("SEANCE_START", "1793000000.0")
    monkeypatch.setenv("SEANCE_END", "1793000001.5")
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    rc = cli.main(["hear"])
    assert rc == 0
    assert capsys.readouterr().out == ""
    es = journal.read_all()
    assert len(es) == 1
    assert es[0]["cmd"] == "ls -la"
    assert es[0]["dur"] == 1.5
    assert es[0]["tier"] == "boring"
    assert es[0]["reaction"] == ""  # throttled: first command after a fresh journal


def test_hear_always_speaks_on_failure(seance_home, capsys, monkeypatch):
    monkeypatch.setenv("SEANCE_CMD", "pytest")
    monkeypatch.setenv("SEANCE_EXIT", "1")
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    assert cli.main(["hear"]) == 0
    es = journal.read_all()
    assert es[0]["tier"] == "failed"
    assert es[0]["reaction"] in ghost_whispers()


def test_hear_dangerous_tier(seance_home, monkeypatch):
    monkeypatch.setenv("SEANCE_CMD", "git push --force origin main")
    monkeypatch.setenv("SEANCE_EXIT", "0")
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    assert cli.main(["hear"]) == 0
    assert journal.read_all()[0]["tier"] == "dangerous"


def test_hear_muted_still_journals_but_says_nothing(seance_home, capsys, monkeypatch):
    config.set_muted(True)
    monkeypatch.setenv("SEANCE_CMD", "pytest")
    monkeypatch.setenv("SEANCE_EXIT", "1")
    assert cli.main(["hear"]) == 0
    es = journal.read_all()
    assert es[0]["reaction"] == ""
    assert capsys.readouterr().out == ""


def test_hear_ignores_missing_or_huge_command(seance_home, capsys, monkeypatch):
    monkeypatch.delenv("SEANCE_CMD", raising=False)
    assert cli.main(["hear"]) == 0
    monkeypatch.setenv("SEANCE_CMD", "x" * 600)
    assert cli.main(["hear"]) == 0
    assert journal.read_all() == []


def test_guard_stays_silent_when_piped(seance_home, capsys, monkeypatch):
    monkeypatch.setenv("SEANCE_CMD", "git push --force origin main")
    assert cli.main(["guard"]) == 0
    assert capsys.readouterr().out == ""


def test_off_and_on_persist(seance_home, capsys):
    assert cli.main(["off"]) == 0
    assert config.load().muted is True
    assert cli.main(["on"]) == 0
    assert config.load().muted is False


def ghost_whispers():
    from seance.ghost import WHISPERS
    return WHISPERS
