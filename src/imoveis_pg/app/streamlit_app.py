"""Observatório de aluguéis de casas em Ponta Grossa (Streamlit).

Execute com ``python -m imoveis_pg app --artefatos data/app/AAAA-MM-DD``.
Nenhum modelo é treinado aqui: tudo vem dos artefatos de ``build-app``.
"""
from __future__ import annotations

import argparse
import html
import os
import sys
from pathlib import Path

import folium
import numpy as np
import pandas as pd
import streamlit as st
from streamlit_folium import st_folium

from imoveis_pg.app.simulador import MIN_BAIRRO, Simulator, brl

CENTER = (-25.095, -50.162)
TILES = "OpenStreetMap"  # sem chave de API; uso acadêmico de baixo volume, com atribuição
# Paleta de referência: rampa azul sequencial, cinza neutro para "dados insuficientes", tinta neutra nos pontos.
RAMP = ["#cde2fb", "#86b6ef", "#3987e5", "#1c5cab"]
NO_DATA, INK, INK_2, OUTLINE = "#e1e0d9", "#0b0b0b", "#52514e", "#8a897f"
INDICATORS = {"Aluguel mediano (R$/mês)": "aluguel", "Aluguel mediano por área (R$/m²)": "aluguel_m2"}


def artifacts_dir() -> Path:
    parser = argparse.ArgumentParser()
    parser.add_argument("--artefatos", type=Path)
    known, _ = parser.parse_known_args(sys.argv[1:])
    if known.artefatos:
        return known.artefatos
    if os.environ.get("IMOVEIS_PG_APP_DIR"):
        return Path(os.environ["IMOVEIS_PG_APP_DIR"])
    candidates = sorted(Path("data/app").glob("*/modelos.joblib"))
    if not candidates:
        st.error("Artefatos não encontrados. Rode `python -m imoveis_pg build-app` e abra o app com `--artefatos`.")
        st.stop()
    return candidates[-1].parent


@st.cache_resource(show_spinner="Carregando modelo e dados…")
def load(path: str) -> Simulator:
    return Simulator(Path(path))


def fmt_money(value) -> str:
    return "—" if pd.isna(value) else brl(value)


def fmt_m2(value) -> str:
    return "—" if pd.isna(value) else f"R$ {value:.2f}".replace(".", ",") + "/m²"


def filter_listings(df: pd.DataFrame) -> pd.DataFrame:
    """Filtros do mapa, exibidos só na aba do mapa (o simulador não depende deles)."""
    with st.expander("Filtros", expanded=True):
        c = st.columns([1, 1.9, 1.1, 1.6])
        c[0].selectbox("Finalidade", ["Locação"], disabled=True,
                       help="A base atual contém apenas anúncios de locação.")
        subtipos = c[1].multiselect("Tipo de imóvel", ["casa", "sobrado", "condominio"],
                                    default=["casa", "sobrado", "condominio"],
                                    format_func={"casa": "Casa", "sobrado": "Sobrado",
                                                 "condominio": "Casa em condomínio"}.get)
        usos = c[2].multiselect("Uso", ["residencial", "comercial"], default=["residencial"])
        bairros = c[3].multiselect("Bairros", sorted(df.bairro_oficial.dropna().unique()), placeholder="Todos")
        c = st.columns([2, 1.2, 1.8])
        low, high = int(df.aluguel.min()), int(df.aluguel.max())
        faixa = c[0].slider("Aluguel (R$/mês)", low, high, (low, high), step=100)
        quartos = c[1].multiselect("Quartos", ["1", "2", "3", "4", "5+", "não informado"], placeholder="Todos")
        perfis = c[2].multiselect("Perfil", sorted(df.perfil.dropna().unique()), placeholder="Todos")
    mask = df.uso.isin(usos) & df.subtipo.isin(subtipos) & df.aluguel.between(*faixa)
    if bairros:
        mask &= df.bairro_oficial.isin(bairros)
    if quartos:
        q = df.quartos.map(lambda v: "não informado" if pd.isna(v) else ("5+" if v >= 5 else str(int(v))))
        mask &= q.isin(quartos)
    if perfis:
        mask &= df.perfil.isin(perfis)
    return df[mask]


