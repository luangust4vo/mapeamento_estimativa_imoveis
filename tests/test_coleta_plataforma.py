"""Coletor da plataforma Portal Dez/Granada/Vila Nova, sem rede e com valores fictícios."""
import json
from datetime import date

import pytest

from coleta_helpers import FakeSite, client, page_html
from imoveis_pg.coleta.contrato import as_number, write_contract_csv
from imoveis_pg.coleta.http import ColetaError
from imoveis_pg.coleta.plataforma import GRANADA, PORTALDEZ
from imoveis_pg.data import load_listings
from imoveis_pg.quality import audit_listings

DAY = date(2026, 11, 9)


def attr(key, value, label=None, section="brief"):
    return {"key": key, "value": value, "label": label, "section": section}


def portaldez_item(ref, type_="Casa", city="PONTA GROSSA", **extra):
    attrs = [attr("city", city, section="location"), attr("state", "PR", section="location"),
             attr("district", "UVARANAS", section="location"), attr("street", "RUA FICTÍCIA", section="location"),
             attr("number", "120", section="location"), attr("postal-code", "84000000", section="location"),
             attr("full-address", "RUA FICTÍCIA - UVARANAS, PONTA GROSSA - PR", section="location"),
             attr("finalidade", "Residencial"), attr("rent-value", 1900),
             attr("bedrooms", 2, "Dormitório(s)"), attr("bathrooms", 1, "Banheiro(s)"),
             attr("unit-area", 70, "Área da unidade"), attr("iptu", 68, "IPTU"),
             attr("seguro_incendio", 30, "Seguro incêndio"),
             attr("id-30225", "Sim", "Piscina", "others"), attr("id-30247", "Colégio X", "Proximidade", "others")]
    attrs += [attr(k, v, label) for k, (v, label) in extra.items()]
    return {"id": 1, "reference": ref, "title": "Casa para Locação", "type": type_, "operation": "rent",
            "description": "Fale com Pessoa Fictícia 99999-9999", "created_at": "2026-09-14T11:30:49.000Z",
            "updated_at": "2026-10-01T00:00:00.000Z", "attributes": attrs}


def granada_item(ref):
    attrs = [attr("city", "Ponta Grossa - PR"), attr("district", "Neves"), attr("address-street", "Rua Exemplo"),
             attr("address-number", "45"), attr("postal-code", "84020-000"), attr("objective", "Residencial"),
             attr("rent-value", 6000), attr("property-tax", "473,00", "IPTU"), attr("total-area", "1.582", "Área total"),
             attr("util-area", "152,61", "Área útil"), attr("suites", 1, "Suíte(s)"), attr("bedrooms", 4, "Quarto(s)"),
             attr("garage", 2, "Vaga(s)"), attr("barbecue", True, "Churrasqueira"), attr("agent", "itm_x"),
             attr("year-built", "2017", "Ano da construção")]
    return {"reference": ref, "type": "Sobrado", "operation": "rent", "attributes": attrs}


def test_portaldez_record_maps_contract_and_drops_personal_data():
    record = PORTALDEZ.to_record(portaldez_item("9431"), DAY)
    assert record["url"] == "https://portaldezimoveis.com.br/imovel/9431"
    assert record["tipo"] == "Casa" and record["subtipo"] == "Casa" and record["finalidade"] == "Locação"
    assert record["aluguel"] == "1900" and record["iptu"] == "68" and record["periodicidade_iptu"] == ""
    assert record["quartos"] == "2" and record["area_m2"] == "70" and record["uso"] == "residencial"
    assert record["endereco"] == "RUA FICTÍCIA, 120" and record["numero"] == "120"
    assert record["caracteristicas"] == "Piscina" and record["latitude"] == ""
    text = json.dumps(record, ensure_ascii=False)
    assert "Pessoa" not in text and "9999" not in text and "Colégio" not in text


def test_granada_dialect_uses_aliases():
    record = GRANADA.to_record(granada_item("10183"), DAY)
    assert record["bairro"] == "Neves" and record["logradouro"] == "Rua Exemplo" and record["cep"] == "84020000"
    assert record["iptu"] == "473" and record["area_m2"] == "152,61" and record["area_total_m2"] == "1582"
    assert record["suites"] == "1" and record["vagas"] == "2" and record["ano_construcao"] == "2017"
    assert record["subtipo"] == "Sobrado" and record["caracteristicas"] == "Churrasqueira"
    assert "itm_x" not in json.dumps(record)


