"""Exportação do experimento de classificação: tabelas, gráficos, modelo e manifesto."""
from __future__ import annotations

import json
from pathlib import Path

import joblib
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.colors import LinearSegmentedColormap

from .classificacao import ExperimentResult, feature_importance, holdout_errors, stability_summary
from .dataset import ModelData

# Paleta de referência (skill dataviz): superfície, tintas, grade e rampa sequencial azul.
SURFACE, INK, INK_2, GRID, AXIS = "#fcfcfb", "#0b0b0b", "#52514e", "#e1e0d9", "#c3c2b7"
SERIES_1, SERIES_2, MUTED = "#2a78d6", "#eb6834", "#a8a79f"
BLUES = LinearSegmentedColormap.from_list("azul", ["#f3f7fd", "#cde2fb", "#86b6ef", "#3987e5", "#1c5cab", "#0d366b"])
MODEL_LABELS = {"baseline_classe_frequente": "Baseline: classe frequente", "baseline_bairro": "Baseline: faixa do bairro",
                "arvore_decisao": "Árvore de decisão", "knn": "KNN", "svm": "SVM", "mlp": "MLP"}
FEATURE_LABELS = {"area_m2": "Área (m²)", "quartos": "Quartos", "suites": "Suítes", "banheiros": "Banheiros",
                  "vagas": "Vagas", "latitude": "Latitude", "longitude": "Longitude",
                  "distancia_centro_km": "Distância ao centro (km)", "bairro_oficial": "Bairro", "subtipo": "Subtipo"}


def _style(ax):
    ax.set_facecolor(SURFACE)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(AXIS)
    ax.tick_params(colors=INK_2, labelsize=9)
    ax.xaxis.label.set_color(INK_2)
    ax.yaxis.label.set_color(INK_2)


def _save(fig, path: Path, title: str, subtitle: str):
    """Título e subtítulo em posições fixas em polegadas, independentes da altura da figura."""
    fig.patch.set_facecolor(SURFACE)
    height = fig.get_size_inches()[1]
    fig.text(0.01, 1 - 0.22 / height, title, ha="left", va="top", fontsize=13, color=INK, fontweight="bold")
    fig.text(0.01, 1 - 0.50 / height, subtitle.replace("$", r"\$"), ha="left", va="top", fontsize=9, color=INK_2)
    fig.tight_layout(rect=(0, 0, 1, 1 - 0.80 / height))
    fig.savefig(path, dpi=130, facecolor=SURFACE)
    plt.close(fig)


def band_labels(experiment: ExperimentResult) -> list[str]:
    edges = [f"R$ {v:,.0f}".replace(",", ".") for v in experiment.thresholds]
    labels = []
    for i, name in enumerate(experiment.band_names):
        if i == 0:
            labels.append(f"{name} (≤ {edges[0]})")
        elif i == len(experiment.band_names) - 1:
            labels.append(f"{name} (> {edges[-1]})")
        else:
            labels.append(f"{name} ({edges[i - 1]}–{edges[i]})")
    return labels


def plot_confusion(experiment: ExperimentResult, path: Path):
    names = list(experiment.results)
    fig, axes = plt.subplots(2, 3, figsize=(13, 8.5))
    vmax = max(r.confusion.max() for r in experiment.results.values())
    short = experiment.band_names
    for ax, name in zip(axes.flat, names):
        result = experiment.results[name]
        ax.imshow(result.confusion, cmap=BLUES, vmin=0, vmax=vmax)
        for (i, j), value in np.ndenumerate(result.confusion):
            ax.text(j, i, str(value), ha="center", va="center", fontsize=11,
                    color="#ffffff" if value > vmax * 0.55 else INK)
        ax.set_xticks(range(len(short)), short)
        ax.set_yticks(range(len(short)), short)
        ax.set_xlabel("Faixa prevista")
        ax.set_ylabel("Faixa real")
        selected = " • selecionado" if name == experiment.selected else ""
        ax.set_title(f"{MODEL_LABELS.get(name, name)}{selected}\nbalanced acc. teste "
                     f"{result.test['balanced_accuracy']:.2f}", fontsize=10, color=INK, loc="left")
        _style(ax)
    for ax in axes.flat[len(names):]:
        ax.axis("off")
    _save(fig, path, "Matrizes de confusão no teste reservado",
          f"n = {len(experiment.test_index)} casas • faixas: " + "; ".join(band_labels(experiment)))


