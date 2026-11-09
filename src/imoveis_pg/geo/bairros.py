"""Bairros oficiais de Ponta Grossa (IBGE, malha de bairros do Censo 2022).

Cada anúncio recebe ``bairro_oficial`` combinando o nome declarado e o polígono
que contém a coordenada:

- coordenada exata dentro (ou a até 300 m) de um bairro: vale o polígono;
- coordenada aproximada ou ausente: vale o nome declarado, se for um bairro oficial;
- nome não oficial ("Vila Palmeirinha"): vale o polígono da coordenada aproximada.

Quando nome oficial e polígono discordam, ``bairro_conflito`` sinaliza para revisão.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from ..data import ISSUE_COLUMNS, normalize_text
from .cnefe import place_key

BAIRROS_URL = ("https://geoftp.ibge.gov.br/organizacao_do_territorio/malhas_territoriais/"
               "malhas_de_setores_censitarios__divisoes_intramunicipais/censo_2022/bairros/gpkg/UF/PR/"
               "PR_bairros_CD2022.gpkg")
BAIRROS_PATH = Path("data/raw/ibge/PR_bairros_CD2022.gpkg")
CD_MUN = "4119905"
METRIC_CRS = "EPSG:31982"  # SIRGAS 2000 / UTM 22S, distâncias em metros
MAX_DISTANCE_M = 300
# Grafias recorrentes nos anúncios que não coincidem com o nome oficial.
ALIASES = {"colonia dona luzia": "colonia dona luiza"}


def load_bairros(path: Path = BAIRROS_PATH, cd_mun: str = CD_MUN):
    """Polígonos de bairros do município, um por bairro, em WGS84."""
    import geopandas as gpd

    frame = gpd.read_file(path)
    frame = frame.loc[frame.CD_MUN.astype(str).eq(cd_mun), ["CD_BAIRRO", "NM_BAIRRO", "geometry"]]
    if frame.empty:
        raise ValueError(f"Nenhum bairro do município {cd_mun} em {path}.")
    return frame.dissolve(by=["CD_BAIRRO", "NM_BAIRRO"], as_index=False).to_crs("EPSG:4326")


class BairroResolver:
    def __init__(self, bairros):
        self.bairros = bairros.reset_index(drop=True)
        self._metric = self.bairros[["NM_BAIRRO", "geometry"]].to_crs(METRIC_CRS)
        self._names = {place_key(name): name for name in self.bairros.NM_BAIRRO}

    @property
    def names(self) -> list[str]:
        return sorted(self.bairros.NM_BAIRRO)

    def by_name(self, value) -> str | None:
        key = place_key(value)
        return self._names.get(ALIASES.get(key, key))

    def distance_m(self, latitude: float, longitude: float, name: str) -> float:
        """Distância em metros do ponto ao polígono do bairro (0 se estiver dentro)."""
        import geopandas as gpd

        point = gpd.GeoSeries(gpd.points_from_xy([longitude], [latitude]), crs="EPSG:4326").to_crs(METRIC_CRS)
        polygon = self._metric.loc[self._metric.NM_BAIRRO.eq(name), "geometry"]
        if polygon.empty:
            raise KeyError(name)
        return float(point.iloc[0].distance(polygon.iloc[0]))

    def by_points(self, latitude, longitude) -> pd.Series:
        """Bairro que contém cada ponto (ou o mais próximo até 300 m); None fora disso."""
        import geopandas as gpd

        lat = pd.to_numeric(pd.Series(latitude), errors="coerce").reset_index(drop=True)
        lon = pd.to_numeric(pd.Series(longitude), errors="coerce").reset_index(drop=True)
        result = pd.Series([None] * len(lat), dtype="object")
        valid = lat.notna() & lon.notna() & np.isfinite(lat) & np.isfinite(lon)
        if not valid.any():
            return result
        points = gpd.GeoDataFrame(geometry=gpd.points_from_xy(lon[valid], lat[valid]),
                                  index=lat.index[valid], crs="EPSG:4326").to_crs(METRIC_CRS)
        joined = gpd.sjoin_nearest(points, self._metric, how="left", max_distance=MAX_DISTANCE_M)
        joined = joined.loc[~joined.index.duplicated()]
        for index, name in joined.NM_BAIRRO.items():
            result.at[index] = name if isinstance(name, str) else None
        return result


def assign_bairros(rows: pd.DataFrame, resolver: BairroResolver) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Acrescenta bairro_oficial, bairro_metodo e bairro_conflito; devolve também os alertas."""
    out = rows.copy()
    declared = out.bairro.map(resolver.by_name)
    spatial = resolver.by_points(out.latitude, out.longitude)
    spatial.index = out.index
    precision = out.get("precisao_localizacao", pd.Series("", index=out.index)).map(normalize_text)
    exact = precision.eq("exata") & spatial.notna()
    official, method = [], []
    for index in out.index:
        if exact.loc[index]:
            official.append(spatial.loc[index]); method.append("poligono")
        elif pd.notna(declared.loc[index]):
            official.append(declared.loc[index]); method.append("nome")
        elif pd.notna(spatial.loc[index]):
            official.append(spatial.loc[index]); method.append("poligono_aproximado")
        else:
            official.append(None); method.append("nao_resolvido")
    out["bairro_oficial"] = pd.Series(official, index=out.index, dtype="object")
    out["bairro_metodo"] = method
    out["bairro_conflito"] = declared.notna() & spatial.notna() & declared.ne(spatial)
    issues = []
    for index in out.index[out.bairro_conflito]:
        issues.append([int(out.loc[index, "linha"]), "bairro", "bairro_divergente", str(out.loc[index, "bairro"]),
                       f"Nome declarado indica {declared.loc[index]}, coordenada cai em {spatial.loc[index]}; "
                       f"adotado {out.loc[index, 'bairro_oficial']}."])
    for index in out.index[out.bairro_metodo.eq("nao_resolvido")]:
        issues.append([int(out.loc[index, "linha"]), "bairro", "bairro_nao_resolvido", str(out.loc[index, "bairro"]),
                       "Bairro fora da lista oficial e sem coordenada dentro de um bairro."])
    return out, pd.DataFrame(issues, columns=ISSUE_COLUMNS)
