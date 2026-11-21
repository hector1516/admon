"""Comparación de descriptores faciales (128 floats).

El descriptor lo calcula el navegador (face-api.js) y viaja al backend como una
lista de números. Aquí solo se compara contra el guardado en
`HUB_UsuariosFaciales.Embedding`, con distancia euclidiana. Es la forma de D1 A
del plan: la foto no sale del teléfono.

El umbral 0.55 es el que usa face-api.js para "misma persona" con descriptores
de 128 dimensiones; si en la práctica rebota a gente con lentes, se sube.
"""
import math
from typing import Sequence

UMBRAL = 0.55


def distancia(a: Sequence[float], b: Sequence[float]) -> float:
    """Distancia euclidiana entre dos descriptores. Falla si no miden igual."""
    if len(a) != len(b):
        raise ValueError("Los descriptores deben medir lo mismo")
    return math.sqrt(sum((x - y) ** 2 for x, y in zip(a, b)))


def coincide(a: Sequence[float], b: Sequence[float], umbral: float = UMBRAL) -> bool:
    """True si los descriptores son de la misma persona (distancia <= umbral)."""
    return distancia(a, b) <= umbral
