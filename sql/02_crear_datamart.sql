-- Generado por src/etl_03_poblar_datamart.py (no editar a mano)
IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='DimFecha' AND xtype='U')
CREATE TABLE DimFecha (
    sk_fecha INT PRIMARY KEY, fecha DATE NOT NULL UNIQUE, anio SMALLINT NOT NULL,
    trimestre TINYINT NOT NULL, mes TINYINT NOT NULL, nombre_mes NVARCHAR(15) NOT NULL,
    nombre_dia NVARCHAR(15) NOT NULL, es_fin_semana BIT NOT NULL, es_feriado BIT NOT NULL);

IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='DimAeropuerto' AND xtype='U')
CREATE TABLE DimAeropuerto (
    sk_aeropuerto INT IDENTITY(1,1) PRIMARY KEY, codigo_iata CHAR(3) NOT NULL UNIQUE,
    ciudad NVARCHAR(60) NULL, estado CHAR(2) NULL, nombre_estado NVARCHAR(50) NULL,
    es_base_principal BIT NOT NULL DEFAULT 0,
    latitud DECIMAL(9,6) NULL, longitud DECIMAL(9,6) NULL);

-- Si la tabla ya existía sin coordenadas, se agregan las columnas
IF COL_LENGTH('DimAeropuerto', 'latitud') IS NULL
ALTER TABLE DimAeropuerto ADD latitud DECIMAL(9,6) NULL, longitud DECIMAL(9,6) NULL;

IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='DimRuta' AND xtype='U')
CREATE TABLE DimRuta (
    sk_ruta INT IDENTITY(1,1) PRIMARY KEY, ruta VARCHAR(7) NOT NULL UNIQUE,
    origen CHAR(3) NOT NULL, destino CHAR(3) NOT NULL,
    distancia_millas INT NULL, tipo_distancia NVARCHAR(10) NULL);

IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='DimHorario' AND xtype='U')
CREATE TABLE DimHorario (
    sk_horario TINYINT PRIMARY KEY, bloque CHAR(9) NOT NULL, franja NVARCHAR(12) NOT NULL);

IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='DimEstadoVuelo' AND xtype='U')
CREATE TABLE DimEstadoVuelo (
    sk_estado TINYINT PRIMARY KEY, estado NVARCHAR(15) NOT NULL, descripcion NVARCHAR(120) NULL);

IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='DimCausaDemora' AND xtype='U')
CREATE TABLE DimCausaDemora (
    sk_causa_demora TINYINT PRIMARY KEY, codigo CHAR(3) NOT NULL,
    causa NVARCHAR(40) NOT NULL, controlable NVARCHAR(10) NULL);

IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='DimCausaCancelacion' AND xtype='U')
CREATE TABLE DimCausaCancelacion (
    sk_causa_cancelacion TINYINT PRIMARY KEY, codigo CHAR(1) NOT NULL,
    causa NVARCHAR(40) NOT NULL, controlable NVARCHAR(10) NULL);

IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='DimRangoDemora' AND xtype='U')
CREATE TABLE DimRangoDemora (
    sk_rango_demora TINYINT PRIMARY KEY, rango NVARCHAR(30) NOT NULL,
    min_desde INT NULL, min_hasta INT NULL, orden TINYINT NOT NULL);

IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='FactVuelos' AND xtype='U')
CREATE TABLE FactVuelos (
    id_vuelo BIGINT IDENTITY(1,1) PRIMARY KEY,
    sk_fecha INT NOT NULL REFERENCES DimFecha(sk_fecha),
    sk_origen INT NOT NULL REFERENCES DimAeropuerto(sk_aeropuerto),
    sk_destino INT NOT NULL REFERENCES DimAeropuerto(sk_aeropuerto),
    sk_ruta INT NOT NULL REFERENCES DimRuta(sk_ruta),
    sk_horario TINYINT NOT NULL REFERENCES DimHorario(sk_horario),
    sk_estado TINYINT NOT NULL REFERENCES DimEstadoVuelo(sk_estado),
    sk_causa_demora TINYINT NOT NULL REFERENCES DimCausaDemora(sk_causa_demora),
    sk_causa_cancelacion TINYINT NOT NULL REFERENCES DimCausaCancelacion(sk_causa_cancelacion),
    sk_rango_demora TINYINT NOT NULL REFERENCES DimRangoDemora(sk_rango_demora),
    numero_vuelo INT NOT NULL, matricula VARCHAR(10) NULL,
    demora_salida_min INT NULL, demora_llegada_min INT NULL, taxi_out_min INT NULL,
    es_puntual TINYINT NOT NULL, es_cancelado TINYINT NOT NULL, es_desviado TINYINT NOT NULL,
    min_causa_aerolinea INT NULL, min_causa_clima INT NULL, min_causa_trafico INT NULL,
    min_causa_seguridad INT NULL, min_causa_avion_tardio INT NULL,
    origen_registro VARCHAR(5) NOT NULL DEFAULT 'ETL',
    fecha_carga DATETIME2 NOT NULL DEFAULT SYSDATETIME());

IF NOT EXISTS (SELECT * FROM sys.indexes WHERE name='UX_Fact_Natural')
CREATE UNIQUE INDEX UX_Fact_Natural ON FactVuelos (sk_fecha, numero_vuelo, sk_origen);
IF NOT EXISTS (SELECT * FROM sys.indexes WHERE name='IX_Fact_Fecha')
CREATE INDEX IX_Fact_Fecha  ON FactVuelos (sk_fecha);
IF NOT EXISTS (SELECT * FROM sys.indexes WHERE name='IX_Fact_Origen')
CREATE INDEX IX_Fact_Origen ON FactVuelos (sk_origen, sk_fecha);