def bairro_stats(df: pd.DataFrame, bairros) -> pd.DataFrame:
    stats = df.groupby("bairro_oficial").agg(
        anuncios=("aluguel", "size"), aluguel=("aluguel", "median"), aluguel_m2=("aluguel_m2", "median"),
        q1=("aluguel", lambda s: s.quantile(.25)), q3=("aluguel", lambda s: s.quantile(.75)))
    stats = stats.reindex(sorted(bairros.NM_BAIRRO)).rename_axis("bairro")
    stats["anuncios"] = stats.anuncios.fillna(0).astype(int)
    stats["confiavel"] = stats.anuncios.ge(MIN_BAIRRO)
    return stats


def color_scale(values: pd.Series) -> tuple[list[float], callable]:
    values = values.dropna()
    if len(values) < 2:
        return [], lambda v: NO_DATA
    edges = list(np.quantile(values, [0.25, 0.5, 0.75]))
    return edges, lambda v: RAMP[int(np.searchsorted(edges, v, side="right"))]


def legend(edges, indicator: str) -> str:
    fmt = fmt_m2 if indicator == "aluguel_m2" else fmt_money
    if not edges:
        return "Poucos bairros com dados suficientes para colorir."
    labels = [f"até {fmt(edges[0])}", f"{fmt(edges[0])} – {fmt(edges[1])}", f"{fmt(edges[1])} – {fmt(edges[2])}",
              f"acima de {fmt(edges[2])}"]
    items = "".join(f'<span style="display:inline-flex;align-items:center;margin-right:14px">'
                    f'<span style="width:14px;height:14px;background:{c};border:1px solid {OUTLINE};'
                    f'margin-right:5px;display:inline-block"></span>{html.escape(t)}</span>'
                    for c, t in zip(RAMP, labels))
    items += (f'<span style="display:inline-flex;align-items:center;margin-right:14px">'
              f'<span style="width:14px;height:14px;background:{NO_DATA};border:1px dashed {OUTLINE};'
              f'margin-right:5px;display:inline-block"></span>menos de {MIN_BAIRRO} anúncios (baixa confiabilidade)</span>'
              f'<span style="display:inline-flex;align-items:center;margin-right:14px">● localização exata&nbsp;&nbsp;'
              f'○ aproximada</span>')
    return f'<div style="font-size:0.85rem;color:{INK_2};line-height:2">{items}<br>Faixas por quartis dos bairros com dados suficientes.</div>'


def popup(row) -> str:
    rows = [("Bairro", row.bairro_oficial), ("Tipo", row.subtipo), ("Aluguel", fmt_money(row.aluguel)),
            ("Área", "—" if pd.isna(row.area_m2) else f"{row.area_m2:.0f} m²"),
            ("Quartos", "—" if pd.isna(row.quartos) else f"{row.quartos:.0f}"),
            ("R$/m²", fmt_m2(row.aluguel_m2))]
    if isinstance(row.perfil, str):
        rows.append(("Perfil", row.perfil))
    if pd.notna(getattr(row, "aluguel_estimado", np.nan)):
        rows.append(("Estimado pelo modelo", fmt_money(row.aluguel_estimado)))
    if isinstance(row.comparacao, str):
        rows.append(("Anunciado × estimado", f"{row.comparacao} (faixa {row.faixa_anunciada}, "
                                             f"modelo: {row.faixa_estimada})"))
    rows.append(("Localização", "exata" if row.precisao_localizacao == "exata" else "aproximada"))
    body = "".join(f"<tr><td style='color:{INK_2};padding-right:8px'>{html.escape(k)}</td>"
                   f"<td>{html.escape(str(v))}</td></tr>" for k, v in rows)
    link = f"<a href='{html.escape(row.url)}' target='_blank'>Ver anúncio ({html.escape(row.fonte)})</a>"
    return f"<table style='font-size:12px'>{body}</table>{link}"


