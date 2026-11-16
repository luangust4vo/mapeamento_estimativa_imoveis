"""Base processada pública: sem endereço e com coordenadas arredondadas.

Usa lista explícita de colunas permitidas (nunca uma lista de exclusão), para que
colunas novas, como ``endereco_original``, não vazem por descuido.
"""
from __future__ import annotations

import pandas as pd

# ~110 m em latitude e ~100 m em longitude em Ponta Grossa: suficiente para mapas por bairro,
# insuficiente para identificar a casa. Os modelos usam a base local com precisão total.
COORDINATE_DECIMALS = 3
PUBLIC_COLUMNS = [
    "id", "fonte", "url", "data_coleta", "publicado_em", "atualizado_em",
    "bairro", "bairro_oficial", "bairro_metodo", "latitude", "longitude", "precisao_localizacao",
    "tipo", "subtipo", "uso", "finalidade",
    "area_m2", "area_total_m2", "quartos", "suites", "banheiros", "vagas",
    "aluguel", "preco", "condominio", "iptu", "iptu_texto", "seguro_incendio", "fundo_conservacao",
    "caracteristicas", "em_condominio", "mobiliado",
    "aluguel_m2", "coordenadas_validas", "elegivel_preliminar", "candidato_duplicata", "grupo_imovel",
]
FORBIDDEN = ("endereco", "logradouro", "numero", "cep", "_original", "corretor", "descricao")


def public_table(snapshot: pd.DataFrame) -> pd.DataFrame:
    table = snapshot[[c for c in PUBLIC_COLUMNS if c in snapshot]].copy()
    table[["latitude", "longitude"]] = table[["latitude", "longitude"]].round(COORDINATE_DECIMALS)
    table["data_coleta"] = pd.to_datetime(table.data_coleta).dt.date.astype(str)
    leaked = [c for c in table.columns if any(f in c for f in FORBIDDEN)]
    if leaked:
        raise ValueError(f"Colunas proibidas na base pública: {leaked}")
    return table.sort_values(["fonte", "id"]).reset_index(drop=True)
