"""Coletor da Torre Blanca Imóveis (torreblanca.com.br).

As páginas de busca trazem os anúncios completos no JSON ``__NEXT_DATA__``
(Next.js), inclusive latitude/longitude, então só a listagem é visitada.
Somente campos do imóvel são copiados: dados do corretor, descrição livre,
fotos e contatos são descartados por privacidade.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import date
from urllib.parse import urlencode

from ..data import normalize_text
from .contrato import as_number, format_number
from .http import ColetaError, PoliteClient

FONTE = "Torre Blanca Imóveis"
BASE_URL = "https://torreblanca.com.br"
CITY = "Ponta Grossa"
RENT_QUERY = {"operacao": "Locação", "endereco_cidade": CITY, "tipo": "Casa/Sobrado"}
_NEXT_DATA = re.compile(r'<script id="__NEXT_DATA__" type="application/json"[^>]*>(.*?)</script>', re.S)


@dataclass
class CollectionResult:
    records: list[dict]
    pages: int = 0
    declared_total: int | None = None
    skipped: dict[str, int] = field(default_factory=dict)


def search_url(page: int, query: dict | None = None) -> str:
    params = dict(query or RENT_QUERY)
    if page > 1:
        params["page"] = page
    return f"{BASE_URL}/imoveis?{urlencode(params)}"


def parse_page(html: str) -> dict:
    match = _NEXT_DATA.search(html)
    if not match:
        raise ColetaError("Página sem __NEXT_DATA__; o layout do site pode ter mudado.")
    try:
        props = json.loads(match.group(1))["props"]["pageProps"]
    except (json.JSONDecodeError, KeyError, TypeError) as exc:
        raise ColetaError(f"JSON da página em formato inesperado: {exc}") from exc
    if not isinstance(props.get("properties"), list):
        raise ColetaError("Página de busca sem lista de imóveis.")
    return props


def _count(value) -> str:
    number = as_number(value)
    return "" if number is None else format_number(number)


def _flag(value) -> str:
    """Booleano do site vira sim/nao; texto é normalizado; ausência fica vazia."""
    if isinstance(value, bool):
        return "sim" if value else "nao"
    return normalize_text(value) if value is not None else ""


def to_record(prop: dict, collected_on: date) -> dict | None:
    """Converte um anúncio no contrato; devolve None se não for de Ponta Grossa."""
    attrs = prop.get("attributes") or {}
    if normalize_text(attrs.get("endereco_cidade")) != normalize_text(CITY):
        return None
    reference = str(prop.get("reference") or "").strip()
    operations = [normalize_text(o) for o in attrs.get("operacao") or []]
    kind = attrs.get("tipo") or ""
    street, number = attrs.get("endereco_logradouro"), attrs.get("endereco_numero")
    lat, lon = as_number(attrs.get("latitude")), as_number(attrs.get("longitude"))
    has_coords = lat is not None and lon is not None
    features = attrs.get("caracteristicas") or []
    return {
        "id": reference,
        "fonte": FONTE,
        "url": f"{BASE_URL}/imovel/{reference}" if reference else "",
        "data_coleta": collected_on.isoformat(),
        "endereco": ", ".join(str(p) for p in (street, number) if p not in (None, "")),
        "bairro": attrs.get("endereco_bairro") or "",
        "latitude": format_number(lat, decimals=7),
        "longitude": format_number(lon, decimals=7),
        # O site agrupa casas e sobrados; o subtipo é preservado à parte.
        "tipo": "Casa" if kind == "Casa/Sobrado" else kind,
        "finalidade": "Locação" if "locacao" in operations else "Venda" if "venda" in operations else "",
        "area_m2": format_number(attrs.get("area_util")),
        "quartos": _count(attrs.get("dormitorios")),
        "suites": _count(attrs.get("suites")),
        "banheiros": _count(attrs.get("banheiros")),
        "vagas": _count(attrs.get("vagas_garagem")),
        "aluguel": format_number(attrs.get("valor_locacao")),
        "preco": format_number(attrs.get("valor_venda")),
        "condominio": format_number(attrs.get("valor_condominio")),
        "iptu": format_number(attrs.get("valor_iptu")),
        # O site não informa se o IPTU é mensal ou anual; não presumimos.
        "periodicidade_iptu": "",
        "subtipo": attrs.get("subtipo") or "",
        "uso": normalize_text(attrs.get("finalidade")),
        "area_total_m2": format_number(attrs.get("area_total")),
        "cep": re.sub(r"\D", "", str(attrs.get("endereco_cep") or "")),
        "em_condominio": _flag(attrs.get("em_condominio")),
        "mobiliado": _flag(attrs.get("mobiliado")),
        "caracteristicas": "|".join(str(f) for f in features),
        "operacoes": "|".join(attrs.get("operacao") or []),
        "publicado_em": prop.get("created_at") or "",
        "atualizado_em": prop.get("source_updated_at") or prop.get("updated_at") or "",
        "precisao_localizacao": "exata" if has_coords else "",
        "origem_localizacao": "coordenada do anúncio (não verificada)" if has_coords else "",
    }


def collect(client: PoliteClient, *, collected_on: date | None = None,
            max_pages: int | None = None, query: dict | None = None) -> CollectionResult:
    """Percorre todas as páginas de busca de casas para locação em Ponta Grossa."""
    collected_on = collected_on or date.today()
    result = CollectionResult(records=[])
    seen: set[str] = set()
    page, last_page = 1, 1
    while page <= last_page and (max_pages is None or page <= max_pages):
        props = parse_page(client.get(search_url(page, query)))
        info = props.get("pageInfo") or {}
        last_page = int(info.get("total") or 1)
        result.declared_total = props.get("totalProperties", result.declared_total)
        result.pages = page
        for prop in props["properties"]:
            record = to_record(prop, collected_on)
            if record is None:
                result.skipped["fora_de_ponta_grossa"] = result.skipped.get("fora_de_ponta_grossa", 0) + 1
            elif not record["id"] or record["id"] in seen:
                result.skipped["repetido_ou_sem_id"] = result.skipped.get("repetido_ou_sem_id", 0) + 1
            else:
                seen.add(record["id"])
                result.records.append(record)
        page += 1
    return result
