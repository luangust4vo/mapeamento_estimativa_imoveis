# Proposta inicial — Aluguéis de casas em Ponta Grossa
Data: 2026-10-19
Status: escopo e arquitetura aprovados pelo usuário em 2026-10-19; implementação ainda não iniciada.
Fonte de requisitos: AGENTS.md do repositório mapeamento_estimativa_imoveis.

## Objetivo e decisões propostas
Permitir selecionar uma localização no mapa, informar características de uma casa e obter uma estimativa de aluguel mensal em reais, acompanhada de evidências sobre cobertura e limitações.
O MVP estima aluguel anunciado, não preço efetivamente negociado. Condomínio e IPTU são custos separados. A previsão inicial atende casas residenciais para locação em Ponta Grossa; a base e os filtros preservam outros tipos e finalidades para análise, sem misturar seus preços no treinamento.

## Situação verificada
O repositório contém README.md e AGENTS.md, sem código ou base de anúncios. O AGENTS.md está não rastreado pelo Git e será preservado. A equipe IFPR está disponível no Linear e não possui projetos retornados pela consulta.
Ainda será necessário selecionar e verificar fontes locais de anúncios e dados geográficos. Nenhuma coleta, cobertura de dados ou precisão de modelo foi demonstrada.

## Alternativas
1. Recomendação: entregas progressivas — dados e EDA; modelagem; mapa e simulador. Permite validar qualidade antes de publicar estimativas e mantém a stack exigida.
2. Protótipo visual com dados sintéticos primeiro: facilita avaliar interação, mas não valida o mercado e precisa ser explicitamente identificado como demonstração.
3. Coleta automatizada ampla primeiro: pode ampliar cobertura, mas depende dos formatos, acessibilidade e condições de cada fonte e adia o fluxo utilizável.

## Arquitetura proposta
Python com pandas e numpy para dados, scikit-learn para modelos, geopandas e folium para geografia e Streamlit para interface.
- Dados: recebe arquivos de anúncios e devolve tabela padronizada, registros rejeitados e relatório de qualidade. Preserva entrada bruta e rastreabilidade.
- Análise: recebe tabela validada e produz agregações, estatísticas e visualizações.
- Modelagem: recebe dados elegíveis e configuração; produz pipeline ajustado, avaliação e metadados de treinamento.
- Predição: recebe localização e características; devolve estimativa, cobertura e avisos.
- Interface: apresenta esses resultados e mantém o ponto selecionado e os filtros.
Treinamento ocorre fora das interações de navegação. A interface não treina novamente a cada clique.

## Primeira entrega: contrato de dados, importação e EDA
Entrada inicial por CSV; adaptadores de coleta entram depois da inspeção das fontes.
Contrato: id, fonte, url, data_coleta, endereco, bairro, latitude, longitude, tipo, finalidade, area_m2, quartos, suites, banheiros, vagas, aluguel, preco, condominio, iptu e periodicidade_iptu. Data de construção e precisão/origem da localização são opcionais.
Valores monetários em BRL e área em m². Campos ausentes permanecem ausentes; custo desconhecido não vira zero. IPTU só é mensalizado quando sua periodicidade for conhecida.
Preservar grafia original e versão normalizada do bairro, sem unir bairros por aproximação silenciosa. Deduplicar por fonte/id/URL; sinalizar possíveis anúncios do mesmo imóvel entre fontes. Histórico de preços não conta como imóveis independentes.
Registros sem aluguel positivo não entram na modelagem. Coordenadas inválidas são sinalizadas; endereço aproximado ou centroide de bairro não é apresentado como localização exata.
Relatório: dimensões, tipos, ausências, duplicatas, rejeições, estatísticas, outliers e cobertura espacial. Extremos plausíveis são sinalizados, não descartados automaticamente.
EDA: histogramas e boxplots de aluguel e aluguel/m²; comparação por bairro, tipo e finalidade; correlação; contagens regionais; variabilidade; inspeção de coordenadas.
Dados sintéticos são permitidos apenas para testes e demonstração identificada, nunca para alegar desempenho de mercado.

Critérios de aceite:
- Importação reproduzível com diagnóstico legível de colunas ausentes e valores inválidos.
- Tratamento verificável de moeda brasileira, área, ausências, duplicatas e periodicidade de IPTU.
- Entrada bruta preservada; relatórios indicam o que foi alterado, rejeitado ou sinalizado.
- EDA contempla todas as perguntas do AGENTS.md e trata base vazia ou insuficiente sem resultados inventados.
- Testes verificam esses comportamentos pela interface pública dos módulos.

## Entregas seguintes e dependências
1. Fontes locais e geografia: documentar origem, condições de acesso, data, precisão e cobertura; construir amostra real rastreável. Pode avançar junto à primeira entrega.
2. Modelagem: depende dos dados validados. Separar treino, validação e teste por identidade do imóvel, com avaliação espacial e temporal quando os dados permitirem. Ajustar imputação, codificação, escalas e limites aprendidos somente no treino.
3. Comparar baseline de mediana com DecisionTreeRegressor, MLPRegressor e SVR, usando MAE, RMSE e R², incluindo resultados por região e tamanho das amostras. Não prometer um erro aceitável antes da avaliação. Faixas de preço, se usadas na classificação, terão limites definidos sem consultar o teste.
4. DBSCAN: agrupar perfis ou localidades com distância/escala coerentes; explicar ruído e parâmetros. Agrupamentos não substituem validação preditiva.
5. Interface geográfica: depende de dados e modelo avaliados. Mapa de pontos, filtros exigidos, camada regional de mediana, contagem e aluguel/m². Não interpretar densidade de anúncios como preço médio.
6. Simulador: clique no mapa, formulário de características e estimativa; avisos de extrapolação, baixa cobertura e localização aproximada. Sem modelo validado, mostrar estado indisponível. Intervalo preditivo só será exibido após calibração e verificação de cobertura.
7. Validação integrada: carregar base, filtrar, selecionar ponto, prever, comparar resultado e tratar erros; documentar execução reproduzível.

## Prevenção de vazamento
Aluguel/m², custo mensal total e quaisquer derivados do aluguel são apenas analíticos e nunca entradas para prever aluguel. Agregações de preço por localização usadas como atributos também exigem cálculo restrito ao treino. Separar duplicatas relacionadas entre partições é proibido.

## Direção de experiência e design
Product Design orientará a escolha visual antes da implementação da interface. Proposta funcional: mapa como área principal, filtros visíveis e formulário associado ao ponto selecionado. Resultado explicita aluguel, custos separados, data da base e cobertura. Valores em pt-BR, contraste legível e avisos que não dependem apenas de cor.
As três alternativas visuais serão exploradas na etapa de interface. Esta primeira entrega se concentra em dados e análise, sem construir telas.

## Fora da primeira versão
Comparação temporal completa, busca de semelhantes, explicações avançadas, exportação e comparação entre anunciado e estimado ficam no backlog após o fluxo principal.

## Próximo marco de revisão
Escopo aprovado. Revisar o plano da primeira entrega e selecionar a forma de execução antes da implementação. Projeto, marcos e tarefas serão mantidos no Linear. Usar Conventional Commits em todos os commits.
