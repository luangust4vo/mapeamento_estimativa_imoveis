"""Exportação do agrupamento: tabelas, gráficos e manifesto."""
from __future__ import annotations

import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.ticker import FixedLocator, FuncFormatter, NullLocator
from sklearn.metrics import adjusted_rand_score

from .agrupamento import (K_RANGE, MAX_NOISE, MIN_STABILITY, PROFILE_FEATURES, ProfileResult, SpatialResult,
                          describe_groups, order_by_rent, profile_by_bairro)
from .dataset import ModelData
from .relatorio import AXIS, GRID, INK, INK_2, MUTED, SERIES_1, SERIES_2, SURFACE, _save, _style

# Paleta categórica de referência, em ordem fixa; nunca reciclada.
CATEGORICAL = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948"]
MARKERS = ["o", "s", "^", "D", "v", "P", "X", "*"]
ALGORITHM_LABELS = {"kmeans": "K-means", "ward": "Hierárquico (Ward)", "dbscan": "DBSCAN"}


def plot_selection(selection: pd.DataFrame, chosen: dict, path: Path):
    fig, (sil_ax, stab_ax) = plt.subplots(1, 2, figsize=(11, 4.6))
    for ax, metric, label in [(sil_ax, "silhueta", "Silhueta (maior = grupos mais separados)"),
                              (stab_ax, "estabilidade", "Estabilidade (ARI médio em 50 subamostras)")]:
        for color, marker, name in [(SERIES_1, "o", "kmeans"), (SERIES_2, "s", "ward")]:
            part = selection[selection.algoritmo.eq(name)].sort_values("k")
            ax.plot(part.k, part[metric], color=color, lw=2, marker=marker, markersize=8,
                    label=ALGORITHM_LABELS[name])
            k = chosen[name]["k"]
            ax.scatter([k], part.loc[part.k.eq(k), metric], s=180, facecolor="none", edgecolor=INK, lw=1.5, zorder=4)
        if metric == "estabilidade":
            ax.axhline(MIN_STABILITY, color=AXIS, ls="--", lw=1)
            ax.text(2.05, MIN_STABILITY + 0.005, f"mínimo exigido {MIN_STABILITY}", fontsize=8, color=INK_2)
        ax.axvspan(1.6, 2.5, color=GRID, alpha=0.6, lw=0)
        ax.set_xticks(range(2, max(K_RANGE) + 1))
        ax.set_xlabel("Número de grupos (k)")
        ax.set_title(label, fontsize=10, color=INK, loc="left")
        ax.grid(axis="y", color=GRID, lw=0.8)
        ax.set_axisbelow(True)
        _style(ax)
    sil_ax.legend(fontsize=8, frameon=False, labelcolor=INK_2)
    _save(fig, path, "Escolha do número de perfis",
          "k=2 (faixa cinza) só separa casas pequenas de grandes e não é candidato • círculo = k escolhido")


def plot_k_distance(result: ProfileResult, path: Path):
    fig, ax = plt.subplots(figsize=(8, 4.4))
    ax.plot(np.arange(len(result.k_distance)), result.k_distance, color=SERIES_1, lw=2)
    if "dbscan" in result.chosen:
        eps = result.chosen["dbscan"]["eps"]
        ax.axhline(eps, color=SERIES_2, lw=1.5, ls="--")
        ax.text(2, eps + 0.04, f"eps escolhido = {eps:.1f}", color=INK_2, fontsize=8)
    ax.set_xlabel("Casas ordenadas pela distância")
    ax.set_ylabel(f"Distância ao {len(PROFILE_FEATURES) * 2}º vizinho")
    ax.grid(axis="y", color=GRID, lw=0.8)
    ax.set_axisbelow(True)
    _style(ax)
    _save(fig, path, "Distância ao k-ésimo vizinho (apoio ao DBSCAN)",
          "O joelho da curva indica um eps natural; acima dele quase tudo vira um único grupo")


