# -*- coding: utf-8 -*-
"""
Página Propuesta: simulador de mejora de la puntualidad.

Si JetBlue reduce un % de los minutos de demora de "Aerolínea" y de "Avión anterior retrasado",
se recalcula vuelo por vuelo la nueva demora de llegada y qué vuelos pasarían a ser puntuales.
Todo se calcula en SQL sobre los datos reales del Data Mart, respetando los filtros globales.
"""

import plotly.express as px
import pyodbc
import streamlit as st

from db import COLORES_ESTADO, FROM_VUELOS, consultar, formato, mostrar_error_conexion, where_filtros

import reglas  # noqa: E402  (db.py agrega src/ al path)

# Costo por minuto de demora (supuesto): A4A estima 98,41 USD por minuto de block time (2025),
# de los cuales 29,34 son combustible. Se excluye el combustible por ser conservadores: 98,41 − 29,34 ≈ 69.
COSTO_MINUTO_DEFECTO = 69.0
FUENTE_COSTO = 'Airlines for America (A4A), "U.S. Passenger Carrier Delay Costs" (2025)'
COLOR_ACTUAL = "#8C8C8C"      # gris para el escenario actual; verde (A tiempo) para el propuesto


def simulacion_por_mes(where, params, pct_aerolinea, pct_avion):
    """Por mes: vuelos, puntuales actuales, vuelos que pasarían a puntuales y minutos ahorrados."""
    # Reducción por vuelo = % de los minutos de Aerolínea + % de los minutos de Avión anterior retrasado.
    # Solo cambia un vuelo demorado: pasa a "A tiempo" si su nueva demora queda bajo el umbral (15 min).
    sql = f"""
        SELECT d.anio, d.mes, COUNT(*) AS vuelos,
               SUM(f.es_puntual) AS puntuales_actual,
               SUM(CASE WHEN f.sk_estado = {reglas.DEMORADO}
                         AND f.demora_llegada_min - x.reduccion < ? THEN 1 ELSE 0 END) AS recuperados,
               SUM(CASE WHEN f.sk_estado = {reglas.DEMORADO} THEN x.reduccion ELSE 0 END) AS minutos_ahorrados
        {FROM_VUELOS}
        CROSS APPLY (SELECT ISNULL(f.min_causa_aerolinea, 0) * ?
                          + ISNULL(f.min_causa_avion_tardio, 0) * ? AS reduccion) AS x
        {where}
        GROUP BY d.anio, d.mes ORDER BY d.anio, d.mes
    """
    # Los ? van en el orden en que aparecen en el texto: umbral, % aerolínea, % avión, filtros
    df = consultar(sql, (reglas.UMBRAL_DEMORA, pct_aerolinea / 100, pct_avion / 100, *params))
    df["Mes"] = df["anio"].astype(str) + "-" + df["mes"].astype(str).str.zfill(2)
    df["Actual"] = df["puntuales_actual"] * 100.0 / df["vuelos"]
    df["Con la propuesta"] = (df["puntuales_actual"] + df["recuperados"]) * 100.0 / df["vuelos"]
    return df


# ------------------------------------------------------------------- Página ---
st.title("💡 Propuesta: simulador de mejora")
st.caption("¿Cuánto mejoraría la puntualidad si JetBlue reduce las demoras que sí puede controlar? "
           "Se recalcula cada vuelo real del período filtrado.")

with st.container(border=True):
    c1, c2, c3 = st.columns(3)
    pct_aerolinea = c1.slider("Reducción de minutos por «Aerolínea» (%)", 0, 50, 20, step=5,
                              help="Mantenimiento, tripulación, limpieza, equipaje, embarque. Controlable.")
    pct_avion = c2.slider("Reducción de minutos por «Avión anterior retrasado» (%)", 0, 50, 10, step=5,
                          help="Demora en cadena del vuelo anterior. Parcialmente controlable "
                               "(colchones de tiempo entre vuelos, aviones de reserva).")
    costo_minuto = c3.number_input("Costo por minuto de demora (USD) — supuesto", min_value=0.0,
                                   value=COSTO_MINUTO_DEFECTO, step=5.0, format="%.2f",
                                   help=f"Supuesto editable. {FUENTE_COSTO}: 98,41 USD/min de block time, "
                                        "menos 29,34 USD de combustible (estimación conservadora).")

