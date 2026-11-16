# Aluguéis de casas em Ponta Grossa

Importação rastreável de CSV, relatório de qualidade, análise exploratória e
coleta automatizada de anúncios públicos de imobiliárias de Ponta Grossa.
Inclui a comparação de classificadores por faixa de aluguel, o agrupamento de
perfis e regiões e um app com mapa, filtros e simulador de aluguel.

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

## Abrir o app (mapa, filtros e simulador)
```bash
python -m imoveis_pg build-app data/base_2026-11-09.csv --output data/app/2026-11-09
python -m imoveis_pg app --artefatos data/app/2026-11-09   # http://localhost:8501
```
Clique no mapa, informe as características da casa e veja a faixa de aluguel estimada,
as casas parecidas anunciadas e os avisos de confiabilidade. Detalhes em [docs/app.md](docs/app.md).

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
- Estima o aluguel **anunciado** em quatro imobiliárias numa única data, não o preço negociado; não é
  avaliação imobiliária oficial.
- Coordenadas sem número exato são aproximadas (rua, CEP ou bairro) e marcadas como tais; o erro medido vai
  de ~74 m a ~3 km conforme o método ([docs/coleta.md](docs/coleta.md)).
- Com 208 casas no modelo, as métricas variam cerca de ±0,09 entre partições ([docs/classificacao.md](docs/classificacao.md)).
- Possíveis duplicatas entre fontes são sinalizadas, não fundidas. IPTU sem periodicidade e custos ausentes
  não viram zero. Outliers permanecem na base; correlação não indica causalidade.
- Nenhum atributo derivado do aluguel entra como preditor.

## Desenvolvimento
[Escopo aprovado](docs/proposta-inicial.md), [cronograma, decisões e pendências](docs/gestao.md) e
[dicionário de dados](docs/dicionario.md). Commits seguem Conventional Commits.
