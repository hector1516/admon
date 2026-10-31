-- Migracion 0048: historial de estatus de cotizaciones
-- Fecha: 2026-10-31
-- Descripcion:
--   * HUB_CotizacionEstatusHistorial: registra cada cambio de estatus de una cotizacion.
--   * Para cotizaciones existentes con Color=1, se usa la fecha de creacion como aproximacion.
--   * A partir de hoy, los cambios se registran con fecha exacta.
--
-- Aplicar primero en ECCSA_Admon_Pruebas y despues en ECCSA_Admon.
-- Registrar en schema_migrations: '0048_cotizacion_estatus_historial.sql'.

IF NOT EXISTS (SELECT 1 FROM sys.tables WHERE name = 'HUB_CotizacionEstatusHistorial')
BEGIN
    CREATE TABLE dbo.HUB_CotizacionEstatusHistorial (
        Id INT IDENTITY(1,1) PRIMARY KEY,
        Folio INT NOT NULL,
        EstatusAnterior INT NULL,
        EstatusNuevo INT NOT NULL,
        FechaCambio DATETIME NOT NULL CONSTRAINT DF_CotEstHist_Fecha DEFAULT (GETDATE()),
        Usuario NVARCHAR(100) NULL,
        CONSTRAINT FK_CotEstHist_Folio FOREIGN KEY (Folio)
            REFERENCES dbo.IndiceMateriales (Folio)
    );
    CREATE INDEX IX_CotEstHist_Folio ON dbo.HUB_CotizacionEstatusHistorial (Folio);
    CREATE INDEX IX_CotEstHist_Estatus ON dbo.HUB_CotizacionEstatusHistorial (EstatusNuevo, FechaCambio);
END
GO

-- Poblar historial para cotizaciones existentes con Color=1 (fecha de creacion como aproximacion)
INSERT INTO dbo.HUB_CotizacionEstatusHistorial (Folio, EstatusAnterior, EstatusNuevo, FechaCambio, Usuario)
SELECT Folio, 0, 1, Fecha, 'Sistema (fecha de creacion - aproximada)'
FROM dbo.IndiceMateriales
WHERE Color = 1
  AND Folio NOT IN (SELECT Folio FROM dbo.HUB_CotizacionEstatusHistorial WHERE EstatusNuevo = 1);
GO
