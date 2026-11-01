# 03 — Dashboard spec (Streamlit)

Multipage app in `app/`. **All queries run live against `VuelosDW`** (no full load at startup like the professor's example). All UI text in Spanish.

## Technical rules
- `app/db.py`: `consultar(sql, params) -> DataFrame` cached with `st.cache_data(ttl=300)`; `ejecutar(sql, params)` for writes, then `st.cache_data.clear()`. Connection via `st.cache_resource`, reconnect on failure (Azure auto-pause).
- **Always parameterized queries** (`?`), never f-strings with user values.
- Aggregate in SQL (`GROUP BY`); never pull 300k rows into pandas.
- Two DB users (`sql/03_usuarios_app.sql`): `app_lector` (read-only: dashboards + SQL console) and `app_editor` (SELECT + INSERT/UPDATE/DELETE on FactVuelos, INSERT on DimFecha/DimAeropuerto/DimRuta).
- No connection → `st.error` + "Reintentar" button. **Never sample data.**
- Global sidebar filters in `st.session_state`: date range, origin airport, time slot (franja).
- `plotly.express`. Fixed colors everywhere: green = A tiempo, amber = Demorado, red = Cancelado, grey = Desviado.

## Pages
1. **`app.py` — Resumen**: 4 `st.metric` (Vuelos programados, % Puntualidad, % Cancelación, Demora promedio de demorados); line % on-time and % cancelled by month; bar % on-time by weekday; stacked bars flights by status and month.
2. **`pages/1_Causas.py`**: 100% stacked bars of cause share (minutes) by month; bars minutes by controllability (Sí/Parcial/No); bars cancellations by cause.
3. **`pages/2_Aeropuertos_y_rutas.py`**: top 15 origin airports by % on-time (min 300 flights) with avg taxi-out; top 15 routes by total delay minutes and top 15 worst % on-time (min 100 flights).
4. **`pages/3_Horario.py`**: line % on-time by scheduled hour 0–23 (expected to worsen during the day); bar share of "Avión anterior retrasado" by franja; histogram by DimRangoDemora (ordered by `orden`).
5. **`pages/4_Consultas_SQL.py`** — read-only console with `app_lector`: `st.text_area` + "Ejecutar". Must start with SELECT/WITH; reject inner `;` and keywords INSERT/UPDATE/DELETE/DROP/ALTER/EXEC/CREATE/GRANT/MERGE/TRUNCATE. Max 1,000 rows, 30 s timeout, CSV download. Selector with 5–6 example queries (KPIs by month, causes by airport, worst route…).
6. **`pages/5_Gestion_de_vuelos.py`** — CRUD with `app_editor`, `st.tabs(["Registrar","Editar","Eliminar"])`:
   - Registrar: date, flight number, tail, origin/destination (selectbox from DimAeropuerto, or new one with code/city/state), scheduled hour, dep delay, arr delay, taxi-out, cancelled (+cause), diverted, cause minutes. Derived keys via **`src/reglas.py`**. Insert missing date/route/airport into their dims. `origen_registro = 'APP'`.
   - Editar: search by date + flight number + origin, show row, edit measures, recompute derived keys.
   - Eliminar: same search, show row, confirm checkbox before delete.
   - Show last 20 rows with `origen_registro = 'APP'`.
   - Validation: delays between -120 and 2000; cancelled → delays empty; cause minutes only if arr delay ≥ 15; duplicate natural key → friendly error.
7. **`pages/6_Propuesta.py`** — improvement simulator: sliders for % reduction of "Aerolínea" and "Avión anterior retrasado" minutes; cost per delay minute (USD, editable default, labeled as **supuesto**). Output: minutes saved/year, estimated new % on-time (recompute which flights drop below 15 min), USD savings. Supports rubric C2.3.