def market_map(df: pd.DataFrame, stats: pd.DataFrame, bairros, indicator: str, show_points: bool):
    fmap = folium.Map(location=CENTER, zoom_start=12, tiles=TILES, control_scale=True)
    edges, color = color_scale(stats.loc[stats.confiavel, indicator])
    geo = bairros.merge(stats, left_on="NM_BAIRRO", right_index=True, how="left")
    fmt = fmt_m2 if indicator == "aluguel_m2" else fmt_money
    geo["rotulo"] = [f"{r.NM_BAIRRO}: {r.anuncios} anúncio(s), mediana {fmt(r[indicator])}"
                     + ("" if r.confiavel else " · baixa confiabilidade") for _, r in geo.iterrows()]

    def style(feature):
        p = feature["properties"]
        ok = p.get("confiavel") and p.get(indicator) is not None
        return {"fillColor": color(p[indicator]) if ok else NO_DATA, "fillOpacity": 0.65 if ok else 0.45,
                "color": OUTLINE, "weight": 1, "dashArray": None if ok else "4 4"}

    folium.GeoJson(geo[["NM_BAIRRO", "rotulo", "confiavel", indicator, "geometry"]].to_json(), style_function=style,
                   tooltip=folium.GeoJsonTooltip(["rotulo"], labels=False), name="Bairros").add_to(fmap)
    if show_points:
        for row in df.itertuples():
            exact = row.precisao_localizacao == "exata"
            folium.CircleMarker((row.latitude, row.longitude), radius=4.5, color="#ffffff", weight=1.2,
                                fill=True, fill_color=INK if exact else "#ffffff", fill_opacity=0.85 if exact else 1,
                                popup=folium.Popup(popup(row), max_width=320)).add_to(fmap)
            if not exact:
                folium.CircleMarker((row.latitude, row.longitude), radius=3.2, color=INK, weight=1.5,
                                    fill=False).add_to(fmap)
    return fmap, edges


def tab_market(sim: Simulator, df: pd.DataFrame):
    indicator_label = st.radio("Indicador por bairro", list(INDICATORS), horizontal=True)
    indicator = INDICATORS[indicator_label]
    stats = bairro_stats(df, sim.bairros)
    cols = st.columns(4)
    cols[0].metric("Anúncios filtrados", f"{len(df)}")
    cols[1].metric("Aluguel mediano", fmt_money(df.aluguel.median()))
    cols[2].metric("Mediana R$/m²", fmt_m2(df.aluguel_m2.median()))
    cols[3].metric("Bairros com ≥ 5 anúncios", f"{int(stats.confiavel.sum())} de {len(stats)}")
    show_points = st.toggle("Mostrar anúncios", value=True)
    fmap, edges = market_map(df, stats, sim.bairros, indicator, show_points)
    st_folium(fmap, height=560, use_container_width=True, returned_objects=[], key="mapa_mercado")
    st.markdown(legend(edges, indicator), unsafe_allow_html=True)
    st.caption("Posições aproximadas vêm de geocodificação (IBGE CNEFE 2022) e podem estar a centenas de metros "
               "do imóvel. Endereços não são exibidos.")
    st.subheader("Indicadores por bairro")
    table = stats.reset_index().rename(columns={"bairro": "Bairro", "anuncios": "Anúncios", "aluguel": "Mediana (R$)",
                                                "aluguel_m2": "Mediana (R$/m²)", "q1": "Q1 (R$)", "q3": "Q3 (R$)",
                                                "confiavel": "≥ 5 anúncios"})
    st.dataframe(table.sort_values("Anúncios", ascending=False), hide_index=True, width="stretch",
                 column_config={c: st.column_config.NumberColumn(format="%.0f") for c in ["Mediana (R$)", "Q1 (R$)", "Q3 (R$)"]}
                 | {"Mediana (R$/m²)": st.column_config.NumberColumn(format="%.2f")})
    export = df.drop(columns=["elegivel"]).to_csv(index=False).encode("utf-8")
    st.download_button("Exportar anúncios filtrados (CSV)", export, "anuncios_filtrados.csv", "text/csv")


