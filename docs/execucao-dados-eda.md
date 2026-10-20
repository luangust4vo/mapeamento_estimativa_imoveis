# Execução da primeira entrega
Execução direta aprovada; branch codex/dados-eda, criada a partir de 56cda60.

## Implementação
- dc3a52e: importação rastreável e padronização CSV (16 testes).
- 80ca877: identidade, histórico, qualidade e derivados (27 testes acumulados).
- ac765c9: tabelas e gráficos de EDA (34 testes acumulados).
- 794567c: CLI, exportação e documentação (38 testes acumulados).

A demonstração usa oito anúncios sintéticos. Foram geradas cinco tabelas e seis
gráficos. Distribuições, comparação regional, correlação e inspeção espacial
foram inspecionadas visualmente. Nenhuma conclusão de mercado foi produzida.

## Revisão independente
Revisão somente de leitura do intervalo 56cda60..794567c encontrou:
- Importante: a marca sintética podia desaparecer quando a observação mais
  recente não tinha a marca. Corrigido no código para considerar toda a entrada
  e transmiti-la à EDA. O teste de regressão falhou antes da correção.
- Menor, adiado: valores monetários na ordem de 10^308 podem causar overflow
  nos derivados e interromper gráficos. Não são plausíveis no domínio; a
  limitação permanece registrada, sem prometer suporte a essas magnitudes.

A revisão não avaliou coleta, cobertura municipal, modelos ou UI porque são
entregas futuras. Compatibilidade foi validada apenas com as versões do ambiente
registradas em requirements-tested.txt; não foi testada cada versão permitida.

## Decisões de execução
- Dados reais e limites municipais continuam pendentes.
- Casa em locação presume uso residencial quando uso não estiver informado;
  uso comercial explícito é excluído da elegibilidade preliminar.
- CSV mantém localidade numérica explícita; não tenta adivinhar separadores.
- Contagens gerais incluem todas as finalidades; preços analisados usam locações.
- Gráficos mostram até 20 grupos para legibilidade; tabelas mantêm todos.
- A CLI usa subpasta eda para respeitar a interface de saída vazia da análise.
- Matplotlib mínimo 3.11 e versões instaladas registradas para reprodução.
- Revisão final, teste de regressão e execução completa precedem integração.

## Validação final (2026-10-20)
39 testes passaram em 79,34 s, incluindo a regressão do histórico sintético.
Também passaram git diff --check e pip check. Branch preservada para integração;
nenhum push ou merge executado.
