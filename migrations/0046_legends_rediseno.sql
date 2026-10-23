-- Migración 0046: rediseño de ECCSA Legends
-- Fecha: 2026-10-23
-- Descripción:
--   * HUB_UserScores.RachaMax: mejor racha histórica (para logros y perfil).
--   * HUB_WeeklyWinners.SemanaKey: clave estable de la semana (domingo en
--     formato YYYY-MM-DD). Antes se comparaba por FechaInicio/FechaFin y el
--     cron nunca encontraba la semana correcta; además el historial tenía
--     fechas lunes-domingo y la regla nueva es domingo-sábado.
--   * HUB_UserLogros: logros desbloqueados por usuario (una fila por logro).
--     El bonus se registra en HUB_ScoreLog con Metrica='logro' y
--     ReferenciaId=orden del logro, así el índice único existente lo hace
--     idempotente.
--   * Índice por usuario+fecha en ScoreLog para que el overview y el auditor
--     no recorran la tabla completa.
--
-- La tabla HUB_ScoreLog ya tiene UX_ScoreLog_Entidad (IdUsuario, Metrica,
-- ReferenciaId); no se toca.
--
-- Aplicar primero en ECCSA_Admon_Pruebas y después en ECCSA_Admon.
-- Registrar en schema_migrations: '0046_legends_rediseno.sql'.

IF COL_LENGTH('dbo.HUB_UserScores', 'RachaMax') IS NULL
    ALTER TABLE dbo.HUB_UserScores ADD RachaMax INT NOT NULL
        CONSTRAINT DF_UserScores_RachaMax DEFAULT (0);
GO

-- En una base nueva HUB_WeeklyWinners puede no existir (la creaba la migración
-- 0022 de Field). Se crea aquí para que esta migración sea aplicable también a
-- ECCSA_Admon_Pruebas sin depender de haber corrido el repo de Field.
IF NOT EXISTS (SELECT 1 FROM sys.tables WHERE name = 'HUB_WeeklyWinners')
BEGIN
    CREATE TABLE dbo.HUB_WeeklyWinners (
        Id INT IDENTITY(1,1) PRIMARY KEY,
        IdUsuario INT NOT NULL,
        PuntuacionSemana INT NOT NULL CONSTRAINT DF_WeeklyWinners_Puntos DEFAULT (0),
        FechaInicio DATE NOT NULL,
        FechaFin DATE NOT NULL,
        FechaCalculo DATETIME NOT NULL CONSTRAINT DF_WeeklyWinners_Fecha DEFAULT (GETDATE()),
        CONSTRAINT FK_WeeklyWinners_Users FOREIGN KEY (IdUsuario)
            REFERENCES dbo.HUB_Users (Id)
    );
    CREATE INDEX IX_WeeklyWinners_Fechas
        ON dbo.HUB_WeeklyWinners (FechaInicio, FechaFin);
END
GO

IF COL_LENGTH('dbo.HUB_WeeklyWinners', 'SemanaKey') IS NULL
    ALTER TABLE dbo.HUB_WeeklyWinners ADD SemanaKey CHAR(10) NULL;
GO

-- Único por semana, pero permite varias filas legacy con NULL mientras el
-- backfill las normaliza.
IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE name = 'UX_WeeklyWinners_Semana'
      AND object_id = OBJECT_ID('dbo.HUB_WeeklyWinners')
)
    CREATE UNIQUE INDEX UX_WeeklyWinners_Semana
        ON dbo.HUB_WeeklyWinners (SemanaKey)
        WHERE SemanaKey IS NOT NULL;
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE name = 'IX_WeeklyWinners_FechaInicio'
      AND object_id = OBJECT_ID('dbo.HUB_WeeklyWinners')
)
    CREATE INDEX IX_WeeklyWinners_FechaInicio
        ON dbo.HUB_WeeklyWinners (FechaInicio DESC);
GO

IF NOT EXISTS (SELECT 1 FROM sys.tables WHERE name = 'HUB_UserLogros')
BEGIN
    CREATE TABLE dbo.HUB_UserLogros (
        Id            INT IDENTITY(1,1) NOT NULL PRIMARY KEY,
        IdUsuario     INT NOT NULL,
        LogroId       VARCHAR(40) NOT NULL,
        FechaObtenido DATETIME NOT NULL CONSTRAINT DF_UserLogros_Fecha DEFAULT (GETDATE()),
        Puntos        INT NOT NULL CONSTRAINT DF_UserLogros_Puntos DEFAULT (0),
        CONSTRAINT UQ_UserLogros_Usuario_Logro UNIQUE (IdUsuario, LogroId),
        CONSTRAINT FK_UserLogros_Usuario FOREIGN KEY (IdUsuario)
            REFERENCES dbo.HUB_Users (Id)
    );
END
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE name = 'IX_UserLogros_Usuario'
      AND object_id = OBJECT_ID('dbo.HUB_UserLogros')
)
    CREATE INDEX IX_UserLogros_Usuario
        ON dbo.HUB_UserLogros (IdUsuario, FechaObtenido DESC);
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE name = 'IX_ScoreLog_Usuario_Fecha'
      AND object_id = OBJECT_ID('dbo.HUB_ScoreLog')
)
    CREATE INDEX IX_ScoreLog_Usuario_Fecha
        ON dbo.HUB_ScoreLog (IdUsuario, FechaRegistro);
GO

-- Los bonus (racha y logros) no entran en UX_ScoreLog_Entidad, así que se
-- protegen con su propio índice único: una racha por día y un logro por
-- usuario/orden, aun si dos ciclos del auditor se solapan.
IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE name = 'UX_ScoreLog_Bonus'
      AND object_id = OBJECT_ID('dbo.HUB_ScoreLog')
)
    CREATE UNIQUE INDEX UX_ScoreLog_Bonus
        ON dbo.HUB_ScoreLog (IdUsuario, Metrica, ReferenciaId)
        WHERE ReferenciaId IS NOT NULL
          AND Metrica IN ('logro', 'racha_dia');
GO

-- Métricas económicas del rediseño 2026-10-23. No entran en
-- UX_ScoreLog_Entidad (que está filtrado a las métricas viejas), así que
-- llevan su propio índice único por usuario+métrica+entidad. `reporte_fotos`
-- además se protege en código de forma global (el punto es del reporte, no
-- del oficinista que subió la foto).
IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE name = 'UX_ScoreLog_Entidad_Economica'
      AND object_id = OBJECT_ID('dbo.HUB_ScoreLog')
)
    CREATE UNIQUE INDEX UX_ScoreLog_Entidad_Economica
        ON dbo.HUB_ScoreLog (IdUsuario, Metrica, ReferenciaId)
        WHERE ReferenciaId IS NOT NULL
          AND Metrica IN (
              'reporte_fotos', 'reporte_mismo_dia', 'cotizacion_entregada',
              'cotizacion_pagada', 'cliente_nuevo_cotizado',
              'cotizacion_con_partidas', 'cobranza_registrada',
              'vale_con_comprobante', 'vale_sin_comprobante',
              'reporte_tardio', 'retrabajo'
          );
GO
