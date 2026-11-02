# -*- coding: utf-8 -*-
"""
Pruebas de permisos en la base de datos (requieren el SQL Server con VuelosDW y los usuarios creados).

Se conectan directo con pyodbc, SIN pasar por el validador de la consola, para demostrar que
la base de datos misma rechaza las escrituras de app_lector. Si no hay conexión, se omiten.
"""

import sys
from pathlib import Path

import pyodbc
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from conexion import (  # noqa: E402
    DB_DW, DB_EDITOR_PASSWORD, DB_EDITOR_USER, DB_LECTOR_PASSWORD, DB_LECTOR_USER, cadena_conexion,
)

PERMISO_DENEGADO = ("229", "262", "3704", "1088", "4701")  # códigos de SQL Server para "permission denied"

ESCRITURAS = [
    "INSERT INTO DimHorario (sk_horario, bloque, franja) VALUES (99, 'X', 'X')",
    "UPDATE FactVuelos SET es_puntual = 1 WHERE id_vuelo = 1",
    "DELETE FROM FactVuelos WHERE id_vuelo = 1",
    "TRUNCATE TABLE FactVuelos",
    "DROP TABLE DimRangoDemora",
    "CREATE TABLE prueba_hack (id INT)",
    "SELECT * INTO copia_vuelos FROM DimRuta",
]


def conectar(usuario, clave):
    """Conexión sin autocommit (todo se deshace al final) o se omite la prueba si no hay BD."""
    try:
        return pyodbc.connect(cadena_conexion(DB_DW, usuario, clave), timeout=10)
    except pyodbc.Error as e:
        pytest.skip(f"Sin conexión a {DB_DW} como {usuario}: {e.args[0]}")


@pytest.fixture(scope="module")
def lector():
    conn = conectar(DB_LECTOR_USER, DB_LECTOR_PASSWORD)
    yield conn
    conn.rollback()
    conn.close()


@pytest.fixture(scope="module")
def editor():
    conn = conectar(DB_EDITOR_USER, DB_EDITOR_PASSWORD)
    yield conn
    conn.rollback()
    conn.close()


def test_lector_puede_leer(lector):
    assert lector.cursor().execute("SELECT COUNT(*) FROM FactVuelos").fetchone()[0] > 0


@pytest.mark.parametrize("sql", ESCRITURAS)
def test_lector_no_puede_escribir(lector, sql):
    with pytest.raises(pyodbc.Error) as error:
        lector.cursor().execute(sql)
    lector.rollback()
    mensaje = str(error.value)
    print(f"\n  {sql[:45]:<45} → {mensaje.split('[SQL Server]')[-1][:90]}")
    assert "permission" in mensaje.lower() or any(f"({c})" in mensaje for c in PERMISO_DENEGADO)


def test_editor_puede_escribir_en_hechos(editor):
    """app_editor sí puede modificar FactVuelos (se deshace con ROLLBACK)."""
    cursor = editor.cursor()
    cursor.execute("UPDATE TOP (1) FactVuelos SET origen_registro = origen_registro")
    assert cursor.rowcount == 1
    editor.rollback()


@pytest.mark.parametrize("sql", ["DROP TABLE DimRangoDemora", "DELETE FROM DimCausaDemora",
                                 "UPDATE DimAeropuerto SET ciudad = ciudad"])
def test_editor_no_puede_tocar_otras_tablas(editor, sql):
    with pytest.raises(pyodbc.Error) as error:
        editor.cursor().execute(sql)
    editor.rollback()
    assert "permission" in str(error.value).lower() or "(3701)" in str(error.value)
