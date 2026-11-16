# Classificação por faixas de aluguel

## Pergunta
Dadas as características e a localização de uma casa residencial para locação em Ponta Grossa,
em qual faixa de aluguel anunciado ela se encontra? A apostila exige comparar ao menos três
classificadores com baseline, validação cruzada, matriz de confusão e análise de erros.

## Executar
```bash
python -m imoveis_pg classify data/base_2026-11-09.csv --output reports/classificacao-3faixas-2026-11-09
python -m imoveis_pg classify data/base_2026-11-09.csv --output reports/classificacao-4faixas-2026-11-09 --faixas 4
```
Opções: `--faixas` (2 a 5, padrão 3), `--seed` (padrão 42) e `--bairros` (malha do IBGE).
Saídas: `metricas.csv`, `faixas.json`, `matrizes_confusao.png`, `comparacao_modelos.png`,
`importancia_atributos.{csv,png}`, `erros_teste.csv`, `erros_por_bairro.csv`,
`modelo_selecionado.joblib` e `manifest.json` (semente, tamanhos, hiperparâmetros, versões e SHA-256 da entrada).

## Dados
Casas residenciais para locação elegíveis da base unificada (`elegivel_preliminar`), com coordenadas
e bairro oficial. Na base de 2026-11-09: **208 casas**, 28 anúncios excluídos (uso comercial).

**Atributos** (nada derivado do aluguel, para evitar vazamento):

| Grupo | Atributos |
|---|---|
| Físicos | área (m²), quartos, suítes, banheiros, vagas |
| Localização | latitude, longitude, distância ao centro (km), bairro oficial |
| Tipo | subtipo: casa, sobrado ou casa em condomínio |

A distância ao centro usa um ponto fixo e externo aos dados: o nó "Ponta Grossa" do OpenStreetMap
(-25,0891685; -50,1601812). A fonte (imobiliária) não é atributo, pois o usuário do simulador não a conhece.

## Método
1. **Alvo:** o aluguel é discretizado em faixas por quantis (tercis com 3 faixas). Os limites são calculados
   **dentro do `fit`, só com o treino de cada partição** (`QuantileBandClassifier`); validação e teste são
   convertidos com esses mesmos limites. Assim nenhuma faixa é definida olhando dados de avaliação.
2. **Pré-processamento** (dentro do pipeline, ajustado só no treino): imputação pela mediana com indicador de
   ausência, padronização dos numéricos e one-hot de bairro e subtipo. Todos os modelos recebem o mesmo.
3. **Partição:** 20% de teste reservado, separado por **grupo de imóvel** (`GroupShuffleSplit`). Um grupo une
   (a) anúncios do mesmo imóvel em fontes diferentes (mesmo logradouro, área e quartos) e (b) anúncios com mesmo
   bairro, área, quartos e aluguel, como unidades idênticas de um empreendimento. Agrupar a mais não vaza
   informação; agrupar a menos permitiria acertar o teste por memorização. Na base atual: 208 casas em 189 grupos.
4. **Hiperparâmetros:** `GridSearchCV` com `GroupKFold` de 5 dobras, só no treino, otimizando balanced accuracy.
5. **Seleção:** o modelo com maior balanced accuracy **média na validação cruzada** (desempate pelo F1 macro).
   O teste reservado nunca é usado para escolher.
6. **Avaliação no teste:** acurácia, balanced accuracy, precisão, recall e F1 macro, matriz de confusão e
   **erro grave** (errar por duas faixas ou mais, já que as faixas são ordenadas).
7. **Fatores:** importância por permutação no teste (queda de balanced accuracy ao embaralhar cada atributo).

**Métricas.** As faixas são quase balanceadas no treino por construção (tercis), mas o teste pode ficar
desbalanceado (ex.: 10/18/14). Por isso a métrica principal é a balanced accuracy, que dá o mesmo peso a cada
faixa, acompanhada do F1 macro. A acurácia simples é reportada, mas não decide.

**Modelos e grades:**

| Modelo | Hiperparâmetros testados |
|---|---|
| Baseline: classe frequente | — (sempre a faixa mais comum do treino) |
| Baseline: faixa do bairro | — (faixa mais comum do bairro no treino) |
| Árvore de decisão | `max_depth` ∈ {3, 5, 8, ∞}; `min_samples_leaf` ∈ {1, 3, 5, 10} |
| KNN | `n_neighbors` ∈ {3, 5, 7, 11, 15}; `weights` ∈ {uniform, distance} |
| SVM (RBF) | `C` ∈ {0,1; 1; 10; 100}; `gamma` ∈ {scale; 0,01; 0,1} |
| MLP | camadas ∈ {(16), (32), (32, 16)}; `alpha` ∈ {0,0001; 0,01; 1} |

Semente 42 para partição, dobras, árvore e MLP.

## Resultados (base de 2026-11-09)
Relatórios em `reports/classificacao-3faixas-2026-11-09` e `reports/classificacao-4faixas-2026-11-09`,
gerados com `--repeticoes 10`.

### Por que repetir com 10 sementes
Com 208 casas, o teste reservado tem 42. Numa única partição, a balanced accuracy de um mesmo modelo varia
cerca de **±0,09** conforme as casas sorteadas para o teste. Na semente 42, por exemplo, o baseline de bairro
teve 0,67 no teste, acima de todos os modelos, mas 0,53 na validação cruzada e 0,54 de média nas 10 partições.
Por isso as conclusões abaixo vêm da **repetição do experimento inteiro** (partição, busca de hiperparâmetros
e seleção) com as sementes 0 a 9, e não de uma única partição.

