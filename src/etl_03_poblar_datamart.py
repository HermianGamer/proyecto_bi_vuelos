# -*- coding: utf-8 -*-
"""
ETL paso 3: poblar el Data Mart de vuelos de JetBlue (esquema estrella).

BD origen : VuelosOrigen (tabla stg_vuelos)
BD destino: VuelosDW     (8 dimensiones + FactVuelos)

Modelo: docs/01_modelo_dimensional.md. Reglas de derivación: src/reglas.py.
"""

import sys
import warnings
from pathlib import Path

import holidays
import pandas as pd

import reglas
from conexion import a_filas, get_connection_destino, get_connection_origen, insertar_por_lotes

# pandas avisa que prefiere SQLAlchemy; con pyodbc funciona bien (igual que el profesor)
warnings.filterwarnings("ignore", message=".*pandas only supports SQLAlchemy.*")

SCRIPT_DATAMART = Path(__file__).resolve().parent.parent / "sql" / "02_crear_datamart.sql"

DDL_DATAMART = """
IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='DimFecha' AND xtype='U')
CREATE TABLE DimFecha (
    sk_fecha INT PRIMARY KEY, fecha DATE NOT NULL UNIQUE, anio SMALLINT NOT NULL,
    trimestre TINYINT NOT NULL, mes TINYINT NOT NULL, nombre_mes NVARCHAR(15) NOT NULL,
    nombre_dia NVARCHAR(15) NOT NULL, es_fin_semana BIT NOT NULL, es_feriado BIT NOT NULL);

IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='DimAeropuerto' AND xtype='U')
CREATE TABLE DimAeropuerto (
    sk_aeropuerto INT IDENTITY(1,1) PRIMARY KEY, codigo_iata CHAR(3) NOT NULL UNIQUE,
    ciudad NVARCHAR(60) NULL, estado CHAR(2) NULL, nombre_estado NVARCHAR(50) NULL,
    es_base_principal BIT NOT NULL DEFAULT 0);

IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='DimRuta' AND xtype='U')
CREATE TABLE DimRuta (
    sk_ruta INT IDENTITY(1,1) PRIMARY KEY, ruta VARCHAR(7) NOT NULL UNIQUE,
    origen CHAR(3) NOT NULL, destino CHAR(3) NOT NULL,
    distancia_millas INT NULL, tipo_distancia NVARCHAR(10) NULL);

IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='DimHorario' AND xtype='U')
CREATE TABLE DimHorario (
    sk_horario TINYINT PRIMARY KEY, bloque CHAR(9) NOT NULL, franja NVARCHAR(12) NOT NULL);

IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='DimEstadoVuelo' AND xtype='U')
CREATE TABLE DimEstadoVuelo (
    sk_estado TINYINT PRIMARY KEY, estado NVARCHAR(15) NOT NULL, descripcion NVARCHAR(120) NULL);

IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='DimCausaDemora' AND xtype='U')
CREATE TABLE DimCausaDemora (
    sk_causa_demora TINYINT PRIMARY KEY, codigo CHAR(3) NOT NULL,
    causa NVARCHAR(40) NOT NULL, controlable NVARCHAR(10) NULL);

IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='DimCausaCancelacion' AND xtype='U')
CREATE TABLE DimCausaCancelacion (
    sk_causa_cancelacion TINYINT PRIMARY KEY, codigo CHAR(1) NOT NULL,
    causa NVARCHAR(40) NOT NULL, controlable NVARCHAR(10) NULL);

IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='DimRangoDemora' AND xtype='U')
CREATE TABLE DimRangoDemora (
    sk_rango_demora TINYINT PRIMARY KEY, rango NVARCHAR(30) NOT NULL,
    min_desde INT NULL, min_hasta INT NULL, orden TINYINT NOT NULL);

IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='FactVuelos' AND xtype='U')
CREATE TABLE FactVuelos (
    id_vuelo BIGINT IDENTITY(1,1) PRIMARY KEY,
    sk_fecha INT NOT NULL REFERENCES DimFecha(sk_fecha),
    sk_origen INT NOT NULL REFERENCES DimAeropuerto(sk_aeropuerto),
    sk_destino INT NOT NULL REFERENCES DimAeropuerto(sk_aeropuerto),
    sk_ruta INT NOT NULL REFERENCES DimRuta(sk_ruta),
    sk_horario TINYINT NOT NULL REFERENCES DimHorario(sk_horario),
    sk_estado TINYINT NOT NULL REFERENCES DimEstadoVuelo(sk_estado),
    sk_causa_demora TINYINT NOT NULL REFERENCES DimCausaDemora(sk_causa_demora),
    sk_causa_cancelacion TINYINT NOT NULL REFERENCES DimCausaCancelacion(sk_causa_cancelacion),
    sk_rango_demora TINYINT NOT NULL REFERENCES DimRangoDemora(sk_rango_demora),
    numero_vuelo INT NOT NULL, matricula VARCHAR(10) NULL,
    demora_salida_min INT NULL, demora_llegada_min INT NULL, taxi_out_min INT NULL,
    es_puntual TINYINT NOT NULL, es_cancelado TINYINT NOT NULL, es_desviado TINYINT NOT NULL,
    min_causa_aerolinea INT NULL, min_causa_clima INT NULL, min_causa_trafico INT NULL,
    min_causa_seguridad INT NULL, min_causa_avion_tardio INT NULL,
    origen_registro VARCHAR(5) NOT NULL DEFAULT 'ETL',
    fecha_carga DATETIME2 NOT NULL DEFAULT SYSDATETIME());

IF NOT EXISTS (SELECT * FROM sys.indexes WHERE name='UX_Fact_Natural')
CREATE UNIQUE INDEX UX_Fact_Natural ON FactVuelos (sk_fecha, numero_vuelo, sk_origen);
IF NOT EXISTS (SELECT * FROM sys.indexes WHERE name='IX_Fact_Fecha')
CREATE INDEX IX_Fact_Fecha  ON FactVuelos (sk_fecha);
IF NOT EXISTS (SELECT * FROM sys.indexes WHERE name='IX_Fact_Origen')
CREATE INDEX IX_Fact_Origen ON FactVuelos (sk_origen, sk_fecha);
"""

