# -*- coding: utf-8 -*-
"""
Página Gestión de vuelos: registrar, editar y eliminar vuelos en FactVuelos.

Escribe con app_editor (solo puede tocar FactVuelos y agregar fechas, aeropuertos y rutas).
Las claves derivadas (estado, rango, causa principal, horario) se calculan con src/reglas.py,
las mismas reglas que usa el ETL. Los vuelos creados aquí quedan con origen_registro = 'APP'
y solo esos se pueden editar o eliminar: los datos reales del ETL (BTS) son de solo lectura.
"""

import re
from datetime import date, time

import pyodbc
import streamlit as st

from db import consultar, ejecutar_transaccion, es_error_de_conexion, mostrar_error_conexion

import reglas  # noqa: E402  (db.py agrega src/ al path)

LIMITE_DEMORA = (-120, 2000)  # minutos permitidos para demora de salida y de llegada
LIMITE_TAXI_OUT = (0, 300)
LIMITE_DISTANCIA = (1, 6000)
NUEVO = "__nuevo__"  # opción "nuevo aeropuerto" en los selectbox
SOLO_APP = "origen_registro = 'APP'"  # los datos del ETL (BTS) son de solo lectura desde la app

# código de causa BTS → columna de minutos en FactVuelos
COLUMNA_MINUTOS = {"CAR": "min_causa_aerolinea", "WEA": "min_causa_clima", "NAS": "min_causa_trafico",
                   "SEC": "min_causa_seguridad", "LAT": "min_causa_avion_tardio"}

# columnas que se recalculan al registrar o editar (en este orden van los valores)
COLUMNAS_MEDIDAS = ["sk_horario", "sk_estado", "sk_causa_demora", "sk_causa_cancelacion", "sk_rango_demora",
                    "matricula", "demora_salida_min", "demora_llegada_min", "taxi_out_min",
                    "es_puntual", "es_cancelado", "es_desviado", *COLUMNA_MINUTOS.values()]

COLUMNAS_SQL = """
    f.id_vuelo, d.fecha AS Fecha, f.numero_vuelo AS Vuelo, o.codigo_iata AS Origen,
           ds.codigo_iata AS Destino, f.sk_horario AS Hora, f.matricula AS Matrícula,
           f.demora_salida_min AS [Demora salida], f.demora_llegada_min AS [Demora llegada],
           f.taxi_out_min AS [Taxi-out], f.es_cancelado, f.es_desviado, cc.codigo AS codigo_cancelacion,
           e.estado AS Estado, rg.rango AS Rango, c.causa AS [Causa principal],
           f.min_causa_aerolinea, f.min_causa_clima, f.min_causa_trafico, f.min_causa_seguridad,
           f.min_causa_avion_tardio, f.origen_registro AS Registro
"""
FROM_SQL = """
    FROM FactVuelos f
    JOIN DimFecha d             ON f.sk_fecha = d.sk_fecha
    JOIN DimAeropuerto o        ON f.sk_origen = o.sk_aeropuerto
    JOIN DimAeropuerto ds       ON f.sk_destino = ds.sk_aeropuerto
    JOIN DimEstadoVuelo e       ON f.sk_estado = e.sk_estado
    JOIN DimRangoDemora rg      ON f.sk_rango_demora = rg.sk_rango_demora
    JOIN DimCausaDemora c       ON f.sk_causa_demora = c.sk_causa_demora
    JOIN DimCausaCancelacion cc ON f.sk_causa_cancelacion = cc.sk_causa_cancelacion
"""
COLUMNAS_VISIBLES = ["Fecha", "Vuelo", "Origen", "Destino", "Hora", "Matrícula", "Demora salida",
                     "Demora llegada", "Taxi-out", "Estado", "Rango", "Causa principal", "Registro"]


