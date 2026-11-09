-- 0062_idempotency_keys.sql
-- Tabla para claves de idempotencia (protección contra duplicados)
-- Fecha: 2026-11-09

IF NOT EXISTS (SELECT 1 FROM sys.tables WHERE name = 'HUB_IdempotencyKeys')
BEGIN
    CREATE TABLE dbo.HUB_IdempotencyKeys (
        Id INT IDENTITY(1,1) PRIMARY KEY,
        Clave VARCHAR(36) NOT NULL,
        Entidad VARCHAR(50) NOT NULL,
        IdEntidad INT NULL,
        FechaCreacion DATETIME DEFAULT GETDATE(),
        CONSTRAINT UQ_IdempotencyKeys_Clave UNIQUE (Clave)
    );
    CREATE INDEX IX_IdempotencyKeys_Clave ON dbo.HUB_IdempotencyKeys(Clave);
    PRINT 'Tabla HUB_IdempotencyKeys creada.';
END
ELSE
    PRINT 'Tabla HUB_IdempotencyKeys ya existe.';
GO
"