def plot_profiles(result: ProfileResult, labels: dict[str, pd.Series], data: ModelData, path: Path):
    algorithms = [a for a in ["kmeans", "dbscan"] if a in labels]
    fig, axes = plt.subplots(1, len(algorithms), figsize=(6 * len(algorithms), 5), squeeze=False)
    area, rent = np.exp(result.table.log_area), np.exp(result.table.log_aluguel)
    for ax, name in zip(axes[0], algorithms):
        groups = labels[name]
        noise = groups.lt(0)
        if noise.any():
            ax.scatter(area[noise], rent[noise], s=22, color=MUTED, marker="x", label=f"Ruído (n={noise.sum()})")
        for g in sorted(groups[groups >= 0].unique()):
            mask = groups.eq(g)
            ax.scatter(area[mask], rent[mask], s=30, color=CATEGORICAL[g - 1], marker=MARKERS[g - 1],
                       edgecolor=SURFACE, linewidth=0.6, label=f"Perfil {g} (n={mask.sum()})")
        ax.set_xscale("log")
        ax.set_yscale("log")
        ax.xaxis.set_major_locator(FixedLocator([40, 60, 100, 200, 300, 500, 800]))
        ax.xaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:.0f}"))
        ax.yaxis.set_major_locator(FixedLocator([1000, 2000, 5000, 10000, 20000]))
        ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"R\\$ {v / 1000:.0f} mil"))
        ax.xaxis.set_minor_locator(NullLocator())
        ax.yaxis.set_minor_locator(NullLocator())
        ax.set_xlabel("Área (m², escala log)")
        ax.set_ylabel("Aluguel (R$/mês, escala log)")
        ax.set_title(ALGORITHM_LABELS[name], fontsize=10, color=INK, loc="left")
        ax.grid(color=GRID, lw=0.6)
        ax.set_axisbelow(True)
        ax.legend(fontsize=8, frameon=False, labelcolor=INK_2, loc="upper left")
        _style(ax)
    _save(fig, path, "Perfis de casas para alugar",
          f"n = {len(result.table)} casas com área, quartos e banheiros • perfis numerados por aluguel mediano crescente")


def plot_space(spatial: SpatialResult, data: ModelData, bairros, path: Path):
    fig, ax = plt.subplots(figsize=(9, 7.5))
    if bairros is not None:
        bairros.boundary.plot(ax=ax, color=AXIS, linewidth=0.8, zorder=1)
        for _, row in bairros.iterrows():
            point = row.geometry.representative_point()
            ax.text(point.x, point.y, row.NM_BAIRRO, fontsize=7, color=INK_2, ha="center", alpha=0.8, zorder=1)
    lat, lon, groups = data.X.latitude, data.X.longitude, spatial.labels
    noise = groups.lt(0)
    ax.scatter(lon[noise], lat[noise], s=12, color=MUTED, marker="x", zorder=2,
               label=f"Anúncio disperso (n={noise.sum()})")
    ax.scatter(lon[~noise], lat[~noise], s=26, color=SERIES_1, edgecolor=SURFACE, linewidth=0.6, zorder=3,
               label=f"Anúncio em concentração (n={(~noise).sum()})")
    for row in spatial.summary.itertuples():
        ax.annotate(str(row.grupo), (row.longitude, row.latitude), xytext=(6, 6), textcoords="offset points",
                    fontsize=10, fontweight="bold", color=INK, zorder=4,
                    bbox=dict(boxstyle="round,pad=0.15", fc=SURFACE, ec=AXIS, lw=0.6))
    margin = 0.01
    ax.set_xlim(lon.min() - margin, lon.max() + margin)
    ax.set_ylim(lat.min() - margin, lat.max() + margin)
    ax.set_aspect(1 / np.cos(np.radians(lat.mean())))
    ax.set_xlabel("Longitude")
    ax.set_ylabel("Latitude")
    ax.legend(fontsize=8, frameon=False, labelcolor=INK_2, loc="lower left")
    _style(ax)
    _save(fig, path, "Concentrações de oferta (DBSCAN geográfico)",
          f"≥ {spatial.min_samples} anúncios num raio de {spatial.eps_m:.0f} m • números = concentrações em ordem "
          "crescente de R$/m² • posições dos anúncios aproximadas")


