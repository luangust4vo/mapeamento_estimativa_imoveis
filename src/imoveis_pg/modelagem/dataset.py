"""Tabela de modelagem: casas residenciais elegíveis e atributos sem vazamento do aluguel."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from ..data import load_listings, normalize_text
from ..geo.bairros import BairroResolver, assign_bairros, load_bairros
from ..quality import audit_listings

# Nó "Ponta Grossa" (place=city) do OpenStreetMap, no centro histórico; referência fixa e externa aos dados.
CENTRO = (-25.0891685, -50.1601812)
NUMERIC_FEATURES = ["area_m2", "quartos", "suites", "banheiros", "vagas",
                    "latitude", "longitude", "distancia_centro_km"]
CATEGORICAL_FEATURES = ["bairro_oficial", "subtipo"]
FEATURES = NUMERIC_FEATURES + CATEGORICAL_FEATURES
TARGET = "aluguel"
GROUP = "grupo_imovel"
DESCRIPTION_COLUMNS = ["id", "fonte", "bairro_oficial", "subtipo", "area_m2", "quartos", "aluguel",
                       "precisao_localizacao"]


@dataclass
class ModelData:
    frame: pd.DataFrame      # linhas usadas, com colunas descritivas (sem endereço)
    X: pd.DataFrame
    y: pd.Series             # aluguel mensal (R$); as faixas são definidas no treino
    groups: pd.Series
    excluded: dict[str, int]


def distance_km(lat, lon, origin=CENTRO) -> np.ndarray:
    lat1, lon1 = np.radians(origin[0]), np.radians(origin[1])
    lat2, lon2 = np.radians(np.asarray(lat, float)), np.radians(np.asarray(lon, float))
    a = np.sin((lat2 - lat1) / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin((lon2 - lon1) / 2) ** 2
    return 6371.0088 * 2 * np.arcsin(np.sqrt(a))


def house_subtype(value) -> str:
    text = normalize_text(value)
    if "condominio" in text:
        return "condominio"
    return "sobrado" if "sobrado" in text else "casa"


def prepare_snapshot(csv_path: Path, bairros_path: Path, *, sep: str = ";", decimal: str = ",") -> pd.DataFrame:
    """Importa, atribui bairros oficiais e devolve o retrato atual (uma linha por anúncio)."""
    rows = load_listings(csv_path, sep=sep, decimal=decimal).rows
    rows, _ = assign_bairros(rows, BairroResolver(load_bairros(bairros_path)))
    return audit_listings(rows).snapshot


def build_dataset(snapshot: pd.DataFrame) -> ModelData:
    """Seleciona casas residenciais de locação com aluguel, coordenadas e bairro oficial."""
    checks = {
        "nao_elegivel": ~snapshot.elegivel_preliminar.astype(bool),
        "sem_coordenadas": ~snapshot.coordenadas_validas.astype(bool),
        "sem_bairro_oficial": snapshot.get("bairro_oficial", pd.Series(index=snapshot.index)).isna(),
    }
    keep = pd.Series(True, index=snapshot.index)
    excluded = {}
    for reason, mask in checks.items():
        excluded[reason] = int((keep & mask).sum())
        keep &= ~mask
    frame = snapshot.loc[keep].copy()
    frame["subtipo"] = frame.get("subtipo", pd.Series("", index=frame.index)).map(house_subtype)
    frame["distancia_centro_km"] = distance_km(frame.latitude, frame.longitude)
    X = frame[FEATURES].copy()
    X[NUMERIC_FEATURES] = X[NUMERIC_FEATURES].astype(float)
    X[CATEGORICAL_FEATURES] = X[CATEGORICAL_FEATURES].astype(str)
    description = frame[[c for c in DESCRIPTION_COLUMNS if c in frame]].copy()
    return ModelData(description, X, frame[TARGET].astype(float), split_groups(frame), excluded)


def split_groups(frame: pd.DataFrame) -> pd.Series:
    """Grupos para separar treino/teste: une o grupo de duplicatas da auditoria com anúncios de
    mesmo bairro, área, quartos e aluguel (o mesmo imóvel em fontes sem número no endereço, ou
    unidades idênticas de um empreendimento). Agrupar a mais não vaza; agrupar a menos vaza."""
    parent = {i: i for i in frame.index}

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def union(indexes):
        roots = [find(i) for i in indexes]
        for root in roots[1:]:
            parent[root] = roots[0]

    for _, group in frame.groupby(GROUP):
        union(list(group.index))
    complete = frame.dropna(subset=["bairro_oficial", "area_m2", "quartos", TARGET])
    for _, group in complete.groupby(["bairro_oficial", "area_m2", "quartos", TARGET]):
        union(list(group.index))
    return pd.Series({i: f"g{find(i)}" for i in frame.index}).loc[frame.index].astype(str)
