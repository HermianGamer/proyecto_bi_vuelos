# -*- coding: utf-8 -*-
"""
Página Causas: qué explica los minutos de demora y las cancelaciones.

Los minutos por causa solo existen en vuelos demorados (llegada con 15+ min de demora).
"""

import plotly.express as px
import pyodbc
import streamlit as st

from db import COLORES_CAUSA, FROM_VUELOS, MINUTOS_POR_CAUSA, consultar, formato, mostrar_error_conexion, where_filtros

CAUSAS = list(COLORES_CAUSA)
ORDEN_CONTROL = ["Sí", "Parcial", "No"]


def filtro_causas(causas):
    """Condición SQL y parámetros para las causas elegidas en el filtro local."""
    return f" AND c.causa IN ({', '.join('?' * len(causas))})", tuple(causas)


def minutos_por_causa(where, params, causas):
    """Minutos de demora por causa y controlabilidad (solo vuelos demorados)."""
    cond, p = filtro_causas(causas)
    return consultar(f"""
        SELECT c.causa AS Causa, c.controlable AS Controlable, SUM(m.minutos) AS Minutos
        {FROM_VUELOS} {MINUTOS_POR_CAUSA}
        {where} AND f.sk_estado = 2 {cond}
        GROUP BY c.causa, c.controlable
    """, params + p)


def participacion_por_mes(where, params, causas):
    """Minutos de demora por mes y causa (para barras apiladas al 100 %)."""
    cond, p = filtro_causas(causas)
    df = consultar(f"""
        SELECT d.anio, d.mes, c.causa AS Causa, SUM(m.minutos) AS Minutos
        {FROM_VUELOS} {MINUTOS_POR_CAUSA}
        {where} AND f.sk_estado = 2 {cond}
        GROUP BY d.anio, d.mes, c.causa ORDER BY d.anio, d.mes
    """, params + p)
    df["Mes"] = df["anio"].astype(str) + "-" + df["mes"].astype(str).str.zfill(2)
    df["% de minutos"] = df["Minutos"] * 100 / df.groupby("Mes")["Minutos"].transform("sum")
    return df


def cancelaciones_por_causa(where, params, causas):
    """Vuelos cancelados por causa de cancelación."""
    cond, p = filtro_causas(causas)
    return consultar(f"""
        SELECT c.causa AS Causa, c.controlable AS Controlable, COUNT(*) AS Cancelaciones
        {FROM_VUELOS}
        JOIN DimCausaCancelacion c ON f.sk_causa_cancelacion = c.sk_causa_cancelacion
        {where} AND f.es_cancelado = 1 {cond}
        GROUP BY c.causa, c.controlable ORDER BY Cancelaciones DESC
    """, params + p)


# ------------------------------------------------------------------- Página ---
st.title("🔍 Causas de demora y cancelación")
st.caption("Minutos de demora reportados a BTS por causa, en vuelos que llegaron con 15 o más minutos de demora. "
           "Un vuelo puede tener minutos en varias causas.")

causas = st.multiselect("Causas a mostrar (filtro de esta página)", CAUSAS, default=CAUSAS)
if not causas:
    st.warning("Elige al menos una causa.")
    st.stop()

where, params = where_filtros()
try:
    df_causa = minutos_por_causa(where, params, causas)
    df_mes = participacion_por_mes(where, params, causas)
    df_cancel = cancelaciones_por_causa(where, params, causas)
except pyodbc.Error as e:
    mostrar_error_conexion(e)

if df_causa.empty:
    st.warning("No hay vuelos demorados para los filtros seleccionados.")
    st.stop()

total = df_causa["Minutos"].sum()
principal = df_causa.sort_values("Minutos", ascending=False).iloc[0]
controlable = df_causa.loc[df_causa["Controlable"] == "Sí", "Minutos"].sum()
c1, c2, c3, c4 = st.columns(4)
c1.metric("Minutos de demora", formato(total, 0))
c2.metric("Causa principal", principal["Causa"], f"{formato(principal['Minutos'] * 100 / total)} % de los minutos",
          delta_color="off")
c3.metric("Minutos controlables (Aerolínea)", f"{formato(controlable * 100 / total)} %")
c4.metric("Vuelos cancelados", formato(df_cancel["Cancelaciones"].sum(), 0))

fig = px.bar(df_mes, x="Mes", y="% de minutos", color="Causa", title="Participación de cada causa por mes (% de minutos)",
             color_discrete_map=COLORES_CAUSA, category_orders={"Causa": CAUSAS},
             hover_data={"Minutos": ":,.0f", "% de minutos": ":.1f"})
fig.update_layout(xaxis_type="category", yaxis_title="% de minutos", yaxis_range=[0, 100], bargap=0.25)
fig.update_traces(marker_line_width=0)
st.plotly_chart(fig, width="stretch")

col_izq, col_der = st.columns(2)
with col_izq:
    fig = px.bar(df_causa, x="Controlable", y="Minutos", color="Causa", text_auto=",.0f",
                 title="Minutos de demora según si la aerolínea puede controlarlos",
                 color_discrete_map=COLORES_CAUSA,
                 category_orders={"Controlable": ORDEN_CONTROL, "Causa": CAUSAS})
    fig.update_layout(xaxis_title="¿Controlable por la aerolínea?", yaxis_title="Minutos")
    st.plotly_chart(fig, width="stretch")
    st.caption("Sí = Aerolínea · Parcial = Avión anterior retrasado (efecto cadena) · No = clima, tráfico aéreo y seguridad.")
with col_der:
    if df_cancel.empty:
        st.info("No hay cancelaciones para los filtros seleccionados.")
    else:
        fig = px.bar(df_cancel, x="Causa", y="Cancelaciones", color="Causa", text_auto=",.0f",
                     title="Vuelos cancelados por causa", color_discrete_map=COLORES_CAUSA,
                     category_orders={"Causa": CAUSAS})
        fig.update_layout(showlegend=False, xaxis_title="")
        st.plotly_chart(fig, width="stretch")
        st.caption("BTS no tiene la causa «Avión anterior retrasado» para cancelaciones.")

with st.expander("Ver datos en tabla"):
    st.dataframe(df_causa.sort_values("Minutos", ascending=False), hide_index=True, width="stretch")
    st.dataframe(df_cancel, hide_index=True, width="stretch")
