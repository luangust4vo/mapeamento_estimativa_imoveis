"""Geocodificação com um CNEFE fictício em miniatura."""
import io
import json
import zipfile

import pandas as pd
import pytest

from coleta_helpers import FakeSite, client, page_html
from imoveis_pg.__main__ import main
from imoveis_pg.coleta.plataforma import PORTALDEZ
from geo_helpers import write_bairros_gpkg
from imoveis_pg.geo.bairros import BAIRROS_URL, BairroResolver, load_bairros
from imoveis_pg.geo.cnefe import CNEFE_URL, CnefeGeocoder, geocode_records, street_key
from test_coleta_plataforma import portaldez_item

ROWS = [  # CEP, tipo, título, nome, número, lat, lon, nível, localidade
    ("84000000", "RUA", "", "FICTICIA", "100", -25.100, -50.100, "1", "UVARANAS"),
    ("84000000", "RUA", "", "FICTICIA", "120", -25.102, -50.102, "1", "UVARANAS"),
    ("84000000", "RUA", "", "FICTICIA", "300", -25.110, -50.110, "1", "UVARANAS"),
    ("84000001", "RUA", "DOUTOR", "COLARES", "563", -25.090, -50.160, "2", "CENTRO"),
    ("84000002", "AVENIDA", "", "LONGA", "10", -25.050, -50.150, "1", "NEVES"),
    ("84000003", "AVENIDA", "", "LONGA", "5000", -25.060, -50.140, "1", "NEVES"),
    ("84000002", "RUA", "", "VIZINHA", "1", -25.052, -50.152, "1", "NEVES"),
    ("84000010", "RUA", "", "PONTE", "1", -25.120, -50.120, "1", "CARA CARA"),
    ("84001970", "RUA", "", "AGENCIA", "1", -25.250, -50.010, "1", "RURAL"),
    ("84000009", "RUA", "", "SETOR", "0", -25.300, -50.300, "6", "RURAL"),
]
COLUMNS = ["CEP", "NOM_TIPO_SEGLOGR", "NOM_TITULO_SEGLOGR", "NOM_SEGLOGR", "NUM_ENDERECO",
           "LATITUDE", "LONGITUDE", "NV_GEO_COORD", "DSC_LOCALIDADE"]


def frame():
    return pd.DataFrame([[str(v) for v in row] for row in ROWS], columns=COLUMNS)


def zipped():
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("4119905_PONTA_GROSSA.csv", frame().to_csv(sep=";", index=False))
    return buffer.getvalue()


@pytest.fixture(scope="module")
def geo():
    return CnefeGeocoder(frame())


def test_street_key_ignores_type_accents_and_abbreviations():
    assert street_key("R. Dr. Colares") == street_key("Rua Doutor Colares") == "doutor colares"
    assert street_key("AVENIDA BONIFÁCIO VILELA") == "bonifacio vilela"


def test_exact_number_is_the_only_exact_precision(geo):
    match = geo.locate(street="Rua Fictícia", number="120", cep="84000-000")
    assert (match.latitude, match.metodo, match.precisao) == (-25.102, "numero", "exata")
    assert geo.locate(street="R. Dr. Colares", number=563).metodo == "numero"


def test_cascade_falls_back_to_coarser_units(geo):
    near = geo.locate(street="Rua Fictícia", number="130", cep="84000000")
    assert near.metodo == "numero_proximo" and near.latitude == -25.102 and near.precisao == "aproximada"
    assert geo.locate(street="Rua Fictícia", number="900", cep="84000000").metodo == "rua_cep"
    assert geo.locate(street="Rua Nova", cep="84000002").metodo == "cep"
    assert geo.locate(street="Av. Longa").metodo == "rua"
    assert geo.locate(street="Rua Nova", bairro="Uvaranas").metodo == "bairro"
    assert geo.locate(street="Rua Nova", bairro="Cará-Cará").metodo == "bairro"
    assert geo.locate(street="Rua Nova", bairro="Inexistente") is None


def test_cep_restricts_long_streets(geo):
    match = geo.locate(street="Avenida Longa", cep="84000003")
    assert match.metodo == "rua_cep" and match.latitude == -25.060


def test_special_cep_is_not_used_as_location(geo):
    assert geo.locate(street="Rua Nova", cep="84001-970", bairro="Uvaranas").metodo == "bairro"
    assert geo.locate(street="Av. Longa", cep="84001970").metodo == "rua"


