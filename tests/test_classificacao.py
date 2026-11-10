"""Classificação por faixas com dados sintéticos de sinal conhecido (área e bairro definem o aluguel)."""
import json

import numpy as np
import pandas as pd
import pytest
from sklearn.dummy import DummyClassifier
from sklearn.pipeline import Pipeline
from sklearn.tree import DecisionTreeClassifier

from imoveis_pg.modelagem import classificacao as clf
from imoveis_pg.modelagem.classificacao import (SCORING, BairroModeClassifier, QuantileBandClassifier,
                                                holdout_errors, preprocessor, run_experiment)
from imoveis_pg.modelagem.dataset import CENTRO, build_dataset, distance_km

BASE = {"Uvaranas": 800, "Cara Cara": 1500, "Colônia Dona Luíza": 3000}


def snapshot(n=150, seed=0):
    rng = np.random.default_rng(seed)
    bairro = rng.choice(list(BASE), n)
    area = rng.uniform(40, 300, n)
    frame = pd.DataFrame({
        "id": [f"s{i}" for i in range(n)], "fonte": "Sintética", "grupo_imovel": [f"g{i}" for i in range(n)],
        "elegivel_preliminar": True, "coordenadas_validas": True, "bairro_oficial": bairro,
        "subtipo": rng.choice(["Casa", "Sobrado", "Casa/Sobrado em Condomínio"], n),
        "area_m2": area, "quartos": rng.integers(1, 5, n).astype(float), "suites": np.nan,
        "banheiros": rng.integers(1, 4, n).astype(float), "vagas": rng.integers(0, 3, n).astype(float),
        "latitude": -25.09 + rng.normal(0, .02, n), "longitude": -50.16 + rng.normal(0, .02, n),
        "aluguel": [BASE[b] for b in bairro] + 15 * area + rng.normal(0, 150, n),
        "precisao_localizacao": "exata",
    })
    frame.loc[:9, "grupo_imovel"] = [f"dup{i // 2}" for i in range(10)]  # 5 pares do mesmo imóvel
    return frame


def small_specs(seed):
    return {
        "baseline_classe_frequente": (DummyClassifier(strategy="most_frequent"), {}),
        "baseline_bairro": (BairroModeClassifier(), {}),
        "arvore_decisao": (Pipeline([("prep", preprocessor()), ("clf", DecisionTreeClassifier(random_state=seed))]),
                           {"clf__max_depth": [3, 6]}),
    }


@pytest.fixture(scope="module")
def data():
    return build_dataset(snapshot())


@pytest.fixture(scope="module")
def experiment(data):
    return run_experiment(data, specs=small_specs(42))


def test_bands_come_from_training_rent_only():
    model = QuantileBandClassifier(DummyClassifier(), n_bands=3).fit(pd.DataFrame({"x": range(9)}), range(1, 10))
    assert np.allclose(model.thresholds_, [11 / 3, 19 / 3])
    assert model.to_bands([1, 3.6667, 6, 100]).tolist() == [0, 1, 1, 2]
    # O scorer converte o aluguel de validação com os limites do treino, sem recalcular.
    X_val = pd.DataFrame({"x": [0, 1]})
    assert SCORING["accuracy"](model, X_val, [100, 200]) == 0.0


def test_bairro_baseline_uses_mode_and_global_fallback():
    X = pd.DataFrame({"bairro_oficial": ["A", "A", "A", "B", "B"]})
    model = BairroModeClassifier().fit(X, [0, 0, 1, 2, 2])
    assert model.predict(pd.DataFrame({"bairro_oficial": ["A", "B", "Novo"]})).tolist() == [0, 2, 0]


def test_dataset_filters_and_has_no_rent_derived_features():
    frame = snapshot(20)
    frame.loc[0, "elegivel_preliminar"] = False
    frame.loc[1, "coordenadas_validas"] = False
    frame.loc[2, "bairro_oficial"] = None
    frame.loc[3, ["latitude", "longitude"]] = CENTRO
    d = build_dataset(frame)
    assert d.excluded == {"nao_elegivel": 1, "sem_coordenadas": 1, "sem_bairro_oficial": 1} and len(d.X) == 17
    assert not any("aluguel" in c or "custo" in c for c in d.X.columns)
    assert d.X.loc[3, "distancia_centro_km"] == pytest.approx(0)
    assert set(d.X.subtipo) <= {"casa", "sobrado", "condominio"}
    assert distance_km([-25.0], [-50.1601812])[0] == pytest.approx(9.95, abs=0.05)


def test_duplicates_stay_on_one_side_and_bands_are_balanced(data, experiment):
    dev_groups = set(data.groups.loc[experiment.dev_index])
    test_groups = set(data.groups.loc[experiment.test_index])
    assert not dev_groups & test_groups
    assert len(experiment.test_index) == pytest.approx(0.2 * len(data.X), abs=3)
    counts = np.bincount(experiment.results["arvore_decisao"].estimator.to_bands(data.y.loc[experiment.dev_index]))
    assert counts.max() - counts.min() <= 2


