from seance import journal


def entry(cmd="ls", exit=0, tier="boring", reaction="", ts="2026-10-30T21:00:00"):
    return {"ts": ts, "cmd": cmd, "exit": exit, "dur": 0.1,
            "tier": tier, "reaction": reaction}


def test_roundtrip(seance_home):
    journal.append(entry(cmd="ls"))
    journal.append(entry(cmd="rm -rf build/", tier="dangerous", reaction="wailed"))
    es = journal.read_all()
    assert [e["cmd"] for e in es] == ["ls", "rm -rf build/"]
    assert es[1]["tier"] == "dangerous"


def test_torn_lines_are_skipped(seance_home):
    p = seance_home / "journal.log"
    p.write_text('{"cmd":"ok","ts":"2026-10-30T21:00:00"}\nnot json at all\n\n', encoding="utf-8")
    es = journal.read_all()
    assert len(es) == 1 and es[0]["cmd"] == "ok"


def test_commands_since_last_reaction(seance_home):
    assert journal.commands_since_last_reaction() == 0
    for cmd in ("a", "b", "c", "d"):
        journal.append(entry(cmd=cmd, reaction="spoke" if cmd == "b" else ""))
    assert journal.commands_since_last_reaction() == 2  # c and d came after b spoke


def test_entry_at_is_one_based_oldest_first(seance_home):
    journal.append(entry(cmd="first"))
    journal.append(entry(cmd="second"))
    assert journal.entry_at(1)["cmd"] == "first"
    assert journal.entry_at(2)["cmd"] == "second"
    assert journal.entry_at(3) is None
    assert journal.entry_at(0) is None


def test_ledger_renders_rows_and_dangerous_marker(seance_home):
    journal.append(entry(cmd="git push --force origin main", tier="dangerous",
                         reaction="Gone, cariño."))
    journal.append(entry(cmd="ls", exit=0, reaction=""))
    journal.append(entry(cmd="pytest", exit=1, tier="failed", reaction="mourned"))
    out = journal.render_ledger(journal.read_all(), color=False)
    assert "L E D G E R" in out
    assert "git push --force origin main" in out
    assert "†" in out            # dangerous marker
    assert "✓" in out and "✗1" in out
    assert "mourned" in out
    assert "seance summon" not in out  # that hint belongs to the CLI, not the ledger


def test_ledger_empty_state(seance_home):
    out = journal.render_ledger([], color=False)
    assert "silent" in out


def test_ledger_numbers_match_entry_at(seance_home):
    for n in range(1, 4):
        journal.append(entry(cmd=f"cmd-{n}"))
    rendered = journal.render_ledger(journal.read_all(), color=False)
    for n in range(1, 4):
        e = journal.entry_at(n)
        assert f"{n:>3}" in rendered
        assert e["cmd"] in rendered


def test_ledger_truncates_long_commands():
    long_cmd = "echo " + "x" * 200
    out = journal.render_ledger([entry(cmd=long_cmd, reaction="r" * 200)], color=False)
    for line in out.splitlines():
        assert len(line) <= journal.WIDTH + 2
    assert "…" in out
