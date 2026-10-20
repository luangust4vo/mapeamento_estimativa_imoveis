import hashlib
import json
from pathlib import Path
import subprocess
import sys
import pandas as pd

FIXTURE = Path("tests/fixtures/anuncios_sinteticos.csv")

def run(source, out):
    return subprocess.run([sys.executable, "-m", "imoveis_pg", "analyze", str(source),
                           "--output", str(out)], capture_output=True, text=True)

def test_cli_reproducible_and_preserves_input(tmp_path):
    before = FIXTURE.read_bytes()
    one, two = tmp_path / "one", tmp_path / "two"
    for out in (one, two):
        result = run(FIXTURE, out)
        assert result.returncode == 0, result.stderr
        manifest = json.loads((out / "manifest.json").read_text(), parse_constant=lambda x: (_ for _ in ()).throw(ValueError(x)))
        assert manifest["source_sha256"] == hashlib.sha256(before).hexdigest()
        assert manifest["dados_sinteticos"]
        assert manifest["versions"]["pandas"]
        assert len(manifest["eda"]["graficos"]) == 6
        quality = json.loads((out / "quality.json").read_text())
        assert quality["anuncios_snapshot"] == 8
        for name in ("observations.csv", "snapshot.csv", "issues.csv"):
            assert (out / name).exists()
    assert FIXTURE.read_bytes() == before
    assert (one / "quality.json").read_bytes() == (two / "quality.json").read_bytes()
    pd.testing.assert_frame_equal(pd.read_csv(one / "snapshot.csv"), pd.read_csv(two / "snapshot.csv"))

def test_invalid_file_has_no_partial_output(tmp_path):
    source = tmp_path / "bad.csv"
    source.write_text("id;fonte\n1;A\n")
    out = tmp_path / "out"
    result = run(source, out)
    assert result.returncode == 2
    assert "Colunas obrigatórias" in result.stderr
    assert not out.exists()

def test_existing_directory_protected(tmp_path):
    out = tmp_path / "out"
    out.mkdir()
    sentinel = out / "keep.txt"
    sentinel.write_text("keep")
    result = run(FIXTURE, out)
    assert result.returncode == 2
    assert sentinel.read_text() == "keep"
    assert list(out.iterdir()) == [sentinel]

def test_missing_input(tmp_path):
    result = run(tmp_path / "missing.csv", tmp_path / "out")
    assert result.returncode == 2
    assert "ler o CSV" in result.stderr

def test_synthetic_history_keeps_global_warning(write_csv, listing, tmp_path):
    from conftest import COLUMNS
    source = write_csv([
        dict(listing, data_coleta="2026-01-01", sintetico="sim"),
        dict(listing, data_coleta="2026-10-19", sintetico=""),
    ], fields=COLUMNS + ["sintetico"])
    out = tmp_path / "out"
    result = run(source, out)
    assert result.returncode == 0, result.stderr
    manifest = json.loads((out / "manifest.json").read_text())
    assert manifest["dados_sinteticos"] is True
    assert manifest["eda"]["dados_sinteticos"] is True
    assert "DADOS SINTÉTICOS" in result.stdout
