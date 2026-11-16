"""Tabelas e gráficos exploratórios de anúncios, sem modelos preditivos."""
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from .data import normalize_text

METRICS = {"aluguel": "Aluguel (R$/mês)", "custo_mensal_total": "Custo total (R$/mês)",
           "aluguel_m2": "Aluguel por área (R$/m²)"}
CORRELATION = ["aluguel", "area_m2", "quartos", "banheiros", "vagas", "custo_mensal_total"]


def analyze_listings(snapshot: pd.DataFrame, output_dir: Path, *, synthetic_input: bool = False) -> dict:
    out = Path(output_dir)
    if out.exists() and (not out.is_dir() or any(out.iterdir())):
        raise ValueError("Diretório de EDA deve estar vazio.")
    out.mkdir(parents=True, exist_ok=True)
    synthetic = synthetic_input or bool(snapshot.get("sintetico", pd.Series(dtype=str)).map(normalize_text).isin(["sim", "true", "1"]).any())
    tag = " • DADOS SINTÉTICOS" if synthetic else ""
    result = {"tabelas": [], "graficos": [], "avisos": [], "dados_sinteticos": synthetic,
              "n_anuncios": len(snapshot)}
    rent = snapshot.loc[snapshot.finalidade.map(normalize_text).isin(["locacao", "aluguel"])].copy()
    rent = rent.loc[rent.aluguel.gt(0)]
    result["n_locacao"] = len(rent)
    if len(rent) < 2:
        result["avisos"].append("Menos de dois anúncios de locação: dispersão e correlação indisponíveis.")
    result["avisos"].append("Análise de anúncios; não representa preços negociados nem comprova cobertura municipal.")

    def save_table(frame, name, index=False):
        frame.to_csv(out / name, index=index)
        result["tabelas"].append(name)

    def save_plot(fig, name, title):
        fig.suptitle(title + tag, fontsize=13)
        fig.tight_layout(rect=(0, 0, 1, .95))
        fig.savefig(out / name, dpi=120)
        plt.close(fig)
        result["graficos"].append(name)

    fig, axes = plt.subplots(3, 2, figsize=(11, 10))
    for (column, label), (hist, box) in zip(METRICS.items(), axes):
        values = rent[column].dropna()
        hist.set_title(f"{label} — n={len(values)}")
        box.set_title(f"Boxplot — n={len(values)}")
        if len(values):
            hist.hist(values, bins=min(15, max(1, int(np.sqrt(len(values))))), color="#287b86")
            box.boxplot(values, orientation="horizontal")
        else:
            for ax in (hist, box):
                ax.text(.5, .5, "Dados insuficientes", ha="center", transform=ax.transAxes)
        hist.set_ylabel("Anúncios")
        for ax in (hist, box):
            ax.set_xlabel(label)
    save_plot(fig, "distribuicoes.png", "Distribuição dos valores de locação")

    official = "bairro_oficial" in snapshot
    bairro_key = "bairro_oficial" if official else "bairro_normalizado"
    for key, name in [(bairro_key, "bairro"), ("tipo", "tipo"), ("finalidade", "finalidade")]:
        all_rows = snapshot.copy()
        label = ("Bairro não resolvido" if official else "Bairro não informado") if name == "bairro" else "Não informado"
        all_rows[key] = all_rows[key].fillna("").replace("", label)
        data = rent.copy()
        data[key] = data[key].fillna("").replace("", label)
        counts = all_rows.groupby(key).size().rename("n_anuncios")
        stats = data.groupby(key).agg(
            n=("aluguel", "count"), mediana_aluguel=("aluguel", "median"),
            q1_aluguel=("aluguel", lambda x: x.quantile(.25)),
            q3_aluguel=("aluguel", lambda x: x.quantile(.75)),
            desvio_aluguel=("aluguel", "std"),
            mediana_aluguel_m2=("aluguel_m2", "median"),
            media_custo_total=("custo_mensal_total", "mean"))
        table = counts.to_frame().join(stats)
        table["n"] = table["n"].fillna(0).astype(int)
        save_table(table.reset_index(), f"por_{name}.csv")
        small = table.loc[table.n.lt(2)].index.tolist()
        if small:
            result["avisos"].append(f"Grupos de {name} com menos de duas locações: " + ", ".join(map(str, small)))
        # Tables retain all groups; a readable plot displays the 20 largest.
        displayed = table.sort_values("n_anuncios", ascending=False).head(20)
        if len(table) > 20:
            result["avisos"].append(f"Gráfico por {name} mostra os 20 maiores grupos; tabela contém todos.")
        fig, (count_ax, price_ax) = plt.subplots(1, 2, figsize=(12, max(4, .4 * len(displayed) + 2)))
        positions = np.arange(len(displayed))
        labels = [str(x) for x in displayed.index]
        count_ax.barh(positions, displayed.n_anuncios, color="#287b86")
        count_ax.set_yticks(positions, labels)
        count_ax.set_xlabel("Anúncios de todas as finalidades")
        for position, group in enumerate(displayed.index):
            values = data.loc[data[key].eq(group), "aluguel"]
            if len(values):
                price_ax.scatter(values, np.full(len(values), position), alpha=.65, s=20)
        price_ax.set_yticks(positions, [f"{g} (n={int(displayed.loc[g, 'n'])})" for g in displayed.index])
        price_ax.set_xlabel("Aluguel (R$/mês) • somente locação")
        save_plot(fig, f"comparacao_{name}.png", f"Contagem e variabilidade por {name}")

    numeric = rent[CORRELATION]
    valid = numeric.notna().astype(int)
    pairs = valid.T.dot(valid)
    corr = numeric.corr(min_periods=2)
    save_table(corr, "correlacao.csv", index=True)
    save_table(pairs, "correlacao_n.csv", index=True)
    if corr.isna().any().any():
        result["avisos"].append("Correlação indisponível para pares constantes ou com dados insuficientes.")
    fig, ax = plt.subplots(figsize=(9, 7))
    matrix = ax.imshow(corr.to_numpy(), vmin=-1, vmax=1, cmap="coolwarm")
    ax.set_xticks(range(len(CORRELATION)), CORRELATION, rotation=35, ha="right")
    ax.set_yticks(range(len(CORRELATION)), CORRELATION)
    for i in range(len(CORRELATION)):
        for j in range(len(CORRELATION)):
            value = corr.iloc[i, j]
            text = "N/D" if pd.isna(value) else f"{value:.2f}"
            ax.text(j, i, f"{text}\nn={pairs.iloc[i,j]}", ha="center", va="center", fontsize=8)
    fig.colorbar(matrix, ax=ax, label="Correlação (não implica causalidade)")
    save_plot(fig, "correlacao.png", "Correlação de atributos de locação")

    fig, ax = plt.subplots(figsize=(9, 6))
    geo = snapshot.loc[snapshot.coordenadas_validas].copy()
    precision = geo.get("precisao_localizacao", pd.Series("", index=geo.index)).map(normalize_text)
    exact = precision.eq("exata")
    for mask, label, marker in [(exact, "Declarada exata (não verificada)", "o"),
                                (~exact, "Aproximada ou precisão desconhecida", "x")]:
        part = geo.loc[mask]
        if len(part):
            ax.scatter(part.longitude, part.latitude, label=f"{label} • n={len(part)}", marker=marker)
    if len(geo):
        ax.legend(fontsize=8)
    else:
        ax.text(.5, .5, "Nenhum par de coordenadas válido", ha="center", transform=ax.transAxes)
    ax.set(xlabel="Longitude (graus WGS84)", ylabel="Latitude (graus WGS84)")
    save_plot(fig, "inspecao_espacial.png", "Inspeção espacial • município ainda não validado")
    return result
