import pandas as pd
import pytest
from imoveis_pg.data import load_listings
from imoveis_pg.quality import audit_listings

def audit(write_csv, records):
    return audit_listings(load_listings(write_csv(records)).rows)

def test_history_keeps_latest_without_mutating(write_csv, listing):
    old = dict(listing, data_coleta="2026-01-01", aluguel="1000")
    new = dict(listing, data_coleta="2026-10-01", aluguel="1200")
    rows = load_listings(write_csv([new, old])).rows
    before = rows.copy(deep=True)
    result = audit_listings(rows)
    assert len(result.observations) == 2
    assert len(result.snapshot) == 1
    assert result.snapshot.iloc[0].aluguel == 1200
    pd.testing.assert_frame_equal(rows, before)

def test_unknown_identity_and_candidate_duplicates(write_csv, listing):
    result = audit(write_csv, [dict(listing, id="", url="", fonte="A"),
                               dict(listing, id="", url="", fonte="B")])
    assert len(result.snapshot) == 2
    assert result.snapshot.candidato_duplicata.all()

def test_missing_address_is_not_duplicate(write_csv, listing):
    result = audit(write_csv, [dict(listing, id="", url="", endereco="", fonte="A"),
                               dict(listing, id="", url="", endereco="", fonte="B")])
    assert not result.snapshot.candidato_duplicata.any()

def test_costs_and_area(write_csv, listing):
    row = audit(write_csv, [dict(listing, aluguel="1200")]).snapshot.iloc[0]
    assert row.iptu_mensal == 100
    assert row.custo_mensal_total == 1400
    assert row.aluguel_m2 == 15
    assert row.densidade_quartos == 0.025
    row = audit(write_csv, [dict(listing, area_m2="0", periodicidade_iptu="")]).snapshot.iloc[0]
    assert pd.isna(row.aluguel_m2)
    assert pd.isna(row.custo_mensal_total)

@pytest.mark.parametrize("changes", [
    {"longitude": ""}, {"latitude": "95"}, {"latitude": "-25,09", "longitude": "200"}
])
def test_bad_coordinates_not_eligible_without_bairro(write_csv, listing, changes):
    result = audit(write_csv, [dict(listing, bairro="", **changes)])
    assert not result.snapshot.iloc[0].coordenadas_validas
    assert not result.snapshot.iloc[0].elegivel_preliminar
    assert "coordenadas_invalidas" in result.issues.codigo.tolist()

def test_price_extreme_preserved(write_csv, listing):
    result = audit(write_csv, [dict(listing, id=str(i), url=f"https://example.test/{i}", aluguel=str(price))
                               for i, price in enumerate([1000, 1100, 1200, 1300, 100000])])
    assert len(result.snapshot) == 5
    assert "extremo_iqr" in result.issues.codigo.tolist()

def test_identity_conflicts_and_exact_duplicates(write_csv, listing):
    result = audit(write_csv, [listing, listing, dict(listing, id="other")])
    assert result.observations.duplicata_exata.sum() == 1
    assert "conflito_identidade" in result.issues.codigo.tolist()

def test_sale_and_commercial_not_eligible(write_csv, listing):
    result = audit(write_csv, [dict(listing, finalidade="Venda")])
    assert not result.snapshot.iloc[0].elegivel_preliminar

def test_empty_quality(write_csv):
    result = audit(write_csv, [])
    assert result.snapshot.empty
    assert result.summary["observacoes"] == 0


def test_duplicate_ignores_missing_house_number(write_csv, listing):
    result = audit(write_csv, [dict(listing, id="1", url="", fonte="A", endereco="Rua das Flores, 120"),
                               dict(listing, id="2", url="", fonte="B", endereco="R. das Flores"),
                               dict(listing, id="3", url="", fonte="C", endereco="Rua das Palmeiras, 120")])
    flagged = result.snapshot.set_index("id").candidato_duplicata
    assert flagged.to_dict() == {"1": True, "2": True, "3": False}
    groups = result.snapshot.set_index("id").grupo_imovel
    assert groups["1"] == groups["2"] != groups["3"]