def tab_simulator(sim: Simulator):
    st.markdown("**1.** Clique no mapa para escolher o local.  **2.** Informe as características.  "
                "**3.** Veja a faixa estimada e casas parecidas.")
    left, right = st.columns([3, 2], gap="large")
    with left:
        fmap = folium.Map(location=CENTER, zoom_start=12, tiles=TILES, control_scale=True)
        folium.GeoJson(sim.bairros[["NM_BAIRRO", "geometry"]].to_json(),
                       style_function=lambda f: {"fillColor": RAMP[0], "fillOpacity": 0.12, "color": INK_2,
                                                 "weight": 1.5},
                       tooltip=folium.GeoJsonTooltip(["NM_BAIRRO"], labels=False)).add_to(fmap)
        point = st.session_state.get("ponto")
        if point:
            folium.Marker(point, icon=folium.Icon(color="blue", icon="home", prefix="fa")).add_to(fmap)
        st.caption("Contornos: bairros oficiais (IBGE, Censo 2022). Os nomes do mapa-base vêm do OpenStreetMap "
                   "e podem ser de loteamentos, diferentes dos bairros oficiais.")
        result = st_folium(fmap, height=520, use_container_width=True, returned_objects=["last_clicked"],
                           key="mapa_simulador")
        clicked = (result or {}).get("last_clicked")
        if clicked and (clicked["lat"], clicked["lng"]) != (tuple(point) if point else None):
            st.session_state["ponto"] = (clicked["lat"], clicked["lng"])
            st.rerun()
    with right:
        point = st.session_state.get("ponto")
        if point:
            st.success(f"Local escolhido: {point[0]:.5f}, {point[1]:.5f}")
        else:
            st.info("Nenhum local escolhido: clique no mapa.")
        with st.form("caracteristicas"):
            area = st.number_input("Área construída (m²)", min_value=10, max_value=5000, value=80, step=5)
            c1, c2 = st.columns(2)
            quartos = c1.number_input("Quartos", min_value=0, max_value=20, value=2)
            banheiros = c2.number_input("Banheiros", min_value=0, max_value=20, value=1)
            vagas = c1.number_input("Vagas de garagem", min_value=0, max_value=20, value=1)
            suites = c2.number_input("Suítes", min_value=0, max_value=20, value=0)
            subtipo = st.selectbox("Tipo", ["casa", "sobrado", "condominio"],
                                   format_func={"casa": "Casa", "sobrado": "Sobrado",
                                                "condominio": "Casa em condomínio"}.get)
            submitted = st.form_submit_button("Estimar aluguel", type="primary", disabled=point is None,
                                              width="stretch")
    if not (submitted and point):
        return
    res = sim.simulate(point[0], point[1], area_m2=float(area), quartos=int(quartos), banheiros=int(banheiros),
                       vagas=int(vagas), suites=int(suites), subtipo=subtipo)
    if not res.disponivel:
        for warning in res.avisos:
            st.error(warning, icon="⛔")
        return
    st.divider()
    cv = sim.metadata["validacao_cruzada"]["balanced_accuracy"]
    q1, median, q3 = res.referencia_comparaveis
    if res.valor is not None:
        c0, c1, c2, c3 = st.columns(4)
        c0.metric("Aluguel estimado", fmt_money(res.valor))
        c0.caption(f"80% de chance entre {fmt_money(res.valor_intervalo[0])} e {fmt_money(res.valor_intervalo[1])}")
    else:
        c1, c2, c3 = st.columns(3)
    c1.metric("Faixa estimada", res.faixa.upper())
    c1.caption(res.faixa_intervalo)
    c2.metric("Casas parecidas anunciadas (mediana)", fmt_money(median))
    c2.caption(f"metade entre {fmt_money(q1)} e {fmt_money(q3)}")
    c3.metric("Bairro oficial", res.bairro)
    c3.caption(f"{res.anuncios_proximos} casa(s) anunciada(s) num raio de 1 km")
    st.markdown("**Probabilidade por faixa**")
    for name, p in res.probabilidades.items():
        st.progress(p, text=f"{name} ({sim.band_interval(sim.band_names.index(name))}): {p:.0%}")
    st.caption("Probabilidades do modelo, não calibradas: indicam a preferência entre faixas, não a chance real de acerto.")
    if res.perfil:
        st.markdown(f"**Perfil semelhante:** {res.perfil}")
    for warning in res.avisos:
        st.warning(warning, icon="⚠️")
    regression = sim.metadata.get("regressao") or {}
    value_note = ""
    if res.valor is not None:
        err = regression["validacao_fora_da_amostra"]
        value_note = (f" O valor em reais vem de um {regression['modelo'].upper()}, que erra em média "
                      f"{fmt_money(err['mae'])} ({err['mape']:.0%}) em casas que não viu; o intervalo de 80% "
                      "vem desses erros.")
    st.caption(f"O classificador ({sim.metadata['modelo'].upper()}) acerta a faixa em cerca de {cv['media']:.0%} dos "
               f"casos (balanced accuracy na validação cruzada, ± {cv['desvio']:.0%}).{value_note} Estimativa de "
               "aluguel anunciado, não de preço negociado; não é avaliação imobiliária oficial.")
    st.markdown("**Casas parecidas anunciadas** (área, quartos e proximidade)")
    table = res.comparaveis.rename(columns={"bairro_oficial": "Bairro", "subtipo": "Tipo", "area_m2": "Área (m²)",
                                            "quartos": "Quartos", "banheiros": "Banheiros", "aluguel": "Aluguel (R$)",
                                            "distancia_km": "Distância (km)", "fonte": "Fonte", "url": "Anúncio"})
    st.dataframe(table, hide_index=True, width="stretch", column_config={
        "Anúncio": st.column_config.LinkColumn(display_text="abrir"),
        "Aluguel (R$)": st.column_config.NumberColumn(format="%.0f"),
        "Distância (km)": st.column_config.NumberColumn(format="%.1f")})


