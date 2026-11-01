-- Tabla de staging en VuelosOrigen: copia de los 26 campos BTS (solo JetBlue).
-- La ejecuta src/etl_02_cargar_staging.py si la tabla no existe.
IF OBJECT_ID('dbo.stg_vuelos', 'U') IS NULL
CREATE TABLE dbo.stg_vuelos (
    FlightDate                      DATE         NOT NULL,
    Reporting_Airline               VARCHAR(2)   NOT NULL,
    Flight_Number_Reporting_Airline INT          NOT NULL,
    Tail_Number                     VARCHAR(10)  NULL,
    Origin                          CHAR(3)      NOT NULL,
    OriginCityName                  VARCHAR(60)  NULL,
    OriginState                     CHAR(2)      NULL,
    OriginStateName                 VARCHAR(50)  NULL,
    Dest                            CHAR(3)      NOT NULL,
    DestCityName                    VARCHAR(60)  NULL,
    DestState                       CHAR(2)      NULL,
    DestStateName                   VARCHAR(50)  NULL,
    CRSDepTime                      INT          NOT NULL,
    DepDelay                        DECIMAL(6,1) NULL,
    ArrDelay                        DECIMAL(6,1) NULL,
    ArrDel15                        INT          NULL,
    TaxiOut                         DECIMAL(6,1) NULL,
    Cancelled                       INT          NOT NULL,
    CancellationCode                CHAR(1)      NULL,
    Diverted                        INT          NOT NULL,
    Distance                        INT          NULL,
    CarrierDelay                    DECIMAL(6,1) NULL,
    WeatherDelay                    DECIMAL(6,1) NULL,
    NASDelay                        DECIMAL(6,1) NULL,
    SecurityDelay                   DECIMAL(6,1) NULL,
    LateAircraftDelay               DECIMAL(6,1) NULL
);
