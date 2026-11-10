"""Agrupamento com dados sintéticos de estrutura conhecida."""
import json

import numpy as np
import pandas as pd
import pytest

from imoveis_pg.modelagem import agrupamento as agr
from imoveis_pg.modelagem.dataset import ModelData

# Três perfis bem separados: (área, quartos, banheiros, suítes, aluguel)
PROFILES = [(55, 2, 1, np.nan, 1100), (150, 3, 2, 1, 3800), (380, 4, 5, 2, 10000)]


def make_data(per_profile=30, seed=0, hotspots=((-25.09, -50.16), (-25.12, -50.12))):
    rng = np.random.default_rng(seed)
    rows = []
    for p, (area, rooms, baths, suites, rent) in enumerate(PROFILES):
        for _ in range(per_profile):
            lat, lon = hotspots[p % len(hotspots)] if p < 2 else (-25.05 + rng.uniform(-.03, .03),
                                                                 -50.20 + rng.uniform(-.03, .03))
            rows.append({"area_m2": area * rng.uniform(.9, 1.1), "quartos": rooms, "banheiros": baths,
                         "vagas": 1.0, "suites": suites, "aluguel": rent * rng.uniform(.9, 1.1),
                         "latitude": lat + rng.normal(0, .0008), "longitude": lon + rng.normal(0, .0008),
                         "bairro_oficial": ["Neves", "Centro", "Chapada"][p], "subtipo": "casa", "perfil_real": p})
    frame = pd.DataFrame(rows)
    frame["distancia_centro_km"] = 1.0
    X = frame.drop(columns=["aluguel", "perfil_real"])
    desc = frame.assign(id=[f"s{i}" for i in range(len(frame))], fonte="Sintética")
    return ModelData(desc, X, frame.aluguel, pd.Series(range(len(frame)), dtype=str), {}), frame.perfil_real


@pytest.fixture(scope="module")
def synthetic():
    return make_data()


@pytest.fixture(scope="module")
def profiles(synthetic):
    return agr.cluster_profiles(synthetic[0], stability_runs=5)


def test_profile_table_treats_missing_suite_as_none(synthetic):
    data, _ = synthetic
    table = agr.profile_table(data)
    assert list(table.columns) == agr.PROFILE_FEATURES
    assert table.loc[0, "tem_suite"] == 0 and table.loc[40, "tem_suite"] == 1
    data.X.loc[1, "banheiros"] = np.nan
    assert 1 not in agr.profile_table(data).index  # sem banheiros: fora do perfil, sem imputar
    data.X.loc[1, "banheiros"] = 1


def test_kmeans_recovers_known_profiles(synthetic, profiles):
    _, truth = synthetic
    assert profiles.chosen["kmeans"]["k"] == 3
    labels = profiles.labels["kmeans"]
    assert agr.adjusted_rand_score(truth.loc[labels.index], labels) == pytest.approx(1)
    sel = profiles.selection
    assert {"kmeans", "ward", "dbscan"} <= set(sel.algoritmo) and sel.k.min() == 2
    assert profiles.chosen["kmeans"]["estabilidade"] >= agr.MIN_STABILITY


def test_dbscan_choice_respects_noise_limit(profiles):
    chosen = profiles.chosen["dbscan"]
    assert chosen["ruido"] <= agr.MAX_NOISE and chosen["n_grupos"] >= 2
    assert len(profiles.k_distance) == len(profiles.table)


def test_groups_are_numbered_by_rent_and_described(synthetic, profiles):
    data, _ = synthetic
    ordered = agr.order_by_rent(profiles.labels["kmeans"], data.y)
    summary = agr.describe_groups(ordered, data)
    assert summary.grupo.tolist() == [1, 2, 3]
    assert summary.aluguel_mediano.is_monotonic_increasing
    assert summary.bairro_principal.tolist() == ["Neves", "Centro", "Chapada"]
    assert summary.com_suite.tolist() == [0, 1, 1]
    noisy = agr.order_by_rent(pd.Series([5, 5, -1, 2]), pd.Series([10.0, 10.0, 1.0, 1.0]))
    assert noisy.tolist() == [2, 2, -1, 1]


def test_spatial_dbscan_uses_meters(synthetic):
    data, _ = synthetic
    result = agr.cluster_space(data, eps_m=600, min_samples=6)
    groups = result.labels
    assert result.summary.shape[0] >= 2
    assert groups[:30].nunique() == 1 and groups[30:60].nunique() == 1 and groups[0] != groups[30]
    assert (groups[60:] < 0).mean() > 0.5  # pontos espalhados por ~6 km viram dispersos
    tight = agr.cluster_space(data, eps_m=20, min_samples=6)
    assert tight.noise > 0.9  # 20 m é menor que o espalhamento (~90 m) dos focos
    assert set(result.sensitivity.columns) == {"eps_m", "min_samples", "n_grupos", "ruido", "ari_bairros"}


def test_profile_by_bairro_proportions(synthetic, profiles):
    data, _ = synthetic
    table, ari = agr.profile_by_bairro(agr.order_by_rent(profiles.labels["kmeans"], data.y), data)
    assert ari == pytest.approx(1) and table.drop(columns="n").sum(axis=1).round(6).eq(1).all()


def test_cli_cluster_writes_report(tmp_path, write_csv, listing, monkeypatch):
    from geo_helpers import write_bairros_gpkg
    from imoveis_pg.__main__ import main

    original = agr.cluster_profiles
    monkeypatch.setattr(agr, "cluster_profiles", lambda data, seed=42: original(data, seed=seed, stability_runs=3))
    data, _ = make_data(per_profile=15, hotspots=((-25.10, -50.11), (-25.14, -50.12)))
    records = []
    for i in data.X.index:
        x = data.X.loc[i]
        records.append(dict(listing, id=f"s{i}", url=f"https://example.test/{i}", bairro="Uvaranas",
                            endereco=f"Rua {i}", latitude=f"{x.latitude:.6f}".replace(".", ","),
                            longitude=f"{x.longitude:.6f}".replace(".", ","), area_m2=f"{x.area_m2:.0f}",
                            quartos=str(int(x.quartos)), banheiros=str(int(x.banheiros)),
                            suites="" if np.isnan(x.suites) else str(int(x.suites)),
                            aluguel=f"{data.y[i]:.0f}", precisao_localizacao="exata"))
    source = write_csv(records, fields=list(records[0]))
    out = tmp_path / "agr"
    gpkg = write_bairros_gpkg(tmp_path / "b.gpkg")
    assert main(["cluster", str(source), "--output", str(out), "--bairros", str(gpkg)]) == 0
    for name in ["perfis_selecao.csv", "perfis_resumo.csv", "perfis_rotulos.csv", "perfis_por_bairro.csv",
                 "regioes_resumo.csv", "regioes_sensibilidade.csv", "regioes_rotulos.csv", "perfis_selecao.png",
                 "perfis_kdistancia.png", "perfis_dispersao.png", "regioes_mapa.png", "manifest.json"]:
        assert (out / name).exists(), name
    manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["perfis"]["escolhidos"]["kmeans"]["k"] == 3 and manifest["status"] == "complete"
    assert main(["cluster", str(source), "--output", str(out), "--bairros", str(gpkg)]) == 2
