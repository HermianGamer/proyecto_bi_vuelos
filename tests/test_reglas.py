# -*- coding: utf-8 -*-
"""Pruebas de las reglas de derivación (src/reglas.py)."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from datetime import date  # noqa: E402

from reglas import (  # noqa: E402
    a_numero, atributos_fecha, bloque, calcular_arr_del15, calcular_causa_cancelacion, calcular_causa_principal,
    calcular_estado, calcular_horario, calcular_rango, franja, tipo_distancia,
)

NAN = float("nan")


# --- a_numero ---
@pytest.mark.parametrize("valor, esperado", [
    ("15.00", 15.0), (7, 7.0), ("", None), ("  ", None), (None, None), (NAN, None),
])
def test_a_numero(valor, esperado):
    assert a_numero(valor) == esperado


# --- calcular_horario ---
@pytest.mark.parametrize("hhmm, hora", [
    ("0005", 0), ("0600", 6), ("0659", 6), (1359, 13), ("2359", 23), ("2400", 0), (2400.0, 0),
])
def test_calcular_horario(hhmm, hora):
    assert calcular_horario(hhmm) == hora


def test_calcular_horario_vacio_falla():
    with pytest.raises(ValueError):
        calcular_horario(None)


# --- calcular_estado ---
@pytest.mark.parametrize("cancelado, desviado, del15, estado", [
    ("1.00", "0.00", None, 3),
    ("1.00", "1.00", None, 3),   # cancelado tiene prioridad sobre desviado
    ("0.00", "1.00", None, 4),
    ("0.00", "0.00", "1.00", 2),
    ("0.00", "0.00", "0.00", 1),
    (0, 0, NAN, 1),              # ArrDel15 NULL y no cancelado → a tiempo
])
def test_calcular_estado(cancelado, desviado, del15, estado):
    assert calcular_estado(cancelado, desviado, del15) == estado


# --- calcular_rango ---
@pytest.mark.parametrize("estado, demora, rango", [
    (3, None, 0), (4, "30.00", 0),
    (1, "-1.00", 1), (1, "0.00", 2), (1, "14.00", 2),
    (2, "15.00", 3),             # exactamente 15 min ya es "Leve"
    (2, "44.00", 3), (2, "45.00", 4), (2, "119.00", 4), (2, "120.00", 5), (2, 600, 5),
    (1, None, 0), (1, NAN, 0),   # sin demora informada → No aplica
])
def test_calcular_rango(estado, demora, rango):
    assert calcular_rango(estado, demora) == rango


def test_estado_y_rango_coinciden_en_15_min():
    estado = calcular_estado("0.00", "0.00", "1.00")
    assert estado == 2 and calcular_rango(estado, "15.00") == 3


# --- calcular_causa_principal ---
def minutos(car=None, wea=None, nas=None, sec=None, lat=None):
    """Arma el diccionario de minutos por causa."""
    return {"CAR": car, "WEA": wea, "NAS": nas, "SEC": sec, "LAT": lat}


@pytest.mark.parametrize("estado, mins, causa", [
    (3, minutos(), 0),
    (4, minutos(car="20"), 0),
    (1, minutos(), 1),
    (2, minutos(car="30", wea="0", nas="5", sec="0", lat="10"), 2),
    (2, minutos(wea="40", car="10"), 3),
    (2, minutos(nas="25"), 4),
    (2, minutos(sec="16"), 5),
    (2, minutos(lat="60", car="59"), 6),
])
def test_causa_principal(estado, mins, causa):
    assert calcular_causa_principal(estado, mins) == causa


@pytest.mark.parametrize("mins, causa", [
    (minutos(car="20", lat="20"), 2),           # CAR gana a LAT
    (minutos(lat="20", nas="20", wea="20"), 6),  # LAT gana a NAS y WEA
    (minutos(nas="20", wea="20", sec="20"), 4),  # NAS gana a WEA y SEC
    (minutos(wea="20", sec="20"), 3),            # WEA gana a SEC
])
def test_causa_principal_empates(mins, causa):
    assert calcular_causa_principal(2, mins) == causa


@pytest.mark.parametrize("mins", [
    minutos(),                                    # todo NULL
    minutos(car="0", wea="0", nas="0", sec="0", lat="0"),
    minutos(car=NAN, wea="", nas=None),
    {},                                           # sin claves
])
def test_causa_principal_sin_dato(mins):
    assert calcular_causa_principal(2, mins) == 7


# --- calcular_causa_cancelacion ---
@pytest.mark.parametrize("codigo, sk", [
    (None, 0), (NAN, 0), ("", 0), ("N", 0), ("A", 1), ("B", 2), ("C", 3), ("D", 4), (" a ", 1),
])
def test_causa_cancelacion(codigo, sk):
    assert calcular_causa_cancelacion(codigo) == sk


def test_causa_cancelacion_desconocida_falla():
    with pytest.raises(ValueError):
        calcular_causa_cancelacion("X")


# --- tipo_distancia, franja, bloque ---
@pytest.mark.parametrize("millas, tipo", [
    ("187.00", "Corta"), (699, "Corta"), (700, "Media"), (1500, "Media"), (1501, "Larga"),
    (None, None), (NAN, None),
])
def test_tipo_distancia(millas, tipo):
    assert tipo_distancia(millas) == tipo


@pytest.mark.parametrize("hora, nombre", [
    (0, "Madrugada"), (5, "Madrugada"), (6, "Mañana"), (11, "Mañana"),
    (12, "Tarde"), (17, "Tarde"), (18, "Noche"), (23, "Noche"),
])
def test_franja(hora, nombre):
    assert franja(hora) == nombre


@pytest.mark.parametrize("hora, texto", [(0, "0000-0059"), (6, "0600-0659"), (23, "2300-2359")])
def test_bloque(hora, texto):
    assert bloque(hora) == texto
    assert len(texto) == 9  # cabe en CHAR(9)


# --- calcular_arr_del15 ---
@pytest.mark.parametrize("demora, indicador", [
    (-5, 0), (0, 0), (14, 0), (15, 1), (300, 1), (None, 0), ("", 0), ("15.00", 1),
])
def test_arr_del15(demora, indicador):
    assert calcular_arr_del15(demora) == indicador


# --- atributos_fecha ---
def test_atributos_fecha_dia_normal():
    assert atributos_fecha(date(2026, 7, 15)) == (20260715, date(2026, 7, 15), 2026, 3, 7, "Julio",
                                                  "Miércoles", 0, 0)


def test_atributos_fecha_feriado_en_fin_de_semana():
    # 4 de julio de 2026 cae sábado y es feriado federal
    fila = atributos_fecha(date(2026, 7, 4))
    assert fila[6:] == ("Sábado", 1, 1)
