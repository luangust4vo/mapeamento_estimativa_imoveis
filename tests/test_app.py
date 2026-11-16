"""Artefatos do app, simulador e interface Streamlit, com dados sintéticos e sem rede."""
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from sklearn.pipeline import Pipeline
from sklearn.tree import DecisionTreeClassifier

from geo_helpers import write_bairros_gpkg
from imoveis_pg.app.artefatos import build_artifacts
from imoveis_pg.app.simulador import Simulator
from imoveis_pg.modelagem.classificacao import preprocessor

APP = Path(__file__).parents[1] / "src" / "imoveis_pg" / "app" / "streamlit_app.py"
# Retângulos de geo_helpers: Uvaranas (-50.13..-50.09, -25.12..-25.08), Cara Cara (..., -25.16..-25.12)
SPOTS = {"Uvaranas": (-25.10, -50.11, 900), "Cara Cara": (-25.14, -50.12, 2500)}


def fast_specs(seed):
    tree = Pipeline([("prep", preprocessor()), ("clf", DecisionTreeClassifier(random_state=seed))])
    return {"mlp": (tree, {"clf__max_depth": [3]})}


def records(listing, n=90, seed=0):
    rng = np.random.default_rng(seed)
    rows = []
    for i in range(n):
        bairro = list(SPOTS)[i % 2]
        lat, lon, base = SPOTS[bairro]
        area = float(rng.uniform(40, 300))
        suites = "" if area < 120 else str(int(rng.integers(1, 3)))
        rows.append(dict(listing, id=f"s{i}", url=f"https://example.test/{i}", bairro=bairro, endereco=f"Rua {i}, 1",
                         latitude=f"{lat + rng.normal(0, .004):.6f}".replace(".", ","),
                         longitude=f"{lon + rng.normal(0, .004):.6f}".replace(".", ","),
                         area_m2=f"{area:.0f}", quartos=str(int(1 + area // 80)), banheiros=str(int(1 + area // 120)),
                         vagas="1", suites=suites, aluguel=f"{base + 18 * area:.0f}", precisao_localizacao="exata"))
    return rows


@pytest.fixture(scope="module")
def artifacts(tmp_path_factory):
    import csv
    root = tmp_path_factory.mktemp("app")
    from conftest import COLUMNS
    base = dict(zip(COLUMNS, [""] * len(COLUMNS)), fonte="Sintética", data_coleta="2026-11-09", tipo="Casa",
                finalidade="Locação", periodicidade_iptu="")
    rows = records(base)
    source = root / "base.csv"
    with source.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]), delimiter=";")
        writer.writeheader()
        writer.writerows(rows)
    gpkg = write_bairros_gpkg(root / "b.gpkg")
    out = root / "artefatos"
    meta = build_artifacts(source, gpkg, out, specs=fast_specs(42))
    return out, meta


def test_build_writes_artifacts_without_addresses(artifacts):
    out, meta = artifacts
    assert {p.name for p in out.iterdir()} == {"anuncios.csv", "bairros.geojson", "modelos.joblib", "metadados.json"}
    listings = pd.read_csv(out / "anuncios.csv")
    assert "endereco" not in listings and len(listings) == 90 and listings.elegivel.all()
    assert set(listings.comparacao) <= {"dentro do padrão", "acima do padrão", "abaixo do padrão"}
    assert listings.perfil.str.startswith(("1 ·", "2 ·", "3 ·")).all()
    assert meta["n_casas_modelo"] == 90 and len(meta["faixas"]["limites"]) == 2
    assert meta["faixa_treino_atributos"]["quartos"] == [int(listings.quartos.min()), int(listings.quartos.max())]
    with pytest.raises(ValueError, match="já existe"):
        build_artifacts(out / "x.csv", out / "b.gpkg", out)


@pytest.fixture(scope="module")
def sim(artifacts):
    return Simulator(artifacts[0])


def test_simulation_inside_city(sim):
    res = sim.simulate(-25.10, -50.11, area_m2=60, quartos=1, banheiros=1, vagas=1, suites=0)
    assert res.disponivel and res.bairro == "Uvaranas"
    assert res.faixa in sim.band_names and sum(res.probabilidades.values()) == pytest.approx(1)
    assert len(res.comparaveis) == 5 and "url" in res.comparaveis
    assert res.anuncios_proximos > 5 and res.perfil.startswith(("1 ·", "2 ·", "3 ·"))
    assert not any("extrapolação" in w for w in res.avisos)


