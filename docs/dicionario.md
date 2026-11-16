# Dicionário de dados

Todas as colunas usadas pelo projeto, da coleta ao app. As regras de importação (formatos aceitos, ausências e
diagnósticos) estão em [dados.md](dados.md). **Preenchimento** = fração de anúncios com valor na base unificada
de 2026-11-09 (236 anúncios); "—" quando não se aplica.

Convenções: valores em reais (BRL) por mês, salvo indicação; área em m²; coordenadas em graus WGS84; no CSV de
entrada o separador é `;` e o decimal é vírgula. **Ausência nunca vira zero.**

## 1. Contrato de entrada (20 colunas obrigatórias)
Toda base importada precisa ter estas colunas; as células podem ficar vazias.

| Coluna | Tipo | Descrição | Preenchimento |
|---|---|---|---|
| `id` | texto | Código do anúncio na fonte (ex.: `CA3386_TB`, `9431`) | 100% |
| `fonte` | texto | Imobiliária de origem | 100% |
| `url` | texto | Página pública do anúncio (rastreabilidade) | 100% |
| `data_coleta` | data | Dia da coleta (AAAA-MM-DD ou DD/MM/AAAA) | 100% |
| `endereco` | texto | Logradouro e, se houver, número. **Só na base local**; não aparece no app nem nos relatórios do modelo | 100% |
| `bairro` | texto | Bairro como a fonte escreve (sem correção) | 100% |
| `latitude`, `longitude` | número | Coordenada do anúncio ou geocodificada (ver `precisao_localizacao`) | 100% |
| `tipo` | texto | Tipo do imóvel; os coletores gravam `Casa` para casas e sobrados | 100% |
| `finalidade` | texto | `Locação` ou `Venda`; a base atual só tem locação | 100% |
| `area_m2` | número | Área útil, privativa ou construída da casa | 79% |
| `quartos` | inteiro | Dormitórios | 79% |
| `suites` | inteiro | Suítes. Nenhum anúncio informa zero: ausência costuma significar "sem suíte" | 31% |
| `banheiros` | inteiro | Banheiros | 78% |
| `vagas` | inteiro | Vagas de garagem. Nenhum anúncio informa zero | 67% |
| `aluguel` | número | Aluguel mensal anunciado (alvo da análise) | 100% |
| `preco` | número | Preço de venda, quando o imóvel também está à venda | 11% |
| `condominio` | número | Taxa de condomínio | 14% |
| `iptu` | número | IPTU informado; periodicidade desconhecida | 75% |
| `periodicidade_iptu` | texto | `mensal` ou `anual`; nenhuma fonte informa, por isso o custo mensal total fica ausente | 0% |

## 2. Colunas opcionais e extras dos coletores
São preservadas pela importação. O preenchimento varia bastante entre as fontes (ver [coleta.md](coleta.md)).

| Coluna | Tipo | Descrição | Preenchimento |
|---|---|---|---|
| `subtipo` | texto | Tipo original: `Casa`, `Sobrado` ou `Casa/Sobrado em Condomínio` | 100% |
| `uso` | texto | `residencial` ou `comercial`; comercial fica fora do modelo | 100%* |
| `precisao_localizacao` | texto | `exata` (coordenada do anúncio ou número exato no CNEFE) ou `aproximada` | 100% |
| `origem_localizacao` | texto | Origem da coordenada e método de geocodificação (ex.: `IBGE CNEFE 2022 (rua_cep, 30 endereços)`) | 100% |
| `cep` | texto | CEP com 8 dígitos | 100% |
| `logradouro`, `numero` | texto | Partes do endereço usadas na geocodificação (coletores sem coordenada) | 51% / 14% |
| `area_total_m2` | número | Área do terreno ou total | 55% |
| `caracteristicas` | texto | Itens declarados, separados por `\|` (ex.: `Piscina\|Churrasqueira`) | 86% |
| `em_condominio`, `mobiliado` | texto | `sim`/`nao` quando informado | 7% / 4% |
| `iptu_texto` | texto | IPTU não numérico (`a confirmar`, `incluso`) | 9% |
| `seguro_incendio`, `fundo_conservacao` | número | Custos mensais adicionais informados pelo Portal Dez, Granada e Vila Nova | 46% / 44% |
| `operacoes` | texto | Operações do anúncio na Torre Blanca (`Locação` ou `Venda\|Locação`) | 49% |
| `publicado_em`, `atualizado_em` | data e hora | Datas do anúncio na fonte | 100% |
| `ano_construcao` | inteiro | Ano de construção (reconhecido, mas nenhuma fonte informa hoje) | 0% |
| `sintetico` | texto | `sim` marca dados sintéticos de teste ou demonstração | — |

\* Um anúncio sem `uso` é presumido residencial, pela regra de elegibilidade.