# ------------------------------------------------------------ Dimensiones fijas ---
ESTADOS = [
    (1, "A tiempo", "Llegó con menos de 15 minutos de demora"),
    (2, "Demorado", "Llegó con 15 minutos o más de demora"),
    (3, "Cancelado", "El vuelo programado no se realizó"),
    (4, "Desviado", "Aterrizó en un aeropuerto distinto al destino"),
]
CAUSAS_DEMORA = [
    (0, "NAP", "No aplica", None),
    (1, "NON", "Sin demora", None),
    (2, "CAR", "Aerolínea", "Sí"),
    (3, "WEA", "Clima", "No"),
    (4, "NAS", "Control de tráfico aéreo", "No"),
    (5, "SEC", "Seguridad", "No"),
    (6, "LAT", "Avión anterior retrasado", "Parcial"),
    (7, "UNK", "Sin dato", None),
]
CAUSAS_CANCELACION = [
    (0, "N", "No cancelado", None),
    (1, "A", "Aerolínea", "Sí"),
    (2, "B", "Clima", "No"),
    (3, "C", "Control de tráfico aéreo", "No"),
    (4, "D", "Seguridad", "No"),
]
RANGOS_DEMORA = [
    (0, "No aplica (cancelado/desviado)", None, None, 6),
    (1, "Llegó antes de hora", None, -1, 1),
    (2, "A tiempo (0–14 min)", 0, 14, 2),
    (3, "Leve (15–44 min)", 15, 44, 3),
    (4, "Moderada (45–119 min)", 45, 119, 4),
    (5, "Grave (120+ min)", 120, None, 5),
]
MESES = {1: "Enero", 2: "Febrero", 3: "Marzo", 4: "Abril", 5: "Mayo", 6: "Junio", 7: "Julio",
         8: "Agosto", 9: "Septiembre", 10: "Octubre", 11: "Noviembre", 12: "Diciembre"}
DIAS = {0: "Lunes", 1: "Martes", 2: "Miércoles", 3: "Jueves", 4: "Viernes", 5: "Sábado", 6: "Domingo"}

# columnas de minutos por causa: staging → hecho
MINUTOS_CAUSA = {
    "CarrierDelay": "min_causa_aerolinea",
    "WeatherDelay": "min_causa_clima",
    "NASDelay": "min_causa_trafico",
    "SecurityDelay": "min_causa_seguridad",
    "LateAircraftDelay": "min_causa_avion_tardio",
}

COLUMNAS_FACT = [
    "sk_fecha", "sk_origen", "sk_destino", "sk_ruta", "sk_horario", "sk_estado",
    "sk_causa_demora", "sk_causa_cancelacion", "sk_rango_demora", "numero_vuelo", "matricula",
    "demora_salida_min", "demora_llegada_min", "taxi_out_min", "es_puntual", "es_cancelado",
    "es_desviado", *MINUTOS_CAUSA.values(),
]


