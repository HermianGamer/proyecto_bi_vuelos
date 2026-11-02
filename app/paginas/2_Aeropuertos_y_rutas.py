# -*- coding: utf-8 -*-
"""
Página Aeropuertos y rutas: dónde se concentran las demoras.

Los aeropuertos se analizan como origen (salidas). Mínimos de vuelos para que los % sean confiables.
"""

import plotly.express as px
import pyodbc
import streamlit as st

from db import COLORES_ESTADO, FROM_VUELOS, consultar, formato, mostrar_error_conexion, where_filtros

MIN_VUELOS_AEROPUERTO = 300
MIN_VUELOS_RUTA = 100
TOP = 15
RANGO_MAPA = 10  # puntos alrededor del promedio; los valores más extremos se pintan con el color pleno
# Escala divergente: rojo = peor que el promedio, neutro claro = promedio, azul = mejor (apta para daltonismo)
ESCALA_PUNTUALIDAD = ["#e34948", "#f7f6f2", "#2a78d6"]


def kpis_aeropuertos(where, params):
    """Vuelos, % puntualidad y taxi-out promedio por aeropuerto de origen (con coordenadas)."""
    return consultar(f"""
        SELECT o.codigo_iata AS Aeropuerto, o.ciudad AS Ciudad, o.latitud, o.longitud,
               COUNT(*) AS Vuelos,
               SUM(f.es_puntual) * 100.0 / COUNT(*) AS [% Puntualidad],
               SUM(f.es_cancelado) * 100.0 / COUNT(*) AS [% Cancelación],
               AVG(f.taxi_out_min * 1.0) AS [Taxi-out promedio (min)]
        {FROM_VUELOS} {where}
        GROUP BY o.codigo_iata, o.ciudad, o.latitud, o.longitud
    """, params)


def rutas_por_minutos(where, params):
    """Top rutas por minutos totales de demora de llegada (solo vuelos demorados)."""
    return consultar(f"""
        SELECT TOP {TOP} r.ruta AS Ruta, COUNT(*) AS [Vuelos demorados],
               SUM(CAST(f.demora_llegada_min AS BIGINT)) AS [Minutos de demora]
        {FROM_VUELOS} {where} AND f.sk_estado = 2
        GROUP BY r.ruta ORDER BY [Minutos de demora] DESC
    """, params)


def rutas_peor_puntualidad(where, params):
    """Top rutas con peor % de puntualidad (mínimo de vuelos programados)."""
    return consultar(f"""
        SELECT TOP {TOP} r.ruta AS Ruta, COUNT(*) AS Vuelos,
               SUM(f.es_puntual) * 100.0 / COUNT(*) AS [% Puntualidad]
        {FROM_VUELOS} {where}
        GROUP BY r.ruta HAVING COUNT(*) >= ?
        ORDER BY [% Puntualidad] ASC
    """, params + (MIN_VUELOS_RUTA,))


def mapa(df, promedio):
    """Mapa de burbujas: tamaño = vuelos, color = % puntualidad (promedio ± 10 puntos)."""
    fig = px.scatter_geo(df.dropna(subset=["latitud"]), lat="latitud", lon="longitud", size="Vuelos",
                         color="% Puntualidad", hover_name="Aeropuerto", size_max=40,
                         hover_data={"Ciudad": True, "Vuelos": ":,.0f", "% Puntualidad": ":.1f",
                                     "% Cancelación": ":.2f", "latitud": False, "longitud": False},
                         color_continuous_scale=ESCALA_PUNTUALIDAD,
                         range_color=[promedio - RANGO_MAPA, promedio + RANGO_MAPA],
                         title="Salidas por aeropuerto (tamaño = vuelos, color = % puntualidad)")
    # scope "usa" (Albers) no dibuja Puerto Rico: se usa Norteamérica ajustada a los aeropuertos
    fig.update_geos(scope="north america", fitbounds="locations", showsubunits=True,
                    subunitcolor="#bbbbbb", showcountries=True, countrycolor="#999999",
                    landcolor="#e4e4e0", showlakes=False)
    # borde gris para que las burbujas de color neutro claro se distingan del fondo
    fig.update_traces(marker_line_color="#6b6b6b", marker_line_width=0.8)
    fig.update_layout(height=550, margin=dict(l=0, r=0, t=50, b=0),
                      coloraxis_colorbar=dict(title="% puntualidad", ticksuffix=" %"))
    return fig


# ------------------------------------------------------------------- Página ---
st.title("🗺️ Aeropuertos y rutas")
st.caption("Aeropuertos como origen del vuelo. % Puntualidad según el DOT: sobre todos los vuelos programados.")

