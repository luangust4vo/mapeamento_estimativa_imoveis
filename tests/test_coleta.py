"""Coleta sem rede: páginas imitam a estrutura __NEXT_DATA__ do site, com valores fictícios."""
import json
from datetime import date

import pytest

from imoveis_pg.__main__ import main
from imoveis_pg.coleta import torreblanca as tb
from imoveis_pg.coleta.contrato import format_number, write_contract_csv
from imoveis_pg.coleta.http import ColetaError, PoliteClient, Response
from imoveis_pg.data import load_listings
from imoveis_pg.quality import audit_listings

DAY = date(2026, 11, 9)


def prop(ref, **attrs):
    base = {"tipo": "Casa/Sobrado", "subtipo": "Casa", "operacao": ["Locação"],
            "finalidade": "Residencial", "endereco_cidade": "Ponta Grossa", "endereco_estado": "PR",
            "endereco_bairro": "Oficinas", "endereco_logradouro": "Rua Fictícia", "endereco_numero": 10,
            "endereco_cep": "84000-000", "latitude": -25.1245727539062, "longitude": -50.1595840454102,
            "area_util": 55, "area_total": 115, "dormitorios": 2, "banheiros": 1, "vagas_garagem": 2,
            "valor_locacao": 1062.5, "valor_iptu": 50.76, "caracteristicas": ["Cozinha", "Quintal"],
            "corretor_id": 1, "corretor_nome": "Pessoa Fictícia"}
    base.update(attrs)
    return {"reference": ref, "created_at": "2026-10-01T10:00:00.000Z",
            "updated_at": "2026-11-01T10:00:00.000Z", "title": "Casa", "description": "Ligue 9999-9999",
            "attributes": {k: v for k, v in base.items() if v is not None}}


def page_html(props, page=1, pages=1, total=None):
    data = {"props": {"pageProps": {"properties": props, "totalProperties": total if total is not None else len(props),
                                    "pageInfo": {"page": page, "take": 20, "total": pages}}}}
    return f'<html><script id="__NEXT_DATA__" type="application/json">{json.dumps(data)}</script></html>'


class FakeSite:
    def __init__(self, pages, robots="User-agent: *\nAllow: /\n"):
        self.pages, self.robots, self.calls = pages, robots, []

    def __call__(self, url, headers, timeout):
        self.calls.append(url)
        assert "imoveis-pg" in headers["User-Agent"]
        if url.endswith("/robots.txt"):
            return Response(200, self.robots.encode()) if self.robots is not None else Response(404, b"")
        if url in self.pages:
            value = self.pages[url]
            return value if isinstance(value, Response) else Response(200, value.encode())
        return Response(404, b"")


def client(site, **kwargs):
    kwargs.setdefault("sleep", lambda s: None)
    return PoliteClient(opener=site, **kwargs)


def test_record_maps_contract_and_drops_personal_data():
    record = tb.to_record(prop("CA1_TB"), DAY)
    assert record["id"] == "CA1_TB" and record["url"] == "https://torreblanca.com.br/imovel/CA1_TB"
    assert record["tipo"] == "Casa" and record["finalidade"] == "Locação" and record["uso"] == "residencial"
    assert record["aluguel"] == "1062,5" and record["iptu"] == "50,76" and record["periodicidade_iptu"] == ""
    assert record["latitude"] == "-25,1245728" and record["precisao_localizacao"] == "exata"
    assert record["endereco"] == "Rua Fictícia, 10" and record["cep"] == "84000000"
    text = json.dumps(record, ensure_ascii=False)
    assert "Pessoa Fictícia" not in text and "9999" not in text and "corretor" not in text


def test_missing_values_stay_empty_not_zero():
    record = tb.to_record(prop("CA2_TB", suites=None, vagas_garagem=None, latitude=None, valor_iptu=None), DAY)
    assert record["suites"] == record["vagas"] == record["iptu"] == record["latitude"] == ""
    assert record["precisao_localizacao"] == ""


def test_other_city_is_rejected():
    assert tb.to_record(prop("CA3_TB", endereco_cidade="Castro"), DAY) is None


