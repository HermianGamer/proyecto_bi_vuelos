# -*- coding: utf-8 -*-
"""
Página Resumen: KPI principales y evolución mensual.

Se abre desde app/app.py (st.navigation); los filtros globales ya están dibujados.
"""

import pandas as pd
import plotly.express as px
import pyodbc
import streamlit as st

from db import COLORES_ESTADO, FROM_VUELOS, consultar, formato, mostrar_error_conexion, where_filtros

DIAS = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]
ORDEN_ESTADOS = ["A tiempo", "Demorado", "Cancelado", "Desviado"]


def kpis(where, params):
    """KPI principales (puntualidad con la definición del DOT: sobre todos los vuelos programados)."""
    return consultar(f"""
        SELECT COUNT(*) AS vuelos,
               SUM(f.es_puntual) * 100.0 / NULLIF(COUNT(*), 0)   AS pct_puntualidad,
               SUM(f.es_cancelado) * 100.0 / NULLIF(COUNT(*), 0) AS pct_cancelacion,
               AVG(CASE WHEN f.sk_estado = 2 THEN f.demora_llegada_min * 1.0 END) AS demora_promedio
        {FROM_VUELOS} {where}
    """, params).iloc[0]


def kpis_por_mes(where, params):
    """% puntualidad y % cancelación por mes."""
    df = consultar(f"""
        SELECT d.anio, d.mes,
               SUM(f.es_puntual) * 100.0 / COUNT(*)   AS [% Puntualidad],
               SUM(f.es_cancelado) * 100.0 / COUNT(*) AS [% Cancelación]
        {FROM_VUELOS} {where}
        GROUP BY d.anio, d.mes ORDER BY d.anio, d.mes
    """, params)
    df["Mes"] = df["anio"].astype(str) + "-" + df["mes"].astype(str).str.zfill(2)
    return df


def puntualidad_por_dia(where, params):
    """% puntualidad por día de la semana (lunes a domingo)."""
    df = consultar(f"""
        SELECT d.nombre_dia AS [Día], SUM(f.es_puntual) * 100.0 / COUNT(*) AS [% Puntualidad]
        {FROM_VUELOS} {where}
        GROUP BY d.nombre_dia
    """, params)
    df["Día"] = pd.Categorical(df["Día"], categories=DIAS, ordered=True)
    return df.sort_values("Día")


def vuelos_por_estado(where, params):
    """Cantidad de vuelos por estado y mes."""
    df = consultar(f"""
        SELECT d.anio, d.mes, e.estado AS Estado, COUNT(*) AS Vuelos
        {FROM_VUELOS}
        JOIN DimEstadoVuelo e ON f.sk_estado = e.sk_estado
        {where}
        GROUP BY d.anio, d.mes, e.estado ORDER BY d.anio, d.mes
    """, params)
    df["Mes"] = df["anio"].astype(str) + "-" + df["mes"].astype(str).str.zfill(2)
    return df


# ------------------------------------------------------------------- Página ---
where, params = where_filtros()

st.title("✈️ Puntualidad de JetBlue Airways")
st.caption("Fuente: BTS Reporting Carrier On-Time Performance. Puntualidad según la definición del DOT "
           "(Air Travel Consumer Report): llega con menos de 15 min de demora, sobre todos los vuelos programados.")

try:
    k = kpis(where, params)
    if not k["vuelos"]:
        st.warning("No hay vuelos para los filtros seleccionados.")
        st.stop()
    df_mes = kpis_por_mes(where, params)
    df_dia = puntualidad_por_dia(where, params)
    df_estado = vuelos_por_estado(where, params)
except pyodbc.Error as e:
    mostrar_error_conexion(e)

c1, c2, c3, c4 = st.columns(4)
c1.metric("Vuelos programados", formato(k["vuelos"], 0))
c2.metric("% Puntualidad", f"{formato(k['pct_puntualidad'])} %")
c3.metric("% Cancelación", f"{formato(k['pct_cancelacion'], 2)} %")
c4.metric("Demora promedio de demorados",
          f"{formato(k['demora_promedio'])} min" if pd.notna(k["demora_promedio"]) else "—")

col_izq, col_der = st.columns(2)
with col_izq:
    fig = px.line(df_mes, x="Mes", y=["% Puntualidad", "% Cancelación"], markers=True,
                  title="Puntualidad y cancelación por mes",
                  color_discrete_map={"% Puntualidad": COLORES_ESTADO["A tiempo"],
                                      "% Cancelación": COLORES_ESTADO["Cancelado"]})
    fig.update_layout(yaxis_title="%", legend_title_text="", xaxis_type="category")
    st.plotly_chart(fig, width="stretch")
with col_der:
    fig = px.bar(df_dia, x="Día", y="% Puntualidad", title="Puntualidad por día de la semana",
                 color_discrete_sequence=[COLORES_ESTADO["A tiempo"]], text_auto=".1f")
    fig.update_layout(yaxis_title="% Puntualidad")
    st.plotly_chart(fig, width="stretch")

fig = px.bar(df_estado, x="Mes", y="Vuelos", color="Estado", title="Vuelos por estado y mes",
             color_discrete_map=COLORES_ESTADO, category_orders={"Estado": ORDEN_ESTADOS})
fig.update_layout(xaxis_type="category")
st.plotly_chart(fig, width="stretch")