where, params = where_filtros()
try:
    df_aer = kpis_aeropuertos(where, params)
    df_rutas_min = rutas_por_minutos(where, params)
    df_rutas_pct = rutas_peor_puntualidad(where, params)
except pyodbc.Error as e:
    mostrar_error_conexion(e)

if df_aer.empty:
    st.warning("No hay vuelos para los filtros seleccionados.")
    st.stop()

promedio = (df_aer["% Puntualidad"] * df_aer["Vuelos"]).sum() / df_aer["Vuelos"].sum()  # suma / suma (toda la red)
df_mapa = df_aer[df_aer["Vuelos"] >= MIN_VUELOS_AEROPUERTO]
if df_mapa.empty:
    st.info(f"Ningún aeropuerto llega a {MIN_VUELOS_AEROPUERTO} salidas con estos filtros: no se dibuja el mapa.")
else:
    st.plotly_chart(mapa(df_mapa, promedio), width="stretch")
    st.caption(f"Solo aeropuertos con al menos {MIN_VUELOS_AEROPUERTO} salidas ({len(df_mapa)} de {len(df_aer)}). "
               f"Color neutro = promedio de la red con los filtros actuales ({formato(promedio)} %); "
               f"rojo = peor, azul = mejor. La escala va de {formato(promedio - RANGO_MAPA)} % a "
               f"{formato(promedio + RANGO_MAPA)} %: los aeropuertos fuera de ese rango se pintan con el color pleno.")

st.subheader(f"Ranking de aeropuertos (mínimo {MIN_VUELOS_AEROPUERTO} salidas)")
orden = st.radio("Mostrar", ["Peor puntualidad", "Mejor puntualidad"], horizontal=True)
df_rank = df_aer[df_aer["Vuelos"] >= MIN_VUELOS_AEROPUERTO]
if df_rank.empty:
    st.info(f"Ningún aeropuerto llega a {MIN_VUELOS_AEROPUERTO} salidas con estos filtros.")
else:
    df_rank = df_rank.sort_values("% Puntualidad", ascending=(orden == "Peor puntualidad")).head(TOP)
    orden_y = {"Aeropuerto": df_rank["Aeropuerto"].tolist()}
    col_izq, col_der = st.columns(2)
    with col_izq:
        fig = px.bar(df_rank, x="% Puntualidad", y="Aeropuerto", orientation="h", text_auto=".1f",
                     title="% Puntualidad", category_orders=orden_y, hover_data=["Ciudad", "Vuelos"],
                     color_discrete_sequence=[COLORES_ESTADO["A tiempo"]])
        fig.update_layout(height=500, xaxis_range=[0, 100])
        st.plotly_chart(fig, width="stretch")
    with col_der:
        fig = px.bar(df_rank, x="Taxi-out promedio (min)", y="Aeropuerto", orientation="h", text_auto=".1f",
                     title="Taxi-out promedio (min, congestión en tierra)", category_orders=orden_y,
                     color_discrete_sequence=["#8C8C8C"])
        fig.update_layout(height=500)
        st.plotly_chart(fig, width="stretch")

st.subheader("Rutas")
col_izq, col_der = st.columns(2)
with col_izq:
    if df_rutas_min.empty:
        st.info("No hay vuelos demorados con estos filtros.")
    else:
        fig = px.bar(df_rutas_min, x="Minutos de demora", y="Ruta", orientation="h", text_auto=",.0f",
                     title=f"Top {TOP} rutas por minutos totales de demora", hover_data=["Vuelos demorados"],
                     category_orders={"Ruta": df_rutas_min["Ruta"].tolist()},
                     color_discrete_sequence=[COLORES_ESTADO["Demorado"]])
        fig.update_layout(height=500)
        st.plotly_chart(fig, width="stretch")
with col_der:
    if df_rutas_pct.empty:
        st.info(f"Ninguna ruta llega a {MIN_VUELOS_RUTA} vuelos con estos filtros.")
    else:
        fig = px.bar(df_rutas_pct, x="% Puntualidad", y="Ruta", orientation="h", text_auto=".1f",
                     title=f"Top {TOP} rutas con peor puntualidad (mín. {MIN_VUELOS_RUTA} vuelos)",
                     hover_data=["Vuelos"], category_orders={"Ruta": df_rutas_pct["Ruta"].tolist()},
                     color_discrete_sequence=[COLORES_ESTADO["Cancelado"]])
        fig.update_layout(height=500, xaxis_range=[0, 100])
        st.plotly_chart(fig, width="stretch")

with st.expander("Ver datos de aeropuertos en tabla"):
    st.dataframe(df_aer.drop(columns=["latitud", "longitud"]).sort_values("Vuelos", ascending=False),
                 hide_index=True, width="stretch")
