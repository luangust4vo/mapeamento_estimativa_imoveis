"""Simulador: ponto no mapa + características → faixa de aluguel, perfil, comparáveis e avisos.

Lógica pura (sem Streamlit), carregada dos artefatos gerados por ``build-app``.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

from ..geo.bairros import BairroResolver
from ..modelagem.dataset import FEATURES, distance_km

COVERAGE_RADIUS_KM = 1.0
MIN_NEARBY = 5
MIN_BAIRRO = 5
N_COMPARABLES = 5
LABELS = {"area_m2": "Área (m²)", "quartos": "Quartos", "banheiros": "Banheiros", "vagas": "Vagas",
          "suites": "Suítes"}


@dataclass
class Simulation:
    disponivel: bool
    bairro: str | None = None
    faixa: str | None = None
    faixa_intervalo: str | None = None
    probabilidades: dict[str, float] = field(default_factory=dict)
    perfil: str | None = None
    comparaveis: pd.DataFrame = field(default_factory=pd.DataFrame)
    referencia_comparaveis: tuple[float, float, float] | None = None   # Q1, mediana, Q3 do aluguel
    anuncios_proximos: int = 0
    avisos: list[str] = field(default_factory=list)


def brl(value: float) -> str:
    return "R$ " + f"{value:,.0f}".replace(",", ".")


class Simulator:
    def __init__(self, artifacts: Path):
        import geopandas as gpd

        artifacts = Path(artifacts)
        models = joblib.load(artifacts / "modelos.joblib")
        self.classifier, self.profiles = models["classificador"], models["perfis"]
        self.metadata = json.loads((artifacts / "metadados.json").read_text(encoding="utf-8"))
        self.listings = pd.read_csv(artifacts / "anuncios.csv")
        self.bairros = gpd.read_file(artifacts / "bairros.geojson")
        self.resolver = BairroResolver(self.bairros)
        self.eligible = self.listings[self.listings.elegivel].copy()
        self.band_names = self.metadata["faixas"]["nomes"]
        self.limits = self.metadata["faixas"]["limites"]

    def band_interval(self, band: int) -> str:
        if band == 0:
            return f"até {brl(self.limits[0])}"
        if band == len(self.band_names) - 1:
            return f"acima de {brl(self.limits[-1])}"
        return f"{brl(self.limits[band - 1])} a {brl(self.limits[band])}"

    def _profile(self, area, quartos, banheiros, suites, rent_reference) -> str | None:
        if None in (area, quartos, banheiros, rent_reference) or area <= 0:
            return None
        row = pd.DataFrame([[np.log(area), quartos, banheiros, float((suites or 0) > 0), np.log(rent_reference)]],
                           columns=self.profiles["atributos"])
        label = int(self.profiles["kmeans"].predict(self.profiles["scaler"].transform(row))[0])
        number = self.profiles["ordem"][label]
        return f"{number} · {self.metadata['perfis'][str(number)]}"

    def comparables(self, lat, lon, area, quartos) -> pd.DataFrame:
        """Casas anunciadas mais parecidas: área (escala log), quartos e distância geográfica."""
        pool = self.eligible.dropna(subset=["area_m2"]).copy()
        pool["distancia_km"] = distance_km(pool.latitude, pool.longitude, origin=(lat, lon))
        score = pool.distancia_km / 2
        if area:
            score = score + np.abs(np.log(pool.area_m2) - np.log(area)) / 0.25
        if quartos is not None:
            score = score + np.abs(pool.quartos.fillna(quartos) - quartos)
        pool["similaridade"] = score
        columns = ["bairro_oficial", "subtipo", "area_m2", "quartos", "banheiros", "aluguel", "distancia_km",
                   "fonte", "url"]
        return pool.nsmallest(N_COMPARABLES, "similaridade")[columns]

    def simulate(self, lat: float, lon: float, *, area_m2: float, quartos: int | None = None,
                 banheiros: int | None = None, vagas: int | None = None, suites: int | None = None,
                 subtipo: str = "casa") -> Simulation:
        bairro = self.resolver.by_points([lat], [lon])[0]
        if bairro is None:
            return Simulation(False, avisos=[
                "O ponto está fora dos bairros oficiais de Ponta Grossa (malha do IBGE, Censo 2022). "
                "Não há dados para estimar o aluguel nesse local."])
        warnings = []
        # Nenhum anúncio informa 0 suítes ou 0 vagas: quem não tem omite o campo. Para reproduzir a
        # codificação do treino (ausente + indicador de ausência), zero vira ausente na entrada do modelo.
        model_suites = None if not suites else suites
        model_vagas = None if not vagas else vagas
        X = pd.DataFrame([{"area_m2": area_m2, "quartos": quartos, "suites": model_suites, "banheiros": banheiros,
                           "vagas": model_vagas, "latitude": lat, "longitude": lon,
                           "distancia_centro_km": float(distance_km([lat], [lon])[0]),
                           "bairro_oficial": bairro, "subtipo": subtipo}])[FEATURES]
        X[FEATURES[:-2]] = X[FEATURES[:-2]].astype(float)
        proba = self.classifier.predict_proba(X)[0]
        band = int(np.argmax(proba))
        comparables = self.comparables(lat, lon, area_m2, quartos)
        q1, median, q3 = comparables.aluguel.quantile([.25, .5, .75])
        nearby = int((distance_km(self.eligible.latitude, self.eligible.longitude, origin=(lat, lon))
                      <= COVERAGE_RADIUS_KM).sum())
        in_bairro = int(self.eligible.bairro_oficial.eq(bairro).sum())
        if nearby < MIN_NEARBY:
            warnings.append(f"Baixa cobertura: só {nearby} casa(s) anunciada(s) num raio de "
                            f"{COVERAGE_RADIUS_KM:.0f} km. A estimativa depende de imóveis mais distantes.")
        if in_bairro < MIN_BAIRRO:
            warnings.append(f"Bairro {bairro} com apenas {in_bairro} casa(s) na base: confiabilidade baixa.")
        for column, value in [("area_m2", area_m2), ("quartos", quartos), ("banheiros", banheiros),
                              ("vagas", vagas), ("suites", suites)]:
            low, high = self.metadata["faixa_treino_atributos"].get(column, (None, None))
            if column in ("vagas", "suites") and value == 0:
                continue  # zero é o caso "não tem", representado no treino pela ausência do campo
            if value is not None and low is not None and not low <= value <= high:
                warnings.append(f"{LABELS[column]} = {value:g} está fora do intervalo da base "
                                f"({low:g} a {high:g}): a estimativa é uma extrapolação.")
        comparable_band = int(self.classifier.to_bands([median])[0])
        if comparable_band != band:
            warnings.append(f"As casas mais parecidas anunciadas têm mediana de {brl(median)} (faixa "
                            f"{self.band_names[comparable_band]}), diferente da faixa estimada pelo modelo "
                            f"({self.band_names[band]}). Considere as duas referências: a estimativa é incerta.")
        if proba.max() < 0.5:
            warnings.append("O modelo está dividido entre faixas (nenhuma passa de 50% de probabilidade).")
        return Simulation(
            True, bairro, self.band_names[band], self.band_interval(band),
            {name: float(p) for name, p in zip(self.band_names, proba)},
            self._profile(area_m2, quartos, banheiros, suites, median), comparables, (q1, median, q3),
            nearby, warnings)
