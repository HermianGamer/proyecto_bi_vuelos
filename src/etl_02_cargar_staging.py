# -*- coding: utf-8 -*-
"""
ETL paso 2: carga de los CSV de JetBlue (data/b6_*.csv) a la BD de staging.

BD destino: VuelosOrigen.dbo.stg_vuelos (se vacía y se vuelve a cargar).
"""

import sys
from pathlib import Path

import pandas as pd

from conexion import a_filas, get_connection_origen, insertar_por_lotes

RAIZ = Path(__file__).resolve().parent.parent
CARPETA_DATA = RAIZ / "data"
SCRIPT_STAGING = RAIZ / "sql" / "01_crear_staging.sql"

COLUMNAS = [
    "FlightDate", "Reporting_Airline", "Flight_Number_Reporting_Airline", "Tail_Number",
    "Origin", "OriginCityName", "OriginState", "OriginStateName",
    "Dest", "DestCityName", "DestState", "DestStateName",
    "CRSDepTime", "DepDelay", "ArrDelay", "ArrDel15", "TaxiOut",
    "Cancelled", "CancellationCode", "Diverted", "Distance",
    "CarrierDelay", "WeatherDelay", "NASDelay", "SecurityDelay", "LateAircraftDelay",
]
COLUMNAS_ENTERAS = [
    "Flight_Number_Reporting_Airline", "CRSDepTime", "ArrDel15", "Cancelled", "Diverted", "Distance",
]
COLUMNAS_DECIMALES = [
    "DepDelay", "ArrDelay", "TaxiOut",
    "CarrierDelay", "WeatherDelay", "NASDelay", "SecurityDelay", "LateAircraftDelay",
]


def crear_tabla_staging(conn):
    """Crea stg_vuelos si no existe (script sql/01_crear_staging.sql)."""
    conn.cursor().execute(SCRIPT_STAGING.read_text(encoding="utf-8"))
    conn.commit()
    print("✓ Tabla stg_vuelos lista")


def leer_csvs():
    """Lee y une todos los data/b6_*.csv con los tipos correctos."""
    archivos = sorted(CARPETA_DATA.glob("b6_*.csv"))
    if not archivos:
        print("No hay archivos data/b6_*.csv. Ejecute primero etl_01_descargar.py")
        sys.exit(1)
    print(f"Leyendo {len(archivos)} archivos: {', '.join(a.name for a in archivos)}")
    df = pd.concat([pd.read_csv(a, dtype=str) for a in archivos], ignore_index=True)
    df["FlightDate"] = pd.to_datetime(df["FlightDate"]).dt.date
    for col in COLUMNAS_ENTERAS:
        df[col] = pd.to_numeric(df[col]).round().astype("Int64")
    for col in COLUMNAS_DECIMALES:
        df[col] = pd.to_numeric(df[col])
    return df[COLUMNAS]


def cargar_staging(conn, df):
    """Vacía stg_vuelos y la carga en lotes."""
    conn.cursor().execute("TRUNCATE TABLE dbo.stg_vuelos")
    conn.commit()
    print(f"Cargando {len(df):,} filas en stg_vuelos...")
    sql = f"INSERT INTO dbo.stg_vuelos ({', '.join(COLUMNAS)}) VALUES ({', '.join('?' * len(COLUMNAS))})"
    insertar_por_lotes(conn, sql, a_filas(df))


def resumen_por_mes(conn):
    """Imprime las filas cargadas por mes."""
    consulta = """
        SELECT FORMAT(FlightDate, 'yyyy-MM') AS mes, COUNT(*) AS filas
        FROM dbo.stg_vuelos GROUP BY FORMAT(FlightDate, 'yyyy-MM') ORDER BY mes
    """
    filas = conn.cursor().execute(consulta).fetchall()
    print("\nFilas en stg_vuelos por mes:")
    for mes, cantidad in filas:
        print(f"  {mes}  {cantidad:>8,}")
    print(f"  TOTAL    {sum(f[1] for f in filas):>8,}")


def main():
    """Ejecuta la carga completa del staging."""
    conn = get_connection_origen()
    if not conn:
        sys.exit(1)
    crear_tabla_staging(conn)
    cargar_staging(conn, leer_csvs())
    resumen_por_mes(conn)
    conn.close()
    print("✓ Staging cargado correctamente.")


if __name__ == "__main__":
    main()
