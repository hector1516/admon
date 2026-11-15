-- 0064_debug_audit.sql
-- Tablas para debugging y auditoría (bitácora de actividad)

GO

-- 1. Tabla de debug (errores con código único)
IF NOT EXISTS (SELECT 1 FROM sys.tables WHERE name = 'HUB_DebugLog')
BEGIN
    CREATE TABLE dbo.HUB_DebugLog (
        Id          BIGINT IDENTITY(1,1) PRIMARY KEY,
        Codigo      VARCHAR(30)    NOT NULL,  -- ADM-COT-LST-001
        App         VARCHAR(10)    NOT NULL,  -- ADM, FLD, etc.
        Modulo      VARCHAR(10)    NOT NULL,  -- COT, CLI, etc.
        Mensaje     NVARCHAR(500)  NOT NULL,
        Contexto    NVARCHAR(MAX)  NULL,      -- JSON con datos adicionales
        Url         NVARCHAR(500)  NULL,
        Usuario     VARCHAR(100)   NULL,
        Fecha       DATETIME       NOT NULL DEFAULT GETDATE()
    );
    PRINT 'HUB_DebugLog creada';
END
ELSE
    PRINT 'HUB_DebugLog ya existe';
GO

CREATE INDEX IX_DebugLog_Codigo ON dbo.HUB_DebugLog (Codigo, Fecha DESC);
GO
CREATE INDEX IX_DebugLog_Fecha ON dbo.HUB_DebugLog (Fecha DESC);
GO
CREATE INDEX IX_DebugLog_App_Modulo ON dbo.HUB_DebugLog (App, Modulo, Fecha DESC);
GO

-- 2. Extender HUB_ActivityLog para auditoría completa
IF NOT EXISTS (SELECT 1 FROM sys.columns WHERE object_id = OBJECT_ID('HUB_ActivityLog') AND name = 'App')
BEGIN
    ALTER TABLE dbo.HUB_ActivityLog ADD
        App VARCHAR(10) NULL,
        UsuarioId INT NULL,
        TipoAccion VARCHAR(20) NULL,
        Detalle NVARCHAR(500) NULL,
        Datos NVARCHAR(MAX) NULL,
        Dispositivo NVARCHAR(200) NULL,
        IpAddress VARCHAR(45) NULL,
        DuracionMs INT NULL;
    PRINT 'HUB_ActivityLog extendida';
END
ELSE
    PRINT 'HUB_ActivityLog ya tiene las columnas';
GO

CREATE INDEX IX_ActivityLog_Usuario_Fecha ON dbo.HUB_ActivityLog (Usuario, FechaHora DESC);
GO
CREATE INDEX IX_ActivityLog_Modulo ON dbo.HUB_ActivityLog (Modulo, FechaHora DESC);
GO
CREATE INDEX IX_ActivityLog_Tipo ON dbo.HUB_ActivityLog (TipoAccion, FechaHora DESC);
GO

-- 3. Job de limpieza (ejecutar diariamente)
-- DELETE FROM HUB_ActivityLog WHERE FechaHora < DATEADD(day, -30, GETDATE());
-- DELETE FROM HUB_DebugLog WHERE Fecha < DATEADD(day, -30, GETDATE());

PRINT '0064_debug_audit.sql aplicada';
GO