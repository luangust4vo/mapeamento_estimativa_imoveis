"""Importação estrita; limpeza nunca altera a entrada ou oculta valores originais."""
import csv
import hashlib
import io
import math
import re
import unicodedata
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import pandas as pd

COLUMNS = "id fonte url data_coleta endereco bairro latitude longitude tipo finalidade area_m2 quartos suites banheiros vagas aluguel preco condominio iptu periodicidade_iptu".split()
COUNTS = {"quartos", "suites", "banheiros", "vagas", "ano_construcao"}
MONEY = {"aluguel", "preco", "condominio", "iptu"}
NUMERIC = MONEY | COUNTS | {"area_m2", "latitude", "longitude"}
ISSUE_COLUMNS = ["linha", "coluna", "codigo", "valor_original", "mensagem"]
RESERVED = {"row_id", "linha", "bairro_normalizado", "entity_id", "coordenadas_validas",
            "elegivel_preliminar", "aluguel_m2", "iptu_mensal", "custo_mensal_total",
            "densidade_quartos", "idade", "duplicata_exata", "candidato_duplicata"}


class DataContractError(ValueError):
    """Arquivo não atende ao contrato; nenhuma tabela parcial é retornada."""


@dataclass
class ImportResult:
    rows: pd.DataFrame
    issues: pd.DataFrame
    source_sha256: str


def normalize_text(value) -> str:
    if pd.isna(value):
        return ""
    text = unicodedata.normalize("NFKD", str(value))
    return " ".join("".join(c for c in text if not unicodedata.combining(c)).lower().split())


def _number(value: str, column: str, decimal: str) -> float:
    text = value.strip()
    if column in MONEY:
        text = re.sub(r"^R\$\s*", "", text)
    if column == "area_m2":
        text = re.sub(r"\s*m(?:²|2)$", "", text)
    # Geographic degrees never use thousands grouping.
    if column in {"latitude", "longitude"}:
        pattern = r"[+-]?\d+(?:,\d+)?" if decimal == "," else r"[+-]?\d+(?:\.\d+)?"
    else:
        pattern = (r"[+-]?(?:\d+|\d{1,3}(?:\.\d{3})+)(?:,\d+)?"
                   if decimal == "," else r"[+-]?\d+(?:\.\d+)?")
    if not re.fullmatch(pattern, text):
        raise ValueError("Formato numérico inválido para a unidade/localidade selecionada.")
    number = float(text.replace(".", "").replace(",", ".") if decimal == "," else text)
    if not math.isfinite(number):
        raise ValueError("Número não finito.")
    if column not in {"latitude", "longitude"} and number < 0:
        raise ValueError("Valor negativo não permitido.")
    if column in COUNTS and not number.is_integer():
        raise ValueError("Contagem deve ser inteira.")
    return number


def _date(value: str) -> pd.Timestamp:
    for fmt in ("%Y-%m-%d", "%d/%m/%Y"):
        try:
            return pd.Timestamp(datetime.strptime(value.strip(), fmt))
        except ValueError:
            pass
    raise ValueError("Data inválida; use AAAA-MM-DD ou DD/MM/AAAA.")


def load_listings(path: Path, *, sep: str = ";", decimal: str = ",") -> ImportResult:
    if len(sep) != 1 or sep in {'"', "\n", "\r"} or decimal not in {",", "."}:
        raise DataContractError("Separador ou marca decimal inválidos.")
    try:
        raw = Path(path).read_bytes()
        parsed = list(csv.reader(io.StringIO(raw.decode("utf-8-sig")), delimiter=sep, strict=True))
    except (OSError, UnicodeError, csv.Error) as exc:
        raise DataContractError(f"Não foi possível ler o CSV: {exc}") from exc
    if not parsed or not parsed[0]:
        raise DataContractError("CSV vazio ou sem cabeçalho.")
    header = parsed[0]
    if len(set(header)) != len(header):
        raise DataContractError("Cabeçalho contém colunas duplicadas.")
    missing = sorted(set(COLUMNS) - set(header))
    if missing:
        raise DataContractError("Colunas obrigatórias ausentes: " + ", ".join(missing))
    if any(c in RESERVED or c.endswith("_original") for c in header):
        raise DataContractError("Cabeçalho usa nomes reservados para rastreabilidade ou derivados.")
    if any(len(row) != len(header) for row in parsed[1:]):
        raise DataContractError("Linha com quantidade de campos diferente do cabeçalho.")
    digest = hashlib.sha256(raw).hexdigest()
    original = pd.DataFrame(parsed[1:], columns=header)
    rows = original.copy()
    issues = []
    for column in header:
        rows[column + "_original"] = original[column]
        values = []
        for index, value in enumerate(original[column]):
            if not value.strip():
                values.append(None)
                continue
            try:
                cleaned = (_number(value, column, decimal) if column in NUMERIC else
                           _date(value) if column == "data_coleta" else value.strip())
                values.append(cleaned)
            except (ValueError, OverflowError) as exc:
                values.append(None)
                issues.append([index + 2, column, "valor_invalido", value, str(exc)])
        if column in NUMERIC:
            rows[column] = pd.Series(values, dtype="float64")
        elif column == "data_coleta":
            rows[column] = pd.to_datetime(pd.Series(values), errors="coerce")
        else:
            rows[column] = pd.Series(values, dtype="object")
    rows["linha"] = range(2, len(rows) + 2)
    rows["row_id"] = [f"{digest}:{line}" for line in rows.linha]
    rows["bairro_normalizado"] = rows.bairro.map(normalize_text)
    return ImportResult(rows, pd.DataFrame(issues, columns=ISSUE_COLUMNS), digest)
