import urllib.error

from seance import config, ghost


def make_cfg(**kw) -> config.Config:
    return config.Config(api_key="test-key", **kw)


def test_ask_returns_trimmed_reply(seance_home, monkeypatch):
    calls = []

    def fake_post(url, payload, headers, timeout):
        calls.append((url, payload, headers, timeout))
        return {"choices": [{"message": {"content": "  One. Two. Three.  "}}]}

    out = ghost.ask_ghost(make_cfg(), "ctx", post=fake_post)

    assert out == "One. Two."
    url, payload, headers, timeout = calls[0]
    assert url == f"{config.DEFAULT_BASE_URL}/chat/completions"
    assert payload["model"] == config.DEFAULT_MODEL
    assert payload["messages"][0]["role"] == "system"
    assert payload["messages"][1]["content"] == "ctx"
    assert headers["Authorization"] == "Bearer test-key"
    assert timeout == 2.0


def test_env_key_is_used_when_config_empty(seance_home, monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "env-key")
    seen = {}

    def fake_post(url, payload, headers, timeout):
        seen["auth"] = headers["Authorization"]
        return {"choices": [{"message": {"content": "boo."}}]}

    ghost.ask_ghost(config.Config(api_key=""), "ctx", post=fake_post)
    assert seen["auth"] == "Bearer env-key"


def test_no_key_never_touches_the_network(seance_home, monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)

    def boom(*a):
        raise AssertionError("network must not be touched without a key")

    assert ghost.ask_ghost(config.Config(api_key=""), "ctx", post=boom) is None


def test_timeout_yields_none(seance_home, monkeypatch):
    def fake_post(*a):
        raise TimeoutError()

    assert ghost.ask_ghost(make_cfg(), "ctx", post=fake_post) is None


def test_rate_limit_sets_cooldown_and_skips_next_call(seance_home):
    calls = []

    def fake_post(*a):
        calls.append(1)
        raise urllib.error.HTTPError("http://x", 429, "Too Many Requests", None, None)

    cfg = make_cfg()
    assert ghost.ask_ghost(cfg, "ctx", post=fake_post) is None
    assert ghost._rate_limited() is True
    assert ghost.ask_ghost(cfg, "ctx", post=fake_post) is None
    assert len(calls) == 1  # cooldown skipped the second attempt entirely


def test_server_error_sets_cooldown_too(seance_home):
    def fake_post(*a):
        raise urllib.error.HTTPError("http://x", 503, "Service Unavailable", None, None)

    ghost.ask_ghost(make_cfg(), "ctx", post=fake_post)
    assert ghost._rate_limited() is True


def test_auth_error_does_not_set_cooldown(seance_home):
    def fake_post(*a):
        raise urllib.error.HTTPError("http://x", 401, "Unauthorized", None, None)

    ghost.ask_ghost(make_cfg(), "ctx", post=fake_post)
    assert ghost._rate_limited() is False


def test_malformed_reply_yields_none(seance_home):
    for body in ({"choices": []}, {}, {"choices": [{"message": {}}]},
                 {"choices": [{"message": {"content": None}}]}):
        assert ghost.ask_ghost(make_cfg(), "ctx",
                               post=lambda *a, b=body: b) is None


def test_cooldown_expires(seance_home):
    ghost._mark_rate_limited()
    assert ghost._rate_limited() is True
    assert ghost._rate_limited(now=ghost.time.time() + ghost.RATELIMIT_COOLDOWN + 1) is False


# --- trim_reply ---------------------------------------------------------------

def test_trim_keeps_at_most_two_sentences():
    assert ghost.trim_reply("A one. B two? C three!") == "A one. B two?"


def test_trim_collapses_newlines_and_fences():
    assert ghost.trim_reply("```\nhello there.\n```") == "hello there."


def test_trim_caps_length():
    out = ghost.trim_reply("x" * 500)
    assert len(out) <= 240
    assert out.endswith("…")


def test_trim_strips_leading_name():
    assert ghost.trim_reply("Agnes: hello") == "hello"
