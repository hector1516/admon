-- 0061 · Horarios de asistencia: catálogo + asignación por usuario
--
-- Revisada el 2026-11-21 ANTES de aplicarse: la primera versión guardaba una
-- fila por usuario y día, pero en la oficina hay horarios con nombre
-- («Operativo», «Administrativo») que comparten varias personas. Se rehace con
-- tres tablas:
--
--   1. HUB_AsistenciaHorarios       · el catálogo: nombre del horario
--   2. HUB_AsistenciaHorarioDias    · los 7 días de cada horario
--   3. HUB_AsistenciaUsuarioHorario · a quién se le asignó cada horario
--
-- El total semanal y la comparativa con la LFT NO se guardan: se calculan
-- (SUM de los días) en la API y en la pantalla, para que no se desincronicen.
--
-- No toca ninguna tabla existente: son tres tablas nuevas, sin ALTER.

-- ── 1. Catálogo de horarios ────────────────────────────────────────────────
IF OBJECT_ID('dbo.HUB_AsistenciaHorarios', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.HUB_AsistenciaHorarios (
        Id             INT IDENTITY(1,1) NOT NULL
            CONSTRAINT PK_HUB_AsistenciaHorarios PRIMARY KEY,
        Nombre         NVARCHAR(60)  NOT NULL,   -- «Operativo», «Administrativo»
        Activo         BIT           NOT NULL CONSTRAINT DF_AsisHor_Activo DEFAULT (1),
        Notas          NVARCHAR(200) NULL,
        Actualizado    DATETIME      NOT NULL CONSTRAINT DF_AsisHor_Actualizado DEFAULT (GETDATE()),
        ActualizadoPor INT           NULL,
        CONSTRAINT UQ_AsisHor_Nombre UNIQUE (Nombre)
    );
    PRINT 'HUB_AsistenciaHorarios creada';
END
ELSE
    PRINT 'HUB_AsistenciaHorarios ya existe';
GO

-- ── 2. Los días de cada horario ────────────────────────────────────────────
IF OBJECT_ID('dbo.HUB_AsistenciaHorarioDias', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.HUB_AsistenciaHorarioDias (
        Id           INT IDENTITY(1,1) NOT NULL
            CONSTRAINT PK_HUB_AsistenciaHorarioDias PRIMARY KEY,
        IdHorario    INT          NOT NULL,
        DiaSemana    TINYINT      NOT NULL,   -- 1 = lunes … 7 = domingo
        HoraEntrada  TIME(0)      NULL,
        HoraSalida   TIME(0)      NULL,
        ComidaMin    SMALLINT     NOT NULL CONSTRAINT DF_AsisHorDia_Comida DEFAULT (60),
        Descanso     BIT          NOT NULL CONSTRAINT DF_AsisHorDia_Descanso DEFAULT (0),
        CONSTRAINT FK_AsisHorDia_Horario FOREIGN KEY (IdHorario)
            REFERENCES dbo.HUB_AsistenciaHorarios (Id) ON DELETE CASCADE,
        CONSTRAINT CK_AsisHorDia_Dia    CHECK (DiaSemana BETWEEN 1 AND 7),
        CONSTRAINT CK_AsisHorDia_Comida CHECK (ComidaMin >= 0 AND ComidaMin <= 240),
        -- Un día laborable necesita entrada y salida; uno de descanso no.
        CONSTRAINT CK_AsisHorDia_Horas  CHECK (
            Descanso = 1 OR (HoraEntrada IS NOT NULL AND HoraSalida IS NOT NULL)
        )
    );

    -- Un solo juego de horas por día y horario.
    CREATE UNIQUE INDEX UX_AsisHorDia_Horario_Dia
        ON dbo.HUB_AsistenciaHorarioDias (IdHorario, DiaSemana);
    PRINT 'HUB_AsistenciaHorarioDias creada';
END
ELSE
    PRINT 'HUB_AsistenciaHorarioDias ya existe';
GO

-- ── 3. A quién se le asignó ────────────────────────────────────────────────
IF OBJECT_ID('dbo.HUB_AsistenciaUsuarioHorario', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.HUB_AsistenciaUsuarioHorario (
        Id           INT IDENTITY(1,1) NOT NULL
            CONSTRAINT PK_HUB_AsistenciaUsuarioHorario PRIMARY KEY,
        IdUsuario    INT      NOT NULL,
        IdHorario    INT      NOT NULL,
        VigenteDesde DATE     NOT NULL CONSTRAINT DF_AsisUsuHor_Desde DEFAULT (CAST(GETDATE() AS date)),
        Actualizado  DATETIME NOT NULL CONSTRAINT DF_AsisUsuHor_Actualizado DEFAULT (GETDATE()),
        CONSTRAINT FK_AsisUsuHor_Horario FOREIGN KEY (IdHorario)
            REFERENCES dbo.HUB_AsistenciaHorarios (Id),
        -- Un horario activo por persona; el histórico queda en VigenteDesde si
        -- algún día se necesita (hoy se sobrescribe).
        CONSTRAINT UQ_AsisUsuHor_Usuario UNIQUE (IdUsuario)
    );
    PRINT 'HUB_AsistenciaUsuarioHorario creada';
END
ELSE
    PRINT 'HUB_AsistenciaUsuarioHorario ya existe';
GO
