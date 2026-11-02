# -*- coding: utf-8 -*-
"""
Crea los usuarios de la app (app_lector y app_editor) en el SQL Server local.

Ejecuta sql/03_usuarios_app.sql reemplazando las variables $(...) con los valores del .env.
Las contraseñas nunca se imprimen ni se guardan en el archivo .sql.
"""

import os
import re
import sys
from pathlib import Path

import pyodbc

from conexion import DB_DW, cadena_conexion

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


def bloques_sql(texto, valores):
    """Reemplaza las variables y separa el script en bloques por cada línea GO."""
    texto = re.sub(r"\$\((\w+)\)", lambda m: valores[m.group(1)], texto)
    return [b.strip() for b in re.split(r"^\s*GO\s*$", texto, flags=re.MULTILINE | re.IGNORECASE) if b.strip()]


def main():
    """Ejecuta el script como administrador (usuario del .env) conectado a master."""
    conn = pyodbc.connect(cadena_conexion("master"), autocommit=True)
    cursor = conn.cursor()
    for bloque in bloques_sql(SCRIPT.read_text(encoding="utf-8"), variables()):
        cursor.execute(bloque)
    print("✓ Usuarios app_lector y app_editor listos en", DB_DW)
    for fila in cursor.execute("""
        SELECT p.name, STRING_AGG(r.name, ', ') AS roles
        FROM sys.database_principals p
        LEFT JOIN sys.database_role_members m ON m.member_principal_id = p.principal_id
        LEFT JOIN sys.database_principals r ON r.principal_id = m.role_principal_id
        WHERE p.name IN ('app_lector', 'app_editor') GROUP BY p.name
    """):
        print(f"  {fila.name}: roles = {fila.roles or '(ninguno, permisos con GRANT)'}")
    conn.close()


if __name__ == "__main__":
    main()
