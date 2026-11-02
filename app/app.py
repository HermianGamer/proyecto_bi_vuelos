# -*- coding: utf-8 -*-
"""
Dashboard de puntualidad de JetBlue — punto de entrada.

Configura la página, dibuja los filtros globales y arma el menú con st.navigation.
Ejecutar: streamlit run app/app.py
"""

import streamlit as st

from db import filtros_sidebar

st.set_page_config(page_title="JetBlue — Puntualidad", page_icon="✈️", layout="wide")

paginas = [
    st.Page("paginas/0_Resumen.py", title="Resumen", icon="📊", default=True),
    st.Page("paginas/1_Causas.py", title="Causas de demora", icon="🔍"),
    st.Page("paginas/2_Aeropuertos_y_rutas.py", title="Aeropuertos y rutas", icon="🗺️"),
    st.Page("paginas/3_Horario.py", title="Horario", icon="🕒"),
    st.Page("paginas/4_Consultas_SQL.py", title="Consultas SQL", icon="🧮"),
]
navegacion = st.navigation(paginas)
filtros_sidebar()
navegacion.run()
