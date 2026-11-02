# -*- coding: utf-8 -*-
"""
Página Horario: cómo cambia la puntualidad a lo largo del día (hora programada de salida).

Hipótesis: la puntualidad empeora durante el día porque las demoras se encadenan (avión anterior retrasado).
"""

import plotly.express as px
import pyodbc
import streamlit as st

from db import COLORES_CAUSA, COLORES_ESTADO, FRANJAS, FROM_VUELOS, consultar, formato, mostrar_error_conexion, where_filtros

MIN_VUELOS_HORA = 100  # horas con menos vuelos se marcan como poco confiables
# Rangos de demora: verdes si llegó a tiempo, ámbar cada vez más oscuro según la gravedad, gris si no aplica
COLORES_RANGO = {
    "Llegó antes de hora": "#2E9E5B",
    "A tiempo (0–14 min)": "#7CC49A",
    "Leve (15–44 min)": "#F7C948",
    "Moderada (45–119 min)": "#F2A900",
    "Grave (120+ min)": "#B07A00",
    "No aplica (cancelado/desviado)": COLORES_ESTADO["Desviado"],
}


def puntualidad_por_hora(where, params):
    """Vuelos y % puntualidad por hora programada de salida (0–23)."""
    return consultar(f"""
        SELECT h.sk_horario AS Hora, h.bloque AS Bloque, COUNT(*) AS Vuelos,
               SUM(f.es_puntual) * 100.0 / COUNT(*) AS [% Puntualidad]
        {FROM_VUELOS} {where}
        GROUP BY h.sk_horario, h.bloque ORDER BY h.sk_horario
    """, params)


def avion_tardio_por_franja(where, params):
    """% de los minutos de demora atribuidos a 'Avión anterior retrasado' por franja (suma / suma)."""
    return consultar(f"""
        SELECT h.franja AS Franja, COUNT(*) AS [Vuelos demorados],
               SUM(CAST(f.min_causa_avion_tardio AS BIGINT)) * 100.0 /
               NULLIF(SUM(CAST(ISNULL(f.min_causa_aerolinea, 0) + ISNULL(f.min_causa_clima, 0)
                             + ISNULL(f.min_causa_trafico, 0) + ISNULL(f.min_causa_seguridad, 0)
                             + ISNULL(f.min_causa_avion_tardio, 0) AS BIGINT)), 0) AS [% Avión anterior retrasado]
        {FROM_VUELOS} {where} AND f.sk_estado = 2
        GROUP BY h.franja
    """, params)


def vuelos_por_rango(where, params):
    """Vuelos por rango de demora de llegada, en el orden de DimRangoDemora."""
    return consultar(f"""
        SELECT rd.rango AS Rango, rd.orden, COUNT(*) AS Vuelos
        {FROM_VUELOS}
        JOIN DimRangoDemora rd ON f.sk_rango_demora = rd.sk_rango_demora
        {where}
        GROUP BY rd.rango, rd.orden ORDER BY rd.orden
    """, params)


# ------------------------------------------------------------------- Página ---
st.title("🕒 Puntualidad según la hora de salida")
st.caption("Hora programada de salida (hora local del aeropuerto de origen).")

where, params = where_filtros()
try:
    df_hora = puntualidad_por_hora(where, params)
    df_franja = avion_tardio_por_franja(where, params)
    df_rango = vuelos_por_rango(where, params)
except pyodbc.Error as e:
    mostrar_error_conexion(e)

if df_hora.empty:
    st.warning("No hay vuelos para los filtros seleccionados.")
    st.stop()

confiables = df_hora[df_hora["Vuelos"] >= MIN_VUELOS_HORA]
if len(confiables) >= 2:  # con una sola hora no hay nada que comparar
    mejor = confiables.loc[confiables["% Puntualidad"].idxmax()]
    peor = confiables.loc[confiables["% Puntualidad"].idxmin()]
    c1, c2, c3 = st.columns(3)
    c1.metric("Hora más puntual", mejor["Bloque"], f"{formato(mejor['% Puntualidad'])} %", delta_color="off")
    c2.metric("Hora menos puntual", peor["Bloque"], f"{formato(peor['% Puntualidad'])} %", delta_color="off")
    c3.metric("Diferencia", f"{formato(mejor['% Puntualidad'] - peor['% Puntualidad'])} puntos")

fig = px.line(df_hora, x="Hora", y="% Puntualidad", markers=True, title="% Puntualidad por hora programada de salida",
              hover_data={"Bloque": True, "Vuelos": ":,.0f", "% Puntualidad": ":.1f", "Hora": False},
              color_discrete_sequence=[COLORES_ESTADO["A tiempo"]])
fig.update_traces(line_width=2, marker_size=8)
fig.update_layout(xaxis=dict(tickmode="linear", dtick=1, range=[-0.5, 23.5]), yaxis_title="% Puntualidad")
st.plotly_chart(fig, width="stretch")
pocas = df_hora.loc[df_hora["Vuelos"] < MIN_VUELOS_HORA, "Hora"].tolist()
if pocas:
    st.caption(f"Horas con menos de {MIN_VUELOS_HORA} vuelos (porcentaje poco confiable): "
               f"{', '.join(f'{h} h' for h in pocas)}.")

col_izq, col_der = st.columns(2)
with col_izq:
    if df_franja.empty:
        st.info("No hay vuelos demorados con estos filtros.")
    else:
        fig = px.bar(df_franja, x="Franja", y="% Avión anterior retrasado", text_auto=".1f",
                     title="Peso de «Avión anterior retrasado» en los minutos de demora",
                     category_orders={"Franja": FRANJAS}, hover_data=["Vuelos demorados"],
                     color_discrete_sequence=[COLORES_CAUSA["Avión anterior retrasado"]])
        fig.update_layout(yaxis_title="% de los minutos de demora", yaxis_range=[0, 100])
        st.plotly_chart(fig, width="stretch")
        st.caption("Madrugada 0–5 h · Mañana 6–11 h · Tarde 12–17 h · Noche 18–23 h")
with col_der:
    df_rango["% de vuelos"] = df_rango["Vuelos"] * 100 / df_rango["Vuelos"].sum()
    fig = px.bar(df_rango, x="Rango", y="Vuelos", color="Rango", text_auto=",.0f",
                 title="Vuelos por rango de demora de llegada", color_discrete_map=COLORES_RANGO,
                 category_orders={"Rango": df_rango["Rango"].tolist()}, hover_data={"% de vuelos": ":.1f"})
    fig.update_layout(showlegend=False, xaxis_title="")
    st.plotly_chart(fig, width="stretch")

with st.expander("Ver datos por hora en tabla"):
    st.dataframe(df_hora, hide_index=True, width="stretch")
