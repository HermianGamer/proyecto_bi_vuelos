-- Ejecutar conectado a VuelosDW como administrador.
CREATE USER app_lector WITH PASSWORD = '<contraseña-fuerte-1>';
ALTER ROLE db_datareader ADD MEMBER app_lector;

CREATE USER app_editor WITH PASSWORD = '<contraseña-fuerte-2>';
GRANT SELECT ON SCHEMA::dbo TO app_editor;
GRANT INSERT, UPDATE, DELETE ON dbo.FactVuelos TO app_editor;
GRANT INSERT ON dbo.DimFecha TO app_editor;
GRANT INSERT ON dbo.DimAeropuerto TO app_editor;
GRANT INSERT ON dbo.DimRuta TO app_editor;
