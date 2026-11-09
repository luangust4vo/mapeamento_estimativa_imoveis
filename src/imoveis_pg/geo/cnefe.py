"""Geocodificação offline com o CNEFE 2022 (IBGE), cadastro aberto de endereços.

Cada endereço do município tem CEP, logradouro, número e coordenadas. A busca
segue uma cascata do mais preciso ao mais grosseiro; só o número exato é
marcado como localização "exata". As demais são "aproximada", com o método
registrado em ``origem_localizacao``.
"""
from __future__ import annotations

import re
import zipfile
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from ..coleta.contrato import format_number
from ..data import normalize_text

CNEFE_URL = ("https://ftp.ibge.gov.br/Cadastro_Nacional_de_Enderecos_para_Fins_Estatisticos/"
             "Censo_Demografico_2022/Arquivos_CNEFE/CSV/Municipio/41_PR/4119905_PONTA_GROSSA.zip")
CNEFE_PATH = Path("data/raw/ibge/4119905_PONTA_GROSSA.zip")
# NV_GEO_COORD 1-3: coordenada do próprio endereço (original, ajustada ou estimada pelo IBGE).
ADDRESS_LEVELS = {"1", "2", "3"}
MAX_NUMBER_GAP = 100
STREET_TYPES = {"rua", "r", "avenida", "av", "travessa", "tv", "trav", "alameda", "al", "rodovia", "rod",
                "estrada", "est", "praca", "pca", "largo", "beco", "viela", "servidao", "via", "caminho"}
ABBREVIATIONS = {"dr": "doutor", "dra": "doutora", "cel": "coronel", "gen": "general", "pe": "padre",
                 "prof": "professor", "profa": "professora", "sen": "senador", "dep": "deputado",
                 "eng": "engenheiro", "sta": "santa", "sto": "santo", "s": "sao", "pres": "presidente",
                 "cap": "capitao", "ten": "tenente", "mal": "marechal", "com": "comendador",
                 "vsc": "visconde", "bar": "barao", "d": "dom", "maj": "major"}
USECOLS = ["CEP", "NOM_TIPO_SEGLOGR", "NOM_TITULO_SEGLOGR", "NOM_SEGLOGR", "NUM_ENDERECO",
           "LATITUDE", "LONGITUDE", "NV_GEO_COORD", "DSC_LOCALIDADE"]


@dataclass(frozen=True)
class GeoMatch:
    latitude: float
    longitude: float
    metodo: str
    pontos: int

    @property
    def precisao(self) -> str:
        return "exata" if self.metodo == "numero" else "aproximada"


def place_key(value) -> str:
    """Nome comparável: sem acento, caixa ou pontuação ("Cará-Cará" == "CARA CARA")."""
    return " ".join(re.sub(r"[^a-z0-9 ]", " ", normalize_text(value)).split())


def street_key(value) -> str:
    """Logradouro comparável: sem acento, pontuação, tipo (Rua/Av.) e com títulos expandidos."""
    words = place_key(value).split()
    while words and words[0] in STREET_TYPES:
        words = words[1:]
    return " ".join(ABBREVIATIONS.get(w, w) for w in words)


def _digits(value) -> str:
    return re.sub(r"\D", "", str(value or ""))


def geographic_cep(value) -> str:
    """CEP de logradouro com 8 dígitos; sufixos 900-999 (Correios, caixas postais,
    grandes usuários) não indicam local e são descartados."""
    cep = _digits(value)
    return cep if len(cep) == 8 and int(cep[-3:]) < 900 else ""


def _number(value) -> int | None:
    match = re.match(r"\s*(\d+)", str(value or ""))
    return int(match.group(1)) if match and int(match.group(1)) > 0 else None


