# -*- coding: utf-8 -*-
"""
Created on Fri Oct 24 10:28:19 2025

@author: JG.WamB

Adaptado para Netflix DW
BD origen : Netflix  (tablas: Pelicula, Pais, VistasPorPais, RecaudacionPorPais)
BD destino: NetflixDW
"""

import pyodbc
import pandas as pd

def get_connection_origen():
    try:
        conn = pyodbc.connect(
            'DRIVER={ODBC Driver 17 for SQL Server};'
            'SERVER=localhost;'
            'DATABASE=NetflixDB;'
            'UID=sa;'
            'PWD=1234567890'
        )
        print("✓ Conexión a origen exitosa")
        return conn
    except pyodbc.Error as e:
        print(f"Error de conexión al origen: {e}")
        return None

def get_connection_destino():
    try:
        conn = pyodbc.connect(
            'DRIVER={ODBC Driver 17 for SQL Server};'
            'SERVER=localhost;'
            'DATABASE=NetflixDW;'
            'UID=sa;'
            'PWD=1234567890'
        )
        print("✓ Conexión a destino exitosa")
        return conn
    except pyodbc.Error as e:
        print(f"Error de conexión al destino: {e}")
        return None

def create_datamart_schema(cursor):
    create_script = """
    IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='DimTiempo' AND xtype='U')
    CREATE TABLE DimTiempo (
        id INT IDENTITY(1,1) PRIMARY KEY,
        fecha DATE NOT NULL UNIQUE,
        anio INT NOT NULL,
        mes INT NOT NULL,
        nombre_mes NVARCHAR(15) NOT NULL,
        dia INT NOT NULL,
        trimestre INT NOT NULL,
        dia_semana NVARCHAR(15) NOT NULL
    );

    IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='DimTitulo' AND xtype='U')
    CREATE TABLE DimTitulo (
        id INT PRIMARY KEY,
        titulo NVARCHAR(255) NOT NULL,
        anio_lanzamiento INT NULL,
        duracion_min INT NULL,
        calificacion_promedio DECIMAL(2,1) NULL
    );

    IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='DimGenero' AND xtype='U')
    CREATE TABLE DimGenero (
        id INT IDENTITY(1,1) PRIMARY KEY,
        nombre NVARCHAR(100) NOT NULL UNIQUE
    );

    IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='DimPais' AND xtype='U')
    CREATE TABLE DimPais (
        id INT PRIMARY KEY,
        nombre NVARCHAR(100) NOT NULL,
        codigo_iso CHAR(3) NULL,
        continente NVARCHAR(50) NULL
    );

    IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='FactVistas' AND xtype='U')
    CREATE TABLE FactVistas (
        titulo_id INT NOT NULL,
        tiempo_id INT NOT NULL,
        genero_id INT NOT NULL,
        pais_id INT NOT NULL,
        cantidad_vistas BIGINT NOT NULL,
        tiempo_promedio_min DECIMAL(5,2) NULL,
        monto_recaudado_usd DECIMAL(18,2) NULL,
        FOREIGN KEY (titulo_id) REFERENCES DimTitulo(id),
        FOREIGN KEY (tiempo_id) REFERENCES DimTiempo(id),
        FOREIGN KEY (genero_id) REFERENCES DimGenero(id),
        FOREIGN KEY (pais_id)   REFERENCES DimPais(id)
    );
    """
    cursor.execute(create_script)
    cursor.commit()

# Conexiones
source_conn = get_connection_origen()
dest_conn = get_connection_destino()

if not source_conn or not dest_conn:
    exit(1)

dest_cursor = dest_conn.cursor()
create_datamart_schema(dest_cursor)
dest_conn.commit()
print("✓ Esquema completo del Data Mart creado.")

def clean_datamart(cursor, conn):
    """
    Limpia todas las tablas del Data Mart en orden seguro.
    """
    print("🧹 Limpiando Data Mart...")
    
    # 1. Borrar hechos primero por integridad referencial
    cursor.execute("DELETE FROM FactVistas")
    print("  → Tabla FactVistas vaciada.")
    
    # 2. Borrar dimensiones
    cursor.execute("DELETE FROM DimPais")
    print("  → Tabla DimPais vaciada.")
    
    cursor.execute("DELETE FROM DimGenero")
    print("  → Tabla DimGenero vaciada.")
    
    cursor.execute("DELETE FROM DimTitulo")
    print("  → Tabla DimTitulo vaciada.")
    
    cursor.execute("DELETE FROM DimTiempo")
    print("  → Tabla DimTiempo vaciada.")
    
    conn.commit()
    print(" Data Mart limpiado completamente.\n")

