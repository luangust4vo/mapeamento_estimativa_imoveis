# Coleta automatizada de anúncios

## Fontes
| Coletor | Imobiliária | Situação | Localização |
|---|---|---|---|
| `torreblanca` | [Torre Blanca Imóveis](https://torreblanca.com.br) | Implementado | Lat/lon do anúncio |
| — | Portal Dez, Granada, Vila Nova | Planejado (mesma plataforma) | Rua + CEP, exige geocodificação |
| — | Kikina, Conceito, Tavarnaro | Avaliar | A verificar |

Verificação em 2026-11-09: nenhuma das fontes bloqueia páginas de anúncios no
`robots.txt`, e não foi encontrada página de termos de uso no site da Torre Blanca.
Repita essa verificação antes de cada nova coleta.

## Executar
```bash
python -m imoveis_pg collect torreblanca --output data/torreblanca_AAAA-MM-DD.csv
python -m imoveis_pg analyze data/torreblanca_AAAA-MM-DD.csv --output reports/torreblanca-AAAA-MM-DD
```
Gera o CSV no [contrato de dados](dados.md) e um `.manifest.json` com a fonte, a data,
o user-agent, o número de requisições e os anúncios descartados.
Opções: `--delay` (padrão 3 s, mínimo 1), `--max-pages`, `--cache-dir` e `--offline`.

## Conduta
- Requisições sequenciais, com intervalo mínimo e user-agent que identifica o projeto acadêmico.
- `robots.txt` é consultado antes da primeira página de cada site. Retentativas só para 429/5xx, com espera crescente.
- Só a listagem pública é visitada; a Torre Blanca já traz os atributos completos (6 páginas para 115 casas).
- As páginas brutas ficam em `data/raw/FONTE/`, com `index.jsonl` (URL e horário). Reexecutar usa o cache
  em vez de acessar o site; `--offline` garante que nenhuma requisição seja feita.
- **Privacidade:** nome e ID do corretor, descrição livre (pode conter telefones), fotos e contatos
  não são copiados para o CSV. As páginas brutas os contêm e por isso nunca são versionadas (`data/*` no `.gitignore`).
  O endereço fica apenas na base local, para detectar duplicatas; mapas públicos devem mostrar só bairro ou posição aproximada.

## Mapeamento da Torre Blanca
| Contrato | Campo do site | Observação |
|---|---|---|
| id, url | `reference` | URL `/imovel/{reference}` |
| tipo / subtipo | `tipo` / `subtipo` | "Casa/Sobrado" vira `Casa`; `subtipo` guarda Casa ou Sobrado |
| finalidade / operacoes | `operacao` | Anúncio com venda e locação vira `Locação`, com `preco` preenchido |
| uso | `finalidade` | residencial/comercial; comercial fica fora da elegibilidade |
| area_m2 / area_total_m2 | `area_util` / `area_total` | |
| quartos, suites, banheiros, vagas | `dormitorios`, `suites`, `banheiros`, `vagas_garagem` | Ausência não vira zero |
| aluguel, preco, condominio, iptu | `valor_locacao`, `valor_venda`, `valor_condominio`, `valor_iptu` | |
| latitude, longitude | idem | `precisao_localizacao=exata`, declarada pelo site, não verificada |
| publicado_em, atualizado_em | `created_at`, `source_updated_at` | Úteis para análise temporal |

## Limitações conhecidas (coleta de 2026-11-09)
- **IPTU sem periodicidade:** o site não informa. A mediana de IPTU/aluguel é cerca de 4,6%, o que sugere valor
  mensal, mas isso não foi confirmado; por isso `custo_mensal_total` fica ausente.
- **Suítes:** ausentes em 76 de 115 anúncios; provavelmente significa zero, mas não é presumido.
- O filtro "Casa/Sobrado" do site inclui 20 imóveis de uso comercial.
- Uma única imobiliária não representa o mercado municipal; há concentração em alguns bairros.
