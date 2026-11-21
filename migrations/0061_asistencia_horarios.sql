-- 0061 · Horarios de asistencia por usuario y día
--
-- Una fila por persona y día de la semana (1 = lunes … 7 = domingo, ISO).
-- La comida es fija por día (minutos) y se descuenta de las horas trabajadas:
-- 09:00–18:00 con 60' son 8 h, no 9. Ver `AsistenciaAdmin.svelte`.
--
-- No toca ninguna tabla existente: es una tabla nueva, así que no hay ALTER.
-- Se probó primero en ECCSA_Admon_Pruebas (convención de `admon/AGENTS.md`).
--
-- Regla de la comida (decidida el 2026-11-21): se descuenta completa solo si la
-- persona estuvo al menos la jornada + la comida; si se fue antes, no se
-- descuenta nada. Esa regla vive en el cálculo, no en la tabla: aquí solo se
-- guarda cuántos minutos corresponden a ese día.

IF OBJECT_ID('dbo.HUB_AsistenciaHorarios', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.HUB_AsistenciaHorarios (
        Id             INT IDENTITY(1,1) NOT NULL
            CONSTRAINT PK_HUB_AsistenciaHorarios PRIMARY KEY,
        IdUsuario      INT          NOT NULL,
        DiaSemana      TINYINT      NOT NULL,   -- 1 = lunes … 7 = domingo
        HoraEntrada    TIME(0)      NULL,
        HoraSalida     TIME(0)      NULL,
        ComidaMin      SMALLINT     NOT NULL CONSTRAINT DF_AsisHor_Comida DEFAULT (60),
        Descanso       BIT          NOT NULL CONSTRAINT DF_AsisHor_Descanso DEFAULT (0),
        VigenteDesde   DATE         NULL,
        Actualizado    DATETIME     NOT NULL CONSTRAINT DF_AsisHor_Actualizado DEFAULT (GETDATE()),
        ActualizadoPor INT          NULL,
        CONSTRAINT CK_AsisHor_Dia    CHECK (DiaSemana BETWEEN 1 AND 7),
        CONSTRAINT CK_AsisHor_Comida CHECK (ComidaMin >= 0 AND ComidaMin <= 240),
        -- Un día laborable necesita hora de entrada y de salida; uno de
        -- descanso no las usa.
        CONSTRAINT CK_AsisHor_Horas  CHECK (
            Descanso = 1 OR (HoraEntrada IS NOT NULL AND HoraSalida IS NOT NULL)
        )
    );

    -- Una sola fila por persona y día: el horario se edita, no se acumula.
    CREATE UNIQUE INDEX UX_AsisHor_Usuario_Dia
        ON dbo.HUB_AsistenciaHorarios (IdUsuario, DiaSemana);

    PRINT 'HUB_AsistenciaHorarios creada';
END
ELSE
    PRINT 'HUB_AsistenciaHorarios ya existe: nada que hacer';
GO
