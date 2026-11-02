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

# Usuarios de la app (sql/03_usuarios_app.sql): lector solo lee, editor también escribe
DB_LECTOR_USER = os.getenv("DB_LECTOR_USER", "app_lector")
DB_LECTOR_PASSWORD = os.getenv("DB_LECTOR_PASSWORD")
DB_EDITOR_USER = os.getenv("DB_EDITOR_USER", "app_editor")
DB_EDITOR_PASSWORD = os.getenv("DB_EDITOR_PASSWORD")

INTENTOS = 3
ESPERA_SEGUNDOS = 20  # la BD serverless de Azure se pausa y tarda en despertar


def cadena_conexion(base_datos, usuario=None, clave=None):
    """Arma la cadena de conexión según sea servidor local o Azure (por defecto, usuario del .env)."""
    cadena = (
        f"DRIVER={{{DB_DRIVER}}};"
        f"SERVER={DB_SERVER};"
        f"DATABASE={base_datos};"
        f"UID={usuario or DB_USER};"
        f"PWD={clave or DB_PASSWORD};"
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
            conn = pyodbc.connect(cadena_conexion(base_datos))
            print(f"✓ Conexión a {etiqueta} exitosa ({base_datos})")
            return conn
        except pyodbc.Error as e:
            print(f"Error de conexión a {etiqueta} (intento {intento}/{INTENTOS}): {e}")
            if "Can't open lib" in str(e) or "IM002" in str(e):
                print(f"  Falta instalar el driver '{DB_DRIVER}' (ver README). No se reintenta.")
                return None
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


def a_filas(df):
    """Convierte un DataFrame en lista de filas con tipos de Python (NaN → None)."""
    return df.astype(object).where(df.notna(), None).values.tolist()


def insertar_por_lotes(conn, sql, filas, tamano_lote=5000):
    """Inserta filas con fast_executemany en lotes de 5,000."""
    cursor = conn.cursor()
    cursor.fast_executemany = True
    for inicio in range(0, len(filas), tamano_lote):
        cursor.executemany(sql, filas[inicio:inicio + tamano_lote])
        conn.commit()
        print(f"\r  {min(inicio + tamano_lote, len(filas)):,} / {len(filas):,} filas", end="")
    print()


if __name__ == "__main__":
    for funcion in (get_connection_origen, get_connection_destino):
        conn = funcion()
        if conn:
            conn.close()
