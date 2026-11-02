# -*- coding: utf-8 -*-
"""
Esquema del Data Mart leído de INFORMATION_SCHEMA (siempre coincide con la BD real)
y diagrama estrella en formato DOT para st.graphviz_chart.
"""

from html import escape

import pandas as pd

TABLA_HECHOS = "FactVuelos"
# Columnas del diagrama (de arriba hacia abajo); una dimensión nueva que no esté aquí va a la derecha
DIM_IZQUIERDA = ["DimFecha", "DimHorario", "DimEstadoVuelo", "DimRangoDemora"]
DIM_DERECHA = ["DimAeropuerto", "DimRuta", "DimCausaDemora", "DimCausaCancelacion"]
DEGENERADAS = ["numero_vuelo", "matricula"]  # dimensiones degeneradas que sí se muestran en el diagrama

SQL_COLUMNAS = """
    SELECT c.TABLE_NAME AS tabla, c.COLUMN_NAME AS columna, c.ORDINAL_POSITION AS orden,
           c.DATA_TYPE AS tipo, c.CHARACTER_MAXIMUM_LENGTH AS largo,
           c.NUMERIC_PRECISION AS precision_num, c.NUMERIC_SCALE AS escala, c.IS_NULLABLE AS nulo,
           CASE WHEN pk.COLUMN_NAME IS NOT NULL THEN 1 ELSE 0 END AS es_pk,
           fk.tabla_ref
    FROM INFORMATION_SCHEMA.COLUMNS c
    JOIN INFORMATION_SCHEMA.TABLES t
         ON t.TABLE_SCHEMA = c.TABLE_SCHEMA AND t.TABLE_NAME = c.TABLE_NAME AND t.TABLE_TYPE = 'BASE TABLE'
    LEFT JOIN (SELECT k.TABLE_NAME, k.COLUMN_NAME
               FROM INFORMATION_SCHEMA.TABLE_CONSTRAINTS tc
               JOIN INFORMATION_SCHEMA.KEY_COLUMN_USAGE k ON k.CONSTRAINT_NAME = tc.CONSTRAINT_NAME
               WHERE tc.CONSTRAINT_TYPE = 'PRIMARY KEY') pk
         ON pk.TABLE_NAME = c.TABLE_NAME AND pk.COLUMN_NAME = c.COLUMN_NAME
    LEFT JOIN (SELECT k.TABLE_NAME, k.COLUMN_NAME, kr.TABLE_NAME AS tabla_ref
               FROM INFORMATION_SCHEMA.REFERENTIAL_CONSTRAINTS rc
               JOIN INFORMATION_SCHEMA.KEY_COLUMN_USAGE k  ON k.CONSTRAINT_NAME = rc.CONSTRAINT_NAME
               JOIN INFORMATION_SCHEMA.KEY_COLUMN_USAGE kr ON kr.CONSTRAINT_NAME = rc.UNIQUE_CONSTRAINT_NAME) fk
         ON fk.TABLE_NAME = c.TABLE_NAME AND fk.COLUMN_NAME = c.COLUMN_NAME
    WHERE c.TABLE_SCHEMA = 'dbo'
    ORDER BY c.TABLE_NAME, c.ORDINAL_POSITION
"""


def tipo_legible(fila):
    """Tipo de dato como en el DDL: nvarchar(60), decimal(9,6), int…"""
    if pd.notna(fila["largo"]):
        return f"{fila['tipo']}({'max' if fila['largo'] == -1 else int(fila['largo'])})"
    if fila["tipo"] == "decimal":
        return f"decimal({int(fila['precision_num'])},{int(fila['escala'])})"
    return fila["tipo"]


def clave(fila):
    """'PK', 'FK' (o 'PK, FK') según las restricciones de la columna."""
    marcas = ["PK"] * bool(fila["es_pk"]) + ["FK"] * pd.notna(fila["tabla_ref"])
    return ", ".join(marcas)


def preparar_columnas(df):
    """Agrega las columnas 'tipo_dato' y 'clave' al resultado de SQL_COLUMNAS."""
    df = df.copy()
    df["tipo_dato"] = df.apply(tipo_legible, axis=1)
    df["clave"] = df.apply(clave, axis=1)
    return df


def tabla_referencia(df, tabla):
    """Columnas de una tabla para mostrar en un dataframe (nombre, tipo, nulo, clave)."""
    t = df[df["tabla"] == tabla].sort_values("orden")
    return pd.DataFrame({
        "Columna": t["columna"],
        "Tipo": t["tipo_dato"],
        "Nulos": t["nulo"].map({"YES": "Sí", "NO": "No"}),
        "Clave": [f"FK → {r}" if pd.notna(r) else ("PK" if pk else "")
                  for pk, r in zip(t["es_pk"], t["tabla_ref"])],
    })


def _texto(texto, color):
    """Texto con color; Graphviz no acepta <font> vacío (invalida toda la etiqueta), así que se omite."""
    return f'<font color="{color}">{escape(texto)}</font>' if texto else " "


def _fila(c):
    """Fila de una columna: nombre, tipo y PK/FK.

    Tiene dos puertos: <col>_w en la primera celda (borde izquierdo de la tabla) y <col>_e en la
    última (borde derecho), para que las flechas entren y salgan por el costado sin cruzar la tabla.
    """
    col = escape(c["columna"])
    nombre = f"<b>{col}</b>" if c["es_pk"] else col
    return (f'<tr><td align="left" port="{col}_w">{nombre}</td>'
            f'<td align="left">{_texto(c["tipo_dato"], "#555555")}</td>'
            f'<td align="left" port="{col}_e">{_texto(c["clave"], "#b5541c")}</td></tr>')


