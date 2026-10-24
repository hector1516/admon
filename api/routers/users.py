"""api/routers/users.py — endpoints de usuarios (Fase 2 del refactor)."""
from fastapi import APIRouter, HTTPException, Depends, Request
from fastapi.security import OAuth2PasswordBearer
from pydantic import BaseModel, Field
from typing import Optional, List, Dict

router = APIRouter()

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/token")


def get_connection():
    from api import main as _m
    return _m.get_connection()


def get_current_user(token: str = Depends(oauth2_scheme)):
    from api import main as _m
    return _m.get_current_user(token)


# --- Acceso lazy a helpers de api.main ---
def __getattr__(name):
    from api import main as _m
    return getattr(_m, name)


class UserInfo(BaseModel):
    id: int
    nombre: str
    email: str
    acceso_inventario: bool = False
    acceso_nominas: bool = False
    acceso_cotizaciones: bool = False
    acceso_proveedores: bool = False
    acceso_oc: bool = False
    acceso_calculo: bool = False
    acceso_usuarios: bool = False
    acceso_reportes: bool = False
    acceso_registro_reportes: bool = False
    acceso_ia: bool = False
    acceso_vales_oxxogas: bool = False
    nickname: str = ""
    mac_telefono: str = ""
    # Puesto y si tiene foto (para la lista/avatares). El NSS NO va aquí:
    # es dato personal y solo se entrega en la ficha del usuario.
    puesto: str = ""
    tiene_foto: bool = False
    # Enlace publico de la tarjeta NFC (app colaboradores.ecc-sa.com.mx). Es el
    # mismo token que esa app calcula: ver api/ficha_nfc.py para el contrato de
    # la derivacion, que esta escrita en los dos repos.
    ficha_url: str = ""


# --- Auth Dependency ---

def _user_from_token(token: str):
    """Valida el token simple (email|timestamp) contra HUB_Users. Retorna dict o None."""
    try:
        parts = (token or "").split("|")
        if len(parts) < 2:
            return None
        email = parts[0]
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT Id, Nombre, Email, AccesoInventario, AccesoNominas, AccesoCotizaciones, AccesoProveedores, AccesoOC, AccesoCalculo, AccesoTelegram, AccesoUsuarios, AccesoReportes, AccesoRegistroReportes, AccesoIA, Nickname, AccesoValesOxxoGas, AccesoRegistroKilometros FROM HUB_Users WHERE LTRIM(RTRIM(Email)) = %s", (email.strip().lower(),))
        row = cursor.fetchone()
        conn.close()
        if row:
            return {
                "id": row[0],
                "nombre": row[1],
                "email": row[2],
                # Nickname de Legends: lo usa el Login para sugerir el nombre de la passkey
                "nickname": (row[14] or "").strip() if len(row) > 14 and row[14] else "",
                "acceso_inventario": row[3] == 1,
                "acceso_nominas": row[4] == 1,
                "acceso_cotizaciones": row[5] == 1,
                "acceso_proveedores": row[6] == 1,
                "acceso_oc": row[7] == 1,
                "acceso_calculo": row[8] == 1,
                "acceso_usuarios": row[10] == 1,
                "acceso_reportes": row[11] == 1,
                "acceso_registro_reportes": row[12] == 1,
                "acceso_ia": row[13] == 1,
                "acceso_vales_oxxogas": row[15] == 1 if len(row) > 15 else False,
                # Módulo Kilómetros (consumo semanal + captura). row[16] = AccesoRegistroKilometros
                "acceso_registro_kilometros": row[16] == 1 if len(row) > 16 else False,
            }
        return None
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Auth error: {str(e)}")


def get_current_user(token: str = Depends(oauth2_scheme)):
    user = _user_from_token(token)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid token")
    return user


def _user_from_header_or_query(request: Request):
    """Auth para descargas/iframes: Bearer en header o ?token= en query (como Field)."""
    auth_h = request.headers.get("Authorization", "")
    token = auth_h[7:] if auth_h.startswith("Bearer ") else request.query_params.get("token", "")
    user = _user_from_token(token)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid token")
    return user


