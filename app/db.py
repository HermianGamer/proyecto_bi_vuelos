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
from conexion import DB_DW, cadena_conexion  # noqa: E402

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

_bloqueo = threading.Lock()  # una sola conexión compartida: una consulta a la vez


# ------------------------------------------------------------------ Conexión ---
@st.cache_resource
def get_conexion():
    """Conexión a VuelosDW (se reutiliza entre recargas de la app)."""
    return pyodbc.connect(cadena_conexion(DB_DW))


def _ejecutar_cursor(sql, params):
    """Ejecuta una consulta; si la conexión se cayó (p. ej. Azure en pausa), reconecta una vez."""
    for intento in range(2):
        try:
            cursor = get_conexion().cursor()
            cursor.execute(sql, params)
            return cursor
        except pyodbc.Error:
            get_conexion.clear()
            if intento == 1:
                raise


@st.cache_data(ttl=300, show_spinner="Consultando base de datos...")
def consultar(sql, params=()):
    """Ejecuta un SELECT parametrizado y devuelve un DataFrame."""
    with _bloqueo:
        cursor = _ejecutar_cursor(sql, tuple(params))
        columnas = [c[0] for c in cursor.description]
        filas = [tuple(f) for f in cursor.fetchall()]
    df = pd.DataFrame.from_records(filas, columns=columnas)
    # SQL Server devuelve DECIMAL como Decimal de Python; plotly y pandas trabajan mejor con float
    for col in df.columns:
        if df[col].map(lambda v: isinstance(v, Decimal)).any():
            df[col] = df[col].astype(float)
    return df


def ejecutar(sql, params=()):
    """Ejecuta un INSERT/UPDATE/DELETE parametrizado y limpia la caché."""
    with _bloqueo:
        cursor = _ejecutar_cursor(sql, tuple(params))
        cursor.commit()
    st.cache_data.clear()


def formato(numero, decimales=1):
    """Número con formato peruano: coma decimal y punto de miles."""
    texto = f"{numero:,.{decimales}f}"
    return texto.replace(",", "X").replace(".", ",").replace("X", ".")


def mostrar_error_conexion(error):
    """Muestra el error de conexión con un botón para reintentar y detiene la página."""
    st.error(f"No se pudo consultar la base de datos VuelosDW.\n\nDetalle: {error}")
    st.info("Si la base de datos está en Azure, puede estar despertando (tarda ~1 minuto).")
    if st.button("Reintentar"):
        get_conexion.clear()
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