def plot_comparison(experiment: ExperimentResult, path: Path):
    names = list(experiment.results)[::-1]
    fig, ax = plt.subplots(figsize=(9, 5.2))
    y = np.arange(len(names))
    means = [experiment.results[n].cv["balanced_accuracy"][0] for n in names]
    stds = [experiment.results[n].cv["balanced_accuracy"][1] for n in names]
    tests = [experiment.results[n].test["balanced_accuracy"] for n in names]
    ax.axvline(1 / experiment.n_bands, color=AXIS, lw=1, ls="--", zorder=1)
    ax.text(1 / experiment.n_bands, len(names) - 0.45, " acaso", color=INK_2, fontsize=8, va="bottom")
    ax.errorbar(means, y, xerr=stds, fmt="o", color=SERIES_1, ecolor=SERIES_1, elinewidth=2, capsize=0,
                markersize=8, label="Validação cruzada (média ± desvio, 5 dobras)", zorder=3)
    ax.scatter(tests, y + 0.18, marker="D", s=40, facecolor=SURFACE, edgecolor=SERIES_2, linewidth=2,
               label="Teste reservado", zorder=3)
    labels = [MODEL_LABELS.get(n, n) + ("  ★" if n == experiment.selected else "") for n in names]
    ax.set_yticks(y, labels)
    for tick, name in zip(ax.get_yticklabels(), names):
        tick.set_color(INK_2 if name.startswith("baseline") else INK)
    ax.set_xlim(0, 1)
    ax.set_xlabel("Balanced accuracy")
    ax.grid(axis="x", color=GRID, lw=0.8)
    ax.set_axisbelow(True)
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.16), ncol=2, fontsize=8, frameon=False, labelcolor=INK_2)
    _style(ax)
    _save(fig, path, "Comparação dos classificadores",
          f"{experiment.n_bands} faixas de aluguel • ★ selecionado pela validação cruzada, não pelo teste")


def plot_importance(importance: pd.DataFrame, experiment: ExperimentResult, path: Path):
    data = importance.iloc[::-1]
    fig, ax = plt.subplots(figsize=(8.5, 4.8))
    y = np.arange(len(data))
    ax.barh(y, data.importancia_media, height=0.55, color=SERIES_1, zorder=2)
    ax.errorbar(data.importancia_media, y, xerr=data.importancia_desvio, fmt="none", ecolor=INK_2,
                elinewidth=1, capsize=0, zorder=3)
    ax.axvline(0, color=AXIS, lw=1)
    ax.set_yticks(y, [FEATURE_LABELS.get(a, a) for a in data.atributo])
    ax.set_xlabel("Queda média de balanced accuracy ao embaralhar o atributo (± desvio, 30 repetições)")
    ax.grid(axis="x", color=GRID, lw=0.8)
    ax.set_axisbelow(True)
    _style(ax)
    _save(fig, path, "Atributos mais associados à faixa de aluguel",
          f"Importância por permutação • {MODEL_LABELS.get(experiment.selected, experiment.selected)} no teste reservado"
          " • associação, não causalidade")


def plot_stability(runs: pd.DataFrame, summary: pd.DataFrame, n_bands: int, path: Path):
    order = list(summary.modelo)[::-1]
    fig, ax = plt.subplots(figsize=(9, 5.2))
    for y, name in enumerate(order):
        values = runs.loc[runs.modelo.eq(name), "teste_balanced_accuracy"]
        jitter = np.linspace(-0.12, 0.12, len(values))
        ax.scatter(values, y + jitter, s=18, color=MUTED, zorder=2)
        ax.plot([values.mean()] * 2, [y - 0.28, y + 0.28], color=SERIES_1, lw=2.5, zorder=3)
    ax.plot([], [], color=SERIES_1, lw=2.5, label="Média no teste")
    ax.scatter([], [], s=18, color=MUTED, label="Uma partição treino/teste")
    ax.axvline(1 / n_bands, color=AXIS, lw=1, ls="--", zorder=1)
    selected = summary.set_index("modelo").vezes_selecionado
    ax.set_yticks(range(len(order)), [f"{MODEL_LABELS.get(n, n)} ({int(selected[n])}×)" for n in order])
    ax.set_xlim(0, 1)
    ax.set_xlabel("Balanced accuracy no teste reservado")
    ax.grid(axis="x", color=GRID, lw=0.8)
    ax.set_axisbelow(True)
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.16), ncol=2, fontsize=8, frameon=False, labelcolor=INK_2)
    _style(ax)
    _save(fig, path, "Estabilidade entre partições",
          f"{runs.semente.nunique()} sementes, {n_bands} faixas • (N×) = vezes em que a validação cruzada escolheu o modelo")


