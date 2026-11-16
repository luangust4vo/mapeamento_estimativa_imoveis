"""Coletores de anúncios públicos de imobiliárias de Ponta Grossa."""
from . import plataforma, torreblanca

SOURCES = {
    "torreblanca": torreblanca,
    "portaldez": plataforma.PORTALDEZ,
    "granada": plataforma.GRANADA,
    "vilanova": plataforma.VILANOVA,
}
