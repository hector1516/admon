"""WhatsApp de los usuarios (HUB_UsuariosWhatsapp).

Una fila por usuario, igual que la foto: el número no vive en HUB_Users porque
esa tabla se lee en cada login y en cada listado de las tres apps, y una columna
más viaja en todas esas consultas.

Lo que se guarda es el número YA NORMALIZADO (solo dígitos y con código de
país). La normalización es la misma que aplica `openwa_client.normalizar_chat_id`
al mandar un aviso: 10 dígitos se toman como México (52 + los 10), 12 a 15 se
respetan tal cual, y un 11 dígitos que empieza con 1 se RECHAZA en vez de
adivinarse (puede ser EUA o el formato viejo de México; elegir mal manda el
aviso a un número válido que no es de nadie).

La tabla la crea la migración `0066_usuarios_whatsapp.sql`.
"""

LARGO_MAX = 20  # VARCHAR(20) en la tabla: 15 dígitos ya es el tope de WhatsApp


def normalizar_telefono(valor):
    """'8121234567' / '+52 81 2123 4567' → '528121234567'.

    Devuelve '' si viene vacío (usuario sin WhatsApp). Lanza ValueError con un
    mensaje para la persona si el número no sirve.
    """
    txt = str(valor or "").strip()
    if not txt:
        return ""
    digitos = "".join(c for c in txt if c.isdigit())
    if not digitos:
        raise ValueError("WhatsApp inválido: escribe el número con dígitos (10 dígitos o 52…).")
    if len(digitos) == 11 and digitos.startswith("1"):
        raise ValueError(
            "WhatsApp inválido: un número de 11 dígitos que empieza con 1 es ambiguo "
            "(puede ser de EUA o el formato viejo de México). Escribe el código de país, "
            "por ejemplo 52 81 2123 4567."
        )
    if len(digitos) == 10:
        return "52" + digitos
    if 12 <= len(digitos) <= 15:
        return digitos[:LARGO_MAX]
    raise ValueError(
        "WhatsApp inválido: escribe 10 dígitos o el número con código de país (52…)."
    )


def guardar_whatsapp(get_connection, id_usuario: int, telefono: str) -> dict:
    """Guarda (MERGE) el teléfono ya normalizado, o borra la fila si viene ''."""
    conn = get_connection()
    try:
        cur = conn.cursor()
        if not telefono:
            cur.execute("DELETE FROM HUB_UsuariosWhatsapp WHERE IdUsuario = %s",
                        (int(id_usuario),))
        else:
            cur.execute(
                "MERGE HUB_UsuariosWhatsapp WITH (HOLDLOCK) AS t "
                "USING (SELECT %s AS IdUsuario, %s AS Telefono) AS s "
                "ON t.IdUsuario = s.IdUsuario "
                "WHEN MATCHED THEN UPDATE SET Telefono = s.Telefono, Activo = 1, "
                "FechaActualizado = GETDATE() "
                "WHEN NOT MATCHED THEN INSERT (IdUsuario, Telefono, Activo, FechaActualizado) "
                "VALUES (s.IdUsuario, s.Telefono, 1, GETDATE());",
                (int(id_usuario), telefono[:LARGO_MAX]))
        conn.commit()
    except Exception as e:
        return {"ok": False, "error": f"No se pudo guardar el WhatsApp: {str(e)[:150]}"}
    finally:
        conn.close()
    return {"ok": True}


def leer_whatsapp(get_connection, id_usuario: int) -> str:
    """Teléfono activo del usuario, o '' si no tiene. Tolerante: si la tabla
    aún no existe (migración sin aplicar), la ficha sigue abriendo sin él."""
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT Telefono FROM HUB_UsuariosWhatsapp WHERE IdUsuario = %s AND Activo = 1",
            (int(id_usuario),))
        r = cur.fetchone()
        return (r[0] or "").strip() if r else ""
    except Exception as e:
        print(f"[whatsapp-usuario] Error leyendo WhatsApp de {id_usuario}: {e}")
        return ""
    finally:
        conn.close()


def mapa_whatsapps(get_connection) -> dict:
    """{IdUsuario: telefono} de los activos. Para la lista de usuarios: un solo
    SELECT en vez de una consulta por persona."""
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute("SELECT IdUsuario, Telefono FROM HUB_UsuariosWhatsapp WHERE Activo = 1")
        return {int(r[0]): (r[1] or "").strip() for r in cur.fetchall()}
    except Exception as e:
        print(f"[whatsapp-usuario] Error listando WhatsApps: {e}")
        return {}
    finally:
        conn.close()