# ---------------------------------------------------------------- Catálogos ---
def leer_catalogos():
    """Aeropuertos, rutas y nombres de las dimensiones fijas (para listas y para el resumen)."""
    aeropuertos = consultar("SELECT codigo_iata, ciudad FROM DimAeropuerto ORDER BY codigo_iata")
    rutas = consultar("SELECT ruta, distancia_millas FROM DimRuta")
    estados = consultar("SELECT sk_estado, estado FROM DimEstadoVuelo")
    rangos = consultar("SELECT sk_rango_demora, rango FROM DimRangoDemora")
    causas = consultar("SELECT sk_causa_demora, codigo, causa FROM DimCausaDemora")
    cancelaciones = consultar("SELECT codigo, causa FROM DimCausaCancelacion WHERE codigo <> 'N' ORDER BY codigo")
    return {
        "aeropuertos": dict(zip(aeropuertos["codigo_iata"], aeropuertos["ciudad"])),
        "rutas": dict(zip(rutas["ruta"], rutas["distancia_millas"])),
        "estados": dict(zip(estados["sk_estado"], estados["estado"])),
        "rangos": dict(zip(rangos["sk_rango_demora"], rangos["rango"])),
        "causas": dict(zip(causas["sk_causa_demora"], causas["causa"])),
        "causa_por_codigo": dict(zip(causas["codigo"], causas["causa"])),
        "cancelaciones": dict(zip(cancelaciones["codigo"], cancelaciones["causa"])),
    }


def entero(valor):
    """Valor de la BD o de un widget → int, o None si está vacío."""
    numero = reglas.a_numero(valor)
    return None if numero is None else int(numero)


# ------------------------------------------------------------- Formularios ---
def elegir_aeropuerto(etiqueta, clave, aeropuertos, por_defecto):
    """Selectbox "código - ciudad" o nuevo aeropuerto; devuelve (código, datos del nuevo o None)."""
    opciones = [*aeropuertos, NUEVO]
    indice = opciones.index(por_defecto) if por_defecto in opciones else 0
    codigo = st.selectbox(etiqueta, opciones, index=indice, key=clave,
                          format_func=lambda c: "➕ Nuevo aeropuerto" if c == NUEVO else f"{c} - {aeropuertos[c]}")
    if codigo != NUEVO:
        return codigo, None
    with st.container(border=True):
        st.caption(f"Nuevo aeropuerto ({etiqueta.lower()})")
        nuevo = st.text_input("Código IATA (3 letras)", max_chars=3, key=f"{clave}_codigo").strip().upper()
        datos = {
            "ciudad": st.text_input("Ciudad", placeholder="Austin, TX", key=f"{clave}_ciudad").strip(),
            "estado": st.text_input("Estado (2 letras)", max_chars=2, key=f"{clave}_estado").strip().upper(),
        }
        col1, col2 = st.columns(2)
        datos["latitud"] = col1.number_input("Latitud (opcional)", value=None, min_value=-90.0, max_value=90.0,
                                             format="%.6f", key=f"{clave}_lat")
        datos["longitud"] = col2.number_input("Longitud (opcional)", value=None, min_value=-180.0,
                                              max_value=180.0, format="%.6f", key=f"{clave}_lon")
    return nuevo, datos


def campo_minutos(columna, etiqueta, valor, clave, ayuda=None):
    """number_input entero que puede quedar vacío (None = sin dato)."""
    return columna.number_input(etiqueta, value=entero(valor), step=1, key=clave, help=ayuda)


def formulario_medidas(clave, catalogos, inicial=None):
    """Campos que se pueden registrar y editar; devuelve un diccionario con lo ingresado."""
    inicial = inicial or {}
    col1, col2, _ = st.columns(3)
    hora_inicial = time(entero(inicial.get("Hora")) or 0, 0) if inicial else time(8, 0)
    m = {"hora": col1.time_input("Hora programada de salida", value=hora_inicial, key=f"{clave}_hora"),
         "matricula": col2.text_input("Matrícula (opcional)", value=inicial.get("Matrícula") or "",
                                      max_chars=10, key=f"{clave}_matricula").strip().upper() or None}

    col1, col2, col3 = st.columns(3)
    m["cancelado"] = col1.checkbox("Cancelado", value=bool(inicial.get("es_cancelado")), key=f"{clave}_cancelado")
    m["desviado"] = col2.checkbox("Desviado", value=bool(inicial.get("es_desviado")), key=f"{clave}_desviado")
    m["codigo_cancelacion"] = None
    if m["cancelado"]:
        codigos = list(catalogos["cancelaciones"])
        actual = inicial.get("codigo_cancelacion")
        m["codigo_cancelacion"] = col3.selectbox(
            "Causa de cancelación", codigos, index=codigos.index(actual) if actual in codigos else 0,
            format_func=lambda c: catalogos["cancelaciones"][c], key=f"{clave}_causa_cancelacion")

    col1, col2, col3 = st.columns(3)
    m["demora_salida"] = campo_minutos(col1, "Demora de salida (min)", inicial.get("Demora salida"),
                                       f"{clave}_salida", "Negativo = salió antes. Vacío si se canceló.")
    m["demora_llegada"] = campo_minutos(col2, "Demora de llegada (min)", inicial.get("Demora llegada"),
                                        f"{clave}_llegada", "Negativo = llegó antes. Vacío si se canceló o desvió.")
    m["taxi_out"] = campo_minutos(col3, "Taxi-out (min, opcional)", inicial.get("Taxi-out"), f"{clave}_taxi")

    st.markdown(f"**Minutos por causa** (solo si la demora de llegada es ≥ {reglas.UMBRAL_DEMORA} min)")
    columnas = st.columns(len(reglas.ORDEN_CAUSAS))
    m["minutos"] = {
        codigo: campo_minutos(columna, catalogos["causa_por_codigo"][codigo], inicial.get(COLUMNA_MINUTOS[codigo]),
                              f"{clave}_min_{codigo}")
        for codigo, columna in zip(reglas.ORDEN_CAUSAS, columnas)
    }
    return m


