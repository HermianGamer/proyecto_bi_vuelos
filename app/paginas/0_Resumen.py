# -*- coding: utf-8 -*-
"""
Página Resumen: KPI principales y evolución mensual.

Se abre desde app/app.py (st.navigation); los filtros globales ya están dibujados.
"""

import pandas as pd
import plotly.express as px
import pyodbc
import streamlit as st

from db import (
    COLORES_CAUSA, COLORES_ESTADO, FROM_VUELOS, MINUTOS_POR_CAUSA, consultar, formato, mostrar_error_conexion,
    sql_temporada, where_filtros,
)

import reglas  # noqa: E402  (db.py agrega src/ al path)

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


def kpis_por_temporada(where, params):
    """% puntualidad y % cancelación por temporada (invierno, verano, resto del año)."""
    df = consultar(f"""
        SELECT {sql_temporada()} AS Temporada, COUNT(*) AS Vuelos,
               SUM(f.es_puntual) * 100.0 / COUNT(*)   AS [% Puntualidad],
               SUM(f.es_cancelado) * 100.0 / COUNT(*) AS [% Cancelación]
        {FROM_VUELOS} {where}
        GROUP BY {sql_temporada()}
    """, params)
    df["Temporada"] = pd.Categorical(df["Temporada"], categories=reglas.TEMPORADAS, ordered=True)
    return df.sort_values("Temporada")


def causas_por_temporada(where, params):
    """Participación de cada causa por temporada: en minutos de demora y en cancelaciones."""
    minutos = consultar(f"""
        SELECT {sql_temporada()} AS Temporada, c.causa AS Causa, SUM(m.minutos) AS Valor
        {FROM_VUELOS} {MINUTOS_POR_CAUSA}
        {where} AND f.sk_estado = {reglas.DEMORADO}
        GROUP BY {sql_temporada()}, c.causa
    """, params)
    cancelaciones = consultar(f"""
        SELECT {sql_temporada()} AS Temporada, c.causa AS Causa, COUNT(*) AS Valor
        {FROM_VUELOS}
        JOIN DimCausaCancelacion c ON f.sk_causa_cancelacion = c.sk_causa_cancelacion
        {where} AND f.es_cancelado = 1
        GROUP BY {sql_temporada()}, c.causa
    """, params)
    minutos["Medida"] = "Minutos de demora"
    cancelaciones["Medida"] = "Cancelaciones"
    df = pd.concat([minutos, cancelaciones], ignore_index=True)
    df["%"] = df["Valor"] * 100 / df.groupby(["Medida", "Temporada"])["Valor"].transform("sum")
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
    df_temp = kpis_por_temporada(where, params)
    df_temp_causa = causas_por_temporada(where, params)
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

# --- Temporadas: invierno vs. verano ---
st.subheader("Invierno vs. verano")
st.caption("Invierno = diciembre a febrero · Verano = junio a agosto · Resto del año = los demás meses.")
df_temp_largo = df_temp.melt(id_vars=["Temporada", "Vuelos"], value_vars=["% Puntualidad", "% Cancelación"],
                             var_name="Indicador", value_name="%")
orden_temp = {"Temporada": reglas.TEMPORADAS, "Causa": list(COLORES_CAUSA)}
col_izq, col_der = st.columns(2)
with col_izq:
    fig = px.bar(df_temp_largo, x="Temporada", y="%", color="Indicador", barmode="group", text_auto=".1f",
                 title="Puntualidad y cancelación por temporada", category_orders=orden_temp,
                 hover_data={"Vuelos": ":,.0f"},
                 color_discrete_map={"% Puntualidad": COLORES_ESTADO["A tiempo"],
                                     "% Cancelación": COLORES_ESTADO["Cancelado"]})
    fig.update_layout(legend_title_text="", yaxis_title="%")
    st.plotly_chart(fig, width="stretch")
with col_der:
    if df_temp_causa.empty:
        st.info("No hay demoras ni cancelaciones con estos filtros.")
    else:
        fig = px.bar(df_temp_causa, x="%", y="Temporada", color="Causa", facet_col="Medida", orientation="h",
                     text_auto=".0f", title="Participación de cada causa por temporada (%)",
                     category_orders={**orden_temp, "Medida": ["Minutos de demora", "Cancelaciones"]},
                     color_discrete_map=COLORES_CAUSA, hover_data={"Valor": ":,.0f", "%": ":.1f"})
        fig.for_each_annotation(lambda a: a.update(text=a.text.split("=")[-1]))
        fig.update_layout(legend_title_text="", xaxis_range=[0, 100], xaxis2_range=[0, 100])
        st.plotly_chart(fig, width="stretch")
        st.caption("BTS no reporta «Avión anterior retrasado» como causa de cancelación.")

with st.expander("Ver datos por temporada en tabla"):
    st.dataframe(df_temp, hide_index=True, width="stretch")
    st.dataframe(df_temp_causa.pivot_table(index=["Medida", "Causa"], columns="Temporada", values="%")
                 .reindex(columns=reglas.TEMPORADAS).round(1).reset_index(), hide_index=True, width="stretch")
