# Contrato de dados
Todas as colunas, inclusive extras e derivadas, estão descritas no [dicionário de dados](dicionario.md).

CSV UTF-8 (BOM aceito), delimitado por ponto e vírgula; decimal vírgula.
Use --sep e --decimal para outra convenção. Não há detecção automática.

Todas as colunas abaixo devem existir; células vazias são permitidas:
- Identidade: id, fonte, url, data_coleta.
- Localização: endereco, bairro, latitude, longitude.
- Escopo: tipo, finalidade.
- Características: area_m2, quartos, suites, banheiros, vagas.
- Valores: aluguel, preco, condominio, iptu, periodicidade_iptu.

Valores monetários são BRL, área é m² e coordenadas são graus WGS84.
"R$ 1.234,56", "80 m²" e datas ISO ou dd/mm/aaaa são aceitos.
Coordenadas seguem o decimal declarado; agrupamento de milhares não é aceito.
Contagens devem ser inteiras não negativas. Valores inválidos ficam ausentes,
com diagnóstico de linha/coluna/valor original. Nenhuma ausência vira zero.
Colunas extras são preservadas. Colunas opcionais reconhecidas: ano_construcao,
uso (residencial/comercial), precisao_localizacao, origem_localizacao, sintetico.
Cabeçalhos reservados para colunas derivadas ou terminados em _original são rejeitados.
O arquivo deve ter o mesmo número de campos em todas as linhas.

As colunas *_original guardam a representação recebida, inclusive espaços.
row_id combina SHA-256 dos bytes de entrada e número ordinal do registro (+ cabeçalho).
A coluna linha é ordinal do registro CSV; em campos multilinha não é a linha física.
A normalização do bairro só remove acentos, caixa e espaços repetidos; não une
nomes aproximados. A importação não imputa nem geocodifica: a geocodificação acontece na coleta
([coleta.md](coleta.md)) e a atribuição aos bairros oficiais, com `--bairros` (abaixo).

## Identidade e qualidade
entity_id prefere fonte normalizada + id, depois URL (host/esquema em minúsculas,
sem fragmento e barra final), depois row_id. Histórico é preservado; snapshot
seleciona a observação de data mais recente (datas ausentes primeiro), com row_id
como desempate determinístico. Conflitos id/URL precisam de revisão antes de
treinar. Contagens do snapshot são de anúncios, não garantia de imóveis únicos.
Mesmo logradouro (sem o número, que algumas fontes omitem), área e quartos entre fontes
sinalizam possível duplicata, sem fusão automática, e recebem o mesmo `grupo_imovel`.
Ausências não geram correspondência.

aluguel_m2 exige aluguel e área positivos. densidade_quartos usa quartos/área.
IPTU mensal é mantido; anual é dividido por 12; periodicidade desconhecida
mantém custo total ausente. idade exige ano_construcao e data_coleta válidos.
IQR usa 1,5 vezes a amplitude interquartil com ao menos quatro observações e
amplitude positiva; sinaliza extremos sem excluir anúncios.

Elegibilidade preliminar: tipo Casa, finalidade Aluguel ou Locação, aluguel
positivo, bairro ou coordenadas globalmente válidas. Sem coluna uso, assume
residencial para Casa; uso comercial explícito é excluído. A marca não autoriza
treinamento: município, identidades e cobertura ainda precisam ser validados.
Latitude [-90,90] e longitude [-180,180] são apenas verificações globais.
Nenhum centroide ou ponto aproximado é promovido a coordenada exata.

## Bairros oficiais
Com `analyze --bairros`, a base recebe `bairro_oficial` (um dos 16 bairros da malha do Censo 2022 do IBGE),
`bairro_metodo` e `bairro_conflito`. Coordenada exata dentro de um bairro (tolerância de 300 m) define o bairro
(`poligono`); sem coordenada exata vale o nome declarado, quando for oficial após remover acento, caixa e pontuação
(`nome`); nomes não oficiais usam o polígono da coordenada aproximada (`poligono_aproximado`).
Nome oficial e polígono discordantes geram `bairro_divergente` em issues.csv. A coluna `bairro` original é preservada.
Tabelas regionais e `regioes` do quality.json passam a usar `bairro_oficial`.
