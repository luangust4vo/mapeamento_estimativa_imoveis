# Dados locais
Arquivos reais não são versionados automaticamente. Mantenha originais imutáveis
e registre fonte, URL, data de coleta, precisão geográfica e condições de acesso.
Consulte docs/dados.md para o contrato e docs/coleta.md para os coletores.
Páginas brutas ficam em data/raw/FONTE/ e contêm dados de corretores: não publique.
A fixture de tests/fixtures é inteiramente sintética.

## Base processada pública (versionada)
`data/processado/base_AAAA-MM-DD.csv` é a única parte de data/ no git. Ela é gerada por
`python -m imoveis_pg export-base data/base_AAAA-MM-DD.csv --output data/processado/base_AAAA-MM-DD.csv`
a partir de uma lista explícita de colunas permitidas:
- sem endereço, logradouro, número, CEP, valores originais nem dados pessoais;
- coordenadas arredondadas a 3 casas decimais (~100 m), o suficiente para mapas por bairro, mas não para
  localizar a casa;
- CSV UTF-8 com separador vírgula e decimal ponto (não é o contrato de entrada do `analyze`).

O `.manifest.json` ao lado registra os SHA-256 da entrada e da saída, as colunas e as regras aplicadas.
As colunas estão descritas em docs/dicionario.md. Os modelos usam a base local completa;
refazer os experimentos a partir da base pública dá resultados próximos, mas não idênticos.