# ------------------------------------------------------ Validación y reglas ---
def validar_medidas(m):
    """Errores de las medidas según la especificación (lista vacía = todo bien)."""
    errores = []
    salida, llegada = m["demora_salida"], m["demora_llegada"]
    for nombre, valor in [("demora de salida", salida), ("demora de llegada", llegada)]:
        if valor is not None and not LIMITE_DEMORA[0] <= valor <= LIMITE_DEMORA[1]:
            errores.append(f"La {nombre} debe estar entre {LIMITE_DEMORA[0]} y {LIMITE_DEMORA[1]} minutos.")
    if m["taxi_out"] is not None and not LIMITE_TAXI_OUT[0] <= m["taxi_out"] <= LIMITE_TAXI_OUT[1]:
        errores.append(f"El taxi-out debe estar entre {LIMITE_TAXI_OUT[0]} y {LIMITE_TAXI_OUT[1]} minutos.")

    if m["cancelado"] and m["desviado"]:
        errores.append("Un vuelo no puede estar cancelado y desviado a la vez.")
    elif m["cancelado"]:
        if salida is not None or llegada is not None:
            errores.append("Un vuelo cancelado no tiene demoras: deja vacías la demora de salida y la de llegada.")
    elif m["desviado"]:
        if llegada is not None:
            errores.append("Un vuelo desviado no llegó a su destino: deja vacía la demora de llegada.")
        if salida is None:
            errores.append("Ingresa la demora de salida (el vuelo desviado sí despegó).")
    elif salida is None or llegada is None:
        errores.append("Ingresa la demora de salida y la de llegada (si no se canceló, ambas son obligatorias).")

    minutos = [v for v in m["minutos"].values() if v is not None]
    if any(v < 0 for v in minutos):
        errores.append("Los minutos por causa no pueden ser negativos.")
    if minutos and (m["cancelado"] or m["desviado"] or not reglas.calcular_arr_del15(llegada)):
        errores.append(f"Los minutos por causa solo se registran si la demora de llegada es de "
                       f"{reglas.UMBRAL_DEMORA} minutos o más: déjalos vacíos.")
    return errores


def validar_registro(fecha, numero, origen, nuevo_origen, destino, nuevo_destino, distancia, catalogos):
    """Errores de la clave natural, aeropuertos y ruta (solo al registrar)."""
    errores = []
    if numero is None or not 1 <= numero <= 9999:
        errores.append("El número de vuelo debe estar entre 1 y 9999.")
    for etiqueta, codigo, datos in [("origen", origen, nuevo_origen), ("destino", destino, nuevo_destino)]:
        if datos is None:
            continue
        if not re.fullmatch(r"[A-Z]{3}", codigo):
            errores.append(f"El código IATA del nuevo aeropuerto de {etiqueta} debe tener 3 letras.")
        elif codigo in catalogos["aeropuertos"]:
            errores.append(f"El aeropuerto {codigo} ya existe: elígelo de la lista de {etiqueta}.")
        if not datos["ciudad"]:
            errores.append(f"Ingresa la ciudad del nuevo aeropuerto de {etiqueta}.")
        if not re.fullmatch(r"[A-Z]{2}", datos["estado"]):
            errores.append(f"El estado del nuevo aeropuerto de {etiqueta} debe tener 2 letras (p. ej. TX).")
    if origen and origen == destino:
        errores.append("El origen y el destino deben ser distintos.")
    if f"{origen}-{destino}" not in catalogos["rutas"] and (
            distancia is None or not LIMITE_DISTANCIA[0] <= distancia <= LIMITE_DISTANCIA[1]):
        errores.append(f"La ruta {origen}-{destino} es nueva: ingresa su distancia "
                       f"({LIMITE_DISTANCIA[0]}–{LIMITE_DISTANCIA[1]} millas).")
    return errores


