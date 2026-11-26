-- Migración 0066: WhatsApp por usuario
-- Fecha: 2026-11-26
-- Descripción: el teléfono de WhatsApp de cada persona, para que las apps
--              (hoy Admon) sepan a qué número escribirle sin que cada una
--              guarde su propia copia. En TODA la base no existía un teléfono
--              por usuario: HUB_Users no tiene columna y
--              HUB_ContactosClientes.Contacto es el NOMBRE del contacto de un
--              cliente, no un número.
--
-- Va en tabla aparte (mismo criterio que HUB_UsuariosFotos): HUB_Users se lee
-- en cada login y en cada listado de las tres apps, y una columna más ahí
-- viaja en todas esas consultas.
--
-- Una fila por usuario (IdUsuario es la PK). `Activo` permite desactivar el
-- número sin perder de vista cuál era; Admon, al vaciar el campo, BORRA la
-- fila (aquí no hay historial que conservar, a diferencia de la MAC del
-- escáner de red).
--
-- Idempotente: se puede correr varias veces sin efecto.
IF NOT EXISTS (SELECT 1 FROM sys.tables WHERE name = 'HUB_UsuariosWhatsapp')
BEGIN
    CREATE TABLE HUB_UsuariosWhatsapp (
        IdUsuario INT NOT NULL PRIMARY KEY,
        -- Solo dígitos, con código de país: 52 + 10 dígitos para México.
        Telefono VARCHAR(20) NOT NULL,
        Activo BIT NOT NULL CONSTRAINT DF_HUB_UsuariosWhatsapp_Activo DEFAULT 1,
        FechaActualizado DATETIME NOT NULL CONSTRAINT DF_HUB_UsuariosWhatsapp_Fecha DEFAULT GETDATE(),
        CONSTRAINT FK_HUB_UsuariosWhatsapp_Users
            FOREIGN KEY (IdUsuario) REFERENCES HUB_Users(Id)
    );
    PRINT 'Tabla HUB_UsuariosWhatsapp creada';
END
ELSE
    PRINT 'Tabla HUB_UsuariosWhatsapp ya existe';
GO