def test_zero_suites_and_garage_match_training_encoding(sim):
    zero = sim.simulate(-25.10, -50.11, area_m2=60, quartos=1, banheiros=1, vagas=0, suites=0)
    missing = sim.simulate(-25.10, -50.11, area_m2=60, quartos=1, banheiros=1, vagas=None, suites=None)
    assert zero.probabilidades == missing.probabilidades


def test_outside_bairros_is_unavailable(sim):
    res = sim.simulate(-25.40, -50.40, area_m2=80, quartos=2)
    assert not res.disponivel and res.faixa is None and "fora dos bairros" in res.avisos[0]


def test_warnings_for_extrapolation_and_low_coverage(sim):
    res = sim.simulate(-25.155, -50.095, area_m2=3000, quartos=15, banheiros=1)
    text = " ".join(res.avisos)
    assert "Área (m²) = 3000" in text and "Quartos = 15" in text
    assert "Baixa cobertura" in text


def test_streamlit_app_runs_and_simulates(artifacts, monkeypatch):
    from streamlit.testing.v1 import AppTest
    monkeypatch.setenv("IMOVEIS_PG_APP_DIR", str(artifacts[0]))
    at = AppTest.from_file(str(APP), default_timeout=60).run()
    assert not at.exception
    assert at.title[0].value == "Aluguéis de casas em Ponta Grossa"
    assert [m.value for m in at.metric][:1] == ["90"]
    at.session_state["ponto"] = (-25.10, -50.11)
    at.run()
    next(b for b in at.button if b.label == "Estimar aluguel").click().run()
    assert not at.exception
    labels = [m.label for m in at.metric]
    assert "Faixa estimada" in labels and "Bairro oficial" in labels
    assert any(m.value == "Uvaranas" for m in at.metric)


def test_filters_live_in_map_tab_and_recalculate(artifacts, monkeypatch):
    from streamlit.testing.v1 import AppTest
    monkeypatch.setenv("IMOVEIS_PG_APP_DIR", str(artifacts[0]))
    at = AppTest.from_file(str(APP), default_timeout=60).run()
    assert len(at.sidebar) == 0  # sem barra lateral: filtros ficam só na aba do mapa
    finalidade = next(s for s in at.selectbox if s.label == "Finalidade")
    assert finalidade.value == "Locação" and finalidade.disabled
    next(m for m in at.multiselect if m.label == "Bairros").set_value(["Uvaranas"]).run()
    assert not at.exception
    assert next(m for m in at.metric if m.label == "Anúncios filtrados").value == "45"


def test_public_base_has_no_address_and_rounded_coordinates(tmp_path, write_csv, listing):
    from imoveis_pg.__main__ import main
    from imoveis_pg.exportacao import public_table

    listing.update(endereco="Rua Secreta, 123", latitude="-25,1234567", longitude="-50,1234567",
                   bairro="Uvaranas", cep="84000123", logradouro="Rua Secreta", numero="123")
    source = write_csv([listing], fields=list(listing))
    out = tmp_path / "publico" / "base.csv"
    assert main(["export-base", str(source), "--output", str(out),
                 "--bairros", str(write_bairros_gpkg(tmp_path / "b.gpkg"))]) == 0
    text = out.read_text(encoding="utf-8")
    assert "Secreta" not in text and "84000123" not in text and "1234567" not in text
    row = pd.read_csv(out).iloc[0]
    assert (row.latitude, row.longitude) == (-25.123, -50.123) and row.bairro_oficial == "Uvaranas"
    manifest = json.loads((out.parent / "base.manifest.json").read_text(encoding="utf-8"))
    assert manifest["linhas"] == 1 and "endereco" not in manifest["colunas"]
    # A lista de colunas permitidas é a proteção; a checagem barra quem incluir uma coluna proibida nela.
    import imoveis_pg.exportacao as exportacao
    frame = pd.DataFrame({"id": [1], "latitude": [0.0], "longitude": [0.0], "data_coleta": ["2026-11-09"],
                          "fonte": ["x"], "endereco_original": ["Rua Secreta, 123"]})
    assert "endereco_original" not in public_table(frame)
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(exportacao, "PUBLIC_COLUMNS", exportacao.PUBLIC_COLUMNS + ["endereco_original"])
        with pytest.raises(ValueError, match="proibidas"):
            exportacao.public_table(frame)
