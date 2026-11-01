# 02 — Especificación del ETL

Flujo (mismo patrón que el profesor, con una BD origen y una BD destino):

```
ZIP mensuales BTS ──► etl_01_descargar.py ──► data/b6_AAAA_MM.csv (solo JetBlue)
                                               │
                         etl_02_cargar_staging.py
                                               ▼
                                 VuelosOrigen.dbo.stg_vuelos   (BD origen)
                                               │
                         etl_03_poblar_datamart.py
                                               ▼
                                 VuelosDW (estrella)            (BD destino)
```

## `src/conexion.py`
- Lee `.env` con `python-dotenv`: `DB_DRIVER`, `DB_SERVER`, `DB_USER`, `DB_PASSWORD`, `DB_ORIGEN`, `DB_DW`.
- `get_connection_origen()` y `get_connection_destino()` con el mismo estilo del profesor (try/except, mensaje ✓).
- Cadena para Azure: `Encrypt=yes;TrustServerCertificate=no;Connection Timeout=60`.
- **Reintento:** hasta 3 intentos con 20 s de espera. La BD gratuita de Azure se "duerme" (auto-pausa) y el primer intento suele fallar mientras despierta.

## `src/reglas.py` (compartido ETL + app)
Funciones puras, sin acceso a BD:
- `calcular_horario(crs_dep_time) -> int` : hhmm → hora 0–23 (2400 → 0).
- `calcular_estado(cancelado, desviado, arr_del15) -> int` : 3 si cancelado, 4 si desviado, 2 si arr_del15 = 1, si no 1.
- `calcular_rango(estado, demora_llegada) -> int` : 0 si estado ∈ {3,4}; 1 si <0; 2 si 0–14; 3 si 15–44; 4 si 45–119; 5 si ≥120.
- `calcular_causa_principal(estado, minutos_por_causa: dict) -> int` : 0 si cancelado/desviado; 1 si a tiempo; si demorado, la causa con más minutos (2 CAR, 3 WEA, 4 NAS, 5 SEC, 6 LAT); 7 si todas son 0/NULL. En empate gana el orden CAR, LAT, NAS, WEA, SEC.
- `calcular_causa_cancelacion(codigo) -> int` : N/NULL→0, A→1, B→2, C→3, D→4.
- `tipo_distancia(millas) -> str` y `franja(hora) -> str`.
- Escribir tests simples en `tests/test_reglas.py` con `pytest`.

## `src/etl_01_descargar.py`
1. Determinar los **últimos 12 meses disponibles**: empezar en el mes actual e ir hacia atrás probando
   `https://transtats.bts.gov/PREZIP/On_Time_Reporting_Carrier_On_Time_Performance_1987_present_{AAAA}_{M}.zip` (mes sin cero a la izquierda). El primer mes que responde es el más reciente.
2. Para cada mes: descargar a `data/raw/`, leer el CSV del ZIP con pandas (solo las columnas de la lista de abajo, `dtype=str`), **filtrar `Reporting_Airline == 'B6'`** y guardar `data/b6_AAAA_MM.csv`. Borrar el ZIP después (son ~70 MB cada uno).
3. Si la descarga automática falla, imprimir instrucciones para la descarga manual desde
   `https://www.transtats.bts.gov/DL_SelectFields.aspx?gnoyr_VQ=FGJ` y dejar que el script lea los CSV que el usuario coloque en `data/raw/`.

Columnas a conservar:
`FlightDate, Reporting_Airline, Flight_Number_Reporting_Airline, Tail_Number, Origin, OriginCityName, OriginState, OriginStateName, Dest, DestCityName, DestState, DestStateName, CRSDepTime, DepDelay, ArrDelay, ArrDel15, TaxiOut, Cancelled, CancellationCode, Diverted, Distance, CarrierDelay, WeatherDelay, NASDelay, SecurityDelay, LateAircraftDelay`

## `src/etl_02_cargar_staging.py`
- Crear (si no existe) `stg_vuelos` en `VuelosOrigen` con esas 26 columnas, nombres iguales al BTS y tipos razonables (`DATE`, `INT`, `DECIMAL(6,1)` para las demoras, `VARCHAR`).
- `TRUNCATE` y cargar todos los `data/b6_*.csv` con `fast_executemany` en lotes de 5 000. NaN → `None`.
- Al final imprimir conteo por mes (`SELECT YEAR, MONTH, COUNT(*) ... GROUP BY`).

## `src/etl_03_poblar_datamart.py` (estilo `poblar_datamart_*.py` del profesor)
1. Conexiones origen/destino.
2. `create_datamart_schema()` con el DDL de `docs/01_modelo_dimensional.md` (`IF NOT EXISTS` como el profesor).
3. `clean_datamart()`: borrar la fact primero, luego dimensiones; usar `DBCC CHECKIDENT(..., RESEED, 0)` en las tablas IDENTITY.
4. Cargar dimensiones fijas (Horario, EstadoVuelo, CausaDemora, CausaCancelacion, RangoDemora) desde listas en el script.
5. `DimFecha`: todas las fechas entre min y max de `stg_vuelos`. Nombres de mes y día **en español** con diccionarios (no depender del locale). Feriados con `holidays.US()`.
6. `DimAeropuerto`: unión de orígenes y destinos distintos. `es_base_principal` = top 5 por número de salidas.
7. `DimRuta`: pares distintos origen–destino con su distancia.
8. Construir diccionarios de mapeo (`codigo_iata → sk`, `ruta → sk`) como hace el profesor con `genero_to_id`.
9. `FactVuelos`: leer `stg_vuelos`, aplicar `reglas.py`, mapear claves, eliminar duplicados por clave natural, insertar con `fast_executemany` por lotes.
10. **Validaciones al final** (imprimir y fallar si no cuadran):
    - filas en staging = filas en fact (menos duplicados descartados, reportados);
    - ninguna FK nula;
    - % cancelación y % puntualidad por mes (sirve para comparar con el ATCR del DOT).

## Volumen esperado
~20–25 mil vuelos de JetBlue por mes → ~250–300 mil filas en 12 meses. Cabe holgado en los 32 GB de la BD gratuita de Azure.
