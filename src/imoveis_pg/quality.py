"""Auditoria exploratória: preserva observações e separa o retrato atual."""
import json
import re
from dataclasses import dataclass
from urllib.parse import urlsplit, urlunsplit

import numpy as np
import pandas as pd

from .data import ISSUE_COLUMNS, normalize_text
from .geo.cnefe import street_key


@dataclass
class QualityResult:
    observations: pd.DataFrame
    snapshot: pd.DataFrame
    issues: pd.DataFrame
    summary: dict


def _url(value):
    if pd.isna(value) or not str(value).strip():
        return ""
    try:
        u = urlsplit(str(value).strip())
        return urlunsplit((u.scheme.lower(), u.netloc.lower(), u.path.rstrip("/"), u.query, ""))
    except ValueError:
        return str(value).strip()


def street_of(address) -> str:
    """Logradouro comparável, sem o número final ("Rua X, 10" == "RUA X")."""
    if pd.isna(address):
        return ""
    return street_key(re.sub(r",\s*(\d+\w*|s/?n)\s*$", "", str(address), flags=re.I))


def audit_listings(rows: pd.DataFrame) -> QualityResult:
    observations = rows.copy(deep=True)
    issues = []

    def issue(index, column, code, message):
        row = observations.loc[index]
        issues.append([int(row.linha), column, code, str(row.get(column, "")), message])

    source = observations.fonte.map(normalize_text)
    identities = []
    urls = observations.url.map(_url)
    for index, row in observations.iterrows():
        if source.loc[index] and pd.notna(row.id) and str(row.id).strip():
            identities.append(json.dumps([source.loc[index], str(row.id)], ensure_ascii=False))
        elif urls.loc[index]:
            identities.append("url:" + urls.loc[index])
        else:
            identities.append("row:" + row.row_id)
    observations["entity_id"] = pd.Series(identities, index=observations.index, dtype="object")
    for _, group in observations.assign(_url=urls).loc[urls.ne("")].groupby("_url"):
        if group.entity_id.nunique() > 1:
            for index in group.index:
                issue(index, "url", "conflito_identidade", "URL associada a identidades diferentes; revisar antes de treinar.")
    for _, group in observations.assign(_url=urls).groupby("entity_id"):
        if group.loc[group._url.ne(""), "_url"].nunique() > 1:
            for index in group.index:
                issue(index, "url", "conflito_identidade", "Identidade associada a URLs diferentes.")
    raw_columns = [c for c in rows if c.endswith("_original")]
    observations["duplicata_exata"] = observations.duplicated(subset=raw_columns) if raw_columns else False
    for index in observations.index[observations.duplicata_exata]:
        issue(index, "entity_id", "duplicata_exata", "Observação repetida preservada no histórico.")

    observations["coordenadas_validas"] = (
        observations.latitude.between(-90, 90) & observations.longitude.between(-180, 180)
        & np.isfinite(observations.latitude) & np.isfinite(observations.longitude))
    for index in observations.index[~observations.coordenadas_validas]:
        issue(index, "latitude", "coordenadas_invalidas", "Par de coordenadas ausente, parcial ou fora dos limites globais.")

    positive_area = observations.area_m2.where(observations.area_m2.gt(0))
    positive_rent = observations.aluguel.where(observations.aluguel.gt(0))
    observations["aluguel_m2"] = positive_rent / positive_area
    observations["densidade_quartos"] = observations.quartos / positive_area
    period = observations.periodicidade_iptu.map(normalize_text)
    observations["iptu_mensal"] = observations.iptu.where(period.eq("mensal"))
    annual = period.eq("anual")
    observations.loc[annual, "iptu_mensal"] = observations.loc[annual, "iptu"] / 12
    observations["custo_mensal_total"] = observations[["aluguel", "condominio", "iptu_mensal"]].sum(axis=1, min_count=3)
    observations["idade"] = np.nan
    if "ano_construcao" in observations:
        age = observations.data_coleta.dt.year - observations.ano_construcao
        observations["idade"] = age.where(age.ge(0))
        for index in observations.index[age.lt(0)]:
            issue(index, "ano_construcao", "ano_futuro", "Construção posterior à data da coleta.")
    usage = observations.get("uso", pd.Series("residencial", index=observations.index)).map(normalize_text)
    observations["elegivel_preliminar"] = (
        observations.tipo.map(normalize_text).eq("casa")
        & observations.finalidade.map(normalize_text).isin(["aluguel", "locacao"])
        & usage.isin(["", "residencial"]) & observations.aluguel.gt(0)
        & (observations.coordenadas_validas | observations.bairro_normalizado.ne("")))

    snapshot = (observations.sort_values(["data_coleta", "row_id"], na_position="first")
                .drop_duplicates("entity_id", keep="last").sort_values("row_id").copy())
    snapshot["candidato_duplicata"] = False
    # Grupo de imóvel: anúncios possivelmente do mesmo imóvel ficam juntos na separação treino/teste.
    snapshot["grupo_imovel"] = snapshot.entity_id
    # Logradouro sem número: algumas fontes omitem o número da casa.
    candidates = snapshot.assign(_address=snapshot.endereco.map(street_of), _source=snapshot.fonte.map(normalize_text))
    complete = candidates._address.ne("") & candidates.area_m2.gt(0) & candidates.quartos.notna() & candidates._source.ne("")
    for _, group in candidates.loc[complete].groupby(["_address", "area_m2", "quartos"]):
        if group._source.nunique() > 1:
            snapshot.loc[group.index, "candidato_duplicata"] = True
            snapshot.loc[group.index, "grupo_imovel"] = "dup:" + min(snapshot.loc[group.index, "entity_id"])
            for index in group.index:
                issue(index, "endereco", "possivel_duplicata", "Logradouro, área e quartos coincidem entre fontes; confirmação necessária.")
    observations["candidato_duplicata"] = observations.entity_id.isin(snapshot.loc[snapshot.candidato_duplicata, "entity_id"])
    for column in ["aluguel", "preco", "area_m2", "aluguel_m2", "custo_mensal_total"]:
        values = snapshot[column].dropna()
        if len(values) >= 4:
            q1, q3 = values.quantile([.25, .75])
            spread = q3 - q1
            if spread > 0:
                for index in values.index[(values < q1 - 1.5 * spread) | (values > q3 + 1.5 * spread)]:
                    issue(index, column, "extremo_iqr", "Extremo exploratório preservado; não é regra de exclusão.")
    numeric = snapshot.select_dtypes(include="number")
    summary = {
        "observacoes": len(observations), "anuncios_snapshot": len(snapshot),
        "colunas": len(rows.columns), "tipos": {c: str(t) for c, t in rows.dtypes.items()},
        "ausentes": {c: int(n) for c, n in rows.isna().sum().items() if not c.endswith("_original")},
        "duplicatas_exatas": int(observations.duplicata_exata.sum()),
        "candidatos_duplicata": int(snapshot.candidato_duplicata.sum()),
        "conflitos_identidade": sum(i[2] == "conflito_identidade" for i in issues),
        "coordenadas_validas": int(snapshot.coordenadas_validas.sum()),
        "elegiveis_preliminares": int(snapshot.elegivel_preliminar.sum()),
        "regioes": (snapshot.bairro_oficial.fillna("Bairro não resolvido") if "bairro_oficial" in snapshot
                    else snapshot.bairro_normalizado.replace("", "Bairro não informado")).value_counts().to_dict(),
        "estatisticas": json.loads(numeric.describe().to_json()) if len(numeric.columns) else {},
        "avisos": ["Validação municipal pendente; coordenadas válidas globalmente não comprovam localização em Ponta Grossa.",
                   "Snapshot conta identidades de anúncios; candidatos entre fontes ainda podem representar o mesmo imóvel.",
                   "Elegibilidade preliminar não substitui validação para treinamento."],
    }
    return QualityResult(observations, snapshot, pd.DataFrame(issues, columns=ISSUE_COLUMNS), summary)
