-- Usuarios de la aplicación (principio de mínimo privilegio)
--   app_lector : solo lectura (páginas del dashboard y consola SQL)
--   app_editor : lectura + escritura en FactVuelos y alta de fecha/aeropuerto/ruta (Gestión de vuelos)
--
-- Las contraseñas NO se escriben aquí: $(DB_LECTOR_PASSWORD), $(DB_EDITOR_PASSWORD) y $(DB_DW)
-- son variables (estilo sqlcmd) que reemplaza src/crear_usuarios_app.py con los valores del .env.
-- Ejecutar:  python src/crear_usuarios_app.py
-- El script elige la sección según DB_SERVER (localhost → LOCAL, Azure → AZURE) y luego
-- aplica PERMISOS. Se puede volver a ejecutar: si el usuario ya existe, solo cambia la contraseña.
-- En Azure las contraseñas NO pueden contener el nombre del usuario (error 40632).

-- ==== LOCAL =========================================================
-- SQL Server en la laptop: login de servidor (en master) + usuario en la BD.
-- SQL Server local no admite usuarios contenidos por defecto.
USE master;
GO
IF NOT EXISTS (SELECT 1 FROM sys.server_principals WHERE name = 'app_lector')
    CREATE LOGIN app_lector WITH PASSWORD = '$(DB_LECTOR_PASSWORD)', DEFAULT_DATABASE = [$(DB_DW)];
ELSE
    ALTER LOGIN app_lector WITH PASSWORD = '$(DB_LECTOR_PASSWORD)';

IF NOT EXISTS (SELECT 1 FROM sys.server_principals WHERE name = 'app_editor')
    CREATE LOGIN app_editor WITH PASSWORD = '$(DB_EDITOR_PASSWORD)', DEFAULT_DATABASE = [$(DB_DW)];
ELSE
    ALTER LOGIN app_editor WITH PASSWORD = '$(DB_EDITOR_PASSWORD)';
GO

USE [$(DB_DW)];
GO
IF NOT EXISTS (SELECT 1 FROM sys.database_principals WHERE name = 'app_lector')
    CREATE USER app_lector FOR LOGIN app_lector;
IF NOT EXISTS (SELECT 1 FROM sys.database_principals WHERE name = 'app_editor')
    CREATE USER app_editor FOR LOGIN app_editor;
GO

-- ==== AZURE =========================================================
-- Azure SQL Database: usuarios contenidos (viven solo dentro de VuelosDW,
-- sin login de servidor). Se ejecuta conectado directamente a VuelosDW.
IF NOT EXISTS (SELECT 1 FROM sys.database_principals WHERE name = 'app_lector')
    CREATE USER app_lector WITH PASSWORD = '$(DB_LECTOR_PASSWORD)';
ELSE
    ALTER USER app_lector WITH PASSWORD = '$(DB_LECTOR_PASSWORD)';

IF NOT EXISTS (SELECT 1 FROM sys.database_principals WHERE name = 'app_editor')
    CREATE USER app_editor WITH PASSWORD = '$(DB_EDITOR_PASSWORD)';
ELSE
    ALTER USER app_editor WITH PASSWORD = '$(DB_EDITOR_PASSWORD)';
GO

-- ==== PERMISOS ======================================================
-- Iguales en local y en Azure (se ejecutan dentro de VuelosDW).
ALTER ROLE db_datareader ADD MEMBER app_lector;

GRANT SELECT ON SCHEMA::dbo TO app_editor;
GRANT INSERT, UPDATE, DELETE ON dbo.FactVuelos TO app_editor;
GRANT INSERT ON dbo.DimFecha TO app_editor;
GRANT INSERT ON dbo.DimAeropuerto TO app_editor;
GRANT INSERT ON dbo.DimRuta TO app_editor;
GO