def derivar(m):
    """Claves derivadas con las reglas de src/reglas.py (las mismas del ETL)."""
    estado = reglas.calcular_estado(int(m["cancelado"]), int(m["desviado"]),
                                    reglas.calcular_arr_del15(m["demora_llegada"]))
    return {
        "sk_horario": reglas.calcular_horario(m["hora"].hour * 100 + m["hora"].minute),
        "sk_estado": estado,
        "sk_causa_demora": reglas.calcular_causa_principal(estado, m["minutos"]),
        "sk_causa_cancelacion": reglas.calcular_causa_cancelacion(m["codigo_cancelacion"]),
        "sk_rango_demora": reglas.calcular_rango(estado, m["demora_llegada"]),
    }


def valores_medidas(m, d):
    """Valores en el orden de COLUMNAS_MEDIDAS."""
    return [d["sk_horario"], d["sk_estado"], d["sk_causa_demora"], d["sk_causa_cancelacion"],
            d["sk_rango_demora"], m["matricula"], m["demora_salida"], m["demora_llegada"], m["taxi_out"],
            int(d["sk_estado"] == reglas.A_TIEMPO), int(d["sk_estado"] == reglas.CANCELADO),
            int(d["sk_estado"] == reglas.DESVIADO), *[m["minutos"][c] for c in COLUMNA_MINUTOS]]


def mostrar_resultado(d, m, catalogos, errores):
    """Muestra cómo quedará el vuelo con las reglas aplicadas (o los errores a corregir)."""
    if errores:
        st.warning("Corrige lo siguiente antes de guardar:\n\n" + "\n".join(f"- {e}" for e in errores))
        return
    partes = [catalogos["estados"][d["sk_estado"]], catalogos["rangos"][d["sk_rango_demora"]],
              catalogos["causas"][d["sk_causa_demora"]]]
    if m["cancelado"]:
        partes.append(f"Cancelación: {catalogos['cancelaciones'][m['codigo_cancelacion']]}")
    hora = d["sk_horario"]
    st.info(f"Este vuelo quedará como: **{' · '.join(partes)}**\n\n"
            f"Horario: {reglas.bloque(hora)} ({reglas.franja(hora)})")


def mostrar_error_bd(error, mensaje_duplicado):
    """Traduce los errores de SQL Server a mensajes en español."""
    texto = str(error)
    if isinstance(error, pyodbc.IntegrityError) and ("2601" in texto or "2627" in texto):
        st.error(mensaje_duplicado)
    elif es_error_de_conexion(error):
        mostrar_error_conexion(error)
    else:
        st.error(f"SQL Server rechazó la operación:\n\n{error.args[-1] if error.args else error}")


def terminar(mensaje):
    """Guarda un mensaje de éxito y recarga la página (así se ven los datos actualizados)."""
    st.session_state["mensaje_gestion"] = mensaje
    st.rerun()


# ---------------------------------------------------------------- Registrar ---
def sentencias_registro(fecha, numero, origen, nuevo_origen, destino, nuevo_destino, distancia, m, d):
    """INSERTs de fecha, aeropuertos y ruta faltantes y del vuelo, para una sola transacción."""
    fila_fecha = reglas.atributos_fecha(fecha)
    sentencias = [(
        "IF NOT EXISTS (SELECT 1 FROM DimFecha WHERE sk_fecha = ?) "
        "INSERT INTO DimFecha (sk_fecha, fecha, anio, trimestre, mes, nombre_mes, nombre_dia, "
        "es_fin_semana, es_feriado) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", (fila_fecha[0], *fila_fecha))]
    for codigo, datos in [(origen, nuevo_origen), (destino, nuevo_destino)]:
        if datos:
            sentencias.append((
                "INSERT INTO DimAeropuerto (codigo_iata, ciudad, estado, latitud, longitud) VALUES (?, ?, ?, ?, ?)",
                (codigo, datos["ciudad"], datos["estado"], datos["latitud"], datos["longitud"])))
    ruta = f"{origen}-{destino}"
    sentencias.append((
        "IF NOT EXISTS (SELECT 1 FROM DimRuta WHERE ruta = ?) "
        "INSERT INTO DimRuta (ruta, origen, destino, distancia_millas, tipo_distancia) VALUES (?, ?, ?, ?, ?)",
        (ruta, ruta, origen, destino, distancia, reglas.tipo_distancia(distancia))))
    columnas = ["sk_fecha", "numero_vuelo", "sk_origen", "sk_destino", "sk_ruta", *COLUMNAS_MEDIDAS, "origen_registro"]
    sentencias.append((
        f"INSERT INTO FactVuelos ({', '.join(columnas)}) SELECT ?, ?, "
        "(SELECT sk_aeropuerto FROM DimAeropuerto WHERE codigo_iata = ?), "
        "(SELECT sk_aeropuerto FROM DimAeropuerto WHERE codigo_iata = ?), "
        "(SELECT sk_ruta FROM DimRuta WHERE ruta = ?), "
        f"{', '.join('?' * len(COLUMNAS_MEDIDAS))}, 'APP'",
        (fila_fecha[0], numero, origen, destino, ruta, *valores_medidas(m, d))))
    return sentencias


