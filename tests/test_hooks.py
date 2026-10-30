from seance import hooks


def test_install_and_uninstall_roundtrip(tmp_path):
    rc = tmp_path / ".zshrc"
    rc.write_text("export EDITOR=vim\n", encoding="utf-8")

    p = hooks.install(shell="zsh", home=tmp_path)
    assert p == rc

    text = rc.read_text(encoding="utf-8")
    assert hooks.MARK_BEGIN in text and hooks.MARK_END in text
    assert text.startswith("export EDITOR=vim\n")
    assert "preexec_functions" in text and "seance hear" in text

    # idempotent: a second install leaves exactly one block
    hooks.install(shell="zsh", home=tmp_path)
    assert rc.read_text(encoding="utf-8").count(hooks.MARK_BEGIN) == 1

    assert hooks.uninstall(shell="zsh", home=tmp_path) is True
    after = rc.read_text(encoding="utf-8")
    assert hooks.MARK_BEGIN not in after and hooks.MARK_END not in after
    assert after.startswith("export EDITOR=vim\n")
    assert hooks.uninstall(shell="zsh", home=tmp_path) is False


def test_install_bash_block_contents(tmp_path):
    rc = hooks.install(shell="bash", home=tmp_path)
    text = rc.read_text(encoding="utf-8")
    assert "trap '__seance_debug' DEBUG" in text
    assert "PROMPT_COMMAND" in text
    assert "seance guard" in text
    assert "disown" in text


def test_install_creates_missing_rc(tmp_path):
    rc = hooks.install(shell="zsh", home=tmp_path)
    assert rc.exists()
    assert hooks.MARK_BEGIN in rc.read_text(encoding="utf-8")


def test_uninstall_repairs_broken_block(tmp_path):
    rc = tmp_path / ".bashrc"
    rc.write_text(f"keep me\n{hooks.MARK_BEGIN}\nbroken middle\n", encoding="utf-8")
    assert hooks.uninstall(shell="bash", home=tmp_path) is True
    text = rc.read_text(encoding="utf-8")
    assert text == "keep me\n"


def test_detect_shell_prefers_env(monkeypatch, tmp_path):
    monkeypatch.setenv("SHELL", "/bin/zsh")
    assert hooks.detect_shell() == "zsh"
    monkeypatch.setenv("SHELL", "/usr/bin/bash")
    assert hooks.detect_shell() == "bash"


def test_rendered_blocks_have_no_template_tokens():
    for block in (hooks.ZSH_BLOCK, hooks.BASH_BLOCK):
        rendered = hooks._render(block)
        assert "@CASE_PATTERNS@" not in rendered
        assert "seance guard" in rendered
