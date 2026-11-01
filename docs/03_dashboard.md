# 03 — Especificación del dashboard (Streamlit)

App multipágina en `app/`. Todas las consultas van **en vivo contra `VuelosDW`** (no se carga todo al inicio como en el ejemplo del profesor).

## Reglas técnicas
- `app/db.py` centraliza el acceso: `consultar(sql, params) -> DataFrame` con `st.cache_data(ttl=300)`; `ejecutar(sql, params)` para escrituras, que luego llama `st.cache_data.clear()`.
- **Siempre consultas parametrizadas** (`?`), nunca f-strings con valores del usuario.
- Agregar en SQL (`GROUP BY`), no traer 300 mil filas a pandas.
- Dos usuarios de BD (ver `sql/03_usuarios_app.sql`):
  - `app_lector` (solo lectura): dashboards y consola SQL.
  - `app_editor`: SELECT + INSERT/UPDATE/DELETE en `FactVuelos` e INSERT en `DimFecha`, `DimAeropuerto`, `DimRuta`.
- Si no hay conexión: `st.error` con el mensaje y un botón "Reintentar". **Nunca datos de ejemplo.**
- Barra lateral con filtros globales (`st.session_state`): rango de fechas, aeropuerto de origen, franja horaria.
- Gráficos con `plotly.express`. Colores: verde = a tiempo, ámbar = demorado, rojo = cancelado, gris = desviado (mismo color en todas las páginas).

## Páginas

### 1. `app.py` — Resumen
- 4 tarjetas (`st.metric`): Vuelos programados, % Puntualidad, % Cancelación, Demora promedio de los demorados (min).
- Línea: % puntualidad y % cancelación por mes.
- Barras: % puntualidad por día de la semana.
- Barras apiladas: vuelos por estado y mes.

### 2. `pages/1_Causas.py` — ¿Por qué se demora?
- Barras apiladas 100 %: participación de cada causa (minutos) por mes.
- Barras: minutos por causa agrupados en Controlable / Parcial / No controlable.
- Barras: cancelaciones por causa.

### 3. `pages/2_Aeropuertos_y_rutas.py`
- Tabla/barras: top 15 aeropuertos de origen por % puntualidad (mínimo 300 vuelos), con taxi-out promedio.
- Top 15 rutas con más minutos de demora total y top 15 con peor % puntualidad (mínimo 100 vuelos).

### 4. `pages/3_Horario.py` — Efecto del horario
- Línea: % puntualidad por hora programada de salida (0–23). Se espera que empeore a lo largo del día.
- Barras: participación de "Avión anterior retrasado" por franja.
- Histograma por `DimRangoDemora` (ordenado por `orden`).

### 5. `pages/4_Consultas_SQL.py` — consola de solo lectura
- `st.text_area` + botón Ejecutar, con conexión **`app_lector`**.
- Validar: debe empezar con `SELECT` o `WITH`; rechazar `;` intermedios y palabras como `INSERT/UPDATE/DELETE/DROP/ALTER/EXEC/CREATE/GRANT`.
- Máximo 1 000 filas (`fetchmany`), timeout de 30 s, botón para descargar CSV.
- Selector con 5–6 consultas de ejemplo (KPI por mes, causas por aeropuerto, peor ruta, etc.) para que el profesor pruebe rápido.

### 6. `pages/5_Gestion_de_vuelos.py` — alta, edición y baja (CRUD)
Pestañas `st.tabs(["Registrar", "Editar", "Eliminar"])`, conexión **`app_editor`**.
- **Registrar:** formulario con fecha, número de vuelo, matrícula, origen y destino (selectbox desde `DimAeropuerto`; permitir uno nuevo con código, ciudad y estado), hora programada, demora salida, demora llegada, taxi-out, cancelado (y causa), desviado, minutos por causa. Las claves `sk_estado`, `sk_rango_demora`, `sk_causa_demora`, `sk_horario` se calculan con **`src/reglas.py`**. Si la fecha o ruta no existe, se inserta en su dimensión. `origen_registro = 'APP'`.
- **Editar:** buscar por fecha + número de vuelo + origen, mostrar el registro, permitir cambiar las métricas y recalcular las claves derivadas.
- **Eliminar:** buscar igual, mostrar el registro y pedir confirmación (`st.checkbox`) antes de borrar.
- Mostrar al final una tabla con los últimos 20 registros con `origen_registro = 'APP'`.
- Validaciones: demora entre -120 y 2 000; si cancelado → demoras vacías; minutos por causa solo si demora de llegada ≥ 15.

### 7. `pages/6_Propuesta.py` — simulador para la propuesta de mejora
- Sliders: % de reducción de minutos por "Aerolínea" y por "Avión anterior retrasado"; costo por minuto de demora (USD, valor por defecto editable y citado como **supuesto** en el README).
- Muestra: minutos ahorrados al año, nuevo % puntualidad estimado (recalculando qué vuelos bajarían de 15 min) y ahorro en USD.
- Sirve para el criterio C2.3 (costos, tiempos, recursos).
