# Protótipo: mapa, filtros e simulador

## Executar
```bash
# 1. Treinar o modelo final e gerar os artefatos (cerca de 1 min; fora da interface)
python -m imoveis_pg build-app data/base_2026-11-09.csv --output data/app/2026-11-09
# 2. Abrir o app em http://localhost:8501
python -m imoveis_pg app --artefatos data/app/2026-11-09
```
O app roda sem cabeçalho de boas-vindas (`--server.headless`) e com estatísticas de uso do Streamlit desligadas.
Nenhum modelo é treinado durante a navegação: tudo vem dos artefatos.

## Artefatos (`build-app`)
| Arquivo | Conteúdo |
|---|---|
| `anuncios.csv` | anúncios com coordenadas, **sem endereço**: bairro oficial, atributos, aluguel, R$/m², precisão da localização, faixa anunciada, faixa estimada fora da amostra, comparação e perfil |
| `bairros.geojson` | os 16 bairros oficiais (IBGE, Censo 2022) |
| `modelos.joblib` | classificador final e modelo de perfis (escalonador + K-means) |
| `metadados.json` | data e fontes da base, hiperparâmetros, métricas de validação cruzada, limites das faixas e dos atributos, avisos |

**Classificador final:** MLP, o modelo escolhido pela validação cruzada em 7 de 10 partições
([classificacao.md](classificacao.md)). Ele é reajustado nas **208 casas**, com hiperparâmetros escolhidos por
`GridSearchCV` com `GroupKFold` (5 dobras, agrupado por imóvel). Na base de 2026-11-09: `alpha = 0,01`,
camadas (32, 16) e balanced accuracy de 0,712 ± 0,053 na validação cruzada. As faixas são os tercis da base
inteira: baixa até R$ 1.500, média até R$ 3.800 e alta acima disso.

**Anunciado × estimado:** cada casa é prevista por um modelo que não a viu (mesmas dobras e hiperparâmetros).
Na base atual: 149 dentro do padrão, 31 anunciadas acima e 28 abaixo do previsto.

## Telas
1. **Mapa do mercado**
   - Indicadores (anúncios, aluguel mediano, R$/m²) recalculados a cada filtro.
   - Bairros coloridos pela mediana do aluguel ou do R$/m², em quatro classes por quartis.
   - **Bairros com menos de 5 anúncios em cinza tracejado** (baixa confiabilidade).
   - Pontos: cheios = localização exata, vazados = aproximada.
   - Popup com aluguel, área, quartos, perfil, comparação anunciado × estimado e link do anúncio.
   - Tabela por bairro e exportação dos anúncios filtrados em CSV.
2. **Simulador**
   - O usuário clica no mapa (contornos dos bairros oficiais) e informa área, quartos, banheiros, vagas, suítes e tipo.
   - Resultado: faixa estimada com intervalo em reais, probabilidade por faixa, mediana das 5 casas anunciadas mais
     parecidas, bairro oficial, número de casas num raio de 1 km, perfil semelhante e tabela de comparáveis com links.
3. **Qualidade dos dados**
   - Anúncios por imobiliária, precisão da localização, atributos ausentes e bairros com poucos dados.
   - Lista dos anúncios acima ou abaixo do padrão.
4. **Sobre e limitações:** método, fontes e avisos.

**Filtros** (barra lateral): uso, tipo (casa, sobrado, casa em condomínio), bairros, faixa de aluguel, quartos e
perfil. A finalidade é fixa: a base atual só tem locação, e o app avisa isso.

## Regras do simulador
- **Fora dos bairros oficiais** (mais de 300 m de qualquer polígono): estimativa indisponível, com a explicação.
- **Suítes = 0 e vagas = 0 viram "não informado"** na entrada do modelo. Nenhum anúncio da base informa zero:
  quem não tem omite o campo, que no treino fica ausente e recebe um indicador. Enviar 0 seria uma entrada que
  o modelo nunca viu: no mesmo ponto de Uvaranas (80 m², 2 quartos, 1 banheiro), o zero cru dava média com
  100% e a codificação correta dá baixa com 80%.
- **Avisos:**
  - menos de 5 casas num raio de 1 km;
  - bairro com menos de 5 casas na base;
  - atributo fora do intervalo da base (área entre os percentis 1 e 99; contagens entre o mínimo e o máximo);
  - nenhuma faixa acima de 50%;
  - **modelo e comparáveis discordam**, quando a mediana das casas parecidas cai em outra faixa.
- **Perfil semelhante:** K-means aplicado à casa informada, usando a mediana dos comparáveis como referência
  de aluguel.
- **Comparáveis:** as 5 casas com menor distância combinada de área (escala log), quartos e distância geográfica.

## Decisões de interface
- **Cores:** rampa azul sequencial da paleta de referência para os bairros, cinza neutro para dados insuficientes e
  tinta neutra para os pontos, para não haver duas escalas de cor competindo. A legenda informa o indicador, a
  unidade e o método (quartis).
- **Mapa-base OpenStreetMap,** com atribuição. Os mapas da CARTO passaram a exigir chave de API nesta versão do
  folium. Os nomes do mapa-base são loteamentos do OpenStreetMap e podem diferir dos bairros oficiais (o app avisa).
- **Privacidade:** endereços não são exibidos nem exportados; os links levam ao anúncio público.
- **Probabilidades:** são as do MLP, sem calibração, e o app as apresenta como preferência entre faixas,
  não como chance de acerto.

## Verificação
- Testes automatizados (`tests/test_app.py`):
  - construção dos artefatos sem endereço;
  - simulação dentro e fora da cidade;
  - zero = ausente;
  - avisos de extrapolação e de baixa cobertura;
  - `AppTest` do Streamlit carregando o app e enviando o formulário com um ponto escolhido.
- Teste manual no navegador (Playwright): mapa, filtros, clique no simulador, resultado e abas de qualidade e
  "Sobre". Foi esse teste que revelou o problema de suítes = 0 e a discordância entre modelo e comparáveis.

## Limitações
- O app usa o clique no mapa (`streamlit-folium`), dependência além da stack listada no AGENTS.md, necessária
  para capturar o ponto clicado.
- O mapa-base vem de servidor externo (OpenStreetMap) e exige internet.
- A estimativa é de aluguel **anunciado** em quatro imobiliárias numa única data.
