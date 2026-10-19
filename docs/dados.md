# Contrato de dados
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
nomes aproximados. Não existe imputação, geocodificação ou certificação municipal nesta fase.
