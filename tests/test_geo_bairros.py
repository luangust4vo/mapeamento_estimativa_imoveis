"""Unificação de bairros com polígonos fictícios."""
import json

import pandas as pd
import pytest

from geo_helpers import write_bairros_gpkg
from imoveis_pg.__main__ import main
from imoveis_pg.geo.bairros import BairroResolver, assign_bairros, load_bairros


@pytest.fixture(scope="module")
def gpkg(tmp_path_factory):
    return write_bairros_gpkg(tmp_path_factory.mktemp("geo") / "bairros.gpkg")


@pytest.fixture(scope="module")
def resolver(gpkg):
    return BairroResolver(load_bairros(gpkg))


def test_load_keeps_municipality_and_dissolves_parts(resolver):
    assert resolver.names == ["Cara Cara", "Colônia Dona Luíza", "Uvaranas"]


def test_names_unify_spelling_variants(resolver):
    for spelling in ["CARÁ-CARÁ", "Cará- Cará", "cara cara", "Cará-cará"]:
        assert resolver.by_name(spelling) == "Cara Cara"
    assert resolver.by_name("COLÔNIA DONA LUZIA") == resolver.by_name("Colônia Dona Luiza") == "Colônia Dona Luíza"
    assert resolver.by_name("Vila Palmeirinha") is None and resolver.by_name(None) is None


def test_points_use_polygon_with_border_tolerance(resolver):
    found = resolver.by_points([-25.10, -25.15, -25.1225, -25.30, None], [-50.10, -50.10, -50.10, -50.10, -50.1])
    assert found.tolist() == ["Uvaranas", "Cara Cara", "Cara Cara", None, None]
    assert resolver.by_points([-25.1215], [-50.08])[0] is None  # ~1 km a leste: fora da tolerância
    assert resolver.distance_m(-25.10, -50.10, "Uvaranas") == 0
    assert 900 < resolver.distance_m(-25.10, -50.08, "Uvaranas") < 1100


def rows(*items):
    columns = ["linha", "bairro", "latitude", "longitude", "precisao_localizacao"]
    return pd.DataFrame([dict(zip(columns, (i + 2, *item))) for i, item in enumerate(items)])


def test_assignment_rules_and_conflicts(resolver):
    frame = rows(("Uvaranas", -25.15, -50.10, "exata"),         # exata: polígono vence
                 ("Uvaranas", -25.15, -50.10, "aproximada"),    # aproximada: nome oficial vence
                 ("Vila Palmeirinha", -25.10, -50.10, "aproximada"),
                 ("CARÁ-CARÁ", None, None, ""),
                 ("Lugar Nenhum", None, None, ""),
                 ("Cara Cara", -25.14, -50.12, "exata"))
    out, issues = assign_bairros(frame, resolver)
    assert out.bairro_oficial.tolist() == ["Cara Cara", "Uvaranas", "Uvaranas", "Cara Cara", None, "Cara Cara"]
    assert out.bairro_metodo.tolist() == ["poligono", "nome", "poligono_aproximado", "nome", "nao_resolvido", "poligono"]
    assert out.bairro_conflito.tolist() == [True, True, False, False, False, False]
    assert issues.codigo.tolist() == ["bairro_divergente", "bairro_divergente", "bairro_nao_resolvido"]
    assert issues.linha.tolist() == [2, 3, 6] and "adotado Cara Cara" in issues.mensagem[0]
    assert "bairro_oficial" not in frame  # entrada preservada


def test_cli_analyze_with_bairros(tmp_path, gpkg, write_csv, listing):
    listing.update(bairro="UVARANAS", latitude="-25,15", longitude="-50,10", precisao_localizacao="exata")
    other = dict(listing, id="2", url="https://example.test/2", bairro="Cará-Cará", latitude="", longitude="")
    source = write_csv([listing, other], fields=list(listing))
    out = tmp_path / "rel"
    assert main(["analyze", str(source), "--output", str(out), "--bairros", str(gpkg)]) == 0
    manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["bairros_oficiais"]["metodos"] == {"poligono": 1, "nome": 1}
    assert manifest["bairros_oficiais"]["conflitos"] == 1
    assert pd.read_csv(out / "eda" / "por_bairro.csv").bairro_oficial.tolist() == ["Cara Cara"]
    assert json.loads((out / "quality.json").read_text(encoding="utf-8"))["regioes"] == {"Cara Cara": 2}
    assert "bairro_divergente" in pd.read_csv(out / "issues.csv").codigo.tolist()


def test_cli_analyze_missing_bairros_file_fails(tmp_path, write_csv, listing, capsys):
    source = write_csv([listing])
    assert main(["analyze", str(source), "--output", str(tmp_path / "r"), "--bairros", str(tmp_path / "x.gpkg")]) == 2
    assert "bairros" in capsys.readouterr().err