def pestana_registrar(catalogos):
    """Formulario para registrar un vuelo nuevo."""
    col1, col2 = st.columns(2)
    fecha = col1.date_input("Fecha del vuelo", value=date.today(), format="DD/MM/YYYY", key="reg_fecha")
    numero = entero(col2.number_input("Número de vuelo", value=None, step=1, key="reg_numero"))

    col1, col2 = st.columns(2)
    with col1:
        origen, nuevo_origen = elegir_aeropuerto("Origen", "reg_origen", catalogos["aeropuertos"], "JFK")
    with col2:
        destino, nuevo_destino = elegir_aeropuerto("Destino", "reg_destino", catalogos["aeropuertos"], "BOS")

    ruta = f"{origen}-{destino}"
    distancia = entero(catalogos["rutas"].get(ruta))
    if ruta in catalogos["rutas"]:
        texto = f"{distancia:,} millas ({reglas.tipo_distancia(distancia)})" if distancia else "sin distancia"
        st.caption(f"Ruta {ruta}: {texto}.")
    elif origen and destino and origen != destino:
        distancia = entero(st.number_input(f"Distancia de la ruta nueva {ruta} (millas)", value=None, step=1,
                                           key="reg_distancia"))

    m = formulario_medidas("reg", catalogos)
    errores = validar_registro(fecha, numero, origen, nuevo_origen, destino, nuevo_destino, distancia,
                               catalogos) + validar_medidas(m)
    d = derivar(m) if not errores else None
    mostrar_resultado(d, m, catalogos, errores)

    if st.button("Registrar vuelo", type="primary", disabled=bool(errores)):
        try:
            ejecutar_transaccion(sentencias_registro(fecha, numero, origen, nuevo_origen, destino,
                                                     nuevo_destino, distancia, m, d))
        except pyodbc.Error as e:
            mostrar_error_bd(e, f"Ya existe el vuelo {numero} del {fecha:%d/%m/%Y} con origen {origen}. "
                                "Si fue registrado desde la app, puedes cambiarlo en la pestaña Editar.")
            return
        terminar(f"Vuelo {numero} {ruta} del {fecha:%d/%m/%Y} registrado.")


# --------------------------------------------------------- Editar / Eliminar ---
def buscar_vuelo(clave, catalogos):
    """Busca un vuelo por su clave natural; devuelve la fila solo si se registró desde la app."""
    col1, col2, col3, col4 = st.columns([2, 2, 3, 1], vertical_alignment="bottom")
    fecha = col1.date_input("Fecha", value=date.today(), format="DD/MM/YYYY", key=f"{clave}_fecha")
    numero = entero(col2.number_input("Número de vuelo", value=None, step=1, key=f"{clave}_numero"))
    aeropuertos = catalogos["aeropuertos"]
    origen = col3.selectbox("Origen", list(aeropuertos), key=f"{clave}_origen",
                            format_func=lambda c: f"{c} - {aeropuertos[c]}")
    if col4.button("Buscar", key=f"{clave}_buscar"):
        st.session_state[f"{clave}_clave"] = (int(fecha.strftime("%Y%m%d")), numero, origen)

    clave_natural = st.session_state.get(f"{clave}_clave")
    if not clave_natural or clave_natural[1] is None:
        st.caption("Ingresa fecha, número de vuelo y origen, y presiona Buscar.")
        return None
    df = consultar(f"SELECT {COLUMNAS_SQL} {FROM_SQL} "
                   "WHERE f.sk_fecha = ? AND f.numero_vuelo = ? AND o.codigo_iata = ?", clave_natural)
    if df.empty:
        st.info("No hay un vuelo con esa fecha, número y origen.")
        return None
    st.dataframe(df[COLUMNAS_VISIBLES], hide_index=True)
    fila = df.astype(object).where(df.notna(), None).iloc[0].to_dict()  # NaN → None
    if fila["Registro"] != "APP":
        st.info("Este vuelo viene de los datos reales de BTS (ETL) y es de solo lectura: "
                "desde la app solo se editan o eliminan vuelos registrados en la app.")
        return None
    return fila


