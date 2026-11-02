# -*- coding: utf-8 -*-
"""
Validador de la consola SQL: solo deja pasar consultas de lectura.

Es una primera barrera para dar mensajes claros. La barrera real son los permisos
de app_lector en la base de datos (solo db_datareader): aunque algo pase este
filtro, SQL Server rechaza cualquier escritura.
"""

import re

PALABRAS_PROHIBIDAS = [
    "INSERT", "UPDATE", "DELETE", "DROP", "ALTER", "EXEC", "EXECUTE", "CREATE",
    "GRANT", "REVOKE", "DENY", "MERGE", "TRUNCATE", "INTO",  # SELECT ... INTO crea una tabla
]


def quitar_comentarios(sql):
    """Elimina comentarios -- de línea y /* de bloque */."""
    sql = re.sub(r"/\*.*?\*/", " ", sql, flags=re.DOTALL)
    return re.sub(r"--[^\n]*", " ", sql)


def validar_consulta(sql):
    """Devuelve (True, consulta limpia) si es de solo lectura, o (False, mensaje de error)."""
    limpia = quitar_comentarios(sql).strip()
    if limpia.endswith(";"):  # se permite un solo ; al final
        limpia = limpia[:-1].strip()
    if not limpia:
        return False, "Escribe una consulta."
    if not re.match(r"(SELECT|WITH)\b", limpia, flags=re.IGNORECASE):
        return False, "La consulta debe empezar con SELECT o WITH."
    if ";" in limpia:
        return False, "Solo se permite una consulta (no uses ; en medio)."
    for palabra in PALABRAS_PROHIBIDAS:
        if re.search(rf"\b{palabra}\b", limpia, flags=re.IGNORECASE):
            return False, f"Palabra no permitida en la consola: {palabra}."
    return True, limpia
