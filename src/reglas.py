# -*- coding: utf-8 -*-
"""
Reglas de derivación del modelo dimensional (docs/01_modelo_dimensional.md).

Se usan tanto en el ETL como en el formulario del dashboard, por eso
viven SOLO aquí. Son funciones puras: no tocan la base de datos.

Los valores de entrada pueden venir como texto del CSV ("15.00"), números,
None o NaN; todos los vacíos se tratan como NULL.
"""

import math

# Orden de desempate de causas: CAR, LAT, NAS, WEA, SEC
ORDEN_CAUSAS = ["CAR", "LAT", "NAS", "WEA", "SEC"]
SK_CAUSA = {"CAR": 2, "WEA": 3, "NAS": 4, "SEC": 5, "LAT": 6}
SK_CANCELACION = {"N": 0, "A": 1, "B": 2, "C": 3, "D": 4}

# sk de DimEstadoVuelo
A_TIEMPO, DEMORADO, CANCELADO, DESVIADO = 1, 2, 3, 4


def a_numero(valor):
    """Convierte un valor a float; devuelve None si está vacío o es NaN."""
    if valor is None:
        return None
    if isinstance(valor, str):
        valor = valor.strip()
        if valor == "":
            return None
    numero = float(valor)
    return None if math.isnan(numero) else numero


def _es_uno(valor):
    """True si el indicador BTS vale 1 (acepta "1.00", 1, 1.0)."""
    return a_numero(valor) == 1


def calcular_horario(crs_dep_time):
    """Hora programada de salida (hhmm) → hora 0–23; 2400 se toma como 0."""
    hhmm = a_numero(crs_dep_time)
    if hhmm is None:
        raise ValueError("CRSDepTime no puede estar vacío")
    hora = int(hhmm) // 100
    return 0 if hora == 24 else hora


def calcular_estado(cancelado, desviado, arr_del15):
    """Estado del vuelo: cancelado → desviado → demorado → a tiempo."""
    if _es_uno(cancelado):
        return CANCELADO
    if _es_uno(desviado):
        return DESVIADO
    if _es_uno(arr_del15):
        return DEMORADO
    return A_TIEMPO


def calcular_rango(estado, demora_llegada):
    """Rango de demora de llegada (sk de DimRangoDemora)."""
    demora = a_numero(demora_llegada)
    if estado in (CANCELADO, DESVIADO) or demora is None:
        return 0  # No aplica
    if demora < 0:
        return 1
    if demora < 15:
        return 2
    if demora < 45:
        return 3
    if demora < 120:
        return 4
    return 5


def calcular_causa_principal(estado, minutos):
    """Causa con más minutos (sk de DimCausaDemora); minutos = {"CAR": .., "WEA": .., ...}."""
    if estado in (CANCELADO, DESVIADO):
        return 0  # No aplica
    if estado == A_TIEMPO:
        return 1  # Sin demora
    mejor_causa, mejor_minutos = None, 0
    for causa in ORDEN_CAUSAS:
        valor = a_numero(minutos.get(causa)) or 0
        if valor > mejor_minutos:  # ">" estricto: en empate gana la primera del orden
            mejor_causa, mejor_minutos = causa, valor
    return SK_CAUSA[mejor_causa] if mejor_causa else 7  # 7 = Sin dato


def calcular_causa_cancelacion(codigo):
    """Código de cancelación BTS (A–D) → sk de DimCausaCancelacion; vacío o N → 0."""
    if codigo is None or (isinstance(codigo, float) and math.isnan(codigo)):
        return 0
    codigo = str(codigo).strip().upper()
    if codigo == "":
        return 0
    if codigo not in SK_CANCELACION:
        raise ValueError(f"Código de cancelación desconocido: {codigo}")
    return SK_CANCELACION[codigo]


def tipo_distancia(millas):
    """Corta (<700 mi), Media (700–1500) o Larga (>1500); None si no hay dato."""
    distancia = a_numero(millas)
    if distancia is None:
        return None
    if distancia < 700:
        return "Corta"
    if distancia <= 1500:
        return "Media"
    return "Larga"


def franja(hora):
    """Franja del día para una hora 0–23."""
    if hora <= 5:
        return "Madrugada"
    if hora <= 11:
        return "Mañana"
    if hora <= 17:
        return "Tarde"
    return "Noche"


def bloque(hora):
    """Bloque horario como texto, p. ej. 6 → "0600-0659"."""
    return f"{hora:02d}00-{hora:02d}59"
