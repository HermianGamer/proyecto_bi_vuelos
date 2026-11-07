# 04 — Guía de despliegue en Azure

Arquitectura final:

```
Navegador del profesor ──► Azure App Service (Streamlit) ──► Azure SQL Database
                                                             ├─ VuelosOrigen (staging)
                                                             └─ VuelosDW (data mart)
Laptop del equipo ── ETL (Python) ─────────────────────────────┘
```

## 0. Antes de empezar
- **Verifica el tipo de suscripción** (Portal → *Subscriptions*). Si dice **"Azure for Students Starter"**, la oferta gratuita de Azure SQL **no es compatible**; con "Azure for Students" (con crédito de USD 100) sí funciona.
- Azure for Students suele restringir **regiones**. Si al crear un recurso sale un error de *policy / allowed locations*, prueba otra región (East US 2, Central US, Brazil South) y usa **la misma región para todo**.
- Crea una **alerta de presupuesto** (Cost Management → Budgets) de USD 20 para no llevarte sorpresas.

## 1. Grupo de recursos
Portal → *Resource groups* → Create → `rg-bi-vuelos`, región elegida.

## 2. Servidor y bases de datos Azure SQL
1. Portal → *SQL databases* → Create.
2. Banner **"Want to try Azure SQL Database for free?" → Apply offer** (debe mostrar *Estimated cost/month: $0*).
3. Base de datos: `VuelosDW`. Servidor: *Create new* → nombre único (ej. `sql-bi-vuelos-<iniciales>`), autenticación **SQL authentication**, usuario admin y contraseña (guárdala).
4. *Behavior when free limit reached*: **Auto-pause the database until next month** (así nunca cobra).
5. Repetir para `VuelosOrigen` en el **mismo servidor** (la oferta da hasta 10 BD gratis por suscripción; cada una con 100 000 vCore-segundos/mes y 32 GB).
6. Servidor → *Networking*:
   - Public access: **Selected networks**.
   - ✅ *Allow Azure services and resources to access this server* (para App Service).
   - **Add your client IPv4 address** (para correr el ETL y SSMS desde tu laptop). Cada integrante agrega su IP.

> La BD gratuita es *serverless*: se pausa tras ~1 hora sin uso. La primera conexión puede tardar ~1 minuto o fallar una vez. Por eso el código reintenta. **Antes de la exposición, abre la app 5–10 minutos antes.**

## 3. Probar conexión
- Con **SSMS** o la extensión **SQL Server (mssql) de VS Code**: servidor `sql-bi-vuelos-xx.database.windows.net`, SQL login.
- Llenar `.env` (copiar de `.env.example`) y correr `python src/conexion.py` (debe imprimir ✓ en ambas).

## 4. Cargar datos
Primero prueba todo contra tu **SQL Server local** (cambiando `.env`). Cuando funcione:
```bash
python src/etl_01_descargar.py
python src/etl_02_cargar_staging.py      # → Azure VuelosOrigen
python src/etl_03_poblar_datamart.py     # → Azure VuelosDW
```

## 5. Usuarios de la aplicación
Con el `.env` apuntando a Azure, ejecutar:
```bash
python src/crear_usuarios_app.py
```
El script mira `DB_SERVER`: si es Azure ejecuta la sección **AZURE** de `sql/03_usuarios_app.sql` (usuarios contenidos, conectado directamente a VuelosDW); si es `localhost`, la sección **LOCAL** (login + usuario). En ambos casos aplica luego la sección **PERMISOS**. Usa las contraseñas del `.env` y se puede volver a ejecutar (solo cambia la contraseña).

> ⚠️ En Azure la contraseña **no puede contener el nombre del usuario** (`app`, `lector`, `editor`); si no, falla con el error 40632.

Equivale a ejecutar esto como admin en VuelosDW:
```sql
CREATE USER app_lector WITH PASSWORD = '<contraseña-fuerte-1>';
ALTER ROLE db_datareader ADD MEMBER app_lector;

CREATE USER app_editor WITH PASSWORD = '<contraseña-fuerte-2>';
GRANT SELECT ON SCHEMA::dbo TO app_editor;
GRANT INSERT, UPDATE, DELETE ON dbo.FactVuelos TO app_editor;
GRANT INSERT ON dbo.DimFecha TO app_editor;
GRANT INSERT ON dbo.DimAeropuerto TO app_editor;
GRANT INSERT ON dbo.DimRuta TO app_editor;
```
(Son *contained users*: existen solo dentro de VuelosDW.) La app **nunca** usa el usuario admin.

## 6. App Service para Streamlit
1. Portal → *App Services* → Create → **Web App**.
   - Publish: Code · Runtime: **Python 3.12** · OS: **Linux** · misma región.
   - Plan: **Basic B1** (≈ USD 13/mes del crédito). Se cobra por hora mientras el plan exista, aunque la app esté detenida: al terminar el curso, **elimina el plan** (o bájalo a F1).
2. *Settings → Configuration → General settings*:
   - **Startup command:**
     ```
     python -m streamlit run app/app.py --server.port 8000 --server.address 0.0.0.0 --server.headless true
     ```
   - **Web sockets: On** (Streamlit los necesita).
   - **Always on: On** (la app no se apaga por inactividad). Ojo: esto no mantiene despierta la BD serverless; si nadie usó la app en ~1 hora, la primera consulta tarda ~1 minuto mientras VuelosDW se reactiva.
3. *Settings → Environment variables (App settings)*:
   | Nombre | Valor |
   |---|---|
   | `DB_DRIVER` | `ODBC Driver 18 for SQL Server` |
   | `DB_SERVER` | `sql-bi-vuelos-xx.database.windows.net` |
   | `DB_DW` | `VuelosDW` |
   | `DB_LECTOR_USER` / `DB_LECTOR_PASSWORD` | credenciales de `app_lector` |
   | `DB_EDITOR_USER` / `DB_EDITOR_PASSWORD` | credenciales de `app_editor` |
   | `SCM_DO_BUILD_DURING_DEPLOYMENT` | `true` |
   | `WEBSITES_PORT` | `8000` |
4. *Deployment Center* → Source: **GitHub** → repo y rama `main` → guarda. Azure crea un workflow de GitHub Actions: cada `git push` despliega solo.
5. Abrir `https://<tu-app>.azurewebsites.net`.

## 7. Si algo falla
- *Monitoring → Log stream*: errores en vivo.
- Error de driver ODBC: *Development Tools → SSH* y correr `odbcinst -q -d`. Si no aparece el 18, prueba `ODBC Driver 17 for SQL Server` en `DB_DRIVER`.
- "Cannot open server… client IP not allowed": falta la regla de firewall (paso 2.6).
- "Database is paused / free limit reached": se agotaron los vCore-segundos del mes (revisa en la BD → *Overview*). Evita dejar la app consultando en bucle.
- La página queda en blanco o "Connecting…": Web sockets apagado.

## 8. Plan B si App Service está bloqueado en la suscripción
Desplegar el mismo repo en **Azure Container Apps** o, como última opción, en **Streamlit Community Cloud** apuntando a la misma Azure SQL (la BD sigue en Azure).

## 9. Después del curso
Detener o borrar `rg-bi-vuelos` para no consumir crédito.
