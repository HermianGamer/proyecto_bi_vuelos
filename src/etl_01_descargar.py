# -*- coding: utf-8 -*-
"""
ETL paso 1: descarga de datos BTS (Reporting Carrier On-Time Performance).

Descarga los últimos 12 meses publicados, se queda solo con JetBlue (B6)
y guarda un CSV por mes en data/b6_YYYY_MM.csv.
"""

import zipfile
from datetime import date
from pathlib import Path

import pandas as pd
import requests

URL_BASE = (
    "https://transtats.bts.gov/PREZIP/"
    "On_Time_Reporting_Carrier_On_Time_Performance_1987_present_{anio}_{mes}.zip"
)
URL_MANUAL = "https://www.transtats.bts.gov/DL_SelectFields.aspx?gnoyr_VQ=FGJ"
AEROLINEA = "B6"
MESES_A_BUSCAR = 6  # cuántos meses hacia atrás probar para hallar el último publicado

CARPETA_DATA = Path(__file__).resolve().parent.parent / "data"
CARPETA_RAW = CARPETA_DATA / "raw"

COLUMNAS = [
    "FlightDate", "Reporting_Airline", "Flight_Number_Reporting_Airline", "Tail_Number",
    "Origin", "OriginCityName", "OriginState", "OriginStateName",
    "Dest", "DestCityName", "DestState", "DestStateName",
    "CRSDepTime", "DepDelay", "ArrDelay", "ArrDel15", "TaxiOut",
    "Cancelled", "CancellationCode", "Diverted", "Distance",
    "CarrierDelay", "WeatherDelay", "NASDelay", "SecurityDelay", "LateAircraftDelay",
]


def mes_anterior(anio, mes):
    """Devuelve el (año, mes) anterior."""
    return (anio - 1, 12) if mes == 1 else (anio, mes - 1)


def ruta_csv(anio, mes):
    """Ruta del CSV final de un mes."""
    return CARPETA_DATA / f"b6_{anio}_{mes:02d}.csv"


def buscar_ultimo_mes():
    """Busca hacia atrás desde el mes actual el último mes publicado por BTS."""
    hoy = date.today()
    anio, mes = hoy.year, hoy.month
    for _ in range(MESES_A_BUSCAR):
        respuesta = requests.head(URL_BASE.format(anio=anio, mes=mes), timeout=30)
        if respuesta.status_code == 200 and "zip" in respuesta.headers.get("Content-Type", ""):
            print(f"✓ Último mes publicado por BTS: {anio}-{mes:02d}")
            return anio, mes
        anio, mes = mes_anterior(anio, mes)
    raise RuntimeError("No se encontró ningún mes publicado en BTS")


def ultimos_12_meses(anio, mes):
    """Lista de los 12 meses (año, mes) terminando en el mes indicado, del más antiguo al más reciente."""
    meses = []
    for _ in range(12):
        meses.append((anio, mes))
        anio, mes = mes_anterior(anio, mes)
    return meses[::-1]


def descargar_zip(anio, mes):
    """Descarga el ZIP de un mes a data/raw/ mostrando el avance."""
    url = URL_BASE.format(anio=anio, mes=mes)
    ruta_zip = CARPETA_RAW / f"bts_{anio}_{mes:02d}.zip"
    ruta_temporal = ruta_zip.with_suffix(".part")  # si se corta, no queda un ZIP a medias
    with requests.get(url, stream=True, timeout=60) as respuesta:
        respuesta.raise_for_status()
        total_mb = int(respuesta.headers.get("Content-Length", 0)) / 1e6
        descargado = 0
        with open(ruta_temporal, "wb") as archivo:
            for bloque in respuesta.iter_content(chunk_size=1024 * 1024):
                archivo.write(bloque)
                descargado += len(bloque)
                print(f"\r  Descargando {descargado / 1e6:5.1f} / {total_mb:.1f} MB", end="")
    print()
    ruta_temporal.rename(ruta_zip)
    return ruta_zip


