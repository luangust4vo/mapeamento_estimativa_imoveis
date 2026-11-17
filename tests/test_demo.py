"""Comando demo: só executa as etapas que faltam."""
from datetime import date

from imoveis_pg import demo

TODAY = date(2026, 11, 20)


def touch(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("x")
    return path


def commands(steps):
    return [s[0] for s in steps]


def test_fresh_folder_collects_merges_builds_and_opens(tmp_path):
    steps = demo.plan(tmp_path, today=TODAY)
    assert commands(steps) == ["collect"] * 4 + ["merge", "build-app", "app"]
    assert steps[4][-1] == str(tmp_path / "base_2026-11-20.csv")
    assert steps[5][-1] == str(tmp_path / "app" / "2026-11-20")


def test_ready_data_only_opens_the_app(tmp_path):
    touch(tmp_path / "base_2026-11-09.csv")
    touch(tmp_path / "base_2026-10-01.csv")
    touch(tmp_path / "app" / "2026-11-09" / "modelos.joblib")
    steps = demo.plan(tmp_path, today=TODAY, port=9000)
    assert steps == [["app", "--artefatos", str(tmp_path / "app" / "2026-11-09"), "--port", "9000"]]


def test_base_without_artifacts_builds_from_latest_base(tmp_path):
    touch(tmp_path / "base_2026-11-09.csv")
    touch(tmp_path / "base_2026-10-01.csv")
    touch(tmp_path / "base_extra.csv")  # nome fora do padrão é ignorado
    steps = demo.plan(tmp_path, today=TODAY)
    assert commands(steps) == ["build-app", "app"] and steps[0][1] == str(tmp_path / "base_2026-11-09.csv")


def test_interrupted_collection_resumes_missing_sources(tmp_path):
    touch(tmp_path / "torreblanca_2026-11-20.csv")
    touch(tmp_path / "portaldez_2026-11-20.csv")
    steps = demo.plan(tmp_path, today=TODAY)
    assert [s[1] for s in steps if s[0] == "collect"] == ["granada", "vilanova"]
    assert len(steps[2]) == 2 + 4 + 1  # merge com as 4 fontes, inclusive as já coletadas


def test_refresh_collects_today_even_with_old_base(tmp_path):
    touch(tmp_path / "base_2026-11-09.csv")
    touch(tmp_path / "app" / "2026-11-09" / "modelos.joblib")
    assert commands(demo.plan(tmp_path, today=TODAY, refresh=True)) == ["collect"] * 4 + ["merge", "build-app", "app"]
    touch(tmp_path / "base_2026-11-20.csv")
    assert commands(demo.plan(tmp_path, today=TODAY, refresh=True)) == ["build-app", "app"]


def test_run_stops_at_first_failure(tmp_path, capsys):
    touch(tmp_path / "base_2026-11-09.csv")
    calls = []

    def runner(step):
        calls.append(step[0])
        return 2 if step[0] == "build-app" else 0

    assert demo.run(tmp_path, today=TODAY, runner=runner) == 2
    assert calls == ["build-app"] and "não serão repetidas" in capsys.readouterr().out


def test_cli_demo_with_ready_data_only_calls_app(tmp_path, monkeypatch):
    from imoveis_pg import __main__ as cli
    touch(tmp_path / "base_2026-11-09.csv")
    touch(tmp_path / "app" / "2026-11-09" / "modelos.joblib")
    seen = []
    monkeypatch.setattr(cli, "_run_app", lambda args: seen.append(args.artefatos) or 0)
    assert cli.main(["demo", "--dados", str(tmp_path)]) == 0
    assert seen == [tmp_path / "app" / "2026-11-09"]
