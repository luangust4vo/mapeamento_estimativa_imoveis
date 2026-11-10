# Agrupamento

## Perguntas
1. **Perfis de imóveis:** existem tipos de casa para alugar com características e preços semelhantes
   ("compactas e econômicas", "familiares", "alto padrão")?
2. **Regiões:** onde a oferta se concentra, e os grupos formados correspondem às divisões oficiais da cidade?

O agrupamento é descritivo: os grupos não são usados para prever aluguel, então o aluguel pode ser atributo.

## Executar
```bash
python -m imoveis_pg cluster data/base_2026-11-09.csv --output reports/agrupamento-2026-11-09
```
Opções: `--eps-m` (raio do DBSCAN geográfico, padrão 600 m), `--min-samples` (padrão 6), `--seed` e `--bairros`.
Saídas: `perfis_selecao.{csv,png}`, `perfis_kdistancia.png`, `perfis_resumo.csv`, `perfis_rotulos.csv`,
`perfis_por_bairro.csv`, `perfis_dispersao.png`, `regioes_resumo.csv`, `regioes_sensibilidade.csv`,
`regioes_rotulos.csv`, `regioes_mapa.png` e `manifest.json`.

## Perfis de imóveis
**Atributos:** log da área, quartos, banheiros, tem suíte (ausência = sem suíte, ver
[classificacao.md](classificacao.md)) e log do aluguel, padronizados. O log reduz a assimetria de área e preço.
Só entram casas com área, quartos e banheiros informados: **140 de 208**. Não há imputação, porque valores
inventados criariam aglomerados artificiais (com imputação pela mediana, o DBSCAN chegava a 60% de ruído).
Vagas ficaram de fora por faltarem em 33% dos anúncios.

**Algoritmos e escolha:**
- **K-means** e **hierárquico (Ward)**, com k de 2 a 6. É escolhido o k de 3 a 6 com maior silhueta entre
  os que têm **estabilidade ≥ 0,85** (ARI médio entre o agrupamento da base inteira e o de 50 subamostras de 80%).
  O k=2 tem a maior silhueta (0,51), mas só separa casas pequenas de grandes; ele é reportado e não escolhido.
- **DBSCAN**, com `eps` de 0,3 a 1,3 e `min_samples` ∈ {5, 8, 10} (10 = 2 × número de atributos). Escolhe-se a
  maior silhueta, calculada sem o ruído, entre configurações com ≥ 2 grupos e **ruído ≤ 25%**. O gráfico de
  distância ao 10º vizinho (`perfis_kdistancia.png`) mostra o joelho perto de 1,0–1,2.

| Algoritmo | Configuração | Silhueta | Davies-Bouldin | Estabilidade | Ruído |
|---|---|---|---|---|---|
| **K-means** | k = 3 | 0,496 | 0,92 | **0,980** | — |
| Ward | k = 4 | 0,465 | 0,92 | 0,878 | — |
| DBSCAN | eps = 1,1; min_samples = 10 | 0,615* | 0,61* | 0,948 | 21% |

\* sem os pontos de ruído, o que favorece o DBSCAN; a comparação direta de silhueta entre algoritmos não é justa.

### Os três perfis (K-means)
| Perfil | n | Aluguel mediano (Q1–Q3) | Área | Quartos / banheiros | Com suíte | R$/m² | Distância ao centro |
|---|---|---|---|---|---|---|---|
| 1 · compactas e econômicas | 75 | R$ 1.300 (1.000–1.800) | 60 m² | 2 / 1 | 1% | 22,5 | 4,7 km |
| 2 · familiares intermediárias | 46 | R$ 3.850 (2.125–4.950) | 145 m² | 3 / 2 | 83% | 27,7 | 3,6 km |
| 3 · amplas de alto padrão | 19 | R$ 9.500 (6.500–13.500) | 361 m² | 4 / 5 | 89% | 25,0 | 2,6 km |

Os nomes foram dados a partir das medianas; os perfis são numerados por aluguel mediano crescente.

### Interpretação
- **Os perfis se separam por tamanho, não por preço do m².** O R$/m² mediano é parecido nos três (22 a 28),
  enquanto a área vai de 60 a 361 m². O aluguel cresce quase proporcionalmente à área (`perfis_dispersao.png`).
- **Os algoritmos concordam.** Sem o ruído, o DBSCAN coincide com o K-means (ARI 0,93): ele encontra os perfis 1
  e 2 como regiões densas. **O ruído do DBSCAN são as casas grandes:** todas as 19 do perfil 3, mais 9 do perfil 2
  e 2 do perfil 1. O alto padrão é heterogêneo (233 a 760 m², R$ 5 mil a R$ 22 mil) e não forma um grupo denso.