def test_selection_uses_cv_and_signal_beats_baselines(experiment):
    cv = {n: r.cv["balanced_accuracy"][0] for n, r in experiment.results.items()}
    assert experiment.selected == max(cv, key=cv.get) == "arvore_decisao"
    assert cv["arvore_decisao"] > cv["baseline_classe_frequente"] + 0.3
    assert cv["baseline_classe_frequente"] == pytest.approx(1 / 3)
    table = experiment.metrics_table()
    assert table.selecionado.sum() == 1 and {"cv_f1_macro_media", "teste_erro_grave"} <= set(table.columns)


def test_holdout_errors_describe_test_rows(data, experiment):
    errors = holdout_errors(experiment, data)
    assert len(errors) == len(experiment.test_index)
    assert set(errors.faixa_real) <= {"baixa", "média", "alta"}
    assert errors.distancia_faixas.abs().is_monotonic_decreasing
    assert "endereco" not in errors


def test_full_specs_compare_required_models():
    specs = clf.model_specs(0)
    assert {"arvore_decisao", "knn", "svm", "mlp", "baseline_bairro", "baseline_classe_frequente"} == set(specs)
    assert all(grid for name, (_, grid) in specs.items() if not name.startswith("baseline"))


def test_invalid_band_count_is_rejected(data):
    with pytest.raises(ValueError):
        run_experiment(data, n_bands=7, specs=small_specs(0))


def test_cli_classify_writes_report(tmp_path, monkeypatch, write_csv, listing):
    from geo_helpers import write_bairros_gpkg
    from imoveis_pg.__main__ import main

    monkeypatch.setattr(clf, "model_specs", small_specs)
    synthetic = snapshot(60, seed=1)
    boxes = {"Uvaranas": (-25.10, -50.11), "Cara Cara": (-25.14, -50.12), "Colônia Dona Luíza": (-25.10, -50.18)}
    records = []
    for row in synthetic.itertuples():
        lat, lon = boxes[row.bairro_oficial]
        records.append(dict(listing, id=row.id, url=f"https://example.test/{row.id}", bairro=row.bairro_oficial,
                            latitude=f"{lat:.4f}".replace(".", ","), longitude=f"{lon:.4f}".replace(".", ","),
                            area_m2=f"{row.area_m2:.0f}", aluguel=f"{row.aluguel:.0f}", quartos=str(int(row.quartos)),
                            endereco=f"Rua {row.id}", precisao_localizacao="exata"))
    source = write_csv(records, fields=list(records[0]))
    gpkg = write_bairros_gpkg(tmp_path / "b.gpkg")
    out = tmp_path / "clf"
    assert main(["classify", str(source), "--output", str(out), "--bairros", str(gpkg), "--repeticoes", "2"]) == 0
    for name in ["metricas.csv", "faixas.json", "erros_teste.csv", "erros_por_bairro.csv", "importancia_atributos.csv",
                 "matrizes_confusao.png", "comparacao_modelos.png", "importancia_atributos.png",
                 "modelo_selecionado.joblib", "manifest.json", "estabilidade.csv", "estabilidade.png"]:
        assert (out / name).exists(), name
    manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["n_casas"] == 60 and manifest["status"] == "complete" and manifest["semente"] == 42
    assert manifest["estabilidade"]["sementes"] == [0, 1]
    assert pd.read_csv(out / "estabilidade_execucoes.csv").groupby("semente").selecionado.sum().tolist() == [1, 1]
    assert main(["classify", str(source), "--output", str(out), "--bairros", str(gpkg)]) == 2


def test_split_groups_join_identical_listings_and_duplicates():
    frame = snapshot(20)  # linhas 0-9 formam 5 pares de duplicatas (0-1, 2-3, ...)
    frame.loc[[12, 13, 14], ["bairro_oficial", "area_m2", "quartos", "aluguel"]] = [["Uvaranas", 68.0, 3.0, 1900.0]] * 3
    groups = build_dataset(frame).groups
    assert groups[0] == groups[1] != groups[2]     # mesmo grupo_imovel (duplicata da auditoria)
    assert groups[12] == groups[13] == groups[14]  # mesmo bairro, área, quartos e aluguel
    assert groups[15] != groups[16] and groups[11] != groups[12]


def test_stability_repeats_whole_experiment(data):
    runs = clf.stability(data, seeds=[0, 1, 2], specs_factory=small_specs)
    assert len(runs) == 3 * 3 and runs.groupby("semente").selecionado.sum().eq(1).all()
    summary = clf.stability_summary(runs)
    assert summary.iloc[0].modelo == "arvore_decisao" and summary.vezes_selecionado.sum() == 3