def create_datamart_schema(conn):
    """Crea las tablas del Data Mart si no existen y guarda el DDL en sql/02."""
    SCRIPT_DATAMART.write_text(
        "-- Generado por src/etl_03_poblar_datamart.py (no editar a mano)\n" + DDL_DATAMART.strip() + "\n",
        encoding="utf-8",
    )
    conn.cursor().execute(DDL_DATAMART)
    conn.commit()
    print("✓ Esquema del Data Mart listo (DDL guardado en sql/02_crear_datamart.sql)")


def clean_datamart(conn):
    """Vacía el Data Mart: primero el hecho, luego las dimensiones."""
    print("🧹 Limpiando Data Mart...")
    cursor = conn.cursor()
    cursor.execute("TRUNCATE TABLE FactVuelos")  # TRUNCATE ya reinicia el IDENTITY
    for tabla in ["DimFecha", "DimAeropuerto", "DimRuta", "DimHorario", "DimEstadoVuelo",
                  "DimCausaDemora", "DimCausaCancelacion", "DimRangoDemora"]:
        cursor.execute(f"DELETE FROM {tabla}")
    # Reiniciar IDENTITY solo si la tabla ya tuvo filas (si no, el primer id sería 0)
    for tabla in ["DimAeropuerto", "DimRuta"]:
        cursor.execute(f"""
            IF EXISTS (SELECT 1 FROM sys.identity_columns
                       WHERE object_id = OBJECT_ID('{tabla}') AND last_value IS NOT NULL)
            DBCC CHECKIDENT ('{tabla}', RESEED, 0)
        """)
    conn.commit()
    print("✓ Data Mart limpiado\n")


def cargar_tabla(conn, tabla, columnas, filas):
    """Inserta una lista de filas en una tabla del Data Mart."""
    sql = f"INSERT INTO {tabla} ({', '.join(columnas)}) VALUES ({', '.join('?' * len(columnas))})"
    insertar_por_lotes(conn, sql, filas)
    print(f"✓ {tabla}: {len(filas):,} filas")


def cargar_dimensiones_fijas(conn):
    """Carga las 5 dimensiones con valores fijos."""
    horas = [(h, reglas.bloque(h), reglas.franja(h)) for h in range(24)]
    cargar_tabla(conn, "DimHorario", ["sk_horario", "bloque", "franja"], horas)
    cargar_tabla(conn, "DimEstadoVuelo", ["sk_estado", "estado", "descripcion"], ESTADOS)
    cargar_tabla(conn, "DimCausaDemora", ["sk_causa_demora", "codigo", "causa", "controlable"], CAUSAS_DEMORA)
    cargar_tabla(conn, "DimCausaCancelacion",
                 ["sk_causa_cancelacion", "codigo", "causa", "controlable"], CAUSAS_CANCELACION)
    cargar_tabla(conn, "DimRangoDemora",
                 ["sk_rango_demora", "rango", "min_desde", "min_hasta", "orden"], RANGOS_DEMORA)


def cargar_dim_fecha(conn, df):
    """Carga DimFecha con todas las fechas entre la mínima y la máxima del staging."""
    fechas = pd.date_range(df["FlightDate"].min(), df["FlightDate"].max(), freq="D")
    feriados = holidays.US(years=range(fechas.min().year, fechas.max().year + 1))
    filas = [
        (int(f.strftime("%Y%m%d")), f.date(), f.year, f.quarter, f.month, MESES[f.month],
         DIAS[f.weekday()], int(f.weekday() >= 5), int(f.date() in feriados))
        for f in fechas
    ]
    cargar_tabla(conn, "DimFecha", ["sk_fecha", "fecha", "anio", "trimestre", "mes", "nombre_mes",
                                    "nombre_dia", "es_fin_semana", "es_feriado"], filas)


def cargar_dim_aeropuerto(conn, df):
    """Carga DimAeropuerto con orígenes y destinos; marca las 5 bases principales."""
    columnas = ["codigo_iata", "ciudad", "estado", "nombre_estado"]
    origenes = df[["Origin", "OriginCityName", "OriginState", "OriginStateName"]].set_axis(columnas, axis=1)
    destinos = df[["Dest", "DestCityName", "DestState", "DestStateName"]].set_axis(columnas, axis=1)
    aeropuertos = pd.concat([origenes, destinos]).drop_duplicates("codigo_iata").sort_values("codigo_iata")
    bases = df["Origin"].value_counts().head(5).index
    aeropuertos["es_base_principal"] = aeropuertos["codigo_iata"].isin(bases).astype(int)
    cargar_tabla(conn, "DimAeropuerto", columnas + ["es_base_principal"], a_filas(aeropuertos))
    print(f"  Bases principales: {', '.join(bases)}")