def tab_quality(sim: Simulator):
    meta, df = sim.metadata, sim.listings
    eligible = df[df.elegivel]
    c = st.columns(4)
    c[0].metric("Anúncios no mapa", len(df))
    c[1].metric("Casas usadas no modelo", meta["n_casas_modelo"])
    c[2].metric("Imobiliárias", len(meta["fontes"]))
    c[3].metric("Data da coleta", ", ".join(meta["data_coleta"]))
    left, right = st.columns(2)
    with left:
        st.markdown("**Anúncios por imobiliária**")
        by_source = df.groupby("fonte").agg(anuncios=("id", "size"), modelo=("elegivel", "sum"))
        st.dataframe(by_source.rename_axis("Imobiliária").rename(columns={"anuncios": "Anúncios",
                                                                          "modelo": "Casas no modelo"}),
                     width="stretch")
        st.markdown("**Precisão da localização (casas do modelo)**")
        st.dataframe(eligible.precisao_localizacao.fillna("sem").value_counts().rename_axis("Localização")
                     .rename("Casas"), width="stretch")
    with right:
        st.markdown("**Atributos ausentes (casas do modelo)**")
        missing = eligible[["area_m2", "quartos", "banheiros", "vagas", "suites"]].isna().mean()
        missing.index = ["Área", "Quartos", "Banheiros", "Vagas", "Suítes"]
        st.dataframe(missing.map(lambda v: f"{v:.0%}").rename_axis("Atributo").rename("Ausentes"), width="stretch")
        st.caption("Suíte ausente costuma significar “sem suíte”: nenhum anúncio informa zero.")
        st.markdown("**Bairros com poucos dados (< 5 casas)**")
        counts = eligible.bairro_oficial.value_counts().reindex(sorted(sim.bairros.NM_BAIRRO), fill_value=0)
        st.dataframe(counts[counts < MIN_BAIRRO].rename_axis("Bairro").rename("Casas"), width="stretch")
    st.subheader("Anunciado × estimado")
    st.caption("Faixa anunciada comparada à prevista por um modelo que não viu o anúncio (validação cruzada). "
               "Diferenças não indicam erro nem fraude: podem ser imóveis especiais, anúncios incorretos ou oportunidades.")
    st.dataframe(eligible.comparacao.value_counts().rename_axis("Anunciado em relação ao modelo").rename("Casas"),
                 width="stretch")
    outliers = eligible[eligible.comparacao.ne("dentro do padrão")][
        ["bairro_oficial", "subtipo", "area_m2", "quartos", "aluguel", "faixa_anunciada", "faixa_estimada", "comparacao", "url"]]
    outliers = outliers.rename(columns={"bairro_oficial": "Bairro", "subtipo": "Tipo", "area_m2": "Área (m²)",
                                        "quartos": "Quartos", "aluguel": "Aluguel (R$)",
                                        "faixa_anunciada": "Faixa anunciada", "faixa_estimada": "Faixa do modelo",
                                        "comparacao": "Comparação"})
    st.dataframe(outliers, hide_index=True, width="stretch",
                 column_config={"url": st.column_config.LinkColumn("Anúncio", display_text="abrir")})


