# -*- coding: utf-8 -*-
"""
Created on Fri Oct 24 10:28:19 2025

@author: JG.WamB
"""

import pyodbc
import pandas as pd

def get_connection_origen():
    try:
        conn = pyodbc.connect(
            'DRIVER={ODBC Driver 17 for SQL Server};'
            'SERVER=localhost;'
            'DATABASE=Veterinaria;'
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
            'DATABASE=VeterinariaDW;'
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
        trimestre INT NOT NULL,  -- Cambiado a INT para almacenar 1,2,3,4
        dia_semana NVARCHAR(15) NOT NULL
    );

    IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='DimVeterinario' AND xtype='U')
    CREATE TABLE DimVeterinario (
        id INT PRIMARY KEY,
        nombre NVARCHAR(100) NOT NULL,
        especialidad NVARCHAR(50) NOT NULL
    );

    IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='DimMascota' AND xtype='U')
    CREATE TABLE DimMascota (
        id INT PRIMARY KEY,
        nombre NVARCHAR(50) NOT NULL,
        especie NVARCHAR(30) NOT NULL,
        raza NVARCHAR(50) NULL
    );

    IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='DimServicio' AND xtype='U')
    CREATE TABLE DimServicio (
        id INT PRIMARY KEY,
        nombre NVARCHAR(100) NOT NULL,
        precio_unitario DECIMAL(10,2) NOT NULL
    );

    IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='FactAtenciones' AND xtype='U')
    CREATE TABLE FactAtenciones (
        mascota_id INT NOT NULL,
        veterinario_id INT NOT NULL,
        tiempo_id INT NOT NULL,
        servicio_id INT NOT NULL,
        cantidad INT NOT NULL,
        monto_total DECIMAL(10,2) NOT NULL,
        FOREIGN KEY (mascota_id) REFERENCES DimMascota(id),
        FOREIGN KEY (veterinario_id) REFERENCES DimVeterinario(id),
        FOREIGN KEY (tiempo_id) REFERENCES DimTiempo(id),
        FOREIGN KEY (servicio_id) REFERENCES DimServicio(id)
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
    cursor.execute("DELETE FROM FactAtenciones")
    print("  → Tabla FactAtenciones vaciada.")
    
    # 2. Borrar dimensiones
    cursor.execute("DELETE FROM DimServicio")
    print("  → Tabla DimServicio vaciada.")
    
    cursor.execute("DELETE FROM DimMascota")
    print("  → Tabla DimMascota vaciada.")
    
    cursor.execute("DELETE FROM DimVeterinario")
    print("  → Tabla DimVeterinario vaciada.")
    
    cursor.execute("DELETE FROM DimTiempo")
    print("  → Tabla DimTiempo vaciada.")
    
    conn.commit()
    print(" Data Mart limpiado completamente.\n")

clean_datamart(dest_cursor, dest_conn)

# -------------------------------------------------------------- Cargar dimensiones ---

# DimVeterinario
print("Cargando DimVeterinario...")
query_veterinarios = "SELECT id, nombre, especialidad FROM Veterinarios"
df_veterinarios = pd.read_sql(query_veterinarios, source_conn)
for _, r in df_veterinarios.iterrows():
    dest_cursor.execute("INSERT INTO DimVeterinario (id, nombre, especialidad) VALUES (?, ?, ?)", 
                       int(r['id']), str(r['nombre']), str(r['especialidad']))
dest_conn.commit()
print(f"✓ {len(df_veterinarios)} veterinarios cargados.")

#------------------------------------------- DimMascota
print("Cargando DimMascota...")
query_mascotas = "SELECT id, nombre, especie, raza FROM Mascotas"
df_mascotas = pd.read_sql(query_mascotas, source_conn)
for _, r in df_mascotas.iterrows():
    raza = r['raza'] if not pd.isna(r['raza']) else None
    dest_cursor.execute("INSERT INTO DimMascota (id, nombre, especie, raza) VALUES (?, ?, ?, ?)", 
                       int(r['id']), str(r['nombre']), str(r['especie']), raza)
dest_conn.commit()
print(f"✓ {len(df_mascotas)} mascotas cargadas.")

# -------------------------------------------DimServicio
print("Cargando DimServicio...")
query_servicios = "SELECT id, nombre, precio FROM Servicios"
df_servicios = pd.read_sql(query_servicios, source_conn)
for _, r in df_servicios.iterrows():
    dest_cursor.execute("INSERT INTO DimServicio (id, nombre, precio_unitario) VALUES (?, ?, ?)", 
                       int(r['id']), str(r['nombre']), float(r['precio']))
dest_conn.commit()
print(f"✓ {len(df_servicios)} servicios cargados.")

# --------------------------------------------DimTiempo
print("Cargando DimTiempo...")
query_fechas = "SELECT DISTINCT fecha FROM Atenciones WHERE fecha IS NOT NULL ORDER BY fecha"
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
    print("⚠ No se encontraron fechas en la tabla Atenciones")

# Obtener mapeo real de fecha -> id
df_tiempo_db = pd.read_sql("SELECT id, fecha FROM DimTiempo", dest_conn)
df_tiempo_db['fecha'] = pd.to_datetime(df_tiempo_db['fecha']).dt.date
fecha_to_id = dict(zip(df_tiempo_db['fecha'], df_tiempo_db['id']))

# ------------------------------------------------------------------- Tabla de Hechos: FactAtenciones
print("Cargando FactAtenciones...")
query_atenciones = """
    SELECT 
        a.mascota_id,
        a.veterinario_id,
        a.fecha,
        da.servicio_id,
        ISNULL(da.cantidad, 1) as cantidad,
        s.precio * ISNULL(da.cantidad, 1) as monto_total
    FROM Atenciones a
    JOIN DetallesAtencion da ON a.id = da.atencion_id
    JOIN Servicios s ON da.servicio_id = s.id
    WHERE a.mascota_id IS NOT NULL 
      AND a.veterinario_id IS NOT NULL 
      AND a.fecha IS NOT NULL
      AND da.servicio_id IS NOT NULL
      AND s.precio IS NOT NULL
"""

df_atenciones = pd.read_sql(query_atenciones, source_conn)

if not df_atenciones.empty:
    # Convertir fechas y mapear tiempoID
    df_atenciones['fecha_date'] = pd.to_datetime(df_atenciones['fecha']).dt.date
    df_atenciones['tiempo_id'] = df_atenciones['fecha_date'].map(fecha_to_id)
    
    # Eliminar filas donde no se pudo mapear el tiempo_id
    df_atenciones = df_atenciones.dropna(subset=['tiempo_id'])
    df_atenciones['tiempo_id'] = df_atenciones['tiempo_id'].astype(int)

    # Limpieza: asegurar tipos numéricos válidos
    df_atenciones['cantidad'] = pd.to_numeric(df_atenciones['cantidad'], errors='coerce').fillna(1).astype(int)
    df_atenciones['monto_total'] = pd.to_numeric(df_atenciones['monto_total'], errors='coerce')
    df_atenciones = df_atenciones.dropna(subset=['monto_total'])

    # -------------------------------------------------Insertar datos en FactAtenciones
    records_count = 0
    for _, r in df_atenciones.iterrows():
        try:
            mascota_id = int(r['mascota_id'])
            veterinario_id = int(r['veterinario_id'])
            tiempo_id = int(r['tiempo_id'])
            servicio_id = int(r['servicio_id'])
            cantidad = int(r['cantidad'])
            monto_total = float(r['monto_total'])

            dest_cursor.execute("""
                INSERT INTO FactAtenciones (mascota_id, veterinario_id, tiempo_id, servicio_id, cantidad, monto_total)
                VALUES (?, ?, ?, ?, ?, ?)
            """, mascota_id, veterinario_id, tiempo_id, servicio_id, cantidad, monto_total)
            records_count += 1
        except Exception as e:
            print(f" Error insertando registro: {e}")
            continue

    dest_conn.commit()
    print(f"✓ {records_count} atenciones cargadas.")
else:
    print(" No se encontraron atenciones para cargar")

# Cerrar conexiones
source_conn.close()
dest_conn.close()
print("ETL completado exitosamente. Data Mart de Veterinaria poblado correctamente.")