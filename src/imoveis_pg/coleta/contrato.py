"""Escrita de registros coletados no contrato CSV aceito por load_listings."""
from __future__ import annotations

import csv
import math
import re
from pathlib import Path

from ..data import COLUMNS


def as_number(value) -> float | None:
    """Aceita número JSON ou texto pt-BR ("1.234,56"); vazio vira None, nunca zero."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value) if math.isfinite(value) else None
    text = str(value).strip().replace("R$", "").replace("+-", "").strip()
    if not text:
        return None
    if "," in text or re.fullmatch(r"\d{1,3}(?:\.\d{3})+", text):
        text = text.replace(".", "").replace(",", ".")
    try:
        number = float(text)
    except ValueError:
        return None
    return number if math.isfinite(number) else None


def format_number(value, *, decimals: int = 2) -> str:
    """Formata com vírgula decimal e sem separador de milhar (padrão do contrato)."""
    number = as_number(value)
    if number is None:
        return ""
    if number.is_integer():
        return str(int(number))
    return f"{number:.{decimals}f}".rstrip("0").rstrip(".").replace(".", ",")


def write_contract_csv(records: list[dict], path: Path) -> list[str]:
    """Grava CSV ';' com as colunas obrigatórias primeiro e extras depois."""
    extras = sorted({key for record in records for key in record} - set(COLUMNS))
    header = COLUMNS + extras
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, delimiter=";")
        writer.writerow(header)
        for record in records:
            writer.writerow(["" if record.get(c) is None else record.get(c) for c in header])
    return header


def merge_contract_csvs(paths: list[Path], output: Path) -> int:
    """Une CSVs de coletores (mesmo separador e decimal) sem alterar valores; extras viram vazios."""
    records = []
    for path in paths:
        with Path(path).open(encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle, delimiter=";")
            missing = set(COLUMNS) - set(reader.fieldnames or [])
            if missing:
                raise ValueError(f"{path}: colunas obrigatórias ausentes: {', '.join(sorted(missing))}")
            records.extend(reader)
    write_contract_csv(records, output)
    return len(records)
