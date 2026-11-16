-- 0065_indexes.sql — Índices para optimización de consultas (sin modificar tablas)
-- Solo crea índices, no altera estructura de tablas

GO

-- Cotizaciones
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_Cotizaciones_Fecha' AND object_id = OBJECT_ID('Cotizaciones'))
    CREATE INDEX IX_Cotizaciones_Fecha ON Cotizaciones(Fecha DESC);
GO
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_Cotizaciones_Cliente' AND object_id = OBJECT_ID('Cotizaciones'))
    CREATE INDEX IX_Cotizaciones_Cliente ON Cotizaciones(IdCliente);
GO

-- Clientes
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_Clientes_Nombre' AND object_id = OBJECT_ID('Clientes'))
    CREATE INDEX IX_Clientes_Nombre ON Clientes(Cliente);
GO

-- Reportes
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_Reportes_Fecha' AND object_id = OBJECT_ID('ReportesServicio'))
    CREATE INDEX IX_Reportes_Fecha ON ReportesServicio(Fecha DESC);
GO

-- Kilómetros
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_Kilometros_Fecha' AND object_id = OBJECT_ID('RegistroKilometros'))
    CREATE INDEX IX_Kilometros_Fecha ON RegistroKilometros(Fecha DESC);
GO

-- Usuarios
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_Users_Email' AND object_id = OBJECT_ID('HUB_Users'))
    CREATE INDEX IX_Users_Email ON HUB_Users(Email);
GO

-- Partidas
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_Partidas_Folio' AND object_id = OBJECT_ID('Partidas'))
    CREATE INDEX IX_Partidas_Folio ON Partidas(Folio);
GO

PRINT '0065_indexes.sql aplicada';
GO