# -*- coding: utf-8 -*-
"""Pruebas del diagrama estrella (app/esquema.py) con un esquema pequeño de ejemplo."""

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "app"))

from esquema import diagrama_estrella, preparar_columnas, tabla_referencia  # noqa: E402

NAN = float("nan")
FILAS = [  # tabla, columna, orden, tipo, largo, precision, escala, nulo, es_pk, tabla_ref
    ("FactVuelos", "id_vuelo", 1, "bigint", NAN, 19, 0, "NO", 1, None),
    ("FactVuelos", "sk_origen", 2, "int", NAN, 10, 0, "NO", 0, "DimAeropuerto"),
    ("FactVuelos", "sk_destino", 3, "int", NAN, 10, 0, "NO", 0, "DimAeropuerto"),
    ("FactVuelos", "sk_fecha", 4, "int", NAN, 10, 0, "NO", 0, "DimFecha"),
    ("FactVuelos", "matricula", 5, "varchar", 10, NAN, NAN, "YES", 0, None),
    ("FactVuelos", "es_puntual", 6, "tinyint", NAN, 3, 0, "NO", 0, None),
    ("FactVuelos", "taxi_out_min", 7, "int", NAN, 10, 0, "YES", 0, None),
    ("DimAeropuerto", "sk_aeropuerto", 1, "int", NAN, 10, 0, "NO", 1, None),
    ("DimAeropuerto", "latitud", 2, "decimal", NAN, 9, 6, "YES", 0, None),
    ("DimFecha", "sk_fecha", 1, "int", NAN, 10, 0, "NO", 1, None),
]
COLUMNAS = ["tabla", "columna", "orden", "tipo", "largo", "precision_num", "escala", "nulo", "es_pk", "tabla_ref"]


def esquema_ejemplo():
    return preparar_columnas(pd.DataFrame(FILAS, columns=COLUMNAS))


def test_tipos_y_claves():
    df = esquema_ejemplo().set_index(["tabla", "columna"])
    assert df.loc[("FactVuelos", "matricula"), "tipo_dato"] == "varchar(10)"
    assert df.loc[("DimAeropuerto", "latitud"), "tipo_dato"] == "decimal(9,6)"
    assert df.loc[("FactVuelos", "id_vuelo"), "clave"] == "PK"
    assert df.loc[("FactVuelos", "sk_origen"), "clave"] == "FK"


def test_diagrama_un_nodo_por_tabla_y_una_flecha_por_fk():
    dot = diagrama_estrella(esquema_ejemplo())
    assert dot.count("[label=<") == 3
    assert dot.count("[arrowtail=") == 3     # una flecha por FK (sin contar las invisibles)


def test_flechas_entran_y_salen_por_el_costado():
    """Izquierda: dimensión (borde este) → hechos (borde oeste). Derecha: hechos (este) → dimensión (oeste)."""
    dot = diagrama_estrella(esquema_ejemplo())
    assert '"DimFecha":"sk_fecha_e":e -> "FactVuelos":"sk_fecha_w":w' in dot
    assert '"FactVuelos":"sk_origen_e":e -> "DimAeropuerto":"sk_aeropuerto_w":w' in dot


def test_columnas_y_roles():
    dot = diagrama_estrella(esquema_ejemplo())
    assert "rankdir=LR" in dot
    assert '{ rank=same; "DimFecha"; }' in dot
    assert '{ rank=same; "DimAeropuerto"; }' in dot
    assert 'headlabel="origen"' in dot and 'headlabel="destino"' in dot   # rol junto a la dimensión
    assert "labelangle=-35" in dot and "labelangle=35" in dot             # etiquetas separadas


def test_hechos_compactos_y_fk_ordenadas_por_lado():
    import re
    dot = diagrama_estrella(esquema_ejemplo())
    nodo_hechos = next(linea for linea in dot.splitlines() if linea.startswith('  "FactVuelos" [label=<'))
    filas = re.findall(r'port="(\w+)_w"', nodo_hechos)
    # PK, FK de la izquierda (DimFecha) antes que las de la derecha (DimAeropuerto), luego la degenerada
    assert filas == ["id_vuelo", "sk_fecha", "sk_origen", "sk_destino", "matricula"]
    assert "+ 2 medidas y campos de control" in nodo_hechos   # es_puntual y taxi_out_min colapsadas


def test_diagrama_sin_font_vacio():
    """Un <font></font> vacío hace que Graphviz dibuje el nodo con tamaño cero."""
    import re
    assert not re.search(r"<font[^>]*></font>", diagrama_estrella(esquema_ejemplo()))


def test_tabla_referencia():
    t = tabla_referencia(esquema_ejemplo(), "FactVuelos")
    assert list(t.columns) == ["Columna", "Tipo", "Nulos", "Clave"]
    assert t.iloc[1]["Clave"] == "FK → DimAeropuerto"
    assert t.iloc[4]["Nulos"] == "Sí"