def write_cluster_report(profiles: ProfileResult, spatial: SpatialResult, data: ModelData, out: Path, *,
                         bairros=None, manifest_extra: dict) -> dict:
    out.mkdir(parents=True, exist_ok=False)
    rent = data.y.loc[profiles.table.index]
    ordered = {name: order_by_rent(profiles.labels[name], rent) for name in profiles.labels}
    profiles.selection.to_csv(out / "perfis_selecao.csv", index=False)
    pd.concat([describe_groups(labels, data).assign(algoritmo=name) for name, labels in ordered.items()],
              ignore_index=True).to_csv(out / "perfis_resumo.csv", index=False)
    rotulos = data.frame.loc[profiles.table.index, ["id", "fonte", "bairro_oficial"]].copy()
    for name, labels in ordered.items():
        rotulos[f"perfil_{name}"] = labels
    rotulos.to_csv(out / "perfis_rotulos.csv", index=False)
    by_bairro, ari_bairro = profile_by_bairro(ordered["kmeans"], data)
    by_bairro.to_csv(out / "perfis_por_bairro.csv")
    agreement = {}
    if "dbscan" in ordered:
        core = ordered["dbscan"].ge(0)
        agreement["kmeans_x_dbscan_sem_ruido"] = float(adjusted_rand_score(ordered["kmeans"][core],
                                                                           ordered["dbscan"][core]))
        agreement["perfil_kmeans_do_ruido_dbscan"] = ordered["kmeans"][~core].value_counts().sort_index().to_dict()
    agreement["kmeans_x_ward"] = float(adjusted_rand_score(ordered["kmeans"], ordered["ward"]))
    spatial.summary.to_csv(out / "regioes_resumo.csv", index=False)
    spatial.sensitivity.to_csv(out / "regioes_sensibilidade.csv", index=False)
    data.frame[["id", "fonte", "bairro_oficial"]].assign(concentracao=spatial.labels).to_csv(
        out / "regioes_rotulos.csv", index=False)
    plot_selection(profiles.selection, profiles.chosen, out / "perfis_selecao.png")
    plot_k_distance(profiles, out / "perfis_kdistancia.png")
    plot_profiles(profiles, ordered, data, out / "perfis_dispersao.png")
    plot_space(spatial, data, bairros, out / "regioes_mapa.png")
    manifest = {
        **manifest_extra,
        "perfis": {"atributos": PROFILE_FEATURES, "n_casas": len(profiles.table),
                   "casas_sem_atributos": int(len(data.X) - len(profiles.table)),
                   "criterio": (f"k em {list(K_RANGE)} com estabilidade ≥ {MIN_STABILITY} e maior silhueta; "
                                f"DBSCAN com ≥ 2 grupos, ruído ≤ {MAX_NOISE:.0%} e maior silhueta sem ruído"),
                   "escolhidos": {n: {k: (float(v) if isinstance(v, (int, float, np.floating)) else v)
                                      for k, v in c.items()} for n, c in profiles.chosen.items()},
                   "concordancia_ari": agreement, "ari_perfil_x_bairro": ari_bairro},
        "regioes": {"eps_m": spatial.eps_m, "min_samples": spatial.min_samples,
                    "n_concentracoes": int(spatial.summary.shape[0]), "ruido": spatial.noise,
                    "ari_concentracao_x_bairro": spatial.ari_bairros},
        "avisos": ["Agrupamento descritivo: os perfis não são usados para prever aluguel.",
                   "Posições geocodificadas aproximadas podem deslocar anúncios entre concentrações."],
        "status": "complete",
    }
    (out / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2, default=str) + "\n",
                                       encoding="utf-8")
    return manifest