def leer_archivo(ruta):
    """Lee un ZIP o CSV de BTS (solo las columnas necesarias) como texto."""
    if ruta.suffix.lower() == ".zip":
        with zipfile.ZipFile(ruta) as zf:
            nombre_csv = [n for n in zf.namelist() if n.lower().endswith(".csv")][0]
            with zf.open(nombre_csv) as f:
                return pd.read_csv(f, usecols=COLUMNAS, dtype=str)
    return pd.read_csv(ruta, usecols=COLUMNAS, dtype=str)


def filtrar_jetblue(df):
    """Se queda solo con los vuelos de JetBlue."""
    return df[df["Reporting_Airline"] == AEROLINEA][COLUMNAS]


def procesar_mes(anio, mes):
    """Descarga, filtra y guarda un mes; si ya existe el CSV, lo salta."""
    destino = ruta_csv(anio, mes)
    if destino.exists():
        print(f"- {anio}-{mes:02d}: ya existe, se omite")
        return
    print(f"- {anio}-{mes:02d}:")
    ruta_zip = descargar_zip(anio, mes)
    df = filtrar_jetblue(leer_archivo(ruta_zip))
    df.to_csv(destino, index=False)
    ruta_zip.unlink()
    print(f"  ✓ {len(df):,} vuelos de JetBlue guardados en {destino.name}")


def procesar_manuales():
    """Procesa los ZIP/CSV descargados a mano y dejados en data/raw/."""
    archivos = sorted(list(CARPETA_RAW.glob("*.zip")) + list(CARPETA_RAW.glob("*.csv")))
    for ruta in archivos:
        print(f"- Procesando archivo manual: {ruta.name}")
        df = filtrar_jetblue(leer_archivo(ruta))
        if df.empty:
            print("  (sin vuelos de JetBlue, se omite)")
            continue
        fechas = pd.to_datetime(df["FlightDate"])
        for (anio, mes), grupo in df.groupby([fechas.dt.year, fechas.dt.month]):
            grupo.to_csv(ruta_csv(anio, mes), index=False)
            print(f"  ✓ {anio}-{mes:02d}: {len(grupo):,} vuelos guardados")


def instrucciones_manuales():
    """Muestra los pasos para descargar los datos a mano desde BTS."""
    print(f"""
No se pudo descargar automáticamente desde BTS. Descarga manual:
  1. Abrir {URL_MANUAL}
  2. Elegir año y mes (filtro "Filter Year" / "Filter Period").
  3. Marcar los campos: {", ".join(COLUMNAS)}
  4. Pulsar "Download" (genera un ZIP con un CSV).
  5. Copiar el ZIP (o el CSV) en: {CARPETA_RAW}
  6. Volver a ejecutar: python src/etl_01_descargar.py
""")


def resumen():
    """Imprime los meses guardados con sus filas y tamaño."""
    print("\nResumen de archivos en data/:")
    print(f"  {'Mes':<8} {'Filas':>8} {'Tamaño':>9}")
    total_filas, total_mb = 0, 0.0
    for ruta in sorted(CARPETA_DATA.glob("b6_*.csv")):
        filas = len(pd.read_csv(ruta, usecols=["FlightDate"]))
        mb = ruta.stat().st_size / 1e6
        mes = ruta.stem.replace("b6_", "").replace("_", "-")
        print(f"  {mes:<8} {filas:>8,} {mb:>6.2f} MB")
        total_filas += filas
        total_mb += mb
    print(f"  {'TOTAL':<8} {total_filas:>8,} {total_mb:>6.2f} MB")


def main():
    """Ejecuta la descarga completa de los últimos 12 meses."""
    CARPETA_RAW.mkdir(parents=True, exist_ok=True)
    procesar_manuales()
    try:
        anio, mes = buscar_ultimo_mes()
        for anio_mes in ultimos_12_meses(anio, mes):
            procesar_mes(*anio_mes)
    except requests.RequestException as e:
        print(f"\nError al descargar desde BTS: {e}")
        instrucciones_manuales()
    resumen()


if __name__ == "__main__":
    main()
