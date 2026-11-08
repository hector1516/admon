-- 0061_oxxogas_vales_solicitud.sql
-- Agrega IdSolicitudVale a HUB_OxxoGasVales para match directo con tickets.
-- Fecha: 2026-11-03

IF NOT EXISTS (SELECT 1 FROM sys.columns WHERE object_id = OBJECT_ID('dbo.HUB_OxxoGasVales') AND name = 'IdSolicitudVale')
BEGIN
    ALTER TABLE dbo.HUB_OxxoGasVales ADD IdSolicitudVale INT NULL;
    PRINT 'Columna IdSolicitudVale agregada a HUB_OxxoGasVales.';
END
ELSE
    PRINT 'Columna IdSolicitudVale ya existe.';
GO

-- Indice para JOIN rapido
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_OxxoGasVales_Solicitud' AND object_id = OBJECT_ID('dbo.HUB_OxxoGasVales'))
BEGIN
    CREATE INDEX IX_OxxoGasVales_Solicitud ON dbo.HUB_OxxoGasVales(IdSolicitudVale);
    PRINT 'Indice IX_OxxoGasVales_Solicitud creado.';
END
GO

-- FK a HUB_SolicitudVales (opcional, para integridad referencial)
-- IF NOT EXISTS (SELECT 1 FROM sys.foreign_keys WHERE name = 'FK_OxxoGasVales_Solicitud')
-- BEGIN
--     ALTER TABLE dbo.HUB_OxxoGasVales ADD CONSTRAINT FK_OxxoGasVales_Solicitud
--         FOREIGN KEY (IdSolicitudVale) REFERENCES dbo.HUB_SolicitudVales(Id);
-- END
-- GO