### 3 faixas (principal)
Limites calculados no treino da semente 42: **baixa ≤ R$ 1.450**, **média R$ 1.450–3.800**, **alta > R$ 3.800**.

| Modelo | CV (média) | Teste: média ± dp | Teste: mín–máx | F1 macro | Erro grave | Selecionado |
|---|---|---|---|---|---|---|
| **MLP** | **0,695** | **0,664 ± 0,096** | 0,48–0,79 | 0,662 | 0,2% | 7× |
| SVM | 0,679 | 0,653 ± 0,092 | 0,44–0,76 | 0,644 | 0,9% | 1× |
| KNN | 0,644 | 0,623 ± 0,080 | 0,49–0,74 | 0,607 | 2,1% | 0× |
| Árvore de decisão | 0,655 | 0,609 ± 0,058 | 0,52–0,72 | 0,600 | 3,1% | 2× |
| Baseline: faixa do bairro | 0,532 | 0,544 ± 0,058 | 0,45–0,64 | 0,533 | 6,3% | — |
| Baseline: classe frequente | 0,333 | 0,333 | — | 0,167 | 35,1% | — |

(balanced accuracy; acaso = 0,333)

### 4 faixas (alternativa)
Limites da semente 42: baixa ≤ R$ 1.225; média até R$ 2.000; alta até R$ 4.725; muito alta acima.

| Modelo | CV (média) | Teste: média ± dp | F1 macro | Erro grave | Selecionado |
|---|---|---|---|---|---|
| SVM | 0,603 | 0,627 ± 0,096 | 0,596 | 8,0% | 5× |
| MLP | 0,599 | 0,634 ± 0,088 | 0,610 | 6,1% | 4× |
| Árvore de decisão | 0,568 | 0,606 ± 0,061 | 0,568 | 8,3% | 1× |
| KNN | 0,545 | 0,551 ± 0,089 | 0,523 | 10,7% | 0× |
| Baseline: faixa do bairro | 0,423 | 0,483 ± 0,090 | 0,434 | 16,9% | — |

(acaso = 0,25)

## Interpretação
- **Os modelos aprendem algo além do bairro.** Com 3 faixas, o modelo escolhido pela validação cruzada superou
  o baseline de bairro no teste em 9 das 10 partições (10 de 10 com 4 faixas). A diferença média é de ~0,10
  de balanced accuracy com 3 faixas (0,641 contra 0,544) e ~0,15 com 4 faixas (0,636 contra 0,483).
  Área e tipo da casa acrescentam informação à localização.
- **MLP e SVM lideram, mas a diferença entre eles não é conclusiva.** As distribuições se sobrepõem
  (`estabilidade.png`); com esta base, não dá para afirmar que um seja melhor que o outro.
  A árvore é a mais estável (menor desvio) e a mais fácil de explicar, porém um pouco pior em média.
- **3 faixas é a escolha principal.** Com 4 faixas o ganho sobre o acaso é proporcionalmente maior (MLP: 2,5×
  contra 2,0×), mas os erros graves (pular uma faixa) sobem de ~0,2% para 6 a 8% nos melhores modelos. Para o
  usuário do simulador, uma faixa mais larga e confiável vale mais que uma estreita que às vezes erra feio.
- **A faixa média é a mais difícil.** Na semente 42, o recall foi 0,60 (baixa), 0,39 (média) e 0,71 (alta).
  Os erros são quase todos para a faixa vizinha. Em classes ordenadas isso é esperado: a faixa do meio tem
  vizinhas dos dois lados.
- **Fatores associados (importância por permutação):** a área domina em todos os modelos. No MLP com 4 faixas,
  a importância se distribui entre distância ao centro (0,10), área (0,07), bairro (0,07) e banheiros (0,06). Na
  árvore com 3 faixas, quase só a área importa. A importância é medida num teste de 42 casas e varia com o modelo;
  é associação, não causalidade.
- **Suítes ausentes carregam informação.** Nenhum anúncio informa "0 suítes": quem não tem suíte omite o campo.
  Casas sem o campo têm mediana de R$ 1.600, contra R$ 5.000 das com ≥ 1 suíte, e as medianas por imobiliária
  são parecidas (R$ 1.900 a R$ 2.100 nas três maiores). Logo, o indicador de ausência criado na imputação capta
  "sem suíte", e não "qual imobiliária anunciou".

## Problemas encontrados e corrigidos durante a análise
- **Duplicatas não detectadas entre fontes:** o Portal Dez omite o número da casa, então o mesmo imóvel na
  Torre Blanca não era reconhecido. A detecção passou a comparar o logradouro sem número (de 2 para 11
  anúncios sinalizados).
- **Unidades idênticas:** 7 casas do Portal Dez na mesma rua, com 68 m², 3 quartos e R$ 1.900. Separadas entre
  treino e teste, permitiriam acertar por memorização; agora ficam no mesmo grupo.

## Limitações
- **Base pequena:** 208 casas e 42 no teste. As métricas têm incerteza de cerca de ±0,09; mais dados
  (Kikina, Conceito) devem estreitar esse intervalo.
- **Hiperparâmetros e seleção na mesma validação cruzada:** a média de CV do modelo escolhido é levemente
  otimista. O teste reservado e as 10 repetições servem de contrapeso.
- **O modelo salvo** (`modelo_selecionado.joblib`) foi ajustado só nos 80% de treino. Para o simulador,
  o modelo final deve ser reajustado na base inteira com os hiperparâmetros escolhidos.
- **Anúncios, não negócios:** o alvo é o aluguel anunciado; não representa preço negociado nem é avaliação
  imobiliária oficial. Quatro imobiliárias não cobrem o mercado municipal de forma representativa.

