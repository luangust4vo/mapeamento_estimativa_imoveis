---
name: novo-coletor
description: Adicionar ou corrigir um coletor (scraper) de anúncios de uma imobiliária de Ponta Grossa em src/imoveis_pg/coleta/. Use ao incluir uma nova fonte de dados, quando um coletor quebrar por mudança de layout do site ou ao refazer uma coleta real.
---

# Novo coletor de anúncios

Cada fonte é um módulo em `src/imoveis_pg/coleta/` registrado em `SOURCES` (`coleta/__init__.py`).
O modelo de referência é `coleta/torreblanca.py`; os testes de referência estão em `tests/test_coleta.py`.

## 1. Investigar a fonte (antes de escrever código)
Use o cliente do projeto ou `curl -A "imoveis-pg/0.1 (projeto academico IFPR; coleta de anuncios publicos)"`,
com pelo menos 2 s entre requisições, e salve as páginas de investigação no scratchpad, nunca no repositório.
- Ler `/robots.txt`; se a listagem ou a página do anúncio estiver bloqueada, **parar** e avisar o usuário.
- Procurar termos de uso (links com termo, privacidade, política) e registrar o que foi encontrado em `docs/coleta.md`.
- Encontrar a URL de busca de **casas para locação em Ponta Grossa** e o parâmetro de paginação.
- Verificar se os dados vêm estruturados: `__NEXT_DATA__` (Next.js), JSON-LD (`application/ld+json`),
  API JSON chamada pela página ou só HTML. Prefira sempre a fonte estruturada.
- Conferir se a listagem já traz os atributos; visitar páginas de detalhe só se for indispensável.
- Anotar quais campos existem: coordenadas? Só CEP/rua (exigirá geocodificação, `precisao_localizacao=aproximada`)?

## 2. Implementar
O coletor deve expor `FONTE`, `BASE_URL`, `search_url(page)`, `to_record(item, collected_on)` e
`collect(client, *, collected_on=None, max_pages=None)`, devolvendo `CollectionResult`. Pode ser um módulo
(`torreblanca.py`) ou uma instância (`plataforma.PlatformSource`, reaproveitada por sites da mesma plataforma:
se o novo site usar `__NEXT_DATA__` com `attributes` `{key, label, value}`, basta registrar uma nova instância
e, se preciso, acrescentar apelidos de chaves em `plataforma.ALIASES`).
- Toda requisição passa por `PoliteClient.get` (robots, intervalo, retentativas e cache). Nunca use `requests`/`urllib` direto.
- `to_record` produz as 20 colunas de `data.COLUMNS` mais extras; números via `contrato.format_number`
  (vírgula decimal, sem milhar). **Ausência fica vazia, nunca zero.**
- Copie apenas campos do imóvel (lista explícita). **Nunca** copie corretor, proprietário, telefone, e-mail,
  descrição livre ou fotos.
- Descartar e contar em `skipped` os anúncios fora de Ponta Grossa, sem id ou repetidos.
- Não presuma o que a fonte não informa (ex.: periodicidade do IPTU); documente a lacuna.
- Layout inesperado deve gerar `ColetaError` com mensagem clara, não registros vazios.
- Nomes de colunas extras não podem terminar em `_original` nem usar os reservados de `data.RESERVED`.
- Sem coordenadas no anúncio: deixe `latitude`/`longitude` vazios e preencha `logradouro`, `numero`, `cep` e
  `bairro`. O `collect` geocodifica com o CNEFE (`geo/cnefe.py`). **Não use Nominatim, Photon, Overpass ou
  BrasilAPI:** todos bloqueiam a busca no `robots.txt`.

## 3. Testar (sem rede)
Em `tests/test_coleta_<fonte>.py`, com páginas fictícias que imitam a estrutura real (reaproveite `FakeSite`,
`client` e o padrão de `tests/test_coleta.py`), cubra no mínimo:
mapeamento dos campos, descarte de dados pessoais, ausências vazias, cidade diferente rejeitada, paginação e
deduplicação, mudança de layout, e o CSV gerado passando por `load_listings` sem issues.
Rode `python -m pytest -q` com a `.venv` ativa.

## 4. Coletar e validar
```bash
python -m imoveis_pg collect <fonte> --output data/<fonte>_AAAA-MM-DD.csv
python -m imoveis_pg analyze data/<fonte>_AAAA-MM-DD.csv --output reports/<fonte>-AAAA-MM-DD
```
- Confirme que `anuncios + descartados` bate com `total_declarado_pelo_site` no manifesto.
- Veja `geocodificacao.metodos` no manifesto: muitos `bairro` ou `nao_localizado` pedem investigação
  (grafia de bairro, CEP genérico, abreviação de rua não expandida).
- Una as fontes com `python -m imoveis_pg merge data/*_AAAA-MM-DD.csv --output data/base_AAAA-MM-DD.csv`
  e rode o `analyze` também na base unificada, onde aparecem as duplicatas entre fontes.
- Revise `issues.csv`, as ausências do `quality.json` e o gráfico `eda/inspecao_espacial.png`
  (os pontos devem formar a mancha urbana de Ponta Grossa, lat ≈ -25,02 a -25,17; lon ≈ -50,09 a -50,24).
- Atualize a tabela de fontes, o mapeamento de campos e as limitações em `docs/coleta.md`.
- Commits em inglês no padrão Conventional Commits (`feat(coleta): ...`). Nunca versione nada de `data/`.
