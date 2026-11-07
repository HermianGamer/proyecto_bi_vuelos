# -*- coding: utf-8 -*-
"""
Crea los usuarios de la app (app_lector y app_editor) en SQL Server local o en Azure SQL.

Ejecuta sql/03_usuarios_app.sql reemplazando las variables $(...) con los valores del .env.
Según DB_SERVER elige la sección del script:
  - LOCAL : login de servidor (conectado a master) + usuario en VuelosDW
  - AZURE : usuarios contenidos (conectado directamente a VuelosDW)
y en ambos casos aplica la sección PERMISOS.
Las contraseñas nunca se imprimen ni se guardan en el archivo .sql.
"""

import os
import re
import sys
from pathlib import Path

import pyodbc

from conexion import DB_DW, _conectar, es_servidor_local

SCRIPT = Path(__file__).resolve().parent.parent / "sql" / "03_usuarios_app.sql"


def variables():
    """Valores del .env que usa el script SQL (comillas simples escapadas para T-SQL)."""
    valores = {"DB_DW": DB_DW}
    for clave in ["DB_LECTOR_PASSWORD", "DB_EDITOR_PASSWORD"]:
        valor = os.getenv(clave)
        if not valor or valor == "cambiar_aqui":
            print(f"✗ Falta {clave} en el archivo .env")
            sys.exit(1)
        valores[clave] = valor.replace("'", "''")
    return valores


def secciones(texto):
    """Separa el script en secciones marcadas con '-- ==== NOMBRE ===='."""
    partes = re.split(r"^-- ==== (\w+) =*\s*$", texto, flags=re.MULTILINE)
    # partes = [encabezado, nombre1, cuerpo1, nombre2, cuerpo2, ...]
    return dict(zip(partes[1::2], partes[2::2]))


def bloques_sql(texto, valores):
    """Reemplaza las variables y separa el texto en bloques por cada línea GO."""
    texto = re.sub(r"\$\((\w+)\)", lambda m: valores[m.group(1)], texto)
    return [b.strip() for b in re.split(r"^\s*GO\s*$", texto, flags=re.MULTILINE | re.IGNORECASE) if b.strip()]


def mostrar_usuarios(cursor):
    """Imprime los usuarios creados y sus roles."""
    for fila in cursor.execute("""
        SELECT p.name, STRING_AGG(r.name, ', ') AS roles
        FROM sys.database_principals p
        LEFT JOIN sys.database_role_members m ON m.member_principal_id = p.principal_id
        LEFT JOIN sys.database_principals r ON r.principal_id = m.role_principal_id
        WHERE p.name IN ('app_lector', 'app_editor') GROUP BY p.name
    """):
        print(f"  {fila.name}: roles = {fila.roles or '(ninguno, permisos con GRANT)'}")


def main():
    """Ejecuta la sección LOCAL o AZURE y luego PERMISOS, como administrador (usuario del .env)."""
    local = es_servidor_local()
    seccion = "LOCAL" if local else "AZURE"
    base_datos = "master" if local else DB_DW  # en Azure no existe USE master
    print(f"Servidor {'local' if local else 'Azure'}: se ejecuta la sección {seccion} + PERMISOS")

    partes = secciones(SCRIPT.read_text(encoding="utf-8"))
    texto = partes[seccion] + "\nGO\n" + partes["PERMISOS"]

    conn = _conectar(base_datos, "servidor")  # con reintentos (Azure serverless se pausa)
    if not conn:
        sys.exit(1)
    conn.autocommit = True
    cursor = conn.cursor()
    try:
        for bloque in bloques_sql(texto, variables()):
            cursor.execute(bloque)
    except pyodbc.Error as e:
        print(f"✗ Error al crear los usuarios: {e}")
        if "40632" in str(e):
            print("  En Azure la contraseña no puede contener el nombre del usuario (app, lector, editor).")
        sys.exit(1)
    print("✓ Usuarios app_lector y app_editor listos en", DB_DW)
    mostrar_usuarios(cursor)
    conn.close()


if __name__ == "__main__":
    main()
