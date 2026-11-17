"""Regressão com dados sintéticos de sinal conhecido (aluguel cresce com área e depende do bairro)."""
import json

import numpy as np
import pandas as pd
import pytest
from sklearn.pipeline import Pipeline
from sklearn.tree import DecisionTreeRegressor

from imoveis_pg.modelagem import regressao as reg
from imoveis_pg.modelagem.classificacao import preprocessor
from imoveis_pg.modelagem.dataset import build_dataset
from test_classificacao import snapshot


def small_specs(seed):
    return {
        "baseline_mediana_bairro": (reg.BairroMedianRegressor(), {}),
        "arvore_decisao": (reg.log_target(Pipeline([("prep", preprocessor()),
                                                    ("reg", DecisionTreeRegressor(random_state=seed))])),
                           {"regressor__reg__max_depth": [4, 8]}),
    }


@pytest.fixture(scope="module")
def data():
    return build_dataset(snapshot(160))


@pytest.fixture(scope="module")
def experiment(data):
    return reg.run_regression(data, specs=small_specs(42))


def test_baseline_uses_bairro_median_and_global_fallback():
    X = pd.DataFrame({"bairro_oficial": ["A", "A", "A", "B"]})
    model = reg.BairroMedianRegressor().fit(X, [100, 200, 900, 50])
    assert model.predict(pd.DataFrame({"bairro_oficial": ["A", "B", "Novo"]})).tolist() == [200, 50, 150]


def test_log_target_predicts_in_reais():
    X = pd.DataFrame({"x": np.arange(50.0)})
    y = np.exp(7 + X.x / 25)
    model = reg.log_target(DecisionTreeRegressor(max_depth=8)).fit(X, y)
    assert model.predict(X[:3]) == pytest.approx(y[:3], rel=0.05)


def test_metrics_in_reais():
    m = reg.metrics([1000, 2000], [1100, 1800])
    assert m["mae"] == 150 and m["mape"] == pytest.approx(0.1) and m["erro_mediano"] == 150


def test_model_beats_baseline_and_is_selected_by_cv(experiment):
    cv = {n: r.cv["mae"][0] for n, r in experiment.results.items()}
    assert experiment.selected == min(cv, key=cv.get) == "arvore_decisao"
    assert cv["arvore_decisao"] < 0.7 * cv["baseline_mediana_bairro"]
    assert all(r.cv["mae"][0] > 0 for r in experiment.results.values())  # sinal natural, não negativo


def test_duplicates_stay_on_one_side(data, experiment):
    assert not set(data.groups.loc[experiment.dev_index]) & set(data.groups.loc[experiment.test_index])


def test_interval_from_out_of_fold_residuals(experiment):
    low, high = experiment.interval_log
    assert low < 0 < high and 0.5 <= experiment.interval_coverage <= 1


def test_residual_analysis_by_band_and_bairro(data, experiment):
    table, by_bairro, by_band = reg.residual_analysis(experiment, data, [2000.0, 4000.0])
    assert len(table) == len(experiment.test_index) and "previsto" in table and "endereco" not in table
    assert set(by_band.index) <= {"baixa", "média", "alta"} and by_band.n.sum() == len(table)
    assert by_bairro.n.sum() == len(table)


def test_stability_repeats_and_summarizes(data):
    runs = reg.regression_stability(data, seeds=[0, 1], specs_factory=small_specs)
    assert runs.groupby("semente").selecionado.sum().eq(1).all()
    summary = reg.stability_summary(runs)
    assert summary.iloc[0].modelo == "arvore_decisao" and summary.vezes_selecionado.sum() == 2


def test_cli_regress_writes_report(tmp_path, monkeypatch, write_csv, listing):
    from geo_helpers import write_bairros_gpkg
    from imoveis_pg.__main__ import main

    monkeypatch.setattr(reg, "regression_specs", small_specs)
    synthetic = snapshot(60, seed=1)
    boxes = {"Uvaranas": (-25.10, -50.11), "Cara Cara": (-25.14, -50.12), "Colônia Dona Luíza": (-25.10, -50.18)}
    records = [dict(listing, id=r.id, url=f"https://example.test/{r.id}", bairro=r.bairro_oficial,
                    latitude=f"{boxes[r.bairro_oficial][0]:.4f}".replace(".", ","),
                    longitude=f"{boxes[r.bairro_oficial][1]:.4f}".replace(".", ","),
                    area_m2=f"{r.area_m2:.0f}", aluguel=f"{r.aluguel:.0f}", quartos=str(int(r.quartos)),
                    endereco=f"Rua {r.id}", precisao_localizacao="exata") for r in synthetic.itertuples()]
    source = write_csv(records, fields=list(records[0]))
    out = tmp_path / "reg"
    gpkg = write_bairros_gpkg(tmp_path / "b.gpkg")
    assert main(["regress", str(source), "--output", str(out), "--bairros", str(gpkg), "--repeticoes", "2"]) == 0
    for name in ["metricas.csv", "erros_teste.csv", "erros_por_bairro.csv", "erros_por_faixa.csv",
                 "comparacao_modelos.png", "previsto_x_anunciado.png", "vies_por_faixa.png", "estabilidade.png",
                 "estabilidade.csv", "modelo_selecionado.joblib", "manifest.json"]:
        assert (out / name).exists(), name
    manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["status"] == "complete" and manifest["estabilidade"]["sementes"] == [0, 1]
    assert 0 <= manifest["intervalo"]["cobertura_teste"] <= 1
    assert main(["regress", str(source), "--output", str(out), "--bairros", str(gpkg)]) == 2
