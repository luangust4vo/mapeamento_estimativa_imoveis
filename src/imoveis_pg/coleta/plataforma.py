"""Coletor da plataforma Next.js usada por Portal Dez, Granada e Vila Nova.

A listagem ``/imoveis?operation=rent`` traz cada anúncio completo em
``__NEXT_DATA__``, com atributos ``{key, label, value}``. Os sites usam duas
variações de chaves (ex.: ``street``/``address-street``, ``iptu``/``property-tax``),
resolvidas por listas de apelidos. Não há coordenadas: o endereço é geocodificado
depois com o CNEFE (``imoveis_pg.geo.cnefe``).
"""
from __future__ import annotations

import re
from datetime import date
from urllib.parse import urlencode

from ..data import normalize_text
from .contrato import as_number, format_number
from .http import PoliteClient
from .torreblanca import CollectionResult, parse_page

HOUSE_TYPES = {"casa", "sobrado", "casa/sobrado", "casa em condominio", "sobrado em condominio",
               "casa/sobrado em condominio", "casa de condominio"}
ALIASES = {
    "logradouro": ["street", "address-street"],
    "numero": ["number", "address-number"],
    "cep": ["postal-code"],
    "bairro": ["district"],
    "cidade": ["city"],
    "uso": ["finalidade", "goal", "objective"],
    "area_m2": ["unit-area", "util-area", "private-area", "constructed-area"],
    "area_total_m2": ["total-area"],
    "quartos": ["bedrooms"],
    "suites": ["suites"],
    "banheiros": ["bathrooms"],
    "vagas": ["garage"],
    "aluguel": ["rent-value"],
    "condominio": ["condominio", "condominium-price"],
    "iptu": ["iptu", "property-tax"],
    "seguro_incendio": ["seguro_incendio", "secure-tax"],
    "fundo_conservacao": ["fundo_conservacao"],
    "ano_construcao": ["year-built"],
}
# Chaves com dados pessoais ou texto livre: nunca copiadas, nem como característica.
PRIVATE_KEYS = {"agent", "client", "description", "title", "integrations", "full-address", "complement",
                "address-complement", "id", "model", "published", "position"}
TRUE_VALUES = {"sim", "true", "1", "yes"}


def _attributes(item: dict) -> tuple[dict, dict]:
    """Devolve (valores por chave, rótulos por chave) da lista de atributos."""
    values, labels = {}, {}
    for attribute in item.get("attributes") or []:
        key = attribute.get("key")
        if key:
            values[key] = attribute.get("value")
            labels[key] = attribute.get("label")
    return values, labels


def _pick(values: dict, field: str):
    for key in ALIASES[field]:
        value = values.get(key)
        if value not in (None, ""):
            return value
    return None


def _count(value) -> str:
    number = as_number(value)
    return "" if number is None else format_number(number)


def _features(values: dict, labels: dict) -> list[str]:
    used = {key for keys in ALIASES.values() for key in keys} | PRIVATE_KEYS
    features = []
    for key, value in values.items():
        label = labels.get(key)
        if key in used or not label or normalize_text(label) == "iptu":
            continue
        if value is True or normalize_text(value) in TRUE_VALUES:
            features.append(str(label))
    return sorted(set(features))