def test_census_sector_level_coordinates_are_ignored(geo):
    assert geo.locate(street="Rua Setor", number=0, cep="84000009") is None


def test_geocode_records_fills_only_missing(geo):
    records = [{"logradouro": "Rua Fictícia", "numero": "100", "cep": "84000000", "latitude": "", "longitude": ""},
               {"latitude": "-25,1", "longitude": "-50,1"},
               {"logradouro": "Rua X", "bairro": "Lugar Nenhum", "latitude": "", "longitude": ""}]
    assert geocode_records(records, geo) == {"numero": 1, "nao_localizado": 1}
    assert records[0]["latitude"] == "-25,1" and records[0]["precisao_localizacao"] == "exata"
    assert "CNEFE" in records[0]["origem_localizacao"] and records[1]["latitude"] == "-25,1"
    assert records[2]["latitude"] == ""


def test_divergent_address_falls_back_to_declared_bairro(geo, tmp_path):
    resolver = BairroResolver(load_bairros(write_bairros_gpkg(tmp_path / "b.gpkg")))
    records = [  # CEP de outra região (Neves, ~3 km fora de Uvaranas) com bairro declarado Uvaranas
        {"logradouro": "Rua Nova", "cep": "84000002", "bairro": "UVARANAS", "latitude": "", "longitude": ""},
        # número exato nunca é substituído, mesmo fora do bairro declarado
        {"logradouro": "Avenida Longa", "numero": "10", "bairro": "Uvaranas", "latitude": "", "longitude": ""},
        # resultado coerente com o bairro é mantido
        {"logradouro": "Rua Fictícia", "cep": "84000000", "bairro": "Uvaranas", "latitude": "", "longitude": ""},
    ]
    counts = geocode_records(records, geo, resolver)
    assert counts == {"bairro_por_divergencia": 1, "numero": 1, "rua_cep": 1}
    assert records[0]["latitude"] == "-25,102" and "divergente" in records[0]["origem_localizacao"]
    assert records[1]["latitude"] == "-25,05" and records[2]["precisao_localizacao"] == "aproximada"


def test_cli_collects_downloads_references_once_and_geocodes(tmp_path):
    gpkg_bytes = write_bairros_gpkg(tmp_path / "src.gpkg").read_bytes()
    site = FakeSite({PORTALDEZ.search_url(1): page_html([portaldez_item("A")]), CNEFE_URL: zipped(),
                     BAIRROS_URL: gpkg_bytes})
    cache, cnefe, bairros = tmp_path / "raw", tmp_path / "ibge" / "cnefe.zip", tmp_path / "ibge" / "b.gpkg"
    PORTALDEZ.collect(client(site, cache_dir=cache))
    client(site).download(CNEFE_URL, cnefe)
    client(site).download(BAIRROS_URL, bairros)
    client(site).download(CNEFE_URL, cnefe)
    assert site.calls.count(CNEFE_URL) == 1 and site.calls.count(BAIRROS_URL) == 1
    out = tmp_path / "portaldez.csv"
    code = main(["collect", "portaldez", "--output", str(out), "--cache-dir", str(cache),
                 "--cnefe", str(cnefe), "--bairros", str(bairros), "--offline"])
    assert code == 0
    row = pd.read_csv(out, sep=";", dtype=str).iloc[0]
    assert row.latitude == "-25,102" and row.precisao_localizacao == "exata"
    manifest = json.loads((tmp_path / "portaldez.manifest.json").read_text(encoding="utf-8"))
    assert manifest["geocodificacao"]["metodos"] == {"numero": 1} and manifest["requisicoes"] == 0
    assert manifest["geocodificacao"]["bairros"]["sha256"]


def test_cli_offline_without_cnefe_fails_clearly(tmp_path, capsys):
    cache = tmp_path / "raw"
    PORTALDEZ.collect(client(FakeSite({PORTALDEZ.search_url(1): page_html([portaldez_item("A")])}), cache_dir=cache))
    code = main(["collect", "portaldez", "--output", str(tmp_path / "x.csv"), "--cache-dir", str(cache),
                 "--cnefe", str(tmp_path / "ausente.zip"), "--offline"])
    assert code == 2 and "CNEFE" in capsys.readouterr().err
