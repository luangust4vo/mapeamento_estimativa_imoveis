# Contexto de Sistema: IA de Especulação Imobiliária

> **Visão Geral e Objetivo Principal:**
> O sistema computacional visa analisar a distribuição espacial dos preços de alugel das casas de Ponta Grossa - Paraná, produzindo estimativas, agrupamentos e classificações que auxiliem a compreensão do mercado imobiliário local. O fluxo final de usuário exigido é: Após o software estar pronto, conseguir clicar no mapa, passar os requisitos da casa e o software retornar o valor estimado levando em consideração a localidade da casa.

## 1. Arquitetura de Dados e Atributos

A base de dados será construída a partir de anúncios e fontes diversas (priorizando fontes oriundas da cidade de Ponta Grossa, como imobiliárias de lá), exigindo limpeza, padronização e integração.

| Categoria | Atributos Incluídos | Descrição / Papel no Modelo |
| :--- | :--- | :--- |
| **Identificação** | ID, fonte, URL, data da coleta | Rastreabilidade e controle de duplicidade. |
| **Localização** | Endereço, bairro, coordenadas (Lat/Lon) | Essencial para mapas e cálculo de densidade/valorização. |
| **Físicas** | Área, quartos, suítes, banheiros, vagas | Features numéricas principais para predição de preço. |
| **Comerciais** | Aluguel, preço, condomínio, IPTU | Variáveis-alvo (target) ou componentes de custo total. |
| **Derivadas** | Preço/m², idade, custo mensal total, densidade | Criadas durante a Engenharia de Atributos. |

## 2. Pipeline de Pré-Processamento (Obrigatório)

Antes da modelagem, a IA deve passar por este pipeline reproduzível e robusto:

1. **Inspeção inicial:** Verificar dimensões, tipos, valores ausentes, duplicidades e estatísticas básicas.
2. **Padronização:** Uniformizar nomes de bairros, unidades de área, moedas e formatos numéricos.
3. **Tratamento de ausentes:** Remover, imputar ou criar categorias específicas, justificando a decisão.
4. **Tratamento de extremos:** Analisar outliers com boxplots, IQR, z-score ou critérios de domínio.
5. **Codificação:** Converter variáveis categóricas por one-hot encoding ou técnica equivalente.
6. **Normalização:** Aplicar padronização ou normalização quando exigida pelo algoritmo.
7. **Engenharia de atributos:** Criar preço/m², custo mensal total, densidade de cômodos e indicadores de localização.
8. **Separação dos dados:** Evitar vazamento de informação ao dividir treino, validação e teste antes de ajustar transformações.

## 3. Análise Exploratória dos Dados (EDA)

O fluxo de desenvolvimento deve iniciar respondendo a perguntas de negócio e compreendendo os dados:

* Histograma e boxplot dos preços totais e preços por metro quadrado.
* Comparação entre bairros, tipos de imóvel e finalidade comercial.
* Correlação entre atributos numéricos (ex: relação entre área e preço).
* Contagem de imóveis por região.
* Identificação de regiões com alta variabilidade de preço.
* Inspeção espacial de pontos possivelmente geocodificados incorretamente.

## 4. Modelagem e Machine Learning

O sistema atuará nas seguintes frentes analíticas:

* **Agrupamento (Clustering):** Executar o DBSCAN para identificar perfis de imóveis ou regiões semelhantes.
* **Classificação:** Comparar Decision Tree, MLP e SVM para categorizar imóveis em faixas de preço ou estimar o preço contínuo.

## 5. Requisitos Funcionais do Software (MVP)

O Componente Geográfico é central. Cada imóvel deverá ser associado a coordenadas ou a uma unidade espacial.

* Carregar uma base de imóveis e exibir um resumo da qualidade dos dados.
* Filtrar por finalidade, tipo de imóvel, bairro, faixa de preço e quantidade de quartos.
* Exibir imóveis como pontos em um mapa.
* Apresentar uma camada colorida (mapa de calor/coroplético) com o preço médio ou mediano por região.
* Mostrar quantidade de anúncios e preço por metro quadrado em cada região.
* **O Simulador (Core):** Permitir informar características de um novo imóvel (clicando no mapa/passando requisitos) e retornar uma faixa ou estimativa de preço.
* Exibir avisos sobre limitações e regiões com poucos dados.

### 5.1 Funcionalidades Adicionais (Diferenciais)

* Comparação temporal de preços.
* Busca de imóveis semelhantes ao imóvel consultado.
* Explicação dos fatores associados à previsão.
* Exportação de mapas e relatórios.
* Comparação entre preço anunciado e preço estimado.
* Painel com indicadores do mercado imobiliário municipal.

## 6. Stack Python
* **Manipulação de Dados:** `pandas`, `numpy`
* **Modelagem de IA:** `scikit-learn`
* **Geoprocessamento e Mapas:** `folium`, `geopandas`
* **Interface/MVP:** `streamlit`
