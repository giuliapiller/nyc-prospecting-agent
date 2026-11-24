import pytest

from prospecting import __main__ as cli


@pytest.fixture
def calls(monkeypatch, tmp_path):
    seen = []
    monkeypatch.setattr(cli.phase1, "run", lambda *a: seen.append("phase1"))
    monkeypatch.setattr(cli.github, "run", lambda *a: seen.append("phase2"))
    monkeypatch.setattr(cli.phase3, "run", lambda *a: seen.append("phase3"))
    monkeypatch.chdir(tmp_path)
    return seen


def test_run_executes_all_phases_in_order(calls, monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "x")
    cli.main(["run", "--out", "out"])
    assert calls == ["phase1", "phase2", "phase3"]


def test_run_without_token_fails_before_any_work(calls, monkeypatch):
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    with pytest.raises(SystemExit):
        cli.main(["run", "--out", "out"])
    assert calls == []


def test_skip_github_reuses_last_scan(calls, monkeypatch, tmp_path):
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    (tmp_path / "out").mkdir()
    (tmp_path / "out" / "phase2_github.csv").write_text("company\n")
    cli.main(["run", "--out", "out", "--skip-github"])
    assert calls == ["phase1", "phase3"]
