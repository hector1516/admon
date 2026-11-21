"""Token de paso (*step-up*) que prueba que el usuario acaba de usar su passkey.

D3 B del plan: la passkey se exige en cada marcado. El flujo es:

1. `/passkey/options` emite el desafío.
2. El navegador firma con el autenticador del teléfono.
3. `/passkey/verify` lo valida y emite este token (2 minutos).
4. `/marcar` lo exige. Así no sirve reusar un marcado viejo ni saltarse el paso.
"""
from datetime import datetime, timedelta, timezone

import jwt

PROPOSITO = "marcado"


def emitir(usuario_id: int, credencial_id: str, secreto: str, minutos: int = 2) -> str:
    """Devuelve un JWT corto con el usuario y la credencial usada."""
    ahora = datetime.now(timezone.utc)
    return jwt.encode(
        {
            "sub": str(usuario_id),
            "cred": credencial_id,
            "purpose": PROPOSITO,
            "iat": ahora,
            "exp": ahora + timedelta(minutes=minutos),
        },
        secreto,
        algorithm="HS256",
    )


def validar(token: str, usuario_id: int, secreto: str) -> str:
    """Valida el token y devuelve la credencial. Lanza ValueError si no sirve."""
    try:
        datos = jwt.decode(token, secreto, algorithms=["HS256"])
    except jwt.InvalidTokenError as e:
        raise ValueError(f"Token invalido: {e}") from e
    if datos.get("purpose") != PROPOSITO:
        raise ValueError("Token de otro proposito")
    if str(datos.get("sub")) != str(usuario_id):
        raise ValueError("Token de otro usuario")
    cred = datos.get("cred")
    if not cred:
        raise ValueError("Token sin credencial")
    return cred