where, params = where_filtros()
try:
    df = simulacion_por_mes(where, params, pct_aerolinea, pct_avion)
except pyodbc.Error as e:
    mostrar_error_conexion(e)

if df.empty:
    st.warning("No hay vuelos para los filtros seleccionados.")
    st.stop()

vuelos = df["vuelos"].sum()
pct_actual = df["puntuales_actual"].sum() * 100.0 / vuelos
pct_nuevo = (df["puntuales_actual"].sum() + df["recuperados"].sum()) * 100.0 / vuelos
minutos = df["minutos_ahorrados"].sum()

m1, m2, m3, m4 = st.columns(4)
m1.metric("Minutos de demora ahorrados", formato(minutos, 0))
m2.metric("% Puntualidad actual", f"{formato(pct_actual)} %")
m3.metric("% Puntualidad con la propuesta", f"{formato(pct_nuevo)} %",
          f"+{formato(pct_nuevo - pct_actual)} puntos")
m4.metric("Ahorro estimado (USD)", f"$ {formato(minutos * costo_minuto, 0)}")
st.caption(f"{formato(df['recuperados'].sum(), 0)} vuelos demorados pasarían a llegar a tiempo "
           f"(de {formato(vuelos, 0)} vuelos programados). Puntualidad según la definición del DOT: "
           "cancelados y desviados cuentan como no puntuales.")

df_largo = df.melt(id_vars="Mes", value_vars=["Actual", "Con la propuesta"],
                   var_name="Escenario", value_name="% Puntualidad")
fig = px.bar(df_largo, x="Mes", y="% Puntualidad", color="Escenario", barmode="group",
             text_auto=".1f", title="% Puntualidad por mes: actual vs. con la propuesta",
             color_discrete_map={"Actual": COLOR_ACTUAL, "Con la propuesta": COLORES_ESTADO["A tiempo"]})
fig.update_layout(xaxis_type="category", yaxis_title="% Puntualidad", legend_title_text="")
st.plotly_chart(fig, width="stretch")

with st.expander("¿Cómo se calcula y qué limitaciones tiene?"):
    st.markdown(f"""
- Para cada vuelo **demorado** (llegó con {reglas.UMBRAL_DEMORA} min o más): nueva demora =
  demora de llegada − % × minutos «Aerolínea» − % × minutos «Avión anterior retrasado».
- Si la nueva demora queda bajo {reglas.UMBRAL_DEMORA} min, el vuelo pasa a **A tiempo**.
  Los vuelos puntuales, cancelados y desviados no cambian.
- Ahorro en USD = minutos ahorrados × costo por minuto (**supuesto**, editable).
  Valor por defecto: 69 USD/min. Fuente: {FUENTE_COSTO}, que estima 98,41 USD por minuto de
  *block time*, de los cuales 29,34 USD son combustible (98,41 − 29,34 ≈ 69).
  Se excluye el combustible como criterio conservador, ya que parte de la demora puede ocurrir
  en puerta sin consumo de combustible.
- **Limitaciones:** la reducción se aplica igual a todos los vuelos; no se recalcula el efecto en
  cadena sobre los vuelos siguientes del mismo avión; no simula cancelaciones; el costo por minuto
  es un promedio de la industria, no un dato propio de JetBlue.
""")
    st.dataframe(df[["Mes", "vuelos", "recuperados", "minutos_ahorrados", "Actual", "Con la propuesta"]]
                 .rename(columns={"vuelos": "Vuelos", "recuperados": "Pasan a puntuales",
                                  "minutos_ahorrados": "Minutos ahorrados"}),
                 hide_index=True, width="stretch")
