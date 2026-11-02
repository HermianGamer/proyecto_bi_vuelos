# -*- coding: utf-8 -*-
"""Pruebas del validador de la consola SQL (app/validador_sql.py)."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "app"))

from validador_sql import validar_consulta  # noqa: E402


@pytest.mark.parametrize("sql", [
    "SELECT * FROM DimAeropuerto",
    "select top 10 ruta from DimRuta",
    "  \n SELECT COUNT(*) FROM FactVuelos;  ",                       # un ; al final
    "WITH t AS (SELECT sk_fecha FROM DimFecha) SELECT * FROM t",
    "-- comentario inicial\nSELECT 1",
    "/* bloque */ SELECT 1",
    "SELECT fecha_carga, origen_registro FROM FactVuelos",          # 'fecha_carga' no es una palabra prohibida
    "SELECT * FROM DimCausaDemora WHERE causa = 'Seguridad'",
    "SELECT o.codigo_iata FROM FactVuelos f JOIN DimAeropuerto o ON f.sk_origen = o.sk_aeropuerto",
])
def test_consultas_permitidas(sql):
    ok, _ = validar_consulta(sql)
    assert ok


@pytest.mark.parametrize("sql, motivo", [
    ("", "Escribe"),
    ("   ;  ", "Escribe"),
    ("-- solo un comentario", "Escribe"),
    ("INSERT INTO DimFecha VALUES (1)", "SELECT o WITH"),
    ("DELETE FROM FactVuelos", "SELECT o WITH"),
    ("EXEC sp_who", "SELECT o WITH"),
    ("SELECT 1; DROP TABLE FactVuelos", "no uses ;"),
    ("SELECT 1; SELECT 2", "no uses ;"),
    ("SELECT 1;;", "no uses ;"),
    ("WITH t AS (SELECT 1 AS x) DELETE FROM FactVuelos", "DELETE"),
    ("WITH t AS (SELECT 1 AS x) UPDATE FactVuelos SET es_puntual = 1", "UPDATE"),
    ("SELECT * INTO copia FROM FactVuelos", "INTO"),
    ("SELECT * FROM DimRuta /* ; */ ; TRUNCATE TABLE DimRuta", "no uses ;"),
    ("select 1 exec('drop table x')", "no permitida"),  # EXEC y DROP: avisa la primera
    ("SELECT 1 MERGE", "MERGE"),
    ("SELECT 1 WHERE 1 = 1 GRANT", "GRANT"),
    ("SELECT 1 aLtEr", "ALTER"),
    ("SELECT 1 CREATE", "CREATE"),
    ("SELECTX * FROM DimRuta", "SELECT o WITH"),                     # palabra completa, no prefijo
])
def test_consultas_bloqueadas(sql, motivo):
    ok, mensaje = validar_consulta(sql)
    assert not ok
    assert motivo in mensaje
