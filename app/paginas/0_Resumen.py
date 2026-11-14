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
    COLORES_CAUSA, COLORES_ESTADO, FROM_VUELOS, MINUTOS_POR_CAUSA, NOMBRE_POBLACION, PCT_CANCELACION,
    PCT_DEMORADOS, PCT_DESVIADOS, PCT_PUNTUALIDAD, SOLO_DEMORADOS, SOLO_OPERADOS, consultar, distribucion, formato,
    mostrar_error_conexion, sql_temporada, where_filtros,
)

import reglas  # noqa: E402  (db.py agrega src/ al path)

DIAS = list(reglas.DIAS.values())
ORDEN_ESTADOS = ["A tiempo", "Demorado", "Cancelado", "Desviado"]


def kpis(where, params):
    """KPI principales: % de vuelos programados en cada estado (definición del DOT); los cuatro suman 100 %."""
    return consultar(f"""
        SELECT COUNT(*) AS vuelos,
               {PCT_PUNTUALIDAD} AS pct_puntualidad,
               {PCT_DEMORADOS}   AS pct_demorados,
               {PCT_CANCELACION} AS pct_cancelacion,
               {PCT_DESVIADOS}   AS pct_desviados
        {FROM_VUELOS} {where}
    """, params).iloc[0]


def distribucion_demora(where, params):
    """Distribución de la demora de llegada: vuelos demorados y todos los que llegaron (una fila por población)."""
    filas = []
    for condicion, nombre in NOMBRE_POBLACION.items():
        df = distribucion(where, params, condicion)
        df.insert(0, "Población", nombre)
        filas.append(df)
    return pd.concat(filas, ignore_index=True)


