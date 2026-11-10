# Aluguéis de casas em Ponta Grossa

Importação rastreável de CSV, relatório de qualidade, análise exploratória e
coleta automatizada de anúncios públicos de imobiliárias de Ponta Grossa.
Inclui a comparação de classificadores por faixa de aluguel e o agrupamento de
perfis e regiões. O mapa interativo e o simulador são etapas futuras.

## Executar
Python 3.12 ou superior. Na raiz deste repositório:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
python -m imoveis_pg analyze tests/fixtures/anuncios_sinteticos.csv --output reports/demo
python -m pytest -q
```

Use uma pasta de saída nova a cada execução. O exemplo contém **dados sintéticos**,
identificados no manifesto e nos gráficos. Para outro CSV:

```bash
python -m imoveis_pg analyze data/anuncios.csv --output reports/coleta-01 --sep ";" --decimal ","
```

## Coletar dados reais
```bash
for f in torreblanca portaldez granada vilanova; do
  python -m imoveis_pg collect $f --output data/${f}_2026-11-09.csv
done
python -m imoveis_pg merge data/*_2026-11-09.csv --output data/base_2026-11-09.csv
python -m imoveis_pg analyze data/base_2026-11-09.csv --output reports/base-2026-11-09 \
  --bairros data/raw/ibge/PR_bairros_CD2022.gpkg
```
Anúncios sem coordenadas são geocodificados localmente com o CNEFE 2022 do IBGE.
Com `--bairros`, cada anúncio recebe um dos 16 bairros oficiais (malha do Censo 2022),
usados nas tabelas e gráficos regionais. Os dois arquivos do IBGE são baixados
automaticamente na primeira coleta que precisar geocodificar.
Fontes, conduta da coleta, privacidade e limitações estão em [docs/coleta.md](docs/coleta.md).
Os dados coletados ficam em data/ e não são versionados.

## Classificar faixas de aluguel
```bash
python -m imoveis_pg classify data/base_2026-11-09.csv --output reports/classificacao-3faixas-2026-11-09
```
Compara baselines, árvore de decisão, KNN, SVM e MLP em faixas de aluguel por quantis
(`--faixas 3` por padrão). Método, resultados e limitações em [docs/classificacao.md](docs/classificacao.md).

## Agrupar perfis e regiões
```bash
python -m imoveis_pg cluster data/base_2026-11-09.csv --output reports/agrupamento-2026-11-09
```
K-means, hierárquico (Ward) e DBSCAN para perfis de casas, e DBSCAN geográfico para concentrações de oferta.
Escolhas, resultados e interpretação em [docs/agrupamento.md](docs/agrupamento.md).

O [contrato de entrada](docs/dados.md) define as 20 colunas obrigatórias,
unidades, campos opcionais e tratamento de valores inválidos. A instalação
testada está registrada em requirements-tested.txt; para reproduzir suas versões,
instale esse arquivo antes de instalar o pacote editável.

## Resultados
- observations.csv: histórico completo, valores originais, identidade e derivados.
- snapshot.csv: observação mais recente de cada identidade de anúncio.
- issues.csv: problemas de importação, identidade, coordenadas e extremos.
- quality.json: ausências, tipos, contagens, estatísticas e limitações.
- eda/: tabelas regionais, correlações com contagem de pares e seis gráficos PNG.
- manifest.json: SHA-256 da entrada, parâmetros, versões, marca sintética e lista
  de artefatos. Só é criado após a conclusão; sem ele, a saída está incompleta.

O arquivo de entrada é preservado. Falhas de contrato retornam código 2.
Saídas existentes nunca são sobrescritas. Se ocorrer falha de escrita, artefatos
parciais podem permanecer sem manifesto; tente novamente em outra pasta.

## Limitações
Coordenadas são verificadas apenas contra limites globais, sem confirmar município.
Localizações aproximadas são identificadas; não há geocodificação.
A análise de aluguel usa somente locações com aluguel positivo. Contagens gerais
incluem todas as finalidades. Identidades entre fontes podem representar o mesmo
imóvel e exigem revisão. IPTU sem periodicidade ou custos ausentes não viram zero.
Outliers permanecem na base; correlação não indica causalidade.
Nenhum atributo derivado do aluguel deve entrar como preditor no futuro modelo.

## Desenvolvimento
[Escopo aprovado](docs/proposta-inicial.md), [plano](docs/superpowers/plans/2026-10-19-dados-eda.md)
e [tarefas no Linear](docs/linear.md). Commits seguem Conventional Commits.
