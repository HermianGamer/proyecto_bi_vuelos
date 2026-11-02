# -*- coding: utf-8 -*-
"""
Acceso a datos del dashboard (VuelosDW) y filtros globales de la barra lateral.

Todas las consultas se ejecutan en vivo contra el Data Mart, siempre
parametrizadas (?) y agregadas en SQL. Nunca se generan datos de ejemplo.
"""

import sys
import threading
from datetime import date
from decimal import Decimal
from pathlib import Path

import pandas as pd
import pyodbc
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from conexion import (  # noqa: E402
    DB_DW, DB_EDITOR_PASSWORD, DB_EDITOR_USER, DB_LECTOR_PASSWORD, DB_LECTOR_USER, cadena_conexion,
)
import reglas  # noqa: E402

TIMEOUT_CONSULTA = 30  # segundos máximos por consulta de lectura

# Colores fijos por estado del vuelo (iguales en todas las páginas)
COLORES_ESTADO = {
    "A tiempo": "#2E9E5B",
    "Demorado": "#F2A900",
    "Cancelado": "#D64541",
    "Desviado": "#8C8C8C",
}
# Colores fijos por causa (paleta validada para daltonismo); el nombre coincide con DimCausaDemora
COLORES_CAUSA = {
    "Aerolínea": "#2a78d6",
    "Avión anterior retrasado": "#eb6834",
    "Control de tráfico aéreo": "#1baf7a",
    "Clima": "#6250d6",
    "Seguridad": "#e87ba4",
}
FRANJAS = ["Madrugada", "Mañana", "Tarde", "Noche"]
TIPOS_DISTANCIA = ["Corta", "Media", "Larga"]

# Tipo de día: categorías excluyentes (un feriado en sábado o domingo cuenta como Feriado)
CONDICION_TIPO_DIA = {
    "Laborable": "d.es_fin_semana = 0 AND d.es_feriado = 0",
    "Fin de semana": "d.es_fin_semana = 1 AND d.es_feriado = 0",
    "Feriado": "d.es_feriado = 1",
}

# FROM común para consultas sobre el hecho con los filtros globales
FROM_VUELOS = """
    FROM FactVuelos f
    JOIN DimFecha d       ON f.sk_fecha = d.sk_fecha
    JOIN DimAeropuerto o  ON f.sk_origen = o.sk_aeropuerto
    JOIN DimAeropuerto ds ON f.sk_destino = ds.sk_aeropuerto
    JOIN DimRuta r        ON f.sk_ruta = r.sk_ruta
    JOIN DimHorario h     ON f.sk_horario = h.sk_horario
"""

# Pasa las 5 columnas de minutos por causa a filas (codigo, minutos) para unirlas con DimCausaDemora
MINUTOS_POR_CAUSA = """
    CROSS APPLY (VALUES ('CAR', f.min_causa_aerolinea), ('WEA', f.min_causa_clima),
                        ('NAS', f.min_causa_trafico), ('SEC', f.min_causa_seguridad),
                        ('LAT', f.min_causa_avion_tardio)) AS m(codigo, minutos)
    JOIN DimCausaDemora c ON c.codigo = m.codigo
"""



def sql_temporada(columna_mes="d.mes"):
    """Expresión CASE de SQL con la temporada del mes, armada desde src/reglas.py (no se duplica la regla)."""
    meses = {}
    for mes, nombre in reglas.MESES_TEMPORADA.items():
        meses.setdefault(nombre, []).append(str(mes))
    casos = " ".join(f"WHEN {columna_mes} IN ({', '.join(m)}) THEN N'{nombre}'" for nombre, m in meses.items())
    return f"CASE {casos} ELSE N'{reglas.TEMPORADA_RESTO}' END"


_bloqueo = threading.Lock()  # conexiones compartidas: una consulta a la vez


# ------------------------------------------------------------------ Conexión ---
@st.cache_resource
def get_conexion_lector():
    """Conexión de solo lectura (app_lector) para las páginas y la consola SQL."""
    conn = pyodbc.connect(cadena_conexion(DB_DW, DB_LECTOR_USER, DB_LECTOR_PASSWORD))
    conn.timeout = TIMEOUT_CONSULTA
    return conn