class PlatformSource:
    """Uma imobiliária da plataforma; a instância expõe a interface de coletor do projeto."""

    def __init__(self, fonte: str, base_url: str, city: str = "Ponta Grossa"):
        self.FONTE, self.BASE_URL, self.city = fonte, base_url.rstrip("/"), city

    def search_url(self, page: int) -> str:
        params = {"operation": "rent"}
        if page > 1:
            params["page"] = page
        return f"{self.BASE_URL}/imoveis?{urlencode(params)}"

    def to_record(self, item: dict, collected_on: date) -> dict | None:
        """None para anúncios fora de Ponta Grossa; tipos não residenciais são filtrados em collect."""
        values, labels = _attributes(item)
        city = normalize_text(_pick(values, "cidade"))
        if re.sub(r"\s*-\s*pr$", "", city) != normalize_text(self.city):
            return None
        reference = str(item.get("reference") or values.get("reference") or "").strip()
        street, number = _pick(values, "logradouro"), _pick(values, "numero")
        iptu, iptu_text = _pick(values, "iptu"), ""
        for key, label in labels.items():
            if normalize_text(label) == "iptu" and key not in ALIASES["iptu"]:
                text = str(values.get(key) or "").strip()
                if iptu is None and as_number(text) is not None:
                    iptu = text
                elif text:
                    iptu_text = normalize_text(text)
        operation = normalize_text(item.get("operation"))
        return {
            "id": reference,
            "fonte": self.FONTE,
            "url": f"{self.BASE_URL}/imovel/{reference}" if reference else "",
            "data_coleta": collected_on.isoformat(),
            "endereco": ", ".join(str(p).strip() for p in (street, number) if p not in (None, "")),
            "bairro": str(_pick(values, "bairro") or "").strip(),
            "latitude": "", "longitude": "",
            "tipo": "Casa",
            "finalidade": {"rent": "Locação", "sale": "Venda"}.get(operation, ""),
            "area_m2": format_number(_pick(values, "area_m2")),
            "quartos": _count(_pick(values, "quartos")),
            "suites": _count(_pick(values, "suites")),
            "banheiros": _count(_pick(values, "banheiros")),
            "vagas": _count(_pick(values, "vagas")),
            "aluguel": format_number(_pick(values, "aluguel")),
            "preco": "",
            "condominio": format_number(_pick(values, "condominio")),
            "iptu": format_number(iptu),
            # Os sites não informam a periodicidade do IPTU; não presumimos.
            "periodicidade_iptu": "",
            "iptu_texto": iptu_text,
            "subtipo": str(item.get("type") or ""),
            "uso": normalize_text(_pick(values, "uso")),
            "area_total_m2": format_number(_pick(values, "area_total_m2")),
            "ano_construcao": _count(_pick(values, "ano_construcao")),
            "seguro_incendio": format_number(_pick(values, "seguro_incendio")),
            "fundo_conservacao": format_number(_pick(values, "fundo_conservacao")),
            "logradouro": str(street or "").strip(),
            "numero": str(number or "").strip(),
            "cep": re.sub(r"\D", "", str(_pick(values, "cep") or "")),
            "caracteristicas": "|".join(_features(values, labels)),
            "publicado_em": item.get("created_at") or "",
            "atualizado_em": item.get("updated_at") or "",
            "precisao_localizacao": "", "origem_localizacao": "",
        }

    def collect(self, client: PoliteClient, *, collected_on: date | None = None,
                max_pages: int | None = None) -> CollectionResult:
        """Percorre todas as locações e mantém casas e sobrados de Ponta Grossa."""
        collected_on = collected_on or date.today()
        result = CollectionResult(records=[])
        seen: set[str] = set()

        def skip(reason):
            result.skipped[reason] = result.skipped.get(reason, 0) + 1

        page, last_page = 1, 1
        while page <= last_page and (max_pages is None or page <= max_pages):
            props = parse_page(client.get(self.search_url(page)))
            last_page = int((props.get("pageInfo") or {}).get("total") or 1)
            result.declared_total = props.get("totalProperties", result.declared_total)
            result.pages = page
            for item in props["properties"]:
                if normalize_text(item.get("type")) not in HOUSE_TYPES:
                    skip("outro_tipo")
                    continue
                record = self.to_record(item, collected_on)
                if record is None:
                    skip("fora_de_ponta_grossa")
                elif not record["id"] or record["id"] in seen:
                    skip("repetido_ou_sem_id")
                else:
                    seen.add(record["id"])
                    result.records.append(record)
            page += 1
        return result


PORTALDEZ = PlatformSource("Portal Dez Imóveis", "https://portaldezimoveis.com.br")
GRANADA = PlatformSource("Imobiliária Granada", "https://imobiliariagranada.com.br")
VILANOVA = PlatformSource("Vila Nova Imobiliária", "https://vilanovaimoveis.com.br")
