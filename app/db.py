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
FRANJAS = ["Madrugada", "Mañana", "Tarde", "Noche"]

# FROM común para consultas sobre el hecho con los filtros globales
FROM_VUELOS = """
    FROM FactVuelos f
    JOIN DimFecha d       ON f.sk_fecha = d.sk_fecha
    JOIN DimAeropuerto o  ON f.sk_origen = o.sk_aeropuerto
    JOIN DimHorario h     ON f.sk_horario = h.sk_horario
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


def _aeropuertos_origen():
    """Códigos de aeropuertos con al menos un vuelo de salida."""
    df = consultar("SELECT DISTINCT o.codigo_iata, o.ciudad FROM FactVuelos f "
                   "JOIN DimAeropuerto o ON f.sk_origen = o.sk_aeropuerto ORDER BY o.codigo_iata")
    return dict(zip(df["codigo_iata"], df["ciudad"]))


def filtros_sidebar():
    """Dibuja los filtros globales y los guarda en st.session_state."""
    try:
        minima, maxima = _rango_fechas()
        aeropuertos = _aeropuertos_origen()
    except pyodbc.Error as e:
        mostrar_error_conexion(e)

    # Valores iniciales; reasignarlos evita que Streamlit los borre al cambiar de página
    valores_iniciales = {"filtro_fechas": (minima, maxima), "filtro_origen": "Todos", "filtro_franja": "Todas"}
    for clave, valor in valores_iniciales.items():
        st.session_state[clave] = st.session_state.get(clave, valor)

    st.sidebar.header("Filtros")
    st.sidebar.date_input("Rango de fechas", min_value=minima, max_value=maxima,
                          key="filtro_fechas", format="DD/MM/YYYY")
    st.sidebar.selectbox("Aeropuerto de origen", ["Todos", *aeropuertos], key="filtro_origen",
                         format_func=lambda c: c if c == "Todos" else f"{c} — {aeropuertos[c]}")
    st.sidebar.selectbox("Franja horaria", ["Todas", *FRANJAS], key="filtro_franja")


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
    if st.session_state.get("filtro_franja", "Todas") != "Todas":
        condiciones.append("h.franja = ?")
        params.append(st.session_state["filtro_franja"])
    return "WHERE " + " AND ".join(condiciones), tuple(params)