class CnefeGeocoder:
    def __init__(self, addresses: pd.DataFrame):
        frame = addresses.loc[addresses.NV_GEO_COORD.astype(str).isin(ADDRESS_LEVELS)].copy()
        frame["lat"] = pd.to_numeric(frame.LATITUDE, errors="coerce")
        frame["lon"] = pd.to_numeric(frame.LONGITUDE, errors="coerce")
        frame = frame.dropna(subset=["lat", "lon"])
        frame["cep"] = frame.CEP.map(_digits)
        frame["numero"] = pd.to_numeric(frame.NUM_ENDERECO, errors="coerce")
        title = frame.NOM_TITULO_SEGLOGR.fillna("")
        frame["rua_titulo"] = (title + " " + frame.NOM_SEGLOGR.fillna("")).map(street_key)
        frame["rua"] = frame.NOM_SEGLOGR.map(street_key)
        frame["localidade"] = frame.DSC_LOCALIDADE.map(place_key)
        self._frame = frame[["cep", "numero", "rua_titulo", "rua", "localidade", "lat", "lon"]]
        self._by_street = {}
        for column in ("rua_titulo", "rua"):
            for key, index in frame.groupby(column).groups.items():
                if key:
                    self._by_street.setdefault(key, []).extend(index)
        self._by_cep = frame.groupby("cep").groups
        self._by_locality = frame.groupby("localidade").groups

    @classmethod
    def from_zip(cls, path: Path = CNEFE_PATH) -> "CnefeGeocoder":
        with zipfile.ZipFile(path) as archive:
            name = next(n for n in archive.namelist() if n.lower().endswith(".csv"))
            with archive.open(name) as handle:
                return cls(pd.read_csv(handle, sep=";", dtype=str, usecols=USECOLS))

    def _point(self, rows: pd.DataFrame, metodo: str) -> GeoMatch:
        return GeoMatch(float(rows.lat.median()), float(rows.lon.median()), metodo, len(rows))

    def locate(self, *, street=None, number=None, cep=None, bairro=None) -> GeoMatch | None:
        cep, number, key = geographic_cep(cep), _number(number), street_key(street)
        street_rows = self._frame.loc[sorted(set(self._by_street.get(key, [])))] if key else self._frame.iloc[0:0]
        in_cep = street_rows.loc[street_rows.cep.eq(cep)] if cep else street_rows.iloc[0:0]
        candidates = in_cep if len(in_cep) else street_rows
        if len(candidates) and number is not None:
            exact = candidates.loc[candidates.numero.eq(number)]
            if len(exact):
                return self._point(exact, "numero")
            gap = (candidates.numero - number).abs()
            if gap.min() <= MAX_NUMBER_GAP:
                return self._point(candidates.loc[gap.eq(gap.min())], "numero_proximo")
        if len(in_cep):
            return self._point(in_cep, "rua_cep")
        if cep and cep in self._by_cep:
            return self._point(self._frame.loc[self._by_cep[cep]], "cep")
        if len(street_rows):
            return self._point(street_rows, "rua")
        locality = place_key(bairro)
        if locality in self._by_locality:
            return self._point(self._frame.loc[self._by_locality[locality]], "bairro")
        return None


def geocode_records(records: list[dict], geocoder: CnefeGeocoder) -> dict[str, int]:
    """Preenche coordenadas ausentes nos registros; devolve contagem por método."""
    counts: dict[str, int] = {}
    for record in records:
        if record.get("latitude") and record.get("longitude"):
            continue
        match = geocoder.locate(street=record.get("logradouro"), number=record.get("numero"),
                                cep=record.get("cep"), bairro=record.get("bairro"))
        method = match.metodo if match else "nao_localizado"
        counts[method] = counts.get(method, 0) + 1
        if match:
            record["latitude"] = format_number(match.latitude, decimals=7)
            record["longitude"] = format_number(match.longitude, decimals=7)
            record["precisao_localizacao"] = match.precisao
            record["origem_localizacao"] = f"IBGE CNEFE 2022 ({match.metodo}, {match.pontos} endereços)"
    return counts
