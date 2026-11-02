# -*- coding: utf-8 -*-
"""
Página Consultas SQL: consola de solo lectura sobre VuelosDW.

Se conecta como app_lector (solo db_datareader). El validador da mensajes claros,
pero la protección real son los permisos del usuario en la base de datos.
"""

import pyodbc
import streamlit as st
from streamlit_ace import st_ace

import esquema
from consultas_ejemplo import EJEMPLOS
from db import TIMEOUT_CONSULTA, consultar, consultar_libre, es_error_de_conexion, formato, mostrar_error_conexion
from validador_sql import validar_consulta

MAX_FILAS = 1000


def cargar_ejemplo():
    """Pone la consulta de ejemplo elegida en el editor (una clave nueva obliga a redibujarlo)."""
    nombre = st.session_state["ejemplo_sql"]
    if nombre in EJEMPLOS:
        st.session_state["consulta_sql"] = EJEMPLOS[nombre]
        st.session_state["version_editor"] += 1


@st.cache_data(ttl=3600, show_spinner=False)
def leer_esquema():
    """Columnas, tipos y claves del Data Mart desde INFORMATION_SCHEMA (caché de 1 hora)."""
    return esquema.preparar_columnas(consultar(esquema.SQL_COLUMNAS))


@st.cache_data(ttl=3600, show_spinner=False)
def diagrama(df):
    """Diagrama estrella en DOT (se arma una sola vez por esquema)."""
    return esquema.diagrama_estrella(df)


def ejecutar_consulta(texto):
    """Valida y ejecuta la consulta con app_lector; muestra el resultado o el error."""
    valida, resultado = validar_consulta(texto)
    if not valida:
        st.error(f"Consulta rechazada: {resultado}")
        return
    try:
        df, recortado = consultar_libre(resultado, MAX_FILAS)
    except pyodbc.Error as e:
        if e.args and e.args[0] == "HYT00":
            st.error(f"La consulta tardó más de {TIMEOUT_CONSULTA} segundos y se canceló. "
                     "Prueba agregando filtros (WHERE) o TOP.")
        elif es_error_de_conexion(e):
            mostrar_error_conexion(e)
        else:
            st.error(f"SQL Server rechazó la consulta:\n\n{e.args[-1] if e.args else e}")
        return

    if df.empty:
        st.info("La consulta no devolvió filas.")
        return
    if recortado:
        st.warning(f"Se muestran solo las primeras {formato(MAX_FILAS, 0)} filas.")
    else:
        st.success(f"{formato(len(df), 0)} filas.")
    st.dataframe(df, hide_index=True, width="stretch")
    st.download_button("Descargar CSV", df.to_csv(index=False).encode("utf-8-sig"),
                       file_name="consulta_vuelos.csv", mime="text/csv")


# ------------------------------------------------------------------- Página ---
st.title("🧮 Consultas SQL")
st.caption(f"Consola de solo lectura (usuario app_lector). Solo SELECT o WITH, una consulta a la vez, "
           f"hasta {formato(MAX_FILAS, 0)} filas y {TIMEOUT_CONSULTA} s. "
           "Los filtros de la barra lateral no se aplican aquí.")

st.session_state.setdefault("consulta_sql", EJEMPLOS["KPI por mes"])
st.session_state.setdefault("version_editor", 0)

col_consulta, col_modelo = st.columns([3, 2], gap="large")

with col_consulta:
    st.selectbox("Consultas de ejemplo", ["— Elegir —", *EJEMPLOS], key="ejemplo_sql", on_change=cargar_ejemplo)
    texto = st_ace(
        value=st.session_state["consulta_sql"],
        language="sql",
        theme="tomorrow",
        font_size=16,
        height=350,
        show_gutter=True,        # números de línea
        wrap=True,
        auto_update=True,        # envía el texto al escribir, así "Ejecutar" usa siempre lo último
        key=f"editor_sql_{st.session_state['version_editor']}",
    )
    if texto is not None:
        st.session_state["consulta_sql"] = texto
    if st.button("Ejecutar", type="primary"):
        ejecutar_consulta(st.session_state["consulta_sql"])

with col_modelo:
    st.subheader("Modelo estrella")
    try:
        df_esquema = leer_esquema()
    except pyodbc.Error as e:
        mostrar_error_conexion(e)
    st.graphviz_chart(diagrama(df_esquema), width="stretch")
    st.caption("En negrita la clave primaria (PK). Cada flecha une una dimensión con su clave foránea (FK) "
               "en FactVuelos; DimAeropuerto se usa dos veces (origen y destino).")

    tablas = [esquema.TABLA_HECHOS] + sorted(t for t in df_esquema["tabla"].unique() if t != esquema.TABLA_HECHOS)
    tabla = st.selectbox("Ver columnas de la tabla", tablas)
    st.dataframe(esquema.tabla_referencia(df_esquema, tabla), hide_index=True, width="stretch")