- **Ward com k = 4 divide o perfil intermediário** em "sem suíte" (15 casas, R$ 2.800) e "com suíte" (33 casas,
  R$ 3.500). A concordância com o K-means é ARI 0,73, e a estabilidade é menor (0,88).
- **Perfis e bairros quase não coincidem** (ARI 0,04): todo bairro com amostra razoável mistura perfis. Mesmo
  assim há tendências (`perfis_por_bairro.csv`): Neves (86%), Boa Vista (88%), Chapada (83%) e Contorno (75%)
  concentram casas compactas; Centro (60%) e Estrela (50%) têm a maior parte de alto padrão; Cara Cara divide-se
  meio a meio entre compactas e familiares.

## Concentrações de oferta (DBSCAN geográfico)
DBSCAN sobre latitude e longitude com distância haversine (`eps` em metros reais). Com **raio de 600 m e
mínimo de 6 anúncios**, há **11 concentrações**, e 54% dos anúncios ficam dispersos (`regioes_mapa.png`).
As concentrações são numeradas por R$/m² mediano crescente.

| Nº | n | Aluguel mediano | R$/m² | Área | Bairro principal |
|---|---|---|---|---|---|
| 1 | 6 | R$ 3.450 | 19,6 | 139 m² | Uvaranas (50%) |
| 2 | 10 | R$ 1.150 | 21,3 | 56 m² | Neves (100%) |
| 3 | 7 | R$ 1.800 | 22,5 | 73 m² | Cara Cara (100%) |
| 4 | 16 | R$ 6.500 | 23,7 | 265 m² | Estrela (56%) |
| 5 | 7 | R$ 5.000 | 24,5 | 200 m² | Uvaranas (100%) |
| 6 | 9 | R$ 4.800 | 24,5 | 209 m² | Oficinas (89%) |
| 7 | 8 | R$ 2.000 | 25,7 | 70 m² | Jardim Carvalho (88%) |
| 8 | 9 | R$ 2.900 | 27,1 | 165 m² | Órfãs (89%) |
| 9 | 12 | R$ 1.900 | 27,9 | 68 m² | Cara Cara (100%) |
| 10 | 6 | R$ 9.250 | 29,0 | 421 m² | Centro (83%) |
| 11 | 6 | R$ 9.450 | 35,6 | 224 m² | Jardim Carvalho (100%) |

- **As concentrações cabem dentro dos bairros:** 9 das 11 têm ≥ 83% dos anúncios num único bairro, e o ARI com
  os bairros é 0,60, considerando só os anúncios em concentrações. Mas um bairro pode ter várias concentrações de
  perfis diferentes: Cara Cara tem a nº 3 (R$ 22,5/m²) e a nº 9 (R$ 27,9/m²), e Jardim Carvalho tem uma de casas
  compactas (nº 7) e uma de alto padrão no extremo norte (nº 11, o maior R$/m²).
- **Concentração de anúncios não é densidade de imóveis.** A nº 9 inclui 7 casas idênticas do mesmo
  empreendimento, anunciadas separadamente. Uma concentração pode refletir um único lançamento ou a carteira
  de uma imobiliária, e não o tamanho do mercado na região.
- **Sensibilidade** (`regioes_sensibilidade.csv`): com 400 m e mínimo de 6, restam 5 concentrações e 83% de
  dispersos (ARI 0,97 com os bairros); com 1 km e mínimo de 4, 8 concentrações largas, só 10% de dispersos e
  ARI 0,12, porque elas atravessam bairros. **Quanto mais local o critério, mais os grupos coincidem com os bairros.**

## Resposta às perguntas da apostila
- **Existem regiões com perfis semelhantes?** Sim, mas como tendências: Neves, Boa Vista, Chapada e Contorno são
  majoritariamente de casas compactas, e Centro e Estrela de alto padrão. Nenhum bairro é homogêneo.
- **Os grupos correspondem às divisões oficiais?** Os perfis de imóvel não (ARI 0,04). As concentrações espaciais
  ficam dentro dos bairros quando o raio é pequeno (≤ 600 m), mas mostram que um mesmo bairro tem polos com
  preços diferentes, o que reforça que o bairro sozinho é um indicador grosseiro de preço (como na
  [classificação](classificacao.md), em que o baseline por bairro ficou bem abaixo dos modelos).

## Limitações
- Os perfis usam 140 das 208 casas; anúncios sem banheiros (sobretudo do Portal Dez) ficam de fora, o que
  pode sub-representar a fonte e os bairros em que ela atua.
- As coordenadas aproximadas (geocodificação por rua, CEP ou bairro) podem deslocar anúncios entre concentrações.
- Os grupos refletem anúncios de quatro imobiliárias numa única data, não o estoque de imóveis da cidade.
