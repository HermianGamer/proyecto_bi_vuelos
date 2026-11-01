# -*- coding: utf-8 -*-
"""
Conexiones a las bases de datos del proyecto (estilo del profesor).

BD origen : VuelosOrigen (staging)
BD destino: VuelosDW     (data mart)

Las credenciales se leen del archivo .env (local) o de las App Settings (Azure).
"""

import os
import time

import pyodbc
from dotenv import load_dotenv

load_dotenv()

DB_DRIVER = os.getenv("DB_DRIVER", "ODBC Driver 18 for SQL Server")
DB_SERVER = os.getenv("DB_SERVER", "localhost")
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_ORIGEN = os.getenv("DB_ORIGEN", "VuelosOrigen")
DB_DW = os.getenv("DB_DW", "VuelosDW")

INTENTOS = 3
ESPERA_SEGUNDOS = 20  # la BD serverless de Azure se pausa y tarda en despertar


def _cadena_conexion(base_datos):
    """Arma la cadena de conexión según sea servidor local o Azure."""
    cadena = (
        f"DRIVER={{{DB_DRIVER}}};"
        f"SERVER={DB_SERVER};"
        f"DATABASE={base_datos};"
        f"UID={DB_USER};"
        f"PWD={DB_PASSWORD};"
    )
    if DB_SERVER.split(",")[0] in ("localhost", "127.0.0.1", "."):
        cadena += "TrustServerCertificate=yes;"
    else:
        cadena += "Encrypt=yes;TrustServerCertificate=no;Connection Timeout=60;"
    return cadena


def _conectar(base_datos, etiqueta):
    """Intenta conectarse hasta 3 veces; devuelve la conexión o None."""
    for intento in range(1, INTENTOS + 1):
        try:
            conn = pyodbc.connect(_cadena_conexion(base_datos))
            print(f"✓ Conexión a {etiqueta} exitosa ({base_datos})")
            return conn
        except pyodbc.Error as e:
            print(f"Error de conexión a {etiqueta} (intento {intento}/{INTENTOS}): {e}")
            if intento < INTENTOS:
                print(f"  Reintentando en {ESPERA_SEGUNDOS} s (la BD puede estar despertando)...")
                time.sleep(ESPERA_SEGUNDOS)
    return None


def get_connection_origen():
    """Conexión a la BD de staging (VuelosOrigen)."""
    return _conectar(DB_ORIGEN, "origen")


def get_connection_destino():
    """Conexión a la BD del data mart (VuelosDW)."""
    return _conectar(DB_DW, "destino")


if __name__ == "__main__":
    for funcion in (get_connection_origen, get_connection_destino):
        conn = funcion()
        if conn:
            conn.close()