def test_missing_values_stay_empty_and_iptu_text_is_kept():
    item = portaldez_item("1")
    item["attributes"] = [a for a in item["attributes"] if a["key"] not in {"bedrooms", "iptu", "number"}]
    item["attributes"].append(attr("id-65733", "a confirmar", "Iptu", "others"))
    record = PORTALDEZ.to_record(item, DAY)
    assert record["quartos"] == record["iptu"] == record["numero"] == ""
    assert record["iptu_texto"] == "a confirmar" and record["endereco"] == "RUA FICTÍCIA"


def test_numeric_iptu_in_generic_attribute_is_used():
    item = portaldez_item("1")
    item["attributes"] = [a for a in item["attributes"] if a["key"] != "iptu"]
    item["attributes"].append(attr("id-65078", "145,00", "Iptu", "others"))
    assert PORTALDEZ.to_record(item, DAY)["iptu"] == "145"


def test_thousands_text_is_not_read_as_decimal():
    assert as_number("1.582") == 1582 and as_number("52,61") == 52.61 and as_number("+- 60,00") == 60


def test_collect_filters_types_city_and_duplicates():
    site = FakeSite({
        PORTALDEZ.search_url(1): page_html([portaldez_item("A"), portaldez_item("B", "Barracão")], 1, 2, total=5),
        PORTALDEZ.search_url(2): page_html([portaldez_item("A"), portaldez_item("C", "Casa/Sobrado em Condomínio"),
                                            portaldez_item("D", city="CARAMBEÍ")], 2, 2, total=5),
    })
    result = PORTALDEZ.collect(client(site), collected_on=DAY)
    assert [r["id"] for r in result.records] == ["A", "C"]
    assert result.skipped == {"outro_tipo": 1, "repetido_ou_sem_id": 1, "fora_de_ponta_grossa": 1}
    assert result.pages == 2 and result.declared_total == 5
    assert PORTALDEZ.search_url(2) == "https://portaldezimoveis.com.br/imoveis?operation=rent&page=2"


def test_layout_change_is_reported():
    site = FakeSite({PORTALDEZ.search_url(1): "<html></html>"})
    with pytest.raises(ColetaError):
        PORTALDEZ.collect(client(site))


def test_collected_csv_is_accepted_by_import_pipeline(tmp_path):
    records = [PORTALDEZ.to_record(portaldez_item("A"), DAY), GRANADA.to_record(granada_item("B"), DAY)]
    for record in records:  # coordenadas vêm da geocodificação
        record.update(latitude="-25,09", longitude="-50,12", precisao_localizacao="aproximada")
    path = tmp_path / "plataforma.csv"
    write_contract_csv(records, path)
    imported = load_listings(path)
    assert imported.issues.empty
    assert audit_listings(imported.rows).snapshot.elegivel_preliminar.all()


def test_cli_merge_unites_sources_with_different_extras(tmp_path, capsys):
    from imoveis_pg.__main__ import main
    a, b = PORTALDEZ.to_record(portaldez_item("A"), DAY), GRANADA.to_record(granada_item("B"), DAY)
    for record in (a, b):
        record.update(latitude="-25,09", longitude="-50,12")
    a.pop("seguro_incendio"); b["extra_so_b"] = "x"
    write_contract_csv([a], tmp_path / "a.csv"); write_contract_csv([b], tmp_path / "b.csv")
    out = tmp_path / "todos.csv"
    assert main(["merge", str(tmp_path / "a.csv"), str(tmp_path / "b.csv"), "--output", str(out)]) == 0
    rows = load_listings(out).rows.set_index("id")
    assert list(rows.index) == ["A", "B"] and rows.loc["B", "extra_so_b"] == "x"
    assert rows.loc["A", "fonte"] == "Portal Dez Imóveis" and rows.loc["B", "fonte"] == "Imobiliária Granada"
    assert main(["merge", str(tmp_path / "a.csv"), "--output", str(out)]) == 2
    (tmp_path / "ruim.csv").write_text("id;fonte\n1;x\n", encoding="utf-8")
    assert main(["merge", str(tmp_path / "ruim.csv"), "--output", str(tmp_path / "n.csv")]) == 2
    assert "ausentes" in capsys.readouterr().err
