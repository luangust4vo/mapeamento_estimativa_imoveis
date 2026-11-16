# Gestão do projeto

Registro de cronograma, decisões e pendências, mantido no repositório junto do código. Até 2026-11-16 as
tarefas eram acompanhadas no Linear (projeto "Aluguéis de casas Ponta Grossa", tarefas IFP-5 a IFP-14). O
quadro ficou desatualizado e foi substituído por este documento, que concentra planejamento e evidências num só
lugar. A [proposta inicial](proposta-inicial.md) e o [plano da primeira entrega](superpowers/plans/2026-10-19-dados-eda.md)
foram mantidos como registro histórico e ainda citam o Linear.

## Escopo
Casas residenciais para **locação** em **Ponta Grossa (PR)**, a partir de anúncios públicos de imobiliárias
locais. Venda, apartamentos e imóveis comerciais ficam fora dos modelos (os comerciais aparecem no mapa, com filtro).

## Cronograma realizado
Datas dos commits; a coluna "Encontros" relaciona cada entrega ao planejamento de 16 encontros da apostila.

| Data | Entrega | Encontros | Evidência |
|---|---|---|---|
| 2026-10-19 | Escopo, requisitos e plano da primeira entrega | 1–2 | `docs/proposta-inicial.md` |
| 2026-10-19/20 | Importação rastreável, auditoria de qualidade, EDA e CLI de relatórios | 3–5 | `docs/dados.md`, `docs/execucao-dados-eda.md` |
| 2026-11-09 | Coleta automatizada de 4 imobiliárias (236 anúncios) | 3 | `docs/coleta.md` |
| 2026-11-09 | Geocodificação offline (CNEFE 2022) e bairros oficiais (malha IBGE 2022) | 6–7 | `docs/coleta.md`, `docs/dados.md` |
| 2026-11-09 | Classificação por faixas: baselines, árvore, KNN, SVM e MLP, com estabilidade entre partições | 10–12 | `docs/classificacao.md` |
| 2026-11-09 | Agrupamento: K-means, Ward e DBSCAN (perfis) e DBSCAN geográfico | 8–9 | `docs/agrupamento.md` |
| 2026-11-09 | Protótipo Streamlit: mapa, filtros, simulador, qualidade dos dados | 14 | `docs/app.md` |
| 2026-11-16 | Filtros reorganizados, dicionário de dados e este registro de gestão | 15 | `docs/dicionario.md` |

## Registro de decisões
| Data | Decisão | Motivo | Alternativa descartada |
|---|---|---|---|
| 2026-10-19 | Entregas progressivas: dados e EDA → modelos → mapa e simulador | Validar a qualidade dos dados antes de publicar estimativas | Protótipo visual primeiro, com dados sintéticos |
| 2026-10-19 | Alvo = aluguel **anunciado**; condomínio e IPTU como custos separados | É o que os anúncios informam; preço negociado não é observável | — |
| 2026-11-09 | Coleta por scraping só de páginas públicas, respeitando `robots.txt`, com 3 s entre requisições e cache | Exigência ética e legal da apostila (seção 18) | Agregadores (Mitula, Trovit) |
| 2026-11-09 | Nenhum dado de corretor, descrição livre ou foto é copiado; endereço só na base local | Privacidade (apostila, seção 18) | — |
| 2026-11-09 | Geocodificação com o **CNEFE 2022 (IBGE)**, offline | Nominatim, Photon, Overpass e BrasilAPI bloqueiam a busca no `robots.txt` | Nominatim |
| 2026-11-09 | CEPs com sufixo 900–999 ignorados; recuo para o bairro quando o resultado cai a mais de 1 km dele | Erros reais encontrados na inspeção espacial (CEP genérico; CEP de outra região) | — |
| 2026-11-09 | **16 bairros oficiais** da malha do IBGE (Censo 2022) como unidade espacial | Unifica as 37 grafias dos anúncios e fornece os polígonos do mapa | Lista de bairros digitada à mão |
| 2026-11-09 | Classificação em **3 faixas** por tercis calculados só no treino | Com 4 faixas, os erros graves sobem de ~0,2% para 6–8% | 4 faixas (mantidas como alternativa documentada) |
| 2026-11-09 | Partição treino/teste por **grupo de imóvel** (duplicatas e unidades idênticas juntas) | Duplicatas entre fontes e 7 casas idênticas permitiriam acertar por memorização | Partição aleatória simples |
| 2026-11-09 | Seleção pela validação cruzada e **10 repetições** do experimento inteiro | O teste de 42 casas varia ±0,09 entre partições | Escolher pelo teste de uma única partição |
| 2026-11-09 | Ausência de suítes tratada como informação ("sem suíte") | Nenhum anúncio informa zero; as medianas por fonte são parecidas, então não é efeito da fonte | Imputar a mediana sem indicador |
| 2026-11-09 | Perfis com K-means k = 3 (k = 2 não é candidato) | k = 2 só separa casas pequenas de grandes; k = 3 tem silhueta 0,50 e estabilidade 0,98 | k pela silhueta máxima |
| 2026-11-09 | MLP reajustado na base inteira como modelo do app | Escolhido pela validação cruzada em 7 de 10 partições | SVM (empate técnico) |
| 2026-11-09 | Suítes = 0 e vagas = 0 tratadas como ausentes no simulador | Reproduz a codificação do treino; no mesmo ponto, o zero cru dava média com 100% e a codificação correta, baixa com 80% | — |
| 2026-11-16 | Filtros dentro da aba do mapa, e não numa barra lateral | Na barra lateral, apareciam também no simulador, que não os usa | Fixar os filtros no código (descartado: é requisito mínimo da apostila) |
| 2026-11-16 | Gestão registrada no repositório em vez do Linear | Um só lugar para planejamento, decisões e evidências | Manter o Linear atualizado à mão |

## Riscos (seção 19 da apostila) e como foram tratados
| Risco | Situação |
|---|---|
| Poucos imóveis por região | Bairros com menos de 5 anúncios em cinza no mapa e com aviso no simulador (Nova Rússia: 4; Vila Ildemira: 2) |
| Endereços incompletos | Geocodificação em cascata com precisão registrada; erro medido de 74 m (número exato) a ~3 km (bairro) |
| Anúncios duplicados | Detecção entre fontes pelo logradouro sem número; grupos de imóvel na partição |
| Valores extremos | Sinalizados por IQR e preservados; log do aluguel no agrupamento; balanced accuracy e F1 macro |
| Vazamento de dados | Faixas, imputação e escalas ajustadas só no treino; nenhum atributo derivado do aluguel |
| Mapa enganoso | Legenda com indicador, unidade e método (quartis); n por bairro; pontos aproximados marcados |
| Escopo excessivo | Casas para locação numa cidade; venda e apartamentos fora |

## Equipe e contribuições
Todos os commits estão em nome de Luan Gustavo. Se o trabalho for em equipe, registre aqui quem foi responsável
por cada frente (dados, geoprocessamento, modelagem, aplicação, documentação), como pede a seção 13 da apostila.

## Pendências
- [x] Relatório técnico consolidado: [relatorio_tecnico.md](relatorio_tecnico.md)
- [x] ~~Apresentação por slides~~: cancelada (informado em 2026-11-16)
- [ ] Forma de entrega da base processada (sem endereço) e decisão sobre versionar o PDF da apostila
- [ ] Confirmar com o professor: regressão obrigatória ou opcional; quantidade mínima de anúncios
- [ ] Opcional: coletores da Kikina e da Conceito para reduzir a incerteza das métricas