clean_datamart(dest_cursor, dest_conn)

# -------------------------------------------------------------- Cargar dimensiones ---

# DimTitulo  ← tabla Pelicula
print("Cargando DimTitulo...")
query_titulos = "SELECT IdPelicula, Titulo, AñoLanzamiento, DuracionMinutos, CalificacionPromedio FROM Pelicula"
df_titulos = pd.read_sql(query_titulos, source_conn)
for _, r in df_titulos.iterrows():
    anio     = int(r['AñoLanzamiento'])      if not pd.isna(r['AñoLanzamiento'])      else None
    duracion = int(r['DuracionMinutos'])     if not pd.isna(r['DuracionMinutos'])     else None
    calif    = float(r['CalificacionPromedio']) if not pd.isna(r['CalificacionPromedio']) else None
    dest_cursor.execute("INSERT INTO DimTitulo (id, titulo, anio_lanzamiento, duracion_min, calificacion_promedio) VALUES (?, ?, ?, ?, ?)",
                       int(r['IdPelicula']), str(r['Titulo']), anio, duracion, calif)
dest_conn.commit()
print(f"✓ {len(df_titulos)} títulos cargados.")

#------------------------------------------- DimGenero  ← géneros distintos de Pelicula.Genero
print("Cargando DimGenero...")
query_generos = "SELECT DISTINCT Genero FROM Pelicula WHERE Genero IS NOT NULL"
df_generos = pd.read_sql(query_generos, source_conn)
for _, r in df_generos.iterrows():
    dest_cursor.execute("INSERT INTO DimGenero (nombre) VALUES (?)", str(r['Genero']))
dest_conn.commit()
print(f"✓ {len(df_generos)} géneros cargados.")

# Construir mapeo nombre_genero -> id generado por IDENTITY
df_genero_db = pd.read_sql("SELECT id, nombre FROM DimGenero", dest_conn)
genero_to_id = dict(zip(df_genero_db['nombre'], df_genero_db['id']))

# -------------------------------------------DimPais  ← tabla Pais
print("Cargando DimPais...")
query_paises = "SELECT IdPais, Nombre, CodigoISO, Continente FROM Pais"
df_paises = pd.read_sql(query_paises, source_conn)
for _, r in df_paises.iterrows():
    iso  = str(r['CodigoISO'])  if not pd.isna(r['CodigoISO'])  else None
    cont = str(r['Continente']) if not pd.isna(r['Continente']) else None
    dest_cursor.execute("INSERT INTO DimPais (id, nombre, codigo_iso, continente) VALUES (?, ?, ?, ?)",
                       int(r['IdPais']), str(r['Nombre']), iso, cont)
dest_conn.commit()
print(f"✓ {len(df_paises)} países cargados.")

# --------------------------------------------DimTiempo
print("Cargando DimTiempo...")
query_fechas = "SELECT DISTINCT PeriodoMes AS fecha FROM VistasPorPais WHERE PeriodoMes IS NOT NULL ORDER BY PeriodoMes"
df_fechas = pd.read_sql(query_fechas, source_conn)

