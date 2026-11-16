"""Agrupamento descritivo: perfis de imóveis e concentrações espaciais de oferta.

Diferente da classificação, aqui o aluguel pode ser atributo: os grupos descrevem
o mercado e não são usados para prever preço. Nada é imputado nos atributos de
perfil, exceto suítes (ausência = sem suíte, ver docs/classificacao.md).
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from sklearn.cluster import DBSCAN, AgglomerativeClustering, KMeans
from sklearn.metrics import adjusted_rand_score, davies_bouldin_score, silhouette_score
from sklearn.neighbors import NearestNeighbors
from sklearn.preprocessing import StandardScaler

from .dataset import ModelData

PROFILE_FEATURES = ["log_area", "quartos", "banheiros", "tem_suite", "log_aluguel"]
K_RANGE = range(3, 7)       # k=2 só separa casas pequenas de grandes; é reportado, mas não escolhido
MIN_STABILITY = 0.85
MAX_NOISE = 0.25
EARTH_RADIUS_M = 6_371_008.8


def profile_table(data: ModelData) -> pd.DataFrame:
    """Atributos de perfil das casas com área, quartos e banheiros informados."""
    X = data.X
    table = pd.DataFrame({
        "log_area": np.log(X.area_m2.where(X.area_m2 > 0)),
        "quartos": X.quartos, "banheiros": X.banheiros,
        "tem_suite": X.suites.fillna(0).gt(0).astype(float),
        "log_aluguel": np.log(data.y),
    }, index=X.index)
    return table.dropna()


def bootstrap_stability(Z: np.ndarray, base: np.ndarray, factory, *, n: int = 50, frac: float = 0.8,
                        seed: int = 0) -> float:
    """ARI médio entre os rótulos na base inteira e os de reajustes em subamostras de 80%."""
    rng = np.random.default_rng(seed)
    scores = []
    for _ in range(n):
        idx = np.sort(rng.choice(len(Z), int(frac * len(Z)), replace=False))
        scores.append(adjusted_rand_score(base[idx], factory().fit_predict(Z[idx])))
    return float(np.mean(scores))


def _quality(Z, labels) -> dict:
    mask = labels >= 0
    n_clusters = len(set(labels[mask]))
    ok = n_clusters >= 2 and mask.sum() > n_clusters
    return {"n_grupos": n_clusters, "ruido": float(1 - mask.mean()),
            "silhueta": float(silhouette_score(Z[mask], labels[mask])) if ok else np.nan,
            "davies_bouldin": float(davies_bouldin_score(Z[mask], labels[mask])) if ok else np.nan}


@dataclass
class ProfileResult:
    table: pd.DataFrame                 # atributos de perfil (sem padronizar)
    Z: np.ndarray                       # padronizados
    selection: pd.DataFrame             # todas as configurações avaliadas
    labels: pd.DataFrame                # rótulos escolhidos por algoritmo (-1 = ruído)
    chosen: dict[str, dict]             # configuração escolhida por algoritmo
    k_distance: np.ndarray              # distâncias ao k-ésimo vizinho (ordenadas), para o DBSCAN


def cluster_profiles(data: ModelData, *, seed: int = 42, stability_runs: int = 50) -> ProfileResult:
    table = profile_table(data)
    Z = StandardScaler().fit_transform(table)
    rows, candidates = [], {}
    for k in [2, *K_RANGE]:
        for name, factory in [("kmeans", lambda k=k: KMeans(k, n_init=20, random_state=seed)),
                              ("ward", lambda k=k: AgglomerativeClustering(k, linkage="ward"))]:
            labels = factory().fit_predict(Z)
            row = {"algoritmo": name, "k": k, "eps": np.nan, "min_samples": np.nan, **_quality(Z, labels),
                   "estabilidade": bootstrap_stability(Z, labels, factory, n=stability_runs, seed=seed)}
            rows.append(row)
            candidates[(name, k)] = labels
    min_samples = 2 * Z.shape[1]
    k_distance = np.sort(NearestNeighbors(n_neighbors=min_samples).fit(Z).kneighbors(Z)[0][:, -1])
    for ms in sorted({5, 8, min_samples}):
        for eps in np.round(np.arange(0.3, 1.31, 0.1), 2):
            factory = lambda eps=eps, ms=ms: DBSCAN(eps=eps, min_samples=ms)
            labels = factory().fit_predict(Z)
            row = {"algoritmo": "dbscan", "k": np.nan, "eps": eps, "min_samples": ms, **_quality(Z, labels)}
            row["estabilidade"] = (bootstrap_stability(Z, labels, factory, n=stability_runs, seed=seed)
                                   if row["n_grupos"] >= 2 else np.nan)
            rows.append(row)
            candidates[("dbscan", eps, ms)] = labels
    selection = pd.DataFrame(rows)
    chosen, labels = {}, {}
    for name in ["kmeans", "ward"]:
        pool = selection[selection.algoritmo.eq(name) & selection.k.isin(K_RANGE)
                         & selection.estabilidade.ge(MIN_STABILITY)]
        pool = pool if len(pool) else selection[selection.algoritmo.eq(name) & selection.k.isin(K_RANGE)]
        best = pool.loc[pool.silhueta.idxmax()]
        chosen[name] = best.dropna().to_dict()
        labels[name] = candidates[(name, int(best.k))]
    pool = selection[selection.algoritmo.eq("dbscan") & selection.n_grupos.ge(2) & selection.ruido.le(MAX_NOISE)]
    if len(pool):
        best = pool.loc[pool.silhueta.idxmax()]
        chosen["dbscan"] = best.dropna().to_dict()
        labels["dbscan"] = candidates[("dbscan", best.eps, best.min_samples)]
    return ProfileResult(table, Z, selection, pd.DataFrame(labels, index=table.index), chosen, k_distance)


def order_by_rent(labels: pd.Series, rent: pd.Series) -> pd.Series:
    """Renumera grupos de 1..k em ordem crescente de aluguel mediano; ruído continua -1."""
    medians = rent.groupby(labels[labels >= 0]).median().sort_values()
    mapping = {old: new for new, old in enumerate(medians.index, start=1)}
    return labels.map(lambda v: mapping.get(v, -1))


def describe_groups(labels: pd.Series, data: ModelData) -> pd.DataFrame:
    """Resumo interpretável de cada grupo (medianas e composição)."""
    frame = data.X.loc[labels.index].assign(grupo=labels, aluguel=data.y.loc[labels.index])
    frame["aluguel_m2"] = frame.aluguel / frame.area_m2
    frame["tem_suite"] = frame.suites.fillna(0).gt(0)
    summary = frame.groupby("grupo").agg(
        n=("aluguel", "size"), aluguel_mediano=("aluguel", "median"),
        aluguel_q1=("aluguel", lambda s: s.quantile(.25)), aluguel_q3=("aluguel", lambda s: s.quantile(.75)),
        area_mediana=("area_m2", "median"), aluguel_m2_mediano=("aluguel_m2", "median"),
        quartos_mediana=("quartos", "median"), banheiros_mediana=("banheiros", "median"),
        com_suite=("tem_suite", "mean"), distancia_centro_mediana=("distancia_centro_km", "median"),
        bairro_principal=("bairro_oficial", lambda s: s.value_counts().index[0]),
        bairro_principal_pct=("bairro_oficial", lambda s: s.value_counts(normalize=True).iloc[0]))
    return summary.reset_index()


@dataclass
class SpatialResult:
    labels: pd.Series
    summary: pd.DataFrame
    eps_m: float
    min_samples: int
    noise: float
    ari_bairros: float
    sensitivity: pd.DataFrame


def cluster_space(data: ModelData, *, eps_m: float = 600, min_samples: int = 6) -> SpatialResult:
    """DBSCAN geográfico (haversine): concentrações de anúncios, independentes do preço."""
    coords = np.radians(data.X[["latitude", "longitude"]].to_numpy())

    def run(eps, ms):
        return DBSCAN(eps=eps / EARTH_RADIUS_M, min_samples=ms, metric="haversine",
                      algorithm="ball_tree").fit_predict(coords)

    def ari(labels):
        mask = labels >= 0
        return float(adjusted_rand_score(data.X.bairro_oficial[mask], labels[mask])) if mask.sum() > 1 else np.nan

    sensitivity = []
    for eps in [400, 600, 800, 1000]:
        for ms in [4, 6, 8]:
            labels = run(eps, ms)
            sensitivity.append({"eps_m": eps, "min_samples": ms, "n_grupos": len(set(labels[labels >= 0])),
                                "ruido": float((labels < 0).mean()), "ari_bairros": ari(labels)})
    labels = pd.Series(run(eps_m, min_samples), index=data.X.index)
    labels = order_by_rent(labels, data.y / data.X.area_m2)
    summary = describe_groups(labels[labels >= 0], data) if (labels >= 0).any() else pd.DataFrame()
    centers = data.X.loc[labels.index].groupby(labels)[["latitude", "longitude"]].median()
    if len(summary):
        summary = summary.merge(centers, left_on="grupo", right_index=True)
    return SpatialResult(labels, summary, eps_m, min_samples, float((labels < 0).mean()), ari(labels.to_numpy()),
                         pd.DataFrame(sensitivity))


def profile_by_bairro(labels: pd.Series, data: ModelData) -> tuple[pd.DataFrame, float]:
    """Composição de perfis em cada bairro (proporções) e ARI entre perfis e bairros."""
    bairros = data.X.loc[labels.index, "bairro_oficial"]
    table = pd.crosstab(bairros, labels, normalize="index").round(3)
    table.insert(0, "n", bairros.value_counts())
    return table.sort_values("n", ascending=False), float(adjusted_rand_score(bairros, labels))
