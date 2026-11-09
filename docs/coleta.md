# Coleta automatizada de anúncios

## Fontes
| Coletor | Imobiliária | Situação | Localização |
|---|---|---|---|
| `torreblanca` | [Torre Blanca Imóveis](https://torreblanca.com.br) | Implementado | Lat/lon do anúncio |
| `portaldez` | [Portal Dez Imóveis](https://portaldezimoveis.com.br) | Implementado | Geocodificada (CNEFE) |
| `granada` | [Imobiliária Granada](https://imobiliariagranada.com.br) | Implementado | Geocodificada (CNEFE) |
| `vilanova` | [Vila Nova Imobiliária](https://vilanovaimoveis.com.br) | Implementado | Geocodificada (CNEFE) |
| — | Kikina, Conceito, Tavarnaro | Avaliar | A verificar |

Verificação em 2026-11-09: nenhuma das fontes bloqueia páginas de anúncios no
`robots.txt` (Portal Dez, Granada, Vila Nova e Torre Blanca respondem 404, ou seja, sem restrições),
e não foi encontrada página de termos de uso nesses sites. Repita essa verificação antes de cada nova coleta.

## Executar
```bash
python -m imoveis_pg collect torreblanca --output data/torreblanca_AAAA-MM-DD.csv
python -m imoveis_pg collect portaldez   --output data/portaldez_AAAA-MM-DD.csv
python -m imoveis_pg collect granada     --output data/granada_AAAA-MM-DD.csv
python -m imoveis_pg collect vilanova    --output data/vilanova_AAAA-MM-DD.csv
python -m imoveis_pg merge data/*_AAAA-MM-DD.csv --output data/base_AAAA-MM-DD.csv
python -m imoveis_pg analyze data/base_AAAA-MM-DD.csv --output reports/base-AAAA-MM-DD
```
Cada coleta gera o CSV no [contrato de dados](dados.md) e um `.manifest.json` com a fonte, a data,
o user-agent, o número de requisições, os anúncios descartados e os métodos de geocodificação.
Opções: `--delay` (padrão 3 s, mínimo 1), `--max-pages`, `--cache-dir`, `--offline` e `--cnefe`.
`merge` só concatena os arquivos; a deduplicação entre fontes é sinalizada pelo `analyze`.

## Conduta
- Requisições sequenciais, com intervalo mínimo e user-agent que identifica o projeto acadêmico.
- `robots.txt` é consultado antes da primeira página de cada site. Retentativas só para 429/5xx, com espera crescente.
- Só a listagem pública é visitada; ela já traz os atributos completos (Torre Blanca: 6 páginas para 115 casas;
  Portal Dez: 24 páginas para 473 locações de todos os tipos, das quais 109 casas).
- As páginas brutas ficam em `data/raw/FONTE/`, com `index.jsonl` (URL e horário). Reexecutar usa o cache
  em vez de acessar o site; `--offline` garante que nenhuma requisição seja feita.
- **Privacidade:** corretor/agente, cliente, descrição livre (pode conter telefones), fotos e contatos
  não são copiados para o CSV. As páginas brutas os contêm e por isso nunca são versionadas (`data/*` no `.gitignore`).
  O endereço fica apenas na base local, para detectar duplicatas e geocodificar; mapas públicos devem mostrar só
  bairro ou posição aproximada.

## Geocodificação (CNEFE 2022)
Portal Dez, Granada e Vila Nova não publicam coordenadas. Os serviços de geocodificação on-line avaliados
(Nominatim, Photon, Overpass, BrasilAPI) bloqueiam `/search` ou `/api` no `robots.txt`, então a geocodificação usa
o **Cadastro Nacional de Endereços para Fins Estatísticos (CNEFE) do Censo 2022**, dado aberto do IBGE com
178.567 endereços de Ponta Grossa (CEP, logradouro, número e coordenadas). O arquivo
`4119905_PONTA_GROSSA.zip` (4,1 MB, SHA-256 `3524d466…a0d1`) é baixado uma vez para `data/raw/ibge/`
pelo próprio `collect`, e a busca é local.

Cascata, do mais ao menos preciso (`origem_localizacao` registra o método e o número de endereços usados):
1. `numero`: logradouro + número exato (dentro do CEP, se houver) → `precisao_localizacao=exata`.
2. `numero_proximo`: número mais próximo no mesmo logradouro, até 100 de diferença.
3. `rua_cep`: mediana dos endereços do logradouro dentro do CEP.
4. `cep`: mediana dos endereços do CEP.
5. `rua`: mediana do logradouro na cidade toda.
6. `bairro`: mediana da localidade do CNEFE com o nome do bairro.

Do 2 em diante a precisão é `aproximada`. Só são usados endereços com coordenada do próprio endereço
(`NV_GEO_COORD` 1 a 3). Logradouros são comparados sem acento, pontuação e tipo (Rua/Av.), e abreviações
de títulos são expandidas (Dr. → Doutor). Não há correspondência aproximada de nomes: uma rua ausente do
CNEFE cai para CEP ou bairro em vez de ser trocada por outra parecida.
CEPs com sufixo 900–999 (agências, caixas postais e grandes usuários dos Correios) são ignorados: o Portal Dez usa
`84001970` como CEP genérico em anúncios de bairros diferentes.

**Erro medido** geocodificando os 115 endereços da Torre Blanca e comparando com as coordenadas do anúncio:

| Método | n | Distância mediana | p90 |
|---|---|---|---|
| numero | 73 | 74 m | 397 m |
| numero_proximo | 16 | 194 m | 1,0 km |
| cep | 3 | 200 m | 360 m |
| rua_cep | 8 | 522 m | 1,6 km |
| bairro | 15 | 2,9 km | 4,9 km |

Parte da diferença pode vir da própria coordenada do anúncio, que também não é verificada.

## Mapeamento dos campos
| Contrato | Torre Blanca | Plataforma (Portal Dez / Granada, Vila Nova) | Observação |
|---|---|---|---|
| id, url | `reference` | `reference` | URL `/imovel/{reference}` |
| tipo / subtipo | `tipo` / `subtipo` | `type` | Casa, Sobrado e Casa/Sobrado em Condomínio viram `Casa`; o original fica em `subtipo` |
| finalidade | `operacao` | `operation` | Coleta somente locações |
| uso | `finalidade` | `finalidade` / `objective` | residencial/comercial; comercial fica fora da elegibilidade |
| area_m2 / area_total_m2 | `area_util` / `area_total` | `unit-area`, `util-area`, `private-area` / `total-area` | |
| quartos, suites, banheiros, vagas | `dormitorios`, `suites`, `banheiros`, `vagas_garagem` | `bedrooms`, `suites`, `bathrooms`, `garage` | Ausência não vira zero |
| aluguel, condominio, iptu | `valor_locacao`, `valor_condominio`, `valor_iptu` | `rent-value`, `condominio` / `condominium-price`, `iptu` / `property-tax` | IPTU textual ("a confirmar", "Incluso") vai para `iptu_texto` |
| endereço | logradouro + número | `street` / `address-street` + `number` / `address-number` | Também em `logradouro`, `numero`, `cep` |
| extras | `caracteristicas`, `publicado_em`, `atualizado_em` | idem, `seguro_incendio`, `fundo_conservacao`, `ano_construcao` | |

## Base de 2026-11-09
236 anúncios (Torre Blanca 115, Portal Dez 109, Vila Nova 8, Granada 4), dos quais **208 casas residenciais
elegíveis**, em 21 bairros. Aluguel mediano de R$ 2.050 (Q1 R$ 1.300; Q3 R$ 4.575). Localização: 113 exatas e
94 aproximadas, mais 1 anúncio sem localização.
Um mesmo imóvel apareceu no Portal Dez e na Torre Blanca e foi sinalizado como possível duplicata.

## Limitações conhecidas
- **IPTU sem periodicidade:** nenhum site informa. A razão IPTU/aluguel (mediana de 4,6% na Torre Blanca) sugere
  valor mensal, mas isso não foi confirmado; por isso `custo_mensal_total` fica ausente.
- **Ausências nos elegíveis:** suítes 68%, vagas 33%, banheiros 25%, área 22% e quartos 13%, maiores no Portal Dez.
  Provavelmente parte das suítes ausentes significa zero, mas nada é presumido; a imputação será decidida no treino.
- O filtro "Casa/Sobrado" da Torre Blanca inclui 20 imóveis de uso comercial, e o Portal Dez tem 8.
- Ruas e CEPs criados depois do Censo 2022 não estão no CNEFE e caem para bairro (erro de quilômetros).
- Um anúncio do Portal Dez (endereço genérico, CEP especial e bairro "Colônia Dona Luzia", quando o oficial é Luiza) ficou sem
  localização e permanece sinalizado.
- Os bairros vêm grafados como cada site escreve ("CARÁ-CARÁ", "Cará-Cará"); a unificação com os nomes oficiais ainda é necessária.
- Quatro imobiliárias não representam o mercado municipal; há concentração em alguns bairros.