if not df_fechas.empty:
    df_fechas['dt'] = pd.to_datetime(df_fechas['fecha'])
    df_fechas['anio'] = df_fechas['dt'].dt.year
    df_fechas['mes'] = df_fechas['dt'].dt.month
    df_fechas['nombre_mes'] = df_fechas['dt'].dt.month_name()
    df_fechas['dia'] = df_fechas['dt'].dt.day
    df_fechas['trimestre'] = df_fechas['dt'].dt.quarter  # Esto devuelve 1,2,3,4 (INT)
    df_fechas['dia_semana'] = df_fechas['dt'].dt.day_name()

    for _, r in df_fechas.iterrows():
        dest_cursor.execute("""
            INSERT INTO DimTiempo (fecha, anio, mes, nombre_mes, dia, trimestre, dia_semana)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, r['fecha'], int(r['anio']), int(r['mes']), str(r['nombre_mes']), 
             int(r['dia']), int(r['trimestre']), str(r['dia_semana']))

    dest_conn.commit()
    print(f"✓ {len(df_fechas)} fechas cargadas.")
else:
    print("⚠ No se encontraron fechas en la tabla VistasPorPais")

# Obtener mapeo real de fecha -> id
df_tiempo_db = pd.read_sql("SELECT id, fecha FROM DimTiempo", dest_conn)
df_tiempo_db['fecha'] = pd.to_datetime(df_tiempo_db['fecha']).dt.date
fecha_to_id = dict(zip(df_tiempo_db['fecha'], df_tiempo_db['id']))

# ------------------------------------------------------------------- Tabla de Hechos: FactVistas
print("Cargando FactVistas...")
query_vistas = """
    SELECT 
        vp.IdPelicula,
        vp.IdPais,
        vp.PeriodoMes AS fecha,
        p.Genero,
        ISNULL(vp.CantidadVistas, 0)        AS cantidad_vistas,
        vp.TiempoPromedioMin                 AS tiempo_promedio_min,
        rp.MontoUSD                          AS monto_recaudado_usd
    FROM VistasPorPais vp
    JOIN Pelicula p  ON vp.IdPelicula = p.IdPelicula
    LEFT JOIN RecaudacionPorPais rp ON vp.IdPelicula = rp.IdPelicula
                                   AND vp.IdPais     = rp.IdPais
    WHERE vp.IdPelicula IS NOT NULL
      AND vp.IdPais     IS NOT NULL
      AND vp.PeriodoMes IS NOT NULL
      AND p.Genero      IS NOT NULL
"""

df_vistas = pd.read_sql(query_vistas, source_conn)

if not df_vistas.empty:
    # Convertir fechas y mapear tiempoID
    df_vistas['fecha_date'] = pd.to_datetime(df_vistas['fecha']).dt.date
    df_vistas['tiempo_id'] = df_vistas['fecha_date'].map(fecha_to_id)
    
    # Eliminar filas donde no se pudo mapear el tiempo_id
    df_vistas = df_vistas.dropna(subset=['tiempo_id'])
    df_vistas['tiempo_id'] = df_vistas['tiempo_id'].astype(int)

    # Mapear genero nombre -> id
    df_vistas['genero_id'] = df_vistas['Genero'].map(genero_to_id)
    df_vistas = df_vistas.dropna(subset=['genero_id'])
    df_vistas['genero_id'] = df_vistas['genero_id'].astype(int)

    # Limpieza: asegurar tipos numéricos válidos
    df_vistas['cantidad_vistas']     = pd.to_numeric(df_vistas['cantidad_vistas'],     errors='coerce').fillna(0).astype(int)
    df_vistas['tiempo_promedio_min'] = pd.to_numeric(df_vistas['tiempo_promedio_min'], errors='coerce')
    df_vistas['monto_recaudado_usd'] = pd.to_numeric(df_vistas['monto_recaudado_usd'], errors='coerce')

    # -------------------------------------------------Insertar datos en FactVistas
    records_count = 0
    for _, r in df_vistas.iterrows():
        try:
            titulo_id           = int(r['IdPelicula'])
            tiempo_id           = int(r['tiempo_id'])
            genero_id           = int(r['genero_id'])
            pais_id             = int(r['IdPais'])
            cantidad_vistas     = int(r['cantidad_vistas'])
            tiempo_promedio_min = None if pd.isna(r['tiempo_promedio_min']) else float(r['tiempo_promedio_min'])
            monto_recaudado_usd = None if pd.isna(r['monto_recaudado_usd']) else float(r['monto_recaudado_usd'])

            dest_cursor.execute("""
                INSERT INTO FactVistas (titulo_id, tiempo_id, genero_id, pais_id, cantidad_vistas, tiempo_promedio_min, monto_recaudado_usd)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, titulo_id, tiempo_id, genero_id, pais_id, cantidad_vistas, tiempo_promedio_min, monto_recaudado_usd)
            records_count += 1
        except Exception as e:
            print(f" Error insertando registro: {e}")
            continue

    dest_conn.commit()
    print(f"✓ {records_count} registros de vistas cargados.")
else:
    print(" No se encontraron registros de vistas para cargar")

# Cerrar conexiones
source_conn.close()
dest_conn.close()
print("ETL completado exitosamente. Data Mart de Netflix poblado correctamente.")