def cargar_dim_ruta(conn, df):
    """Carga DimRuta con los pares origen–destino distintos."""
    rutas = df.groupby(["Origin", "Dest"], as_index=False)["Distance"].max()
    rutas["ruta"] = rutas["Origin"] + "-" + rutas["Dest"]
    rutas["Distance"] = a_entero(rutas["Distance"])
    rutas["tipo_distancia"] = rutas["Distance"].map(reglas.tipo_distancia)
    rutas = rutas[["ruta", "Origin", "Dest", "Distance", "tipo_distancia"]]
    cargar_tabla(conn, "DimRuta", ["ruta", "origen", "destino", "distancia_millas", "tipo_distancia"],
                 a_filas(rutas))


def construir_mapas(conn):
    """Mapas de clave natural → clave subrogada (como genero_to_id del profesor)."""
    df_aerop = pd.read_sql("SELECT sk_aeropuerto, codigo_iata FROM DimAeropuerto", conn)
    df_ruta = pd.read_sql("SELECT sk_ruta, ruta FROM DimRuta", conn)
    aeropuerto_to_sk = dict(zip(df_aerop["codigo_iata"], df_aerop["sk_aeropuerto"]))
    ruta_to_sk = dict(zip(df_ruta["ruta"], df_ruta["sk_ruta"]))
    return aeropuerto_to_sk, ruta_to_sk


def a_entero(serie):
    """Convierte una columna numérica a entero con NULL (Int64)."""
    return pd.to_numeric(serie).round().astype("Int64")


def preparar_hechos(df, aeropuerto_to_sk, ruta_to_sk):
    """Aplica las reglas de reglas.py y mapea las claves de FactVuelos."""
    hechos = pd.DataFrame()
    hechos["sk_fecha"] = pd.to_datetime(df["FlightDate"]).dt.strftime("%Y%m%d").astype(int)
    hechos["sk_origen"] = df["Origin"].map(aeropuerto_to_sk)
    hechos["sk_destino"] = df["Dest"].map(aeropuerto_to_sk)
    hechos["sk_ruta"] = (df["Origin"] + "-" + df["Dest"]).map(ruta_to_sk)
    hechos["sk_horario"] = df["CRSDepTime"].map(reglas.calcular_horario)
    hechos["sk_estado"] = [reglas.calcular_estado(c, d, x)
                           for c, d, x in zip(df["Cancelled"], df["Diverted"], df["ArrDel15"])]
    minutos = pd.DataFrame({"CAR": df["CarrierDelay"], "WEA": df["WeatherDelay"], "NAS": df["NASDelay"],
                            "SEC": df["SecurityDelay"], "LAT": df["LateAircraftDelay"]})
    hechos["sk_causa_demora"] = [reglas.calcular_causa_principal(e, m)
                                 for e, m in zip(hechos["sk_estado"], minutos.to_dict("records"))]
    hechos["sk_causa_cancelacion"] = df["CancellationCode"].map(reglas.calcular_causa_cancelacion)
    hechos["sk_rango_demora"] = [reglas.calcular_rango(e, a)
                                 for e, a in zip(hechos["sk_estado"], df["ArrDelay"])]
    hechos["numero_vuelo"] = df["Flight_Number_Reporting_Airline"].astype(int)
    hechos["matricula"] = df["Tail_Number"]
    hechos["demora_salida_min"] = a_entero(df["DepDelay"])
    hechos["demora_llegada_min"] = a_entero(df["ArrDelay"])
    hechos["taxi_out_min"] = a_entero(df["TaxiOut"])
    hechos["es_puntual"] = (hechos["sk_estado"] == reglas.A_TIEMPO).astype(int)
    hechos["es_cancelado"] = (hechos["sk_estado"] == reglas.CANCELADO).astype(int)
    hechos["es_desviado"] = (hechos["sk_estado"] == reglas.DESVIADO).astype(int)
    for col_stg, col_fact in MINUTOS_CAUSA.items():
        hechos[col_fact] = a_entero(df[col_stg])
    return hechos[COLUMNAS_FACT]