Dados pessoais (corretor, cliente, telefones, e-mails), descrições livres e fotos **nunca** são copiados.

## 3. Colunas derivadas pela análise (`analyze`)
Criadas na importação e na auditoria; os nomes são reservados e não podem vir no CSV de entrada.

| Coluna | Descrição |
|---|---|
| `*_original` | Valor exatamente como recebido, para cada coluna de entrada |
| `linha`, `row_id` | Número do registro no CSV; SHA-256 do arquivo + número do registro |
| `bairro_normalizado` | Bairro sem acento, caixa e espaços repetidos |
| `bairro_oficial` | Um dos 16 bairros do IBGE (Censo 2022), com `--bairros` |
| `bairro_metodo` | `poligono`, `nome`, `poligono_aproximado` ou `nao_resolvido` |
| `bairro_conflito` | Nome declarado oficial diferente do polígono da coordenada |
| `entity_id` | Identidade do anúncio: fonte + id, senão URL, senão `row_id` |
| `duplicata_exata` | Linha repetida idêntica (mantida no histórico) |
| `candidato_duplicata` | Mesmo logradouro (sem número), área e quartos em fontes diferentes |
| `grupo_imovel` | Grupo compartilhado por possíveis duplicatas; usado na separação treino/teste |
| `coordenadas_validas` | Par de coordenadas presente e dentro dos limites globais |
| `aluguel_m2` | Aluguel ÷ área (exige ambos positivos). **Só analítico, nunca atributo do modelo** |
| `densidade_quartos` | Quartos ÷ área |
| `iptu_mensal` | IPTU mensal (anual ÷ 12), só com periodicidade conhecida |
| `custo_mensal_total` | Aluguel + condomínio + IPTU mensal, só com os três conhecidos. **Só analítico** |
| `idade` | Ano da coleta − ano de construção |
| `elegivel_preliminar` | Casa, locação, uso residencial, aluguel positivo e bairro ou coordenada |

## 4. Atributos dos modelos
| Atributo | Classificação | Agrupamento de perfis | Observação |
|---|---|---|---|
| `area_m2` | sim | log da área | |
| `quartos`, `banheiros` | sim | sim | |
| `suites` | sim (ausente + indicador) | `tem_suite` (ausente = 0) | |
| `vagas` | sim (ausente + indicador) | não | 33% ausente |
| `latitude`, `longitude` | sim | não | |
| `distancia_centro_km` | sim | não | Distância ao nó "Ponta Grossa" do OpenStreetMap (-25,0891685; -50,1601812) |
| `bairro_oficial` | sim (one-hot) | não | |
| `subtipo` | sim (`casa`, `sobrado`, `condominio`) | não | |
| `aluguel` | **alvo** (faixas por tercis do treino) | log do aluguel | |

Na classificação, a imputação (mediana + indicador), a padronização e o one-hot são ajustados só no treino.

## 5. Artefatos do app (`build-app`)
`anuncios.csv` traz as colunas `id`, `fonte`, `url`, `bairro_oficial`, `uso`, `subtipo`, `area_m2`, `quartos`,
`suites`, `banheiros`, `vagas`, `aluguel`, `aluguel_m2`, `latitude`, `longitude`, `precisao_localizacao`,
`data_coleta` e `distancia_centro_km`, **sem endereço**, mais:

| Coluna | Descrição |
|---|---|
| `elegivel` | Casa usada no modelo |
| `faixa_anunciada` | Faixa do aluguel anunciado (baixa ≤ R$ 1.500; média até R$ 3.800; alta acima) |
| `faixa_estimada` | Faixa prevista por um modelo que não viu o anúncio (validação cruzada agrupada) |
| `comparacao` | `dentro do padrão`, `acima do padrão` (anunciado acima do previsto) ou `abaixo do padrão` |
| `perfil` | Perfil do K-means: `1 · compacta e econômica`, `2 · familiar intermediária` ou `3 · ampla de alto padrão` |

## 6. Base processada pública (`export-base`)
`data/processado/base_2026-11-09.csv` (236 anúncios, 37 colunas) traz as colunas das seções 1 a 3 que não
identificam o imóvel: sem `endereco`, `logradouro`, `numero`, `cep` e `*_original`, e com `latitude` e
`longitude` arredondadas a 3 casas decimais (~100 m). Separador vírgula, decimal ponto.

## 7. Dados geográficos de referência (IBGE)
| Arquivo | Uso |
|---|---|
| `4119905_PONTA_GROSSA.zip` (CNEFE 2022) | 178.567 endereços com CEP, logradouro, número e coordenadas; geocodificação offline |
| `PR_bairros_CD2022.gpkg` (malha de bairros, Censo 2022) | Polígonos dos 16 bairros oficiais de Ponta Grossa |
