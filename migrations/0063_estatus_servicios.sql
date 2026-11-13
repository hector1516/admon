-- 0063_estatus_servicios.sql
-- Migración para el módulo "Estatus de Servicios"

GO

-- 1. Catálogo de servicios
IF NOT EXISTS (SELECT 1 FROM sys.tables WHERE name = 'HUB_EstatusServicios')
BEGIN
    CREATE TABLE dbo.HUB_EstatusServicios (
        Id              INT IDENTITY(1,1) PRIMARY KEY,
        Nombre          NVARCHAR(100)  NOT NULL,
        Tipo            VARCHAR(20)    NOT NULL,  -- 'externo' o 'interno'
        Categoria       NVARCHAR(50)   NULL,      -- 'microsoft', 'godaddy', 'cloudflare', 'eccsa', 'infraestructura'
        UrlCheck        NVARCHAR(500)  NULL,      -- URL del health check o API
        UrlStatus       NVARCHAR(500)  NULL,      -- URL de la página de status pública
        Icono           NVARCHAR(10)   NULL,
        Activo          BIT            NOT NULL DEFAULT 1,
        Orden           INT            NOT NULL DEFAULT 0,
        UltimoCheck     DATETIME       NULL,
        UltimoEstatus   VARCHAR(10)    NULL,      -- 'verde', 'amarillo', 'rojo', 'gris'
        UltimoDetalle   NVARCHAR(500)  NULL,
        TiempoRespuestaMs INT           NULL,
        Creado          DATETIME       NOT NULL DEFAULT GETDATE(),
        Actualizado     DATETIME       NOT NULL DEFAULT GETDATE()
    );
    PRINT 'HUB_EstatusServicios creada';
END
ELSE
    PRINT 'HUB_EstatusServicios ya existe';
GO

-- 2. Historial de checks
IF NOT EXISTS (SELECT 1 FROM sys.tables WHERE name = 'HUB_EstatusHistorial')
BEGIN
    CREATE TABLE dbo.HUB_EstatusHistorial (
        Id              BIGINT IDENTITY(1,1) PRIMARY KEY,
        IdServicio      INT            NOT NULL,
        Estatus         VARCHAR(10)    NOT NULL,  -- 'verde', 'amarillo', 'rojo', 'gris'
        Detalle         NVARCHAR(500)  NULL,
        TiempoRespuestaMs INT           NULL,
        FechaCheck      DATETIME       NOT NULL DEFAULT GETDATE(),
        IncidenciaId    INT            NULL,
        CONSTRAINT FK_EstatusHistorial_Servicio
            FOREIGN KEY (IdServicio) REFERENCES dbo.HUB_EstatusServicios(Id) ON DELETE CASCADE
    );
    PRINT 'HUB_EstatusHistorial creada';
END
ELSE
    PRINT 'HUB_EstatusHistorial ya existe';
GO

CREATE INDEX IX_EstatusHistorial_Servicio_Fecha
    ON dbo.HUB_EstatusHistorial (IdServicio, FechaCheck DESC);
GO

-- 3. Incidencias
IF NOT EXISTS (SELECT 1 FROM sys.tables WHERE name = 'HUB_EstatusIncidencias')
BEGIN
    CREATE TABLE dbo.HUB_EstatusIncidencias (
        Id              INT IDENTITY(1,1) PRIMARY KEY,
        IdServicio      INT            NOT NULL,
        Titulo          NVARCHAR(200)  NOT NULL,
        Descripcion     NVARCHAR(1000) NULL,
        Estatus         VARCHAR(20)    NOT NULL DEFAULT 'activa',  -- 'activa', 'resuelta'
        FechaInicio     DATETIME       NOT NULL DEFAULT GETDATE(),
        FechaResolucion DATETIME       NULL,
        Fuente          VARCHAR(20)    NOT NULL DEFAULT 'api',     -- 'api', 'manual'
        CONSTRAINT FK_EstatusIncidencias_Servicio
            FOREIGN KEY (IdServicio) REFERENCES dbo.HUB_EstatusServicios(Id) ON DELETE CASCADE
    );
    PRINT 'HUB_EstatusIncidencias creada';
END
ELSE
    PRINT 'HUB_EstatusIncidencias ya existe';
GO

-- 4. Insertar servicios iniciales
IF NOT EXISTS (SELECT 1 FROM dbo.HUB_EstatusServicios WHERE Nombre = 'Microsoft 365')
BEGIN
    INSERT INTO dbo.HUB_EstatusServicios (Nombre, Tipo, Categoria, UrlCheck, UrlStatus, Icono, Orden) VALUES
    ('Microsoft 365', 'externo', 'microsoft', 'https://status.office.com', 'https://status.office.com', '📧', 1),
    ('GoDaddy', 'externo', 'godaddy', 'https://status.godaddy.com/api/v2/summary.json', 'https://status.godaddy.com', '🌐', 2),
    ('Cloudflare', 'externo', 'cloudflare', 'https://www.cloudflarestatus.com/api/v2/summary.json', 'https://www.cloudflarestatus.com', '☁️', 3),
    ('Admon', 'interno', 'eccsa', 'http://localhost:8103/health', '', '📋', 4),
    ('Field', 'interno', 'eccsa', 'http://localhost:8100/api/health', '', '📱', 5),
    ('Dashboard', 'interno', 'eccsa', 'http://localhost:8101/healthz', '', '📊', 6),
    ('Mailbox', 'interno', 'eccsa', 'http://localhost:8104/health', '', '📬', 7),
    ('Colaboradores', 'interno', 'eccsa', 'http://localhost:8105/healthz', '', '👥', 8),
    ('WorkersAdmon', 'interno', 'eccsa', 'http://localhost:8200/healthz', '', '⚙️', 9),
    ('SQL Server', 'interno', 'infraestructura', 'tcp://10.188.141.15:1433', '', '🗄️', 10),
    ('WebbApps Server', 'interno', 'infraestructura', 'http://10.188.141.17', '', '🖥️', 11);
    PRINT 'Servicios iniciales insertados';
END
ELSE
    PRINT 'Servicios ya existen';
GO

PRINT '0063_estatus_servicios.sql aplicada';
GO