def cargar_fact_vuelos(conn, df, aeropuerto_to_sk, ruta_to_sk):
    """Carga FactVuelos; devuelve la cantidad de duplicados eliminados."""
    print("Preparando FactVuelos...")
    hechos = preparar_hechos(df, aeropuerto_to_sk, ruta_to_sk)
    antes = len(hechos)
    hechos = hechos.drop_duplicates(subset=["sk_fecha", "numero_vuelo", "sk_origen"])
    duplicados = antes - len(hechos)
    print(f"  Duplicados por clave natural (fecha, vuelo, origen) eliminados: {duplicados}")
    cargar_tabla(conn, "FactVuelos", COLUMNAS_FACT, a_filas(hechos))
    return duplicados


def validar(conn, filas_staging, duplicados):
    """Valida la carga; termina con error si algo no cuadra."""
    print("\n=== Validaciones ===")
    cursor = conn.cursor()
    filas_fact = cursor.execute("SELECT COUNT(*) FROM FactVuelos").fetchone()[0]
    ok_filas = filas_staging == filas_fact + duplicados
    print(f"{'✓' if ok_filas else '✗'} Filas: staging {filas_staging:,} = hechos {filas_fact:,} "
          f"+ duplicados {duplicados}")

    # claves foráneas sin correspondencia en su dimensión (LEFT JOIN)
    huerfanas = cursor.execute("""
        SELECT COUNT(*) FROM FactVuelos f
        LEFT JOIN DimFecha d  ON f.sk_fecha = d.sk_fecha
        LEFT JOIN DimAeropuerto o ON f.sk_origen = o.sk_aeropuerto
        LEFT JOIN DimAeropuerto t ON f.sk_destino = t.sk_aeropuerto
        LEFT JOIN DimRuta r ON f.sk_ruta = r.sk_ruta
        WHERE d.sk_fecha IS NULL OR o.sk_aeropuerto IS NULL
           OR t.sk_aeropuerto IS NULL OR r.sk_ruta IS NULL
    """).fetchone()[0]
    ok_fk = huerfanas == 0
    print(f"{'✓' if ok_fk else '✗'} Claves foráneas nulas o sin dimensión: {huerfanas}")

    print("\n% por mes (comparar con el Air Travel Consumer Report del DOT):")
    df_kpi = pd.read_sql("""
        SELECT d.anio, d.mes, COUNT(*) AS vuelos,
               SUM(f.es_puntual) * 100.0 / COUNT(*) AS pct_puntualidad,  -- definición DOT (ATCR)
               SUM(f.es_cancelado) * 100.0 / COUNT(*) AS pct_cancelacion
        FROM FactVuelos f JOIN DimFecha d ON f.sk_fecha = d.sk_fecha
        GROUP BY d.anio, d.mes ORDER BY d.anio, d.mes
    """, conn)
    print(f"  {'Mes':<8} {'Vuelos':>8} {'% Puntual':>10} {'% Cancel':>9}")
    for _, r in df_kpi.iterrows():
        print(f"  {int(r['anio'])}-{int(r['mes']):02d}  {int(r['vuelos']):>8,} "
              f"{r['pct_puntualidad']:>9.1f}% {r['pct_cancelacion']:>8.2f}%")

    if not (ok_filas and ok_fk):
        print("\n✗ Validaciones fallidas")
        sys.exit(1)
    print("\n✓ Todas las validaciones pasaron")


def main():
    """Ejecuta el poblado completo del Data Mart."""
    source_conn = get_connection_origen()
    dest_conn = get_connection_destino()
    if not source_conn or not dest_conn:
        sys.exit(1)

    create_datamart_schema(dest_conn)
    clean_datamart(dest_conn)

    print("Leyendo staging...")
    df = pd.read_sql("SELECT * FROM dbo.stg_vuelos", source_conn)
    print(f"✓ {len(df):,} filas leídas de stg_vuelos\n")

    cargar_dimensiones_fijas(dest_conn)
    cargar_dim_fecha(dest_conn, df)
    cargar_dim_aeropuerto(dest_conn, df)
    cargar_dim_ruta(dest_conn, df)

    aeropuerto_to_sk, ruta_to_sk = construir_mapas(dest_conn)
    duplicados = cargar_fact_vuelos(dest_conn, df, aeropuerto_to_sk, ruta_to_sk)

    validar(dest_conn, len(df), duplicados)
    source_conn.close()
    dest_conn.close()
    print("ETL completado. Data Mart de JetBlue poblado correctamente.")


if __name__ == "__main__":
    main()