def _nodo(nombre, filas_html, es_hechos):
    """Nodo con forma de tabla HTML: encabezado de color + filas."""
    color = "#2a78d6" if es_hechos else "#5b6770"
    encabezado = (f'<tr><td colspan="3" bgcolor="{color}"><font color="white"><b>{escape(nombre)}</b>'
                  "</font></td></tr>")
    tabla = ('<table border="0" cellborder="1" cellspacing="0" cellpadding="3" bgcolor="white" '
             f'color="#999999">{encabezado}{"".join(filas_html)}</table>')
    return f'  "{nombre}" [label=<{tabla}>];'


def _filas_hechos(hechos, fks):
    """Filas de FactVuelos: PK, FK (izquierda y luego derecha, sin cruces), degeneradas y resumen de medidas."""
    pk = hechos[hechos["es_pk"] == 1]
    degeneradas = hechos[hechos["columna"].isin(DEGENERADAS)]
    resto = len(hechos) - len(pk) - len(fks) - len(degeneradas)
    filas = [_fila(c) for _, c in pd.concat([pk, fks, degeneradas]).iterrows()]
    filas.append(f'<tr><td colspan="3" align="left"><i>+ {resto} medidas y campos de control '
                 "(ver tabla abajo)</i></td></tr>")
    return filas


def _etiqueta_rol(atributo, rol, dim, roles, angulos):
    """Etiqueta del rol (origen/destino) junto a la dimensión; '' si la dimensión tiene un solo rol."""
    if roles[dim] < 2:
        return ""
    angulo = -35 if angulos.get(dim, 0) % 2 == 0 else 35  # el primer rol (origen) arriba, el segundo abajo
    angulos[dim] = angulos.get(dim, 0) + 1
    return f', {atributo}="{rol}", labelangle={angulo}, labeldistance=2.2'


def diagrama_estrella(df):
    """Texto DOT del modelo estrella en 3 columnas: dimensiones | FactVuelos | dimensiones.

    Las flechas salen del costado de cada tabla (puertos con :e / :w), así nunca cruzan una tabla.
    """
    hechos = df[df["tabla"] == TABLA_HECHOS].sort_values("orden")
    fks = hechos[hechos["tabla_ref"].notna()].copy()
    fks["lado"] = fks["tabla_ref"].map(lambda t: "izq" if t in DIM_IZQUIERDA else "der")
    # orden de las FK = orden vertical de las dimensiones en su columna (evita que las flechas se crucen)
    posicion = {t: i for i, t in enumerate(DIM_IZQUIERDA + DIM_DERECHA)}
    fks["pos"] = fks["tabla_ref"].map(lambda t: posicion.get(t, len(posicion)))
    fks = fks.sort_values(["lado", "pos", "orden"], ascending=[False, True, True])  # "izq" antes que "der"

    dims = [t for t in df["tabla"].unique() if t != TABLA_HECHOS]
    izquierda = [t for t in DIM_IZQUIERDA if t in dims]
    derecha = [t for t in DIM_DERECHA if t in dims] + sorted(t for t in dims if t not in posicion)

    lineas = [
        "digraph estrella {",
        "  # fondo blanco por defecto: se lee igual en tema claro u oscuro",
        "  rankdir=LR; splines=spline; nodesep=0.25; ranksep=1.1; newrank=true;",
        '  node [shape=plain, fontname="Helvetica", fontsize=10];',
        '  edge [color="#888888", dir=both, fontname="Helvetica", fontsize=9, fontcolor="#b5541c"];',
        _nodo(TABLA_HECHOS, _filas_hechos(hechos, fks), es_hechos=True),
    ]
    for tabla in izquierda + derecha:
        columnas = df[df["tabla"] == tabla].sort_values("orden")
        lineas.append(_nodo(tabla, [_fila(c) for _, c in columnas.iterrows()], es_hechos=False))

    # columnas forzadas: cada lado en el mismo rango, en orden fijo de arriba hacia abajo (flechas invisibles)
    for lado in (izquierda, derecha):
        if lado:
            lineas.append(f'  {{ rank=same; {"; ".join(f"{chr(34)}{t}{chr(34)}" for t in lado)}; }}')
            if len(lado) > 1:
                lineas.append(f'  {" -> ".join(f"{chr(34)}{t}{chr(34)}" for t in lado)} [style=invis];')

    pk = df[df["es_pk"] == 1].groupby("tabla")["columna"].first()
    roles = fks["tabla_ref"].value_counts()
    angulos = {}  # varias flechas a la misma dimensión: etiquetas a ángulos opuestos para que no se tapen
    for _, fk in fks.iterrows():
        dim, col = fk["tabla_ref"], fk["columna"]
        # dimensión role-playing (DimAeropuerto): el rol se escribe junto a la dimensión, no sobre los hechos
        rol = col.replace("sk_", "")
        if fk["lado"] == "izq":   # dimensión → hechos: 1 en la dimensión, muchos (pata de gallo) en los hechos
            etiqueta = _etiqueta_rol("taillabel", rol, dim, roles, angulos)
            lineas.append(f'  "{dim}":"{pk[dim]}_e":e -> "{TABLA_HECHOS}":"{col}_w":w '
                          f'[arrowtail=tee, arrowhead=crow{etiqueta}];')
        else:                     # hechos → dimensión
            etiqueta = _etiqueta_rol("headlabel", rol, dim, roles, angulos)
            lineas.append(f'  "{TABLA_HECHOS}":"{col}_e":e -> "{dim}":"{pk[dim]}_w":w '
                          f'[arrowtail=crow, arrowhead=tee{etiqueta}];')
    lineas.append("}")
    return "\n".join(lineas)
