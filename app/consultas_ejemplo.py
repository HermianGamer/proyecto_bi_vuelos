# -*- coding: utf-8 -*-
"""Consultas de ejemplo de la consola SQL (todas de solo lectura sobre VuelosDW)."""

EJEMPLOS = {
    "KPI por mes": """SELECT d.anio, d.mes, d.nombre_mes,
       COUNT(*) AS vuelos,
       SUM(f.es_puntual) * 100.0 / COUNT(*)   AS pct_puntualidad,
       SUM(f.es_cancelado) * 100.0 / COUNT(*) AS pct_cancelacion
FROM FactVuelos f
JOIN DimFecha d ON f.sk_fecha = d.sk_fecha
GROUP BY d.anio, d.mes, d.nombre_mes
ORDER BY d.anio, d.mes""",
    "Causas de demora por aeropuerto (top 10)": """SELECT TOP 10 o.codigo_iata, o.ciudad,
       COUNT(*) AS vuelos_demorados,
       SUM(f.min_causa_aerolinea)    AS min_aerolinea,
       SUM(f.min_causa_avion_tardio) AS min_avion_tardio,
       SUM(f.min_causa_trafico)      AS min_trafico,
       SUM(f.min_causa_clima)        AS min_clima,
       SUM(f.min_causa_seguridad)    AS min_seguridad
FROM FactVuelos f
JOIN DimAeropuerto o ON f.sk_origen = o.sk_aeropuerto
WHERE f.sk_estado = 2   -- solo vuelos demorados
GROUP BY o.codigo_iata, o.ciudad
ORDER BY vuelos_demorados DESC""",
    "Peores rutas (mín. 100 vuelos)": """SELECT TOP 10 r.ruta, r.distancia_millas, r.tipo_distancia,
       COUNT(*) AS vuelos,
       SUM(f.es_puntual) * 100.0 / COUNT(*) AS pct_puntualidad
FROM FactVuelos f
JOIN DimRuta r ON f.sk_ruta = r.sk_ruta
GROUP BY r.ruta, r.distancia_millas, r.tipo_distancia
HAVING COUNT(*) >= 100
ORDER BY pct_puntualidad ASC""",
    "Cancelaciones por causa y mes": """SELECT d.anio, d.mes, c.causa, COUNT(*) AS cancelaciones
FROM FactVuelos f
JOIN DimFecha d            ON f.sk_fecha = d.sk_fecha
JOIN DimCausaCancelacion c ON f.sk_causa_cancelacion = c.sk_causa_cancelacion
WHERE f.es_cancelado = 1
GROUP BY d.anio, d.mes, c.causa
ORDER BY d.anio, d.mes, cancelaciones DESC""",
    "Puntualidad por franja horaria": """SELECT h.franja,
       COUNT(*) AS vuelos,
       SUM(f.es_puntual) * 100.0 / COUNT(*) AS pct_puntualidad,
       AVG(f.taxi_out_min * 1.0)            AS taxi_out_promedio
FROM FactVuelos f
JOIN DimHorario h ON f.sk_horario = h.sk_horario
GROUP BY h.franja
ORDER BY MIN(h.sk_horario)""",
    "Aviones (matrícula) con más vuelos demorados": """SELECT TOP 10 f.matricula,
       COUNT(*) AS vuelos,
       SUM(CASE WHEN f.sk_estado = 2 THEN 1 ELSE 0 END) AS demorados,
       SUM(f.min_causa_aerolinea) AS min_causa_aerolinea
FROM FactVuelos f
WHERE f.matricula IS NOT NULL
GROUP BY f.matricula
ORDER BY demorados DESC""",
}
