"""Exportação do experimento de regressão: tabelas, gráficos, modelo e manifesto."""
from __future__ import annotations

import json
from pathlib import Path

import joblib
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.ticker import FixedLocator, FuncFormatter, NullLocator

from .dataset import ModelData
from .regressao import INTERVAL, RegressionExperiment, residual_analysis, stability_summary
from .relatorio import AXIS, GRID, INK, INK_2, MUTED, SERIES_1, SERIES_2, SURFACE, _save, _style

MODEL_LABELS = {"baseline_mediana_bairro": "Referência: mediana do bairro", "regressao_linear": "Regressão linear (Ridge)",
                "arvore_decisao": "Árvore de decisão", "knn": "KNN", "svr": "SVR", "mlp": "MLP"}


def _money_axis(axis, ticks):
    axis.set_major_locator(FixedLocator(ticks))
    axis.set_major_formatter(FuncFormatter(lambda v, _: f"R\\$ {v / 1000:g} mil"))
    axis.set_minor_locator(NullLocator())


def plot_comparison(experiment: RegressionExperiment, path: Path):
    names = list(experiment.results)[::-1]
    fig, ax = plt.subplots(figsize=(9, 5.2))
    y = np.arange(len(names))
    cv = [experiment.results[n].cv["mae"][0] for n in names]
    sd = [experiment.results[n].cv["mae"][1] for n in names]
    test = [experiment.results[n].test["mae"] for n in names]
    limit = max(np.nanmax(np.array(cv) + np.array(sd)), *[t for t in test if t < 10000]) * 1.15
    ax.errorbar(cv, y, xerr=sd, fmt="o", color=SERIES_1, elinewidth=2, markersize=8, capsize=0, zorder=3,
                label="Validação cruzada (média ± desvio, 5 dobras)")
    shown = [min(t, limit * 0.98) for t in test]
    ax.scatter(shown, y + 0.18, marker="D", s=40, facecolor=SURFACE, edgecolor=SERIES_2, linewidth=2, zorder=3,
               label="Teste reservado")
    for yi, t in zip(y, test):
        if t >= limit:
            ax.annotate(f"R$ {t:,.0f} →".replace(",", ".").replace("$", r"\$"), (limit * 0.97, yi + 0.18),
                        ha="right", va="center", fontsize=8, color=INK_2)
    labels = [MODEL_LABELS.get(n, n) + ("  ★" if n == experiment.selected else "") for n in names]
    ax.set_yticks(y, labels)
    for tick, name in zip(ax.get_yticklabels(), names):
        tick.set_color(INK_2 if name.startswith("baseline") else INK)
    ax.set_xlim(0, limit)
    ax.xaxis.set_major_formatter(FuncFormatter(lambda v, _: f"R\\$ {v:,.0f}".replace(",", ".")))
    ax.set_xlabel("Erro absoluto médio (MAE, R$/mês) — menor é melhor")
    ax.grid(axis="x", color=GRID, lw=0.8)
    ax.set_axisbelow(True)
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.16), ncol=2, fontsize=8, frameon=False, labelcolor=INK_2)
    _style(ax)
    _save(fig, path, "Comparação dos regressores",
          "★ selecionado pelo menor MAE na validação cruzada, não pelo teste • valores fora da escala indicados por →")


def plot_predictions(experiment: RegressionExperiment, data: ModelData, path: Path):
    result = experiment.results[experiment.selected]
    real = data.y.loc[experiment.test_index].to_numpy()
    pred = result.predictions
    low, high = np.exp(experiment.interval_log)
    fig, ax = plt.subplots(figsize=(7.5, 6.5))
    grid = np.geomspace(400, 40000, 50)
    ax.fill_between(grid, grid * low, grid * high, color=SERIES_1, alpha=0.12, lw=0,
                    label=f"Intervalo de {INTERVAL[1] - INTERVAL[0]:.0%} (resíduos fora da amostra)")
    ax.plot(grid, grid, color=AXIS, lw=1, ls="--", label="Previsão perfeita")
    inside = (real >= pred * low) & (real <= pred * high)
    ax.scatter(pred[inside], real[inside], s=28, color=SERIES_1, edgecolor=SURFACE, linewidth=0.6, zorder=3,
               label=f"Dentro do intervalo (n={inside.sum()})")
    ax.scatter(pred[~inside], real[~inside], s=34, color=SERIES_2, marker="D", edgecolor=SURFACE, linewidth=0.6,
               zorder=3, label=f"Fora do intervalo (n={(~inside).sum()})")
    ax.set_xscale("log")
    ax.set_yscale("log")
    ticks = [500, 1000, 2000, 5000, 10000, 20000]
    _money_axis(ax.xaxis, ticks)
    _money_axis(ax.yaxis, ticks)
    lo, hi = min(real.min(), pred.min()) * 0.8, max(real.max(), pred.max()) * 1.25
    ax.set_xlim(lo, hi)
    ax.set_ylim(lo, hi)
    ax.set_xlabel("Aluguel previsto (escala log)")
    ax.set_ylabel("Aluguel anunciado (escala log)")
    ax.grid(color=GRID, lw=0.6)
    ax.set_axisbelow(True)
    ax.legend(fontsize=8, frameon=False, labelcolor=INK_2, loc="upper left")
    _style(ax)
    _save(fig, path, "Previsto × anunciado no teste reservado",
          f"{MODEL_LABELS.get(experiment.selected)} • n = {len(real)} casas • cobertura do intervalo "
          f"{experiment.interval_coverage:.0%}")


