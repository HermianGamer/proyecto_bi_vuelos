# 02 — ETL spec

```
BTS monthly ZIPs → etl_01_descargar.py → data/b6_YYYY_MM.csv (JetBlue only)
                 → etl_02_cargar_staging.py → VuelosOrigen.dbo.stg_vuelos (source DB)
                 → etl_03_poblar_datamart.py → VuelosDW star schema (target DB)
```

## `src/conexion.py`
- Load `.env` (python-dotenv): `DB_DRIVER, DB_SERVER, DB_USER, DB_PASSWORD, DB_ORIGEN, DB_DW`.
- `get_connection_origen()`, `get_connection_destino()` in the professor's style (try/except, ✓ print).
- Azure string adds `Encrypt=yes;TrustServerCertificate=no;Connection Timeout=60`. For localhost use `TrustServerCertificate=yes`.
- **Retry** 3 times with 20 s wait: Azure free serverless DB auto-pauses and the first connect often fails while resuming.
- `if __name__ == "__main__":` tests both connections.

## `src/reglas.py` (shared by ETL + app; pure functions, no DB)
- `calcular_horario(crs_dep_time) -> int`: hhmm → 0–23 (2400 → 0).
- `calcular_estado(cancelado, desviado, arr_del15) -> int`: 3 if cancelled, 4 if diverted, 2 if arr_del15 == 1, else 1.
- `calcular_rango(estado, demora_llegada) -> int`: 0 if estado in {3,4}; 1 if <0; 2 if 0–14; 3 if 15–44; 4 if 45–119; 5 if ≥120.
- `calcular_causa_principal(estado, minutos: dict) -> int`: 0 if cancelled/diverted; 1 if on time; if delayed, cause with most minutes (2 CAR, 3 WEA, 4 NAS, 5 SEC, 6 LAT); 7 if all 0/NULL. Tie order: CAR, LAT, NAS, WEA, SEC.
- `calcular_causa_cancelacion(codigo) -> int`: N/NULL→0, A→1, B→2, C→3, D→4.
- `tipo_distancia(millas) -> str`, `franja(hora) -> str`, `bloque(hora) -> str`.
- Tests in `tests/test_reglas.py` (pytest), including edge cases (2400, exactly 15 min, ties, NULLs).

## `src/etl_01_descargar.py`
1. Find the **latest 12 available months**: from current month backwards, try
   `https://transtats.bts.gov/PREZIP/On_Time_Reporting_Carrier_On_Time_Performance_1987_present_{YYYY}_{M}.zip` (M without leading zero). First month that responds = most recent.
2. Per month: download to `data/raw/` (stream, show progress), read CSV inside ZIP with pandas (`usecols` = list below, `dtype=str`), **filter `Reporting_Airline == 'B6'`**, save `data/b6_YYYY_MM.csv`, delete ZIP (~70 MB each). Skip months already saved.
3. If automatic download fails (SSL/403), print Spanish instructions for manual download from `https://www.transtats.bts.gov/DL_SelectFields.aspx?gnoyr_VQ=FGJ` and process any ZIP/CSV the user drops in `data/raw/`.

Columns to keep:
`FlightDate, Reporting_Airline, Flight_Number_Reporting_Airline, Tail_Number, Origin, OriginCityName, OriginState, OriginStateName, Dest, DestCityName, DestState, DestStateName, CRSDepTime, DepDelay, ArrDelay, ArrDel15, TaxiOut, Cancelled, CancellationCode, Diverted, Distance, CarrierDelay, WeatherDelay, NASDelay, SecurityDelay, LateAircraftDelay`

## `src/etl_02_cargar_staging.py`
- Write `sql/01_crear_staging.sql`; script creates `stg_vuelos` in `VuelosOrigen` if missing (same 26 BTS column names; DATE, INT, DECIMAL(6,1) for delays, VARCHAR).
- `TRUNCATE`, load all `data/b6_*.csv` with fast_executemany, 5,000-row batches. NaN → None.
- Print row count per month at the end.

## `src/etl_03_poblar_datamart.py` (mirror professor's `poblar_datamart_*.py` structure)
1. Source/target connections.
2. `create_datamart_schema()` with DDL from `docs/01` (`IF NOT EXISTS` like the professor). Also save DDL to `sql/02_crear_datamart.sql`.
3. `clean_datamart()`: delete fact first, then dims; `DBCC CHECKIDENT(..., RESEED, 0)` on IDENTITY tables.
4. Fixed dims (Horario, EstadoVuelo, CausaDemora, CausaCancelacion, RangoDemora) from lists in the script.
5. `DimFecha`: every date between min and max of staging. Spanish month/day names via dicts (no locale). Holidays via `holidays.US()`.
6. `DimAeropuerto`: union of distinct origins and destinations. `es_base_principal` = top 5 by departures.
7. `DimRuta`: distinct origin–destination pairs with distance.
8. Key maps (`codigo_iata → sk`, `ruta → sk`) like the professor's `genero_to_id`.
9. `FactVuelos`: read staging, apply `reglas.py` (vectorize with pandas where easy), map keys, drop natural-key duplicates (report count), insert in batches.
10. **Validations** at the end (print; fail if broken): staging rows = fact rows + reported duplicates; no NULL FKs; % cancellation and % on-time per month (to compare with DOT Air Travel Consumer Report).

## Volume
~20–25k JetBlue flights/month → ~250–300k rows for 12 months. Fits easily in Azure free tier (32 GB).