@st.cache_resource
def get_conexion_editor():
    """Conexión con permisos de escritura (app_editor), solo para Gestión de vuelos."""
    return pyodbc.connect(cadena_conexion(DB_DW, DB_EDITOR_USER, DB_EDITOR_PASSWORD))


def es_error_de_conexion(error):
    """True si el error es de conexión (vale la pena reconectar), no de la consulta en sí."""
    return error.args and str(error.args[0]) in ("08S01", "08001", "08003", "08004", "HY000")


def _ejecutar_cursor(get_conexion, sql, params):
    """Ejecuta una consulta; si la conexión se cayó (p. ej. Azure en pausa), reconecta una vez."""
    for intento in range(2):
        try:
            cursor = get_conexion().cursor()
            cursor.execute(sql, params)
            return cursor
        except pyodbc.Error as e:
            if intento == 1 or not es_error_de_conexion(e):
                raise
            get_conexion.clear()


@st.cache_data(ttl=300, show_spinner="Consultando base de datos...")
def consultar(sql, params=()):
    """Ejecuta un SELECT parametrizado con app_lector y devuelve un DataFrame."""
    with _bloqueo:
        cursor = _ejecutar_cursor(get_conexion_lector, sql, tuple(params))
        columnas = [c[0] for c in cursor.description]
        filas = [tuple(f) for f in cursor.fetchall()]
    return _a_dataframe(filas, columnas)


def consultar_libre(sql, max_filas):
    """Ejecuta una consulta escrita por el usuario (consola SQL) con app_lector, sin caché.

    Devuelve (DataFrame con hasta max_filas filas, True si había más filas).
    """
    with _bloqueo:
        cursor = _ejecutar_cursor(get_conexion_lector, sql, ())
        if cursor.description is None:  # la sentencia no devolvió filas
            return pd.DataFrame(), False
        columnas = [c[0] or f"columna_{i + 1}" for i, c in enumerate(cursor.description)]
        filas = [tuple(f) for f in cursor.fetchmany(max_filas + 1)]
        cursor.cancel()  # no leer el resto de filas
    return _a_dataframe(filas[:max_filas], columnas), len(filas) > max_filas


def _a_dataframe(filas, columnas):
    """Convierte filas de pyodbc en DataFrame (DECIMAL de SQL Server → float)."""
    df = pd.DataFrame.from_records(filas, columns=columnas)
    for col in df.columns:
        if df[col].map(lambda v: isinstance(v, Decimal)).any():
            df[col] = df[col].astype(float)
    return df


def ejecutar(sql, params=()):
    """Ejecuta un INSERT/UPDATE/DELETE parametrizado con app_editor y limpia la caché."""
    with _bloqueo:
        cursor = _ejecutar_cursor(get_conexion_editor, sql, tuple(params))
        cursor.commit()
    st.cache_data.clear()


def ejecutar_transaccion(sentencias):
    """Ejecuta varias sentencias [(sql, params), ...] con app_editor: todas o ninguna."""
    with _bloqueo:
        prueba = _ejecutar_cursor(get_conexion_editor, "SELECT 1", ())  # reconecta si hace falta
        prueba.fetchall()
        conn = prueba.connection
        cursor = conn.cursor()
        try:
            for sql, params in sentencias:
                cursor.execute(sql, tuple(params))
            filas_afectadas = cursor.rowcount  # de la última sentencia
            conn.commit()
        except pyodbc.Error:
            conn.rollback()
            raise
    st.cache_data.clear()
    return filas_afectadas


def formato(numero, decimales=1):
    """Número con formato peruano: coma decimal y punto de miles."""
    texto = f"{numero:,.{decimales}f}"
    return texto.replace(",", "X").replace(".", ",").replace("X", ".")


def mostrar_error_conexion(error):
    """Muestra el error de conexión con un botón para reintentar y detiene la página."""
    st.error(f"No se pudo consultar la base de datos VuelosDW.\n\nDetalle: {error}")
    st.info("Si la base de datos está en Azure, puede estar despertando (tarda ~1 minuto).")
    if st.button("Reintentar"):
        get_conexion_lector.clear()
        get_conexion_editor.clear()
        st.cache_data.clear()
        st.rerun()
    st.stop()


