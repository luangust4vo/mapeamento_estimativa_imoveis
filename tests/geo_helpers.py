"""Malha de bairros fictícia (retângulos) no formato da malha do IBGE."""
from shapely.geometry import box


def bairros_frame():
    import geopandas as gpd

    rows = [  # nome, código, município, (lon_min, lat_min, lon_max, lat_max)
        ("Uvaranas", "4119905009", "4119905", (-50.13, -25.12, -50.09, -25.08)),
        ("Cara Cara", "4119905015", "4119905", (-50.13, -25.16, -50.11, -25.12)),
        ("Cara Cara", "4119905015", "4119905", (-50.11, -25.16, -50.09, -25.12)),  # multiparte
        ("Colônia Dona Luíza", "4119905002", "4119905", (-50.20, -25.12, -50.16, -25.08)),
        ("Centro", "4100000001", "4100000", (-50.13, -25.12, -50.09, -25.08)),  # outro município
    ]
    return gpd.GeoDataFrame(
        {"CD_MUN": [r[2] for r in rows], "CD_BAIRRO": [r[1] for r in rows], "NM_BAIRRO": [r[0] for r in rows]},
        geometry=[box(*r[3]) for r in rows], crs="EPSG:4674")


def write_bairros_gpkg(path):
    bairros_frame().to_file(path, driver="GPKG")
    return path