def plot_bias(by_band: pd.DataFrame, path: Path):
    fig, ax = plt.subplots(figsize=(8, 4))
    y = np.arange(len(by_band))[::-1]
    values = by_band.vies_mediano.to_numpy() * 100
    ax.barh(y, values, height=0.5, color=[SERIES_2 if v > 0 else SERIES_1 for v in values], zorder=2)
    for yi, v, n in zip(y, values, by_band.n):
        ax.text(v + (1.5 if v >= 0 else -1.5), yi, f"{v:+.0f}% (n={int(n)})", va="center",
                ha="left" if v >= 0 else "right", fontsize=9, color=INK)
    ax.axvline(0, color=AXIS, lw=1)
    ax.set_yticks(y, [f"Faixa {f}" for f in by_band.index])
    span = max(10, np.abs(values).max() * 1.6)
    ax.set_xlim(-span, span)
    ax.set_xlabel("Erro percentual mediano (previsto − anunciado) / anunciado")
    ax.grid(axis="x", color=GRID, lw=0.8)
    ax.set_axisbelow(True)
    _style(ax)
    _save(fig, path, "Viés por faixa de preço",
          "Positivo = modelo superestima; negativo = subestima • faixas pelos tercis do treino")


def plot_stability(runs: pd.DataFrame, summary: pd.DataFrame, path: Path):
    order = list(summary.modelo)[::-1]
    fig, ax = plt.subplots(figsize=(9, 5.2))
    finite = runs.teste_mae[runs.teste_mae < 10000]
    limit = finite.max() * 1.15
    for y, name in enumerate(order):
        values = runs.loc[runs.modelo.eq(name), "teste_mae"].to_numpy()
        jitter = np.linspace(-0.12, 0.12, len(values))
        ax.scatter(np.minimum(values, limit * 0.98), y + jitter, s=18, color=MUTED, zorder=2)
        median = np.median(values)
        ax.plot([min(median, limit * 0.98)] * 2, [y - 0.28, y + 0.28], color=SERIES_1, lw=2.5, zorder=3)
        if (values >= limit).any():
            ax.text(limit * 0.97, y + 0.3, f"{(values >= limit).sum()} fora da escala →", ha="right", fontsize=7,
                    color=INK_2)
    ax.plot([], [], color=SERIES_1, lw=2.5, label="Mediana no teste")
    ax.scatter([], [], s=18, color=MUTED, label="Uma partição treino/teste")
    selected = summary.set_index("modelo").vezes_selecionado
    ax.set_yticks(range(len(order)), [f"{MODEL_LABELS.get(n, n)} ({int(selected[n])}×)" for n in order])
    ax.set_xlim(0, limit)
    ax.xaxis.set_major_formatter(FuncFormatter(lambda v, _: f"R\\$ {v:,.0f}".replace(",", ".")))
    ax.set_xlabel("MAE no teste reservado (R$/mês)")
    ax.grid(axis="x", color=GRID, lw=0.8)
    ax.set_axisbelow(True)
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.16), ncol=2, fontsize=8, frameon=False, labelcolor=INK_2)
    _style(ax)
    _save(fig, path, "Estabilidade entre partições",
          f"{runs.semente.nunique()} sementes • (N×) = vezes em que a validação cruzada escolheu o modelo")


def write_regression_report(experiment: RegressionExperiment, data: ModelData, out: Path, *, band_limits,
                            manifest_extra: dict, stability_runs: pd.DataFrame | None = None) -> dict:
    out.mkdir(parents=True, exist_ok=False)
    experiment.metrics_table().to_csv(out / "metricas.csv", index=False)
    errors, by_bairro, by_band = residual_analysis(experiment, data, band_limits)
    errors.to_csv(out / "erros_teste.csv", index=False)
    by_bairro.to_csv(out / "erros_por_bairro.csv")
    by_band.to_csv(out / "erros_por_faixa.csv")
    plot_comparison(experiment, out / "comparacao_modelos.png")
    plot_predictions(experiment, data, out / "previsto_x_anunciado.png")
    plot_bias(by_band, out / "vies_por_faixa.png")
    joblib.dump(experiment.results[experiment.selected].estimator, out / "modelo_selecionado.joblib")
    stability = None
    if stability_runs is not None:
        stability_runs.to_csv(out / "estabilidade_execucoes.csv", index=False)
        summary = stability_summary(stability_runs)
        summary.to_csv(out / "estabilidade.csv", index=False)
        plot_stability(stability_runs, summary, out / "estabilidade.png")
        stability = {"sementes": sorted(map(int, stability_runs.semente.unique())),
                     "resumo": json.loads(summary.round(4).to_json(orient="records"))}
    manifest = {
        **manifest_extra,
        "semente": experiment.seed, "n_casas": len(data.X), "n_treino": len(experiment.dev_index),
        "n_teste": len(experiment.test_index), "atributos": list(data.X.columns),
        "alvo": "log(aluguel); previsões e métricas em reais",
        "modelo_selecionado": experiment.selected, "criterio_selecao": "menor MAE médio na validação cruzada",
        "validacao": "GroupShuffleSplit 80/20 por imóvel; GridSearchCV com GroupKFold(5) no treino",
        "intervalo": {"quantis": list(INTERVAL), "log_residuos": list(experiment.interval_log),
                      "multiplicadores": [float(np.exp(v)) for v in experiment.interval_log],
                      "cobertura_teste": experiment.interval_coverage},
        "faixas_para_analise_de_residuos": [float(b) for b in band_limits],
        "melhores_parametros": {n: {k: str(v) for k, v in r.best_params.items()} for n, r in experiment.results.items()},
        "estabilidade": stability,
        "avisos": experiment.warnings + ["Estimativa de aluguel anunciado; não é avaliação imobiliária oficial."],
        "status": "complete",
    }
    (out / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return manifest