def pestana_editar(catalogos):
    """Busca un vuelo, permite cambiar sus medidas y recalcula las claves derivadas."""
    fila = buscar_vuelo("edi", catalogos)
    if fila is None:
        return
    st.markdown("**Nuevos valores** (fecha, número y ruta no se cambian: forman la clave del vuelo)")
    m = formulario_medidas(f"edi_{fila['id_vuelo']}", catalogos, fila)
    errores = validar_medidas(m)
    d = derivar(m) if not errores else None
    mostrar_resultado(d, m, catalogos, errores)
    if st.button("Guardar cambios", type="primary", disabled=bool(errores)):
        asignaciones = ", ".join(f"{c} = ?" for c in COLUMNAS_MEDIDAS)
        try:
            filas = ejecutar_transaccion([(f"UPDATE FactVuelos SET {asignaciones} "
                                           f"WHERE id_vuelo = ? AND {SOLO_APP}",
                                           (*valores_medidas(m, d), int(fila["id_vuelo"])))])
        except pyodbc.Error as e:
            mostrar_error_bd(e, "Ya existe otro vuelo con esa clave.")
            return
        if filas == 0:
            st.error("No se actualizó nada: el vuelo ya no existe o no fue registrado desde la app.")
            return
        terminar(f"Vuelo {fila['Vuelo']} {fila['Origen']}-{fila['Destino']} actualizado.")


def pestana_eliminar(catalogos):
    """Busca un vuelo y lo elimina tras confirmar."""
    fila = buscar_vuelo("eli", catalogos)
    if fila is None:
        return
    confirmado = st.checkbox("Confirmo que quiero eliminar este vuelo (no se puede deshacer)",
                             key=f"eli_confirmar_{fila['id_vuelo']}")
    if st.button("Eliminar vuelo", type="primary", disabled=not confirmado):
        try:
            filas = ejecutar_transaccion([(f"DELETE FROM FactVuelos WHERE id_vuelo = ? AND {SOLO_APP}",
                                           (int(fila["id_vuelo"]),))])
        except pyodbc.Error as e:
            mostrar_error_bd(e, "No se pudo eliminar el vuelo.")
            return
        if filas == 0:
            st.error("No se eliminó nada: el vuelo ya no existe o no fue registrado desde la app.")
            return
        st.session_state.pop("eli_clave", None)
        terminar(f"Vuelo {fila['Vuelo']} {fila['Origen']}-{fila['Destino']} del {fila['Fecha']:%d/%m/%Y} eliminado.")


def ultimos_registros():
    """Últimos 20 vuelos registrados desde la app."""
    st.subheader("Últimos vuelos registrados desde la app")
    df = consultar(f"SELECT TOP 20 {COLUMNAS_SQL} {FROM_SQL} "
                   "WHERE f.origen_registro = 'APP' ORDER BY f.fecha_carga DESC, f.id_vuelo DESC")
    if df.empty:
        st.caption("Todavía no hay vuelos registrados desde la app.")
    else:
        st.dataframe(df[COLUMNAS_VISIBLES[:-1]], hide_index=True)


# -------------------------------------------------------------------- Página ---
st.title("Gestión de vuelos")
st.caption("Registra, edita o elimina vuelos del Data Mart. El estado, el rango de demora y la causa "
           "principal se calculan con las mismas reglas del ETL.")

if "mensaje_gestion" in st.session_state:
    st.success(st.session_state.pop("mensaje_gestion"))

try:
    catalogos = leer_catalogos()
    registrar, editar, eliminar = st.tabs(["Registrar", "Editar", "Eliminar"])
    with registrar:
        pestana_registrar(catalogos)
    with editar:
        pestana_editar(catalogos)
    with eliminar:
        pestana_eliminar(catalogos)
    st.divider()
    ultimos_registros()
except pyodbc.Error as e:
    mostrar_error_conexion(e)
