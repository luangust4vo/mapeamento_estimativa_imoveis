"""Artefatos do app, gerados fora da interface (nenhum treino acontece a cada clique).

- ``anuncios.csv``: anúncios com coordenadas, sem endereço, com faixa, perfil e previsão fora da amostra.
- ``bairros.geojson``: polígonos dos 16 bairros oficiais.
- ``modelos.joblib``: classificador final (reajustado na base inteira) e modelo de perfis.
- ``metadados.json``: data da base, métricas de validação, limites das faixas e avisos.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.base import clone
from sklearn.cluster import KMeans
from sklearn.model_selection import GridSearchCV, GroupKFold
from sklearn.preprocessing import StandardScaler

from ..geo.bairros import load_bairros
from ..modelagem.agrupamento import PROFILE_FEATURES, profile_table
from ..modelagem.classificacao import BAND_NAMES, SCORING, QuantileBandClassifier, model_specs
from ..modelagem.dataset import build_dataset, distance_km, house_subtype, prepare_snapshot

FINAL_MODEL = "mlp"   # escolhido pela validação cruzada em 7 de 10 partições (docs/classificacao.md)
N_BANDS = 3
N_PROFILES = 3        # K-means k=3 (docs/agrupamento.md)
PROFILE_NAMES = {1: "compacta e econômica", 2: "familiar intermediária", 3: "ampla de alto padrão"}
LISTING_COLUMNS = ["id", "fonte", "url", "bairro_oficial", "uso", "subtipo", "area_m2", "quartos", "suites",
                   "banheiros", "vagas", "aluguel", "aluguel_m2", "latitude", "longitude", "precisao_localizacao",
                   "data_coleta", "elegivel"]


def _fit_final_classifier(data, *, seed: int, specs=None):
    estimator, grid = (specs or model_specs(seed))[FINAL_MODEL]
    cv = GroupKFold(n_splits=5, shuffle=True, random_state=seed)
    search = GridSearchCV(QuantileBandClassifier(estimator, N_BANDS),
                          [{f"estimator__{k}": v for k, v in grid.items()}],
                          scoring=SCORING, refit="balanced_accuracy", cv=cv)
    search.fit(data.X, data.y, groups=data.groups)
    i = search.best_index_
    metrics = {m: {"media": float(search.cv_results_[f"mean_test_{m}"][i]),
                   "desvio": float(search.cv_results_[f"std_test_{m}"][i])} for m in SCORING}
    # Previsões fora da amostra: cada casa é prevista por um modelo que não a viu (mesmos hiperparâmetros).
    oof = pd.Series(-1, index=data.X.index)
    for train, test in cv.split(data.X, data.y, data.groups):
        model = clone(search.best_estimator_).fit(data.X.iloc[train], data.y.iloc[train])
        oof.iloc[test] = model.predict(data.X.iloc[test])
    params = {k.removeprefix("estimator__"): v for k, v in search.best_params_.items()}
    return search.best_estimator_, metrics, oof, params


def _fit_profiles(data, *, seed: int):
    table = profile_table(data)
    scaler = StandardScaler().fit(table)
    kmeans = KMeans(N_PROFILES, n_init=20, random_state=seed).fit(scaler.transform(table))
    medians = data.y.loc[table.index].groupby(kmeans.labels_).median().sort_values()
    order = {int(old): new for new, old in enumerate(medians.index, start=1)}
    labels = pd.Series([order[int(v)] for v in kmeans.labels_], index=table.index)
    return {"scaler": scaler, "kmeans": kmeans, "ordem": order, "atributos": PROFILE_FEATURES}, labels


def build_artifacts(csv_path: Path, bairros_path: Path, out: Path, *, seed: int = 42, specs=None) -> dict:
    out = Path(out)
    if out.exists():
        raise ValueError("a pasta de artefatos já existe; escolha uma pasta nova.")
    snapshot = prepare_snapshot(csv_path, bairros_path)
    data = build_dataset(snapshot)
    classifier, metrics, oof, params = _fit_final_classifier(data, seed=seed, specs=specs)
    profiles, profile_labels = _fit_profiles(data, seed=seed)

    listings = snapshot.loc[snapshot.coordenadas_validas].copy()
    listings["subtipo"] = listings.get("subtipo", pd.Series("", index=listings.index)).map(house_subtype)
    listings["elegivel"] = listings.index.isin(data.X.index)
    # Mesma regra da elegibilidade: casa sem uso declarado é presumida residencial.
    listings["uso"] = listings.get("uso", pd.Series("", index=listings.index)).fillna("").replace("", "residencial")
    listings["data_coleta"] = listings.data_coleta.dt.date.astype(str)
    table = listings[[c for c in LISTING_COLUMNS if c in listings]].copy()
    bands = pd.Series(classifier.to_bands(data.y), index=data.X.index)
    names = np.array(BAND_NAMES[N_BANDS], dtype=object)
    table["faixa_anunciada"] = bands.map(lambda b: names[b])
    table["faixa_estimada"] = oof.map(lambda b: names[b] if b >= 0 else None)
    table["comparacao"] = (oof - bands).map({-2: "acima do padrão", -1: "acima do padrão", 0: "dentro do padrão",
                                             1: "abaixo do padrão", 2: "abaixo do padrão"})
    table["perfil"] = profile_labels.map(lambda p: f"{p} · {PROFILE_NAMES.get(p, '')}")
    table["distancia_centro_km"] = distance_km(table.latitude, table.longitude)

    out.mkdir(parents=True)
    table.to_csv(out / "anuncios.csv", index=False)
    load_bairros(bairros_path).to_file(out / "bairros.geojson", driver="GeoJSON")
    joblib.dump({"classificador": classifier, "perfis": profiles}, out / "modelos.joblib")
    eligible = table[table.elegivel]
    metadata = {
        "gerado_em": datetime.now(timezone.utc).isoformat(),
        "entrada": str(csv_path), "entrada_sha256": hashlib.sha256(Path(csv_path).read_bytes()).hexdigest(),
        "data_coleta": sorted(set(table.data_coleta)), "fontes": sorted(table.fonte.unique()),
        "n_anuncios_mapa": len(table), "n_casas_modelo": len(data.X),
        "modelo": FINAL_MODEL, "hiperparametros": {k: str(v) for k, v in params.items()}, "semente": seed,
        "faixas": {"nomes": list(names), "limites": [float(t) for t in classifier.thresholds_]},
        "validacao_cruzada": metrics,
        "perfis": {str(k): v for k, v in PROFILE_NAMES.items()},
        # Área: percentis 1–99 (há valores extremos); contagens: mínimo e máximo observados.
        "faixa_treino_atributos": {
            "area_m2": [round(float(eligible.area_m2.quantile(.01))), round(float(eligible.area_m2.quantile(.99)))],
            **{c: [int(eligible[c].min()), int(eligible[c].max())]
               for c in ["quartos", "banheiros", "vagas", "suites"] if eligible[c].notna().any()}},
        "avisos": ["Estimativa de aluguel anunciado, não de preço negociado; não é avaliação imobiliária oficial.",
                   "Base de quatro imobiliárias numa única data; não representa todo o mercado de Ponta Grossa.",
                   "Comparação anunciado × estimado usa previsão fora da amostra (validação cruzada agrupada)."],
    }
    (out / "metadados.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return metadata