def tab_about(sim: Simulator):
    meta = sim.metadata
    limits = meta["faixas"]["limites"]
    st.markdown(f"""
**O que o app faz.** Mostra casas anunciadas para alugar em Ponta Grossa e estima a **faixa de aluguel** de uma casa
a partir do local e das características. Faixas: baixa (até {brl(limits[0])}), média ({brl(limits[0])} a
{brl(limits[1])}) e alta (acima de {brl(limits[1])}), definidas pelos tercis da base.

**Modelo.** {meta['modelo'].upper()} escolhido entre árvore de decisão, KNN, SVM e MLP por validação cruzada agrupada
por imóvel; ver `docs/classificacao.md`. Perfis vêm do agrupamento K-means (`docs/agrupamento.md`).

**Dados.** Anúncios públicos de {', '.join(meta['fontes'])}, coletados em {', '.join(meta['data_coleta'])}.
Bairros oficiais: malha de bairros do IBGE (Censo 2022). Geocodificação: CNEFE 2022 (IBGE).
""")
    for warning in meta["avisos"]:
        st.info(warning, icon="ℹ️")
    st.markdown("Regiões com menos de 5 anúncios aparecem em cinza tracejado e recebem aviso no simulador. "
                "A concentração de anúncios não indica tamanho do mercado nem preço; um único empreendimento "
                "pode gerar vários anúncios.")


def main():
    st.set_page_config(page_title="Aluguéis em Ponta Grossa", page_icon="🏠", layout="wide")
    sim = load(str(artifacts_dir().resolve()))
    st.title("Aluguéis de casas em Ponta Grossa")
    st.caption(f"Protótipo acadêmico (IFPR) • {len(sim.listings)} anúncios de {len(sim.metadata['fontes'])} "
               f"imobiliárias • coleta de {', '.join(sim.metadata['data_coleta'])}")
    tabs = st.tabs(["Mapa do mercado", "Simulador", "Qualidade dos dados", "Sobre e limitações"])
    with tabs[0]:
        df = filter_listings(sim.listings)
        if df.empty:
            st.warning("Nenhum anúncio com os filtros atuais.")
        else:
            tab_market(sim, df)
    with tabs[1]:
        tab_simulator(sim)
    with tabs[2]:
        tab_quality(sim)
    with tabs[3]:
        tab_about(sim)


main()
