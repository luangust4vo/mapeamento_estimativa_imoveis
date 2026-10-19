import hashlib
import pandas as pd
import pytest
from imoveis_pg.data import load_listings, DataContractError
from conftest import COLUMNS

def test_normalization_preserves_source(write_csv, listing):
    path = write_csv([listing])
    before = path.read_bytes()
    result = load_listings(path)
    row = result.rows.iloc[0]
    assert row.aluguel == 1234.56
    assert row.area_m2 == 80
    assert row.latitude == -25.09
    assert row.bairro_normalizado == "orfas"
    assert row.bairro_original == " Órfãs "
    assert row.data_coleta == pd.Timestamp("2026-10-19")
    assert pd.isna(row.preco)
    assert result.source_sha256 == hashlib.sha256(before).hexdigest()
    assert path.read_bytes() == before
    assert result.rows.row_id.tolist() == load_listings(path).rows.row_id.tolist()

@pytest.mark.parametrize("column,value", [
    ("aluguel", "inf"), ("aluguel", "1.23"), ("area_m2", "80 ha"),
    ("quartos", "-1"), ("quartos", "1,5"), ("data_coleta", "31/02/2026"),
    ("aluguel", "-20"),
])
def test_invalid_value_is_missing_with_diagnostic(write_csv, listing, column, value):
    listing[column] = value
    result = load_listings(write_csv([listing]))
    assert pd.isna(result.rows.iloc[0][column])
    assert column in result.issues.coluna.tolist()
    assert value in result.issues.valor_original.tolist()

def test_dot_decimal_is_explicit(write_csv, listing):
    listing.update(aluguel="1234.56", area_m2="80", latitude="-25.09", longitude="-50.16")
    assert load_listings(write_csv([listing]), decimal=".").rows.iloc[0].aluguel == 1234.56

@pytest.mark.parametrize("content", ["", "id;fonte\n1;A\n", "id;id\n1;1\n", ",".join(COLUMNS)+"\n"])
def test_invalid_header_fails(tmp_path, content):
    path = tmp_path / "bad.csv"
    path.write_text(content)
    with pytest.raises(DataContractError):
        load_listings(path)

def test_empty_table_and_extra_columns(write_csv):
    result = load_listings(write_csv([], fields=COLUMNS+["nota"]))
    assert result.rows.empty
    assert "nota" in result.rows

def test_reserved_column_rejected(write_csv, listing):
    with pytest.raises(DataContractError):
        load_listings(write_csv([listing], fields=COLUMNS+["row_id"]))

def test_malformed_row_rejected(write_csv, listing):
    path = write_csv([listing])
    with path.open("a") as f:
        f.write("somente;duas\n")
    with pytest.raises(DataContractError):
        load_listings(path)
