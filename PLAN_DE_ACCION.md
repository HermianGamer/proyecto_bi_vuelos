# Plan de acción

Cada fase termina con un commit. Entre paréntesis, el criterio de la rúbrica que alimenta.

## Fase 0 — Preparación (1 día)
- [ ] Crear repo nuevo en GitHub, agregar a los 4 integrantes y al profesor (`javierwam`).
- [ ] Copiar el contenido de esta carpeta al repo y hacer el primer commit.
- [ ] Crear entorno: `python -m venv .venv` + `pip install -r requirements.txt`.
- [ ] Instalar **ODBC Driver 18 for SQL Server** en la laptop.
- [ ] Copiar `.env.example` → `.env` apuntando al SQL Server local.

## Fase 1 — Datos (1–2 días)
- [ ] `etl_01_descargar.py`: últimos 12 meses, solo JetBlue.
- [ ] Notebook de exploración: filas por mes, % nulos por columna, distribución de `ArrDelay`, conteo de cancelados y desviados, verificar que las 5 causas solo existen cuando `ArrDel15 = 1`.
- [ ] Comparar % puntualidad y % cancelación por mes con el *Air Travel Consumer Report* del DOT (validación de que los datos están bien).

## Fase 2 — 1ra entrega: README secciones 1–3 (C1.1, C1.3)
- [ ] Revisar y completar `README.md`: marco teórico, empresa y problemática, diccionario de datos, modelo dimensional (diagrama mermaid).
- [ ] Rellenar en la sección 2 las cifras reales que salgan de la Fase 1.

## Fase 3 — ETL (2–3 días)
- [ ] `src/reglas.py` + tests.
- [ ] `etl_02_cargar_staging.py` y `etl_03_poblar_datamart.py` contra **SQL Server local**.
- [ ] Validaciones del paso 10 de `docs/02_etl.md` sin errores.

## Fase 4 — Azure (1 día, cuando entreguen la cuenta)
- [ ] Pasos 0–5 de `docs/04_despliegue_azure.md`.
- [ ] Correr el ETL contra Azure.

## Fase 5 — Dashboard (3–4 días)
- [ ] Páginas en este orden: Resumen → Causas → Aeropuertos → Horario → Consultas SQL → Gestión de vuelos → Propuesta.
- [ ] Probar local contra Azure SQL.
- [ ] Desplegar en App Service (paso 6) y probar desde otra red (celular con datos móviles).

## Fase 6 — Análisis y propuesta (C1.2, C2.3)
- [ ] Llenar sección 4 del README con capturas y hallazgos (qué causa domina, en qué aeropuertos y horas).
- [ ] Propuesta con **acciones, cronograma, recursos y costos** (usar la página Propuesta para cuantificar).
- [ ] Conclusiones y recomendaciones (secciones 5 y 6).

## Fase 7 — Exposición (C2.1, C2.2)
- [ ] PPT de 10–12 diapositivas: problema → modelo → demo en vivo → hallazgos → propuesta.
- [ ] Ensayo con la app en Azure (abrirla 10 min antes para despertar la BD).

---

## Cómo usar Claude Code

1. Abre la terminal en la raíz del repo y ejecuta `claude`.
2. Primer mensaje (pégalo tal cual):

```
Lee CLAUDE.md, PLAN_DE_ACCION.md y todo docs/. No escribas código todavía.
Resúmeme en 10 líneas qué entendiste del proyecto y dime si hay algo
contradictorio o ambiguo en las especificaciones.
```

3. Luego, una fase por sesión, por ejemplo:

```
Fase 1: implementa src/conexion.py y src/etl_01_descargar.py según docs/02_etl.md.
Usa plan mode primero y muéstrame el plan antes de escribir.
```

```
Fase 3: implementa src/reglas.py con tests en tests/test_reglas.py, luego
etl_02 y etl_03. Imita el estilo de docs/ejemplos_profesor/poblar_datamart_Veterinaria__1_.py
pero con fast_executemany. Pruébalo contra mi SQL Server local.
```

```
Fase 5: implementa app/db.py y la página Resumen según docs/03_dashboard.md.
Cuando funcione, sigue con una página a la vez.
```

Consejos:
- Pídele que **corra** lo que escribe y te muestre la salida.
- Al final de cada fase: `"Resume los cambios y propón el mensaje de commit"`.
- Si propone cambiar el modelo dimensional, decide tú: el modelo está en `docs/01_modelo_dimensional.md`.