# --- Root / health (sin auth, para Docker HEALTHCHECK y pruebas) ---
# Si existe el frontend compilado (dist/), "/" sirve la SPA; la info JSON
# de la API se mueve a "/api". Sin dist/, "/" sigue devolviendo JSON.

@router.get("/api/users/me", response_model=UserInfo)
async def get_me(current_user: dict = Depends(get_current_user)):
    return UserInfo(**current_user)


@router.get("/api/users", response_model=List[UserInfo])
async def get_users(current_user: dict = Depends(get_current_user)):
    """Get all users - admin only"""
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT Id, Nombre, Email, AccesoInventario, AccesoNominas, AccesoCotizaciones, AccesoProveedores, AccesoOC, AccesoCalculo, AccesoTelegram, AccesoUsuarios, ISNULL(Puesto, '') FROM HUB_Users")
        rows = cursor.fetchall()
        # MAC del celular por usuario (para el badge 📡 de la lista);
        # solo activas: es lo que el escáner mide para entradas/salidas.
        cursor.execute("""
            SELECT IdUsuario, MACAddress FROM HUB_NetworkDevices
            WHERE Activo = 1 AND Tipo = 'CELULAR' AND IdUsuario IS NOT NULL
        """)
        macs = {r[0]: (r[1] or "").strip() for r in cursor.fetchall()}
        # Un solo SELECT para saber quiénes tienen foto (no se traen binarios).
        con_foto = set(_foto_usuario.listar_fotos(get_connection))
        conn.close()
        result = []
        for row in rows:
            result.append(UserInfo(
                id=row[0], nombre=row[1], email=row[2],
                acceso_inventario=row[3] == 1,
                acceso_nominas=row[4] == 1,
                acceso_cotizaciones=row[5] == 1,
                acceso_proveedores=row[6] == 1,
                acceso_oc=row[7] == 1,
                acceso_calculo=row[8] == 1,
                acceso_usuarios=row[10] == 1,
                mac_telefono=macs.get(row[0], ""),
                puesto=row[11] or "",
                tiene_foto=row[0] in con_foto,
            ))
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")


@router.get("/api/usuarios")
async def api_list_usuarios(current_user: dict = Depends(get_current_user)):
    """Catálogo ligero {Id, Nombre, Activo} de HUB_Users para los selects de
    técnicos en el detalle/edición de reportes (la página pide /api/usuarios;
    antes no existía y el select quedaba siempre vacío). Mismo permiso que
    los reportes. El prefetch offline también lo cachea."""
    _require_reporte(current_user)
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT Id, Nombre, Activo FROM HUB_Users ORDER BY Nombre")
        rows = cursor.fetchall()
        conn.close()
        # Activo como entero 1/0: el frontend filtra con `Activo === 1`
        return [{"Id": r[0], "Nombre": r[1], "Activo": 1 if r[2] else 0} for r in rows]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")


# --- Detalle / edición de usuario (espejo del Administrador de Usuarios del HUB) ---

# Columnas de HUB_Users administrables (mismo orden que get_all_hub_users del HUB)
def _config_ficha(connect_fn):
    """(secreto, base_url) de las fichas NFC. Lee HUB_Config una vez.

    Se lee aquí y no por usuario: son dos valores constantes para toda la
    pantalla, y meterlos en el SELECT de cada usuario sería una ida a la BD por
    persona. Si falta el secreto se devuelve ("", "") y el frontend simply no
    muestra el enlace, en vez de romper la lista.
    """
    try:
        conn = connect_fn()
        cur = conn.cursor()
        cur.execute(
            "SELECT Clave, Valor FROM HUB_Config "
            "WHERE Clave IN ('colab_ficha_secreto', 'colab_ficha_base_url')"
        )
        valores = {k: (v or "").strip() for k, v in cur.fetchall()}
        conn.close()
        return (valores.get("colab_ficha_secreto", ""),
                valores.get("colab_ficha_base_url", "")
                or _ficha_nfc.BASE_POR_DEFECTO)
    except Exception as e:
        print(f"[ficha_nfc] no se pudo leer la config: {e}")
        return "", _ficha_nfc.BASE_POR_DEFECTO


