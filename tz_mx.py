"""
Zona horaria estándar del ecosistema ECCSA: Monterrey, Nuevo León, México.

México abolió el horario de verano en 2022 para la mayoría del país
(incluyendo Nuevo León). Por lo tanto, Monterrey es UTC-6 todo el año,
sin cambios de DST.

REGLA: nunca usar datetime.now() sin zona, datetime.utcnow() - N, ni
depender de la variable de entorno TZ del contenedor. Siempre usar
now_mx() de este módulo.
"""
from datetime import datetime, timezone, timedelta

TZ_MX = timezone(timedelta(hours=-6))


def now_mx() -> datetime:
    return datetime.now(TZ_MX).replace(tzinfo=None)


def to_mx(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(TZ_MX).replace(tzinfo=None)