def kpis_por_mes(where, params):
    """% puntualidad, % demorados y % cancelación por mes."""
    df = consultar(f"""
        SELECT d.anio, d.mes,
               {PCT_PUNTUALIDAD} AS [% Puntualidad],
               {PCT_DEMORADOS}   AS [% Demorados],
               {PCT_CANCELACION} AS [% Cancelación]
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
    """% puntualidad, % demorados y % cancelación por temporada, con la mediana y el P90 de la demora de los demorados."""
    df = consultar(f"""
        SELECT {sql_temporada()} AS Temporada, COUNT(*) AS Vuelos,
               {PCT_PUNTUALIDAD} AS [% Puntualidad],
               {PCT_DEMORADOS}   AS [% Demorados],
               {PCT_CANCELACION} AS [% Cancelación]
        {FROM_VUELOS} {where}
        GROUP BY {sql_temporada()}
    """, params)
    dist = distribucion(where, params, SOLO_DEMORADOS, grupo=sql_temporada())
    dist = dist.rename(columns={"Grupo": "Temporada", "Vuelos": "Vuelos demorados", "Promedio": "Promedio (min)",
                                "Mediana": "Mediana (min)", "P90": "P90 (min)"})
    df = df.merge(dist[["Temporada", "Vuelos demorados", "Mediana (min)", "P90 (min)", "Promedio (min)"]],
                  on="Temporada", how="left")
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
    df_dist = distribucion_demora(where, params)
except pyodbc.Error as e:
    mostrar_error_conexion(e)

c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("Vuelos programados", formato(k["vuelos"], 0))
c2.metric("% Puntualidad", f"{formato(k['pct_puntualidad'])} %",
          help="Estado «A tiempo»: llegó con menos de 15 min de demora. Sobre todos los vuelos programados.")
c3.metric("% Demorados", f"{formato(k['pct_demorados'])} %",
          help="Estado «Demorado»: llegó con 15 min o más de demora. Sobre todos los vuelos programados.")
c4.metric("% Cancelación", f"{formato(k['pct_cancelacion'], 2)} %")
c5.metric("% Desviados", f"{formato(k['pct_desviados'], 2)} %")
partes = [("A tiempo", k["pct_puntualidad"], 1), ("Demorado", k["pct_demorados"], 1),
          ("Cancelado", k["pct_cancelacion"], 2), ("Desviado", k["pct_desviados"], 2)]
suma = sum(p for _, p, _ in partes)
st.caption(" + ".join(f"{n} {formato(p, d)} %" for n, p, d in partes) + f" = **{formato(suma)} %** "
           "de los vuelos programados (cada vuelo tiene un solo estado; los valores mostrados están redondeados).")

# --- Distribución de la demora de llegada (compacta; el detalle está en la página Horario) ---
st.markdown("**Demora de llegada (minutos)** — el promedio se muestra junto a la mediana y los percentiles, "
            "porque unas pocas demoras muy largas lo inflan.")
demorados = df_dist.iloc[0]
if demorados["Vuelos"] and pd.notna(demorados["Mediana"]):
    d1, d2, d3, d4 = st.columns(4)
    d1.metric("Mediana de los demorados", f"{formato(demorados['Mediana'], 0)} min",
              help="La mitad de los vuelos demorados llegó con menos de esta demora.")
    d2.metric("P90 de los demorados", f"{formato(demorados['P90'], 0)} min",
              help="El 10 % de los vuelos demorados llegó con más de esta demora.")
    d3.metric("Promedio de los demorados", f"{formato(demorados['Promedio'])} min")
    d4.metric("Máximo", f"{formato(demorados['Máximo'], 0)} min")
st.dataframe(df_dist, hide_index=True, width="stretch",
             column_config={c: st.column_config.NumberColumn(c, format="%.0f min")
                            for c in ["P25", "Mediana", "P75", "P90", "Máximo"]}
             | {"Promedio": st.column_config.NumberColumn("Promedio", format="%.1f min"),
                "Vuelos": st.column_config.NumberColumn("Vuelos", format="localized")})
st.caption("Valores negativos = llegó antes de hora. «Todos los vuelos que llegaron» excluye cancelados y "
           "desviados, que no tienen demora de llegada. Percentiles con PERCENTILE_CONT en SQL Server.")

col_izq, col_der = st.columns(2)
with col_izq:
    fig = px.line(df_mes, x="Mes", y=["% Puntualidad", "% Demorados", "% Cancelación"], markers=True,
                  title="Puntualidad, demorados y cancelación por mes",
                  color_discrete_map={"% Puntualidad": COLORES_ESTADO["A tiempo"],
                                      "% Demorados": COLORES_ESTADO["Demorado"],
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
df_temp_largo = df_temp.melt(id_vars=["Temporada", "Vuelos"],
                             value_vars=["% Puntualidad", "% Demorados", "% Cancelación"],
                             var_name="Indicador", value_name="%")
orden_temp = {"Temporada": reglas.TEMPORADAS, "Causa": list(COLORES_CAUSA)}
col_izq, col_der = st.columns(2)
with col_izq:
    fig = px.bar(df_temp_largo, x="Temporada", y="%", color="Indicador", barmode="group", text_auto=".1f",
                 title="Puntualidad, demorados y cancelación por temporada", category_orders=orden_temp,
                 hover_data={"Vuelos": ":,.0f"},
                 color_discrete_map={"% Puntualidad": COLORES_ESTADO["A tiempo"],
                                     "% Demorados": COLORES_ESTADO["Demorado"],
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
        st.caption("Minutos de demora: solo vuelos demorados. Cancelaciones: solo su propia causa "
                   "(DimCausaCancelacion); BTS no reporta «Avión anterior retrasado» como causa de cancelación.")

df_temp_dist = df_temp.melt(id_vars=["Temporada", "Vuelos demorados"], value_vars=["Mediana (min)", "P90 (min)"],
                            var_name="Medida", value_name="Minutos")
col_izq, _ = st.columns(2)
with col_izq:
    fig = px.bar(df_temp_dist, x="Temporada", y="Minutos", color="Medida", barmode="group", text_auto=".0f",
                 title="Demora de llegada de los vuelos demorados: mediana y P90", category_orders=orden_temp,
                 hover_data={"Vuelos demorados": ":,.0f"},
                 color_discrete_map={"Mediana (min)": COLORES_ESTADO["Demorado"], "P90 (min)": "#B07A00"})
    fig.update_layout(legend_title_text="", yaxis_title="Minutos de demora")
    st.plotly_chart(fig, width="stretch")
    st.caption("Mediana: la mitad de los vuelos demorados llegó con menos demora. "
               "P90: el 10 % llegó con más demora que este valor.")

with st.expander("Ver datos por temporada en tabla"):
    st.dataframe(df_temp, hide_index=True, width="stretch")
    st.dataframe(df_temp_causa.pivot_table(index=["Medida", "Causa"], columns="Temporada", values="%")
                 .reindex(columns=reglas.TEMPORADAS).round(1).reset_index(), hide_index=True, width="stretch")