_USER_COLS = (
    "Id, Email, Nombre, Password, Activo, FechaIngreso, CurpRfc, "
    "AccesoCotizaciones, AccesoVM, AccesoConfiguracion, AccesoUsuarios, AccesoReportes, "
    "AccesoRegistroReportes, AccesoCotizacionesReportes, AccesoClientes, AccesoRegistroKilometros, "
    "AccesoAutomoviles, AccesoVacaciones, AccesoConfigurarCorreo, AccesoConfigAI, "
    "Notificaciones, AccesoMisVacaciones, AccesoHorasExtras, AccesoMisHorasExtras, AccesoOxxoGas, "
    "AccesoValesOxxoGas, AccesoRegistroTicketOxxoGas, AccesoEdicionBD, AccesoNominas, AccesoInventario, "
    "AccesoCalculo, AccesoProveedores, AccesoOC, AccesoAppConfig, AccesoSolicitarVales, "
    "AccesoAdminVales, AccesoConfigOxxogas, AccesoDeteccionRed, AccesoPdfConfig, "
    "NSS, Puesto"
)
# Orden propio (cada columna UNA vez): _user_row_to_dict usa índices fijos
# id=0, email=1, nombre=2, password=3, activo=4, fecha_ingreso=5, curp_rfc=6,
# accesos desde 7 en el orden de `keys`, y al final nss=39 y puesto=40.


def _require_admin(current_user: dict):
    if not current_user.get("acceso_usuarios"):
        raise HTTPException(status_code=403, detail="No access")


def _user_row_to_dict(row) -> dict:
    d = {
        "id": row[0], "email": row[1], "nombre": row[2], "password": row[3],
        "activo": bool(row[4]),
        "fecha_ingreso": str(row[5])[:10] if row[5] else None,
        "curp_rfc": row[6] or "",
    }
    keys = [
        "AccesoCotizaciones", "AccesoVM", "AccesoConfiguracion", "AccesoUsuarios", "AccesoReportes",
        "AccesoRegistroReportes", "AccesoCotizacionesReportes", "AccesoClientes", "AccesoRegistroKilometros",
        "AccesoAutomoviles", "AccesoVacaciones", "AccesoConfigurarCorreo", "AccesoConfigAI",
        "Notificaciones", "AccesoMisVacaciones", "AccesoHorasExtras", "AccesoMisHorasExtras", "AccesoOxxoGas",
        "AccesoValesOxxoGas", "AccesoRegistroTicketOxxoGas", "AccesoEdicionBD", "AccesoNominas", "AccesoInventario",
        "AccesoCalculo", "AccesoProveedores", "AccesoOC", "AccesoAppConfig",
        "AccesoSolicitarVales", "AccesoAdminVales", "AccesoConfigOxxogas", "AccesoDeteccionRed", "AccesoPdfConfig",
    ]
    for i, k in enumerate(keys):
        v = row[7 + i]
        d[k] = (v == 1) if v is not None else False
    # NSS y Puesto van al FINAL de _USER_COLS para no mover los índices de los
    # accesos (migración 0045). Se normalizan a texto para que el front no
    # tenga que distinguir '' de None.
    d["nss"] = str(row[7 + len(keys)] or "").strip()
    d["puesto"] = str(row[8 + len(keys)] or "").strip()
    return d


@router.get("/api/users/{user_id:int}")
async def get_user_detail(user_id: int, current_user: dict = Depends(get_current_user)):
    _require_admin(current_user)
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(f"SELECT {_USER_COLS} FROM HUB_Users WHERE Id = %s", (int(user_id),))
        row = cursor.fetchone()
        conn.close()
        if not row:
            raise HTTPException(status_code=404, detail="Usuario no encontrado")
        return _user_row_to_dict(row)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")


