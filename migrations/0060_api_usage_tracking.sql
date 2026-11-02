-- 0060_api_usage_tracking.sql
-- Tracking de uso de las apps (Admon y Field) para estadisticas.
-- Tabla compartida por ambas apps.

IF NOT EXISTS (SELECT 1 FROM sys.tables WHERE name = 'HUB_ApiUsage')
BEGIN
    CREATE TABLE HUB_ApiUsage (
        Id INT IDENTITY(1,1) PRIMARY KEY,
        App VARCHAR(20) NOT NULL,           -- 'admon' o 'field'
        Endpoint VARCHAR(200) NOT NULL,      -- '/api/cotizaciones/...'
        Metodo VARCHAR(10) NOT NULL,          -- GET, POST, PUT, DELETE
        Usuario VARCHAR(100),                -- nombre del usuario (del JWT)
        Fecha DATETIME2 NOT NULL DEFAULT GETDATE(),
        DuracionMs INT,                      -- tiempo de respuesta en ms
        StatusCode INT                       -- 200, 404, 500, etc.
    );
    CREATE INDEX IX_ApiUsage_Fecha ON HUB_ApiUsage(Fecha);
    CREATE INDEX IX_ApiUsage_App ON HUB_ApiUsage(App);
    CREATE INDEX IX_ApiUsage_Usuario ON HUB_ApiUsage(Usuario);
    PRINT 'Tabla HUB_ApiUsage creada.';
END
ELSE
    PRINT 'Tabla HUB_ApiUsage ya existe.';
GO