def write_report(experiment: ExperimentResult, data: ModelData, out: Path, *, manifest_extra: dict,
                 stability_runs: pd.DataFrame | None = None) -> dict:
    out.mkdir(parents=True, exist_ok=False)
    metrics = experiment.metrics_table()
    metrics.to_csv(out / "metricas.csv", index=False)
    importance = feature_importance(experiment, data)
    importance.to_csv(out / "importancia_atributos.csv", index=False)
    errors = holdout_errors(experiment, data)
    errors.to_csv(out / "erros_teste.csv", index=False)
    by_region = (errors.groupby("bairro_oficial")
                 .agg(n=("acertou", "size"), acertos=("acertou", "sum"),
                      erros_graves=("distancia_faixas", lambda d: int((d.abs() >= 2).sum())))
                 .assign(taxa_acerto=lambda t: t.acertos / t.n).sort_values("n", ascending=False))
    by_region.to_csv(out / "erros_por_bairro.csv")
    selected = experiment.results[experiment.selected]
    recall = np.diag(selected.confusion) / selected.confusion.sum(axis=1).clip(min=1)
    dev_bands = selected.estimator.to_bands(data.y.loc[experiment.dev_index])
    bands = {"limites_reais": [float(t) for t in experiment.thresholds],
             "faixas": band_labels(experiment),
             "contagem_treino": np.bincount(dev_bands, minlength=experiment.n_bands).tolist(),
             "contagem_teste": np.bincount(experiment.y_test_bands, minlength=experiment.n_bands).tolist(),
             "recall_por_faixa_teste": dict(zip(experiment.band_names, map(float, recall)))}
    (out / "faixas.json").write_text(json.dumps(bands, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    plot_confusion(experiment, out / "matrizes_confusao.png")
    plot_comparison(experiment, out / "comparacao_modelos.png")
    plot_importance(importance, experiment, out / "importancia_atributos.png")
    joblib.dump(selected.estimator, out / "modelo_selecionado.joblib")
    stability = None
    if stability_runs is not None:
        stability_runs.to_csv(out / "estabilidade_execucoes.csv", index=False)
        summary = stability_summary(stability_runs)
        summary.to_csv(out / "estabilidade.csv", index=False)
        plot_stability(stability_runs, summary, experiment.n_bands, out / "estabilidade.png")
        stability = {"sementes": sorted(map(int, stability_runs.semente.unique())),
                     "resumo": json.loads(summary.round(4).to_json(orient="records"))}
    manifest = {
        **manifest_extra,
        "semente": experiment.seed, "n_faixas": experiment.n_bands,
        "n_casas": len(data.X), "n_treino": len(experiment.dev_index), "n_teste": len(experiment.test_index),
        "excluidos": data.excluded, "atributos": list(data.X.columns),
        "faixas": bands, "modelo_selecionado": experiment.selected, "estabilidade": stability,
        "criterio_selecao": "maior balanced accuracy média na validação cruzada (desempate: F1 macro)",
        "validacao": "GroupShuffleSplit 80/20 por imóvel; GridSearchCV com GroupKFold(5) no treino",
        "melhores_parametros": {n: {k: str(v) for k, v in r.best_params.items()}
                                for n, r in experiment.results.items()},
        "avisos": experiment.warnings + [
            "Modelo salvo foi ajustado só no conjunto de treino (80%), não na base inteira.",
            "Estimativas de anúncios, não de preços negociados; não é avaliação imobiliária oficial."],
        "status": "complete",
    }
    (out / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return manifest