def test_format_number_uses_contract_locale():
    assert format_number(1500.0) == "1500" and format_number("52,61") == "52,61"
    assert format_number(None) == "" and format_number(1234.567) == "1234,57"


def test_collect_paginates_and_deduplicates():
    site = FakeSite({
        tb.search_url(1): page_html([prop("A"), prop("B")], 1, 2, total=4),
        tb.search_url(2): page_html([prop("B"), prop("C", endereco_cidade="Carambeí")], 2, 2, total=4),
    })
    result = tb.collect(client(site), collected_on=DAY)
    assert [r["id"] for r in result.records] == ["A", "B"]
    assert result.pages == 2 and result.declared_total == 4
    assert result.skipped == {"repetido_ou_sem_id": 1, "fora_de_ponta_grossa": 1}


def test_layout_change_is_reported():
    site = FakeSite({tb.search_url(1): "<html>novo layout</html>"})
    with pytest.raises(ColetaError, match="__NEXT_DATA__"):
        tb.collect(client(site))


def test_robots_disallow_blocks_request():
    site = FakeSite({tb.search_url(1): page_html([prop("A")])}, robots="User-agent: *\nDisallow: /imoveis\n")
    with pytest.raises(ColetaError, match="robots"):
        tb.collect(client(site))
    assert tb.search_url(1) not in site.calls


def test_missing_robots_allows_and_requests_are_spaced():
    waits, now = [], [0.0]
    site = FakeSite({tb.search_url(1): page_html([prop("A")])}, robots=None)
    c = PoliteClient(opener=site, delay=3, sleep=waits.append, clock=lambda: now[0])
    tb.collect(c, collected_on=DAY)
    assert site.calls[0].endswith("/robots.txt") and waits == [3]


def test_retries_transient_errors_then_fails():
    site = FakeSite({tb.search_url(1): Response(503, b"")})
    with pytest.raises(ColetaError, match="503"):
        tb.collect(client(site, retries=2))
    assert site.calls.count(tb.search_url(1)) == 3


def test_cache_allows_offline_reprocessing(tmp_path):
    site = FakeSite({tb.search_url(1): page_html([prop("A")])})
    tb.collect(client(site, cache_dir=tmp_path), collected_on=DAY)
    assert (tmp_path / "index.jsonl").exists()
    offline = PoliteClient(cache_dir=tmp_path, offline=True, opener=lambda *a: pytest.fail("rede usada"))
    assert [r["id"] for r in tb.collect(offline, collected_on=DAY).records] == ["A"]
    with pytest.raises(ColetaError, match="offline"):
        PoliteClient(cache_dir=tmp_path / "vazio", offline=True).get(tb.search_url(1))


def test_collected_csv_is_accepted_by_import_pipeline(tmp_path):
    records = [tb.to_record(prop("A"), DAY),
               tb.to_record(prop("B", subtipo="Sobrado", valor_venda=450000, operacao=["Venda", "Locação"]), DAY)]
    path = tmp_path / "coleta.csv"
    write_contract_csv(records, path)
    imported = load_listings(path)
    assert imported.issues.empty
    rows = imported.rows.set_index("id")
    assert rows.loc["A", "aluguel"] == 1062.5 and rows.loc["B", "preco"] == 450000
    assert rows.loc["B", "subtipo"] == "Sobrado"
    assert audit_listings(imported.rows).snapshot.elegivel_preliminar.all()


def test_cli_collect_offline_writes_csv_and_manifest(tmp_path, capsys):
    cache = tmp_path / "raw"
    tb.collect(client(FakeSite({tb.search_url(1): page_html([prop("A"), prop("B")])}), cache_dir=cache))
    out = tmp_path / "torreblanca.csv"
    assert main(["collect", "torreblanca", "--output", str(out), "--cache-dir", str(cache), "--offline"]) == 0
    assert len(load_listings(out).rows) == 2
    manifest = json.loads((tmp_path / "torreblanca.manifest.json").read_text(encoding="utf-8"))
    assert manifest["anuncios"] == 2 and manifest["requisicoes"] == 0 and manifest["paginas_do_cache"] == 1
    assert main(["collect", "torreblanca", "--output", str(out), "--cache-dir", str(cache), "--offline"]) == 2
    assert "já existe" in capsys.readouterr().err
