import pytest


@pytest.fixture
def seance_home(tmp_path, monkeypatch):
    """Point SEANCE_HOME at a throwaway dir for the duration of a test."""
    home = tmp_path / "seance-home"
    home.mkdir()
    monkeypatch.setenv("SEANCE_HOME", str(home))
    return home