# ----------------------------------------------------------- Filtros globales ---
def _rango_fechas():
    """Fecha mínima y máxima con vuelos en el Data Mart."""
    df = consultar("SELECT MIN(d.fecha) AS minima, MAX(d.fecha) AS maxima "
                   "FROM FactVuelos f JOIN DimFecha d ON f.sk_fecha = d.sk_fecha")
    return df.loc[0, "minima"], df.loc[0, "maxima"]


def _aeropuertos(columna_fk):
    """Códigos de aeropuertos con al menos un vuelo (columna_fk: sk_origen o sk_destino)."""
    df = consultar(f"SELECT DISTINCT a.codigo_iata, a.ciudad FROM FactVuelos f "
                   f"JOIN DimAeropuerto a ON f.{columna_fk} = a.sk_aeropuerto ORDER BY a.codigo_iata")
    return dict(zip(df["codigo_iata"], df["ciudad"]))


def filtros_sidebar():
    """Dibuja los filtros globales y los guarda en st.session_state."""
    try:
        minima, maxima = _rango_fechas()
        origenes = _aeropuertos("sk_origen")
        destinos = _aeropuertos("sk_destino")
    except pyodbc.Error as e:
        mostrar_error_conexion(e)

    # Valores iniciales; reasignarlos evita que Streamlit los borre al cambiar de página
    valores_iniciales = {"filtro_fechas": (minima, maxima), "filtro_origen": "Todos",
                         "filtro_destino": "Todos", "filtro_distancia": "Todas",
                         "filtro_franja": "Todas", "filtro_tipo_dia": "Todos"}
    for clave, valor in valores_iniciales.items():
        st.session_state[clave] = st.session_state.get(clave, valor)

    st.sidebar.header("Filtros")
    st.sidebar.date_input("Rango de fechas", min_value=minima, max_value=maxima,
                          key="filtro_fechas", format="DD/MM/YYYY")
    st.sidebar.selectbox("Aeropuerto de origen", ["Todos", *origenes], key="filtro_origen",
                         format_func=lambda c: c if c == "Todos" else f"{c} — {origenes[c]}")
    st.sidebar.selectbox("Aeropuerto de destino", ["Todos", *destinos], key="filtro_destino",
                         format_func=lambda c: c if c == "Todos" else f"{c} — {destinos[c]}")
    st.sidebar.selectbox("Tipo de distancia", ["Todas", *TIPOS_DISTANCIA], key="filtro_distancia",
                         help="Corta: menos de 700 millas · Media: 700–1500 · Larga: más de 1500")
    st.sidebar.selectbox("Franja horaria", ["Todas", *FRANJAS], key="filtro_franja")
    st.sidebar.selectbox("Tipo de día", ["Todos", *CONDICION_TIPO_DIA], key="filtro_tipo_dia",
                         help="Un feriado que cae en fin de semana cuenta como Feriado.")


def where_filtros():
    """Condición WHERE y parámetros según los filtros globales (usa los alias de FROM_VUELOS)."""
    fechas = st.session_state.get("filtro_fechas", ())
    if len(fechas) == 2:
        desde, hasta = fechas
    else:  # el usuario solo eligió la fecha inicial
        desde = hasta = fechas[0] if fechas else date.today()
    condiciones = ["f.sk_fecha BETWEEN ? AND ?"]
    params = [int(desde.strftime("%Y%m%d")), int(hasta.strftime("%Y%m%d"))]
    if st.session_state.get("filtro_origen", "Todos") != "Todos":
        condiciones.append("o.codigo_iata = ?")
        params.append(st.session_state["filtro_origen"])
    if st.session_state.get("filtro_destino", "Todos") != "Todos":
        condiciones.append("ds.codigo_iata = ?")
        params.append(st.session_state["filtro_destino"])
    if st.session_state.get("filtro_distancia", "Todas") != "Todas":
        condiciones.append("r.tipo_distancia = ?")
        params.append(st.session_state["filtro_distancia"])
    if st.session_state.get("filtro_franja", "Todas") != "Todas":
        condiciones.append("h.franja = ?")
        params.append(st.session_state["filtro_franja"])
    tipo_dia = st.session_state.get("filtro_tipo_dia", "Todos")
    if tipo_dia in CONDICION_TIPO_DIA:  # texto fijo del diccionario, no del usuario
        condiciones.append(CONDICION_TIPO_DIA[tipo_dia])
    return "WHERE " + " AND ".join(condiciones), tuple(params)
