-- Usuarios de la aplicación (principio de mínimo privilegio)
--   app_lector : solo lectura (páginas del dashboard y consola SQL)
--   app_editor : lectura + escritura en FactVuelos y alta de fecha/aeropuerto/ruta (Gestión de vuelos)
--
-- Las contraseñas NO se escriben aquí: $(DB_LECTOR_PASSWORD), $(DB_EDITOR_PASSWORD) y $(DB_DW)
-- son variables (estilo sqlcmd) que reemplaza src/crear_usuarios_app.py con los valores del .env.
-- Ejecutar:  python src/crear_usuarios_app.py
-- Se puede volver a ejecutar: si el login ya existe, solo actualiza la contraseña.

-- =====================================================================
-- VERSIÓN LOCAL (SQL Server en la laptop): login de servidor + usuario
-- SQL Server local no admite usuarios contenidos por defecto, así que
-- primero se crea el LOGIN en master y luego el USER en la base de datos.
-- =====================================================================
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

-- Permisos (iguales en local y en Azure)
ALTER ROLE db_datareader ADD MEMBER app_lector;

GRANT SELECT ON SCHEMA::dbo TO app_editor;
GRANT INSERT, UPDATE, DELETE ON dbo.FactVuelos TO app_editor;
GRANT INSERT ON dbo.DimFecha TO app_editor;
GRANT INSERT ON dbo.DimAeropuerto TO app_editor;
GRANT INSERT ON dbo.DimRuta TO app_editor;
GO

-- =====================================================================
-- VERSIÓN AZURE SQL DATABASE: usuarios contenidos (sin login de servidor)
-- En Azure no existe USE master ni CREATE LOGIN para esto: conectarse
-- directamente a VuelosDW como administrador y ejecutar este bloque en el
-- editor de consultas del portal, con las contraseñas reales, en lugar de
-- la versión local de arriba. Luego aplicar los mismos permisos.
-- =====================================================================
-- CREATE USER app_lector WITH PASSWORD = '<contraseña-fuerte-1>';
-- CREATE USER app_editor WITH PASSWORD = '<contraseña-fuerte-2>';
-- ALTER ROLE db_datareader ADD MEMBER app_lector;
-- GRANT SELECT ON SCHEMA::dbo TO app_editor;
-- GRANT INSERT, UPDATE, DELETE ON dbo.FactVuelos TO app_editor;
-- GRANT INSERT ON dbo.DimFecha TO app_editor;
-- GRANT INSERT ON dbo.DimAeropuerto TO app_editor;
-- GRANT INSERT ON dbo.DimRuta TO app_editor;