@router.get("/api/users/{user_id:int}/ficha")
async def get_user_ficha(user_id: int, current_user: dict = Depends(get_current_user)):
    """Enlace publico de la tarjeta NFC de un usuario, para copiarlo.

    Se devuelve aqui y no se mete en `/api/users` porque la lista es de todos los
    usuarios y el enlace solo hace falta en el detalle, que es donde se esta
    grabando la tarjeta. Asi tampoco viaja en cada listado.
    """
    _require_admin(current_user)
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT Id, Nombre FROM HUB_Users WHERE Id = %s", (int(user_id),))
        row = cursor.fetchone()
        conn.close()
        if not row:
            raise HTTPException(status_code=404, detail="Usuario no encontrado")
        secreto, base = _config_ficha(get_connection)
        return {
            "id": row[0],
            "slug": _ficha_nfc.slug_de(row[1], row[0], secreto),
            "url": _ficha_nfc.url_de(row[1], row[0], secreto, base),
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")


class UserUpdateRequest(BaseModel):
    nombre: str = ""
    email: str = ""
    password: str = ""
    activo: bool = True
    fecha_ingreso: Optional[str] = None
    curp_rfc: str = ""
    nss: str = ""
    puesto: str = ""
    accesos: Dict[str, bool] = {}


@router.put("/api/users/{user_id:int}")
async def update_user_detail(user_id: int, body: UserUpdateRequest, current_user: dict = Depends(get_current_user)):
    _require_admin(current_user)
    if not body.nombre.strip() or not body.email.strip() or not body.password.strip():
        raise HTTPException(status_code=400, detail="Nombre, correo y contraseña son obligatorios.")
    try:
        conn = get_connection()
        cursor = conn.cursor()
        sets = ["Nombre = %s", "Email = %s", "Password = %s", "Activo = %s", "FechaIngreso = %s", "CurpRfc = %s",
                "NSS = %s", "Puesto = %s"]
        vals: list = [
            body.nombre.strip(), body.email.strip().lower(), body.password,
            1 if body.activo else 0,
            body.fecha_ingreso or None,
            (body.curp_rfc or "").strip() or None,
            _clean_nss(body.nss),
            (body.puesto or "").strip()[:120] or None,
        ]
        allowed = [
            "AccesoCotizaciones", "AccesoVM", "AccesoConfiguracion", "AccesoUsuarios", "AccesoReportes",
            "AccesoRegistroReportes", "AccesoCotizacionesReportes", "AccesoClientes", "AccesoRegistroKilometros",
            "AccesoAutomoviles", "AccesoVacaciones", "AccesoConfigurarCorreo", "AccesoConfigAI",
            "Notificaciones", "AccesoMisVacaciones", "AccesoHorasExtras", "AccesoMisHorasExtras", "AccesoOxxoGas",
            "AccesoValesOxxoGas", "AccesoRegistroTicketOxxoGas", "AccesoEdicionBD", "AccesoNominas", "AccesoInventario",
            "AccesoCalculo", "AccesoProveedores", "AccesoOC", "AccesoAppConfig",
            "AccesoSolicitarVales", "AccesoAdminVales", "AccesoConfigOxxogas", "AccesoDeteccionRed", "AccesoPdfConfig",
        ]
        for k in allowed:
            sets.append(f"{k} = %s")
            vals.append(1 if body.accesos.get(k, False) else 0)
        vals.append(int(user_id))
        cursor.execute(f"UPDATE HUB_Users SET {', '.join(sets)} WHERE Id = %s", tuple(vals))
        conn.close()
        return {"ok": True}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")


@router.delete("/api/users/{user_id:int}")
async def delete_user_detail(user_id: int, current_user: dict = Depends(get_current_user)):
    _require_admin(current_user)
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT Email, Nombre FROM HUB_Users WHERE Id = %s", (int(user_id),))
        row = cursor.fetchone()
        if not row:
            conn.close()
            raise HTTPException(status_code=404, detail="Usuario no encontrado")
        if (row[0] or "").strip().lower() == (current_user.get("email") or "").strip().lower():
            conn.close()
            raise HTTPException(status_code=400, detail="No puedes eliminar tu propia cuenta.")
        try:
            cursor.execute("DELETE FROM HUB_Users WHERE Id = %s", (int(user_id),))
        except Exception as e:
            conn.close()
            raise HTTPException(status_code=400, detail=f"No se pudo eliminar (referencias en otros módulos): {str(e)[:150]}")
        conn.close()
        return {"ok": True}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")


# --- Teléfono / MAC del usuario (relación con HUB_NetworkDevices) ---
# La tabla HUB_NetworkDevices es la que usa el escáner de red (módulo Detección
# de Red 📡) para medir ENTRADAS y SALIDAS de la oficina: si la MAC del celular
# aparece en la red, el usuario está aquí. Aquí solo se gestiona la fila
# vinculada al usuario (IdUsuario); nunca se borra (HUB_NetworkPresence y
# HUB_NetworkState tienen FK hacia ella) — al quitar la MAC se desvincula y se
# marca Activo = 0, así el historial de eventos queda intacto.

def _normalizar_mac(valor) -> Optional[str]:
    """'aa-bb-cc-dd-ee-ff' / 'aabbccddeeff' / 'aabb.ccdd.eeff' → 'AA:BB:CC:DD:EE:FF'.

    Devuelve None si no son 12 dígitos hexadecimales (formato que espera
    HUB_NetworkDevices.MACAddress, varchar(17)).
    """
    s = (valor or "").strip().upper().replace(":", "").replace("-", "").replace(".", "")
    if len(s) != 12 or any(c not in "0123456789ABCDEF" for c in s):
        return None
    return ":".join(s[i:i + 2] for i in range(0, 12, 2))


def _telefono_del_usuario(user_id: int, conn=None) -> dict:
    """Lee el celular vinculado al usuario + su presencia en la red.

    Devuelve siempre la misma forma aunque no haya MAC: la página la usa tanto
    para pintar el formulario como para mostrar 'AQUI/FUERA' y el último
    evento de entrada/salida.
    """
    propia = conn is None
    if propia:
        conn = get_connection()
    try:
        cursor = conn.cursor(as_dict=True)
        cursor.execute("""
            SELECT Id, MACAddress, NombreDispositivo, Activo, FechaRegistro
            FROM HUB_NetworkDevices
            WHERE IdUsuario = %s AND Tipo = 'CELULAR'
            ORDER BY Activo DESC, FechaRegistro DESC, Id DESC
        """, (int(user_id),))
        devs = cursor.fetchall()
        dev = next((d for d in devs if d["Activo"]), (devs[0] if devs else None))
        out = {
            "id_dispositivo": int(dev["Id"]) if dev else None,
            "mac": (dev["MACAddress"] or "").strip() if dev else "",
            "nombre_dispositivo": (dev["NombreDispositivo"] or "").strip() if dev else "",
            "activo": bool(dev["Activo"]) if dev else False,
            "estado": None,
            "ultima_vez_en_red": None,
            "ultimo_evento": None,
        }
        if not dev:
            return out
        # Estado en vivo del escáner (AQUI = detectado en la última red)
        cursor.execute("""
            SELECT Estado, UltimaVezEnRed FROM HUB_NetworkState
            WHERE IdDispositivo = %s
        """, (int(dev["Id"]),))
        st = cursor.fetchone()
        if st:
            out["estado"] = st["Estado"]
            out["ultima_vez_en_red"] = st["UltimaVezEnRed"].isoformat() if st["UltimaVezEnRed"] else None
        # Último evento de presencia (ENTRADA / SALIDA)
        cursor.execute("""
            SELECT TOP 1 TipoEvento, FechaHora FROM HUB_NetworkPresence
            WHERE IdDispositivo = %s ORDER BY Id DESC
        """, (int(dev["Id"]),))
        ev = cursor.fetchone()
        if ev:
            out["ultimo_evento"] = {
                "tipo": ev["TipoEvento"],
                "fecha": ev["FechaHora"].isoformat() if ev["FechaHora"] else None,
            }
        return out
    finally:
        if propia:
            conn.close()


class TelefonoMacRequest(BaseModel):
    mac: str = ""
    nombre_dispositivo: str = ""


@router.get("/api/users/{user_id:int}/telefono")
async def get_user_telefono(user_id: int, current_user: dict = Depends(get_current_user)):
    """MAC del celular vinculado + estado de presencia (¿está en la oficina?)."""
    _require_admin(current_user)
    try:
        conn = get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT Id FROM HUB_Users WHERE Id = %s", (int(user_id),))
            if not cursor.fetchone():
                raise HTTPException(status_code=404, detail="Usuario no encontrado")
            return _telefono_del_usuario(user_id, conn)
        finally:
            conn.close()
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")


@router.put("/api/users/{user_id:int}/telefono")
async def set_user_telefono(user_id: int, body: TelefonoMacRequest,
                            current_user: dict = Depends(get_current_user)):
    """Vincula (o desvincula) la MAC del celular al usuario.

    Upsert sobre HUB_NetworkDevices:
      · MAC vacía        → desvincula el celular del usuario (Activo = 0,
                           IdUsuario = NULL); NO se borra la fila porque
                           HUB_NetworkPresence/HUB_NetworkState dependen de ella.
      · MAC ya en uso    → si es de OTRO usuario activo, 400 (evita que dos
                           personas midan la misma MAC).
      · MAC existente    → se reutiliza la fila (realectiva si estaba apagada).
      · MAC nueva        → si el usuario tenía otra fila CELULAR se le cambia
                           la MAC; si no, se inserta una fila nueva.
    """
    _require_admin(current_user)
    conn = get_connection()
    try:
        cursor = conn.cursor(as_dict=True)
        cursor.execute("SELECT Id, Nombre FROM HUB_Users WHERE Id = %s", (int(user_id),))
        user = cursor.fetchone()
        if not user:
            raise HTTPException(status_code=404, detail="Usuario no encontrado")
        nombre = (body.nombre_dispositivo or "").strip()
        mac = (body.mac or "").strip()

        # 1) MAC vacía → desvincular sin borrar historial
        if not mac:
            cursor.execute("""
                UPDATE HUB_NetworkDevices SET Activo = 0, IdUsuario = NULL
                WHERE IdUsuario = %s AND Tipo = 'CELULAR'
            """, (int(user_id),))
            conn.commit()
            return {"ok": True, **_telefono_del_usuario(user_id, conn)}

        # 2) validar formato
        normalizada = _normalizar_mac(mac)
        if not normalizada:
            raise HTTPException(status_code=400, detail="MAC inválida: usa 12 dígitos hex (ej. EE:E2:FD:A3:43:EC).")

        # 3) ¿ya la usa OTRO usuario activo?
        cursor.execute("""
            SELECT TOP 1 d.Id, d.IdUsuario, u.Nombre
            FROM HUB_NetworkDevices d
            LEFT JOIN HUB_Users u ON u.Id = d.IdUsuario
            WHERE LTRIM(RTRIM(d.MACAddress)) = %s AND d.Activo = 1
              AND d.IdUsuario IS NOT NULL AND d.IdUsuario <> %s
        """, (normalizada, int(user_id)))
        otra = cursor.fetchone()
        if otra:
            raise HTTPException(
                status_code=400,
                detail=f"Esa MAC ya está registrada a {(otra['Nombre'] or '').strip() or 'otro usuario'}. "
                       f"Quítala primero desde su ficha de usuario.",
            )

        # 4) upsert: reactivar fila con esa MAC / cambiar la MAC del usuario / insertar
        cursor.execute("""
            SELECT Id FROM HUB_NetworkDevices
            WHERE LTRIM(RTRIM(MACAddress)) = %s
            ORDER BY Activo DESC, Id DESC
        """, (normalizada,))
        existente = cursor.fetchone()
        if existente:
            sets, vals = ["MACAddress = %s", "IdUsuario = %s", "Activo = 1"], [normalizada, int(user_id)]
        else:
            cursor.execute("""
                SELECT TOP 1 Id FROM HUB_NetworkDevices
                WHERE IdUsuario = %s AND Tipo = 'CELULAR'
                ORDER BY Activo DESC, Id DESC
            """, (int(user_id),))
            previo = cursor.fetchone()
            if previo:
                sets, vals = ["MACAddress = %s", "Activo = 1"], [normalizada]
                existente = previo
            else:
                sets, vals = ["MACAddress = %s", "IdUsuario = %s", "Activo = 1", "FechaRegistro = GETDATE()"],                              [normalizada, int(user_id)]
        if nombre:
            sets.append("NombreDispositivo = %s")
            vals.append(nombre[:100])
        if existente:
            cursor.execute(f"UPDATE HUB_NetworkDevices SET {', '.join(sets)} WHERE Id = %s",
                           tuple(vals + [int(existente["Id"])]))
        else:
            cursor.execute(f"""
                INSERT INTO HUB_NetworkDevices (MACAddress, NombreDispositivo, IdUsuario, Tipo, Activo)
                VALUES (%s, %s, %s, 'CELULAR', 1)
            """, (normalizada, nombre[:100] or None, int(user_id)))
        conn.commit()
        return {"ok": True, **_telefono_del_usuario(user_id, conn)}
    except HTTPException:
        raise
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")
    finally:
        conn.close()


# --- NSS / Puesto / Foto del usuario ---------------------------------------
# NSS y Puesto son columnas de HUB_Users (migración 0045) y se editan junto con
# el resto de la ficha. La foto va en HUB_UsuariosFotos (tabla aparte, para no
# engordar HUB_Users) con su propio par de endpoints: subir y borrar.

def _clean_nss(valor) -> Optional[str]:
    """NSS: solo dígitos. El capture también pone guiones ('123-45-6789') y a
    veces 11 dígitos; se deja como 11 dígitos, sin guiones ni espacios, que es
    como lo usa el imss. Vacío = NULL (no se capturó)."""
    d = "".join(c for c in str(valor or "") if c.isdigit())
    if not d:
        return None
    return d[:20]


class FotoUsuarioRequest(BaseModel):
    contenido_base64: str
    content_type: str = "image/jpeg"


@router.get("/api/users/{user_id:int}/foto")
async def get_user_foto(user_id: int, current_user: dict = Depends(get_current_user)):
    """Foto del usuario en binario. Devuelve 404 si no tiene foto, para que el
    front pueda pintar un avatar con iniciales sin descargar nada."""
    _require_admin(current_user)
    foto = _foto_usuario.leer_foto_usuario(get_connection, user_id)
    if not foto:
        raise HTTPException(status_code=404, detail="Este usuario no tiene foto.")
    return Response(content=foto["bytes"], media_type=foto["content_type"])


@router.put("/api/users/{user_id:int}/foto")
async def set_user_foto(user_id: int, body: FotoUsuarioRequest,
                        current_user: dict = Depends(get_current_user)):
    """Sube o reemplaza la foto del usuario. Llega en base64 (mismo camino que
    la imagen de portada de la TV), no multipart, para no sumar dependencias."""
    _require_admin(current_user)
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT Id FROM HUB_Users WHERE Id = %s", (int(user_id),))
        if not cursor.fetchone():
            raise HTTPException(status_code=404, detail="Usuario no encontrado")
    finally:
        conn.close()
    try:
        contenido = base64.b64decode(body.contenido_base64.split(",")[-1])
    except Exception:
        raise HTTPException(status_code=400, detail="No se pudo leer la imagen (base64 inválido).")
    r = _foto_usuario.guardar_foto_usuario(
        get_connection, int(user_id), contenido, body.content_type,
        actualizado_por=int(current_user.get("id") or 0) or None)
    if not r.get("ok"):
        raise HTTPException(status_code=400, detail=r.get("error") or "No se pudo guardar la foto.")
    return r


@router.delete("/api/users/{user_id:int}/foto")
async def delete_user_foto(user_id: int, current_user: dict = Depends(get_current_user)):
    _require_admin(current_user)
    r = _foto_usuario.borrar_foto_usuario(get_connection, int(user_id))
    if not r.get("ok"):
        raise HTTPException(status_code=400, detail=r.get("error") or "No se pudo borrar la foto.")
    return r


# --- Asistencia del día -----------------------------------------------------
# Quién entró y quién salió HOY. Es la misma información que muestra la pantalla
# "🕘 Asistencia de hoy" del kiosco Dashboard (app en :8101), pero leída por
# Admon DIRECTAMENTE de la base: el kiosco va por un snapshot en disco que otro
# worker refresca cada 2 min, y acá se calcula al momento, sin depender de que
# ese proceso esté arriba.
#
# La fuente es `HUB_NetworkPresence`, que escribe el `network_scanner_worker`
# del contenedor `workersadmon` cuando ve aparecer o desaparecer una MAC conocida
# en la red. OJO: hay otras dos tablas de asistencia y NINGUNA sirve para esto
# hoy — `ControlAsistencia` (la del checador viejo) tiene su último registro de
# enero de 2023 y está abandonada, y `HUB_AsistenciaDiaria` sólo se calculó a
# mano una vez (2026-09-11) y trae casi todo en NULL.
#
# Por persona se toma la PRIMERA entrada del día y la ÚLTIMA salida: un celular
# que entra y sale seis veces no debe verse como seis llegadas distintas. Quien
# sigue dentro (su último evento es ENTRADA) va con `en_sitio`, para no pintar
# una salida que todavía no pasa.
AJUSTE_ENTRADA_MIN = 4  # ver el docstring de asistencia_hoy() en dashboard/api/datos.py

# Minutos que puede pasar el ESCÁNER sin registrar un ciclo antes de que la
# pantalla deje de dar por buenos los datos. Corre cada minuto, así que 10 min
# ya no es "un ratito": es que nadie está escaneando. Sin este aviso, un
# escáner caído deja la pantalla lanzando "9 en sitio" con datos de hace horas:
# la última cosa que se sabe de cada quien es que entró, y su salida nunca
# llegó a escribirse.
#
# OJO: se mide contra los CICLOS del escáner y NO contra los movimientos de
# gente. Los movimientos son por evento: si nadie entra ni sale en media hora no
# pasa nada y no hay ni un solo registro nuevo. Medir eso (que fue como se hizo
# primero) daba falsos positivos a media mañana, con el escáner funcionando
# perfecto. Lo que dice si el escáner vive es su último ciclo.
VENTANA_SIN_ESCANER_MIN = 10

# Marcha simultánea: cuántas personas tienen que registrar el mismo tipo de
# evento (entradas o salidas) dentro del MISMO minuto para que el dato se tome
# por escrito. Tres personas no entran ni salen de la oficina en el mismo
# segundo, así que ese patrón es del proceso, no de la gente: pasa cuando el
# escáner (o el worker que lee los ciclos) se reinicia y escribe de golpe el
# estado que tenía guardado, o cuando la red de la oficina se cae un momento y
# todos los equipos "desaparecen" juntos. Sin esta guarda, ese reinicio deja
# toda la pantalla en verde aunque la oficina esté vacía.
MARCHA_SIMULTANEA_MIN = 3


def _latido_scan(conn):
    """(ciclo, minutos) del último escáner, o (None, None) si nunca ha corrido.

    `ciclo` es la fecha del último ciclo y `minutos` su antigüedad. La
    antigüedad la calcula el SERVIDOR SQL con DATEDIFF, no Python: el reloj del
    contenedor y el del servidor SQL no están sincronizados (difieren horas) y
    restarlos en Python daba diferencias de miles de minutos.

    El escáner puede escribir en el camino NUEVO (`HUB_NetworkScanRuns`, un
    renglón por ciclo con la lista completa de MACs) o en el VIEJO
    (`HUB_NetworkScanResults`, un renglón por MAC y ciclo). Se mira EL MÁS
    RECIENTE de las dos, no la primera que tenga filas.

    OJO con esto, que ya costó un falso positivo real: si el escáner está
    escribiendo en la tabla vieja, la nueva se queda congelada con miles de
    filas viejas. Devolviendo la nueva "porque tiene datos", la pantalla
    anunciaba "el escáner no corre desde hace 16 h" mientras el escáner escribía
    hace 1 minuto. Con el MAX de las dos, el latido refleja lo que de verdad
    pasa.
    """
    consulta = ("SELECT MAX({col}) AS ciclo, "
                "DATEDIFF(MINUTE, MAX({col}), GETDATE()) AS minutos FROM dbo.{tab}")
    cur = conn.cursor(as_dict=True)
    mejor_ciclo, mejor_minutos = None, None
    for tab, col in (("HUB_NetworkScanRuns", "FechaScan"),
                     ("HUB_NetworkScanResults", "FechaScan")):
        try:
            cur.execute(consulta.format(tab=tab, col=col))
        except Exception:
            continue  # la tabla no existe en esta base: se prueba la otra
        fila = cur.fetchone()
        if not fila or not fila.get("ciclo"):
            continue
        if mejor_ciclo is None or fila["ciclo"] > mejor_ciclo:
            mejor_ciclo = fila["ciclo"]
            mejor_minutos = int(fila["minutos"] or 0)
    cur.close()
    return mejor_ciclo, mejor_minutos


