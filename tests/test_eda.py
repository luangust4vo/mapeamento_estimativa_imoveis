from pathlib import Path
import pandas as pd
import pytest
from imoveis_pg.data import load_listings
from imoveis_pg.quality import audit_listings
from imoveis_pg.eda import analyze_listings

def snapshot(write_csv, records):
    return audit_listings(load_listings(write_csv(records)).rows).snapshot

def test_regional_metrics_and_artifacts(write_csv, listing, tmp_path):
    rows = [dict(listing, id=str(i), url=f"https://example.test/{i}", bairro=b, aluguel=p, condominio=c)
            for i, (b,p,c) in enumerate([("A","1000","100"),("A","2000",""),("B","3000","100"),("","4000","100")])]
    out = tmp_path / "eda"
    result = analyze_listings(snapshot(write_csv, rows), out)
    table = pd.read_csv(out / "por_bairro.csv")
    a = table.loc[table.bairro_normalizado.eq("a")].iloc[0]
    assert a.n == 2
    assert a.mediana_aluguel == 1500
    assert a.media_custo_total == 1200
    assert "Bairro não informado" in table.bairro_normalizado.tolist()
    assert all((out / file).stat().st_size > 100 for file in result["graficos"])
    pairs = pd.read_csv(out / "correlacao_n.csv", index_col=0)
    assert pairs.loc["aluguel", "custo_mensal_total"] == 3

@pytest.mark.parametrize("n", [0, 1, 2])
def test_small_constant_data_warns(write_csv, listing, tmp_path, n):
    rows = [dict(listing, id=str(i), url=f"https://example.test/{i}") for i in range(n)]
    result = analyze_listings(snapshot(write_csv, rows), tmp_path / "eda")
    assert result["avisos"]
    corr = pd.read_csv(tmp_path / "eda/correlacao.csv", index_col=0)
    assert corr.isna().all().all()

def test_sales_do_not_pollute_rental_distribution(write_csv, listing, tmp_path):
    rows = [dict(listing, id="rent", aluguel="1000"),
            dict(listing, id="sale", finalidade="Venda", aluguel="900000")]
    result = analyze_listings(snapshot(write_csv, rows), tmp_path / "eda")
    assert result["n_locacao"] == 1
    table = pd.read_csv(tmp_path / "eda/por_bairro.csv")
    assert table.iloc[0].mediana_aluguel == 1000

def test_existing_output_protected(write_csv, tmp_path):
    out = tmp_path / "eda"
    out.mkdir()
    sentinel = out / "keep.txt"
    sentinel.write_text("keep")
    with pytest.raises(ValueError):
        analyze_listings(snapshot(write_csv, []), out)
    assert sentinel.read_text() == "keep"

def test_synthetic_flag_in_manifest(tmp_path):
    rows = audit_listings(load_listings(Path("tests/fixtures/anuncios_sinteticos.csv")).rows).snapshot
    assert analyze_listings(rows, tmp_path / "eda")["dados_sinteticos"]
