import csv
import pytest

COLUMNS = "id fonte url data_coleta endereco bairro latitude longitude tipo finalidade area_m2 quartos suites banheiros vagas aluguel preco condominio iptu periodicidade_iptu".split()

@pytest.fixture
def write_csv(tmp_path):
    def write(records, **kwargs):
        path = tmp_path / "input.csv"
        fields = kwargs.pop("fields", COLUMNS)
        with path.open("w", encoding="utf-8-sig", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fields, delimiter=kwargs.pop("sep", ";"))
            writer.writeheader()
            for record in records:
                writer.writerow(record)
        return path
    return write

@pytest.fixture
def listing():
    return dict(id="1", fonte="Sintética", url="https://example.test/1",
                data_coleta="19/10/2026", endereco="Rua Exemplo, 1",
                bairro=" Órfãs ", latitude="-25,09", longitude="-50,16",
                tipo="Casa", finalidade="Locação", area_m2="80 m²", quartos="2",
                suites="0", banheiros="1", vagas="1", aluguel="R$ 1.234,56",
                preco="", condominio="100", iptu="1200", periodicidade_iptu="anual")
