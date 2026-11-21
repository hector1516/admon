"""Comparación de descriptores faciales (128 floats).

D1 A del plan: el navegador calcula el descriptor y el backend solo compara
contra el que está guardado en HUB_UsuariosFaciales.Embedding. Distancia
euclidiana, umbral 0.55.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "api"))

from rostro import UMBRAL, coincide, distancia  # noqa: E402


def test_identicos_dan_cero_y_coinciden():
    a = [0.1] * 128
    assert distancia(a, a) == 0.0
    assert coincide(a, a) is True


def test_muy_distintos_no_coinciden():
    a = [0.0] * 128
    b = [1.0] * 128
    assert round(distancia(a, b), 3) == round(128 ** 0.5, 3)
    assert coincide(a, b) is False


def test_justo_en_el_umbral_coincide():
    a = [0.0] * 128
    b = [0.0] * 128
    b[0] = UMBRAL
    assert coincide(a, b) is True


def test_apenas_pasado_el_umbral_no_coincide():
    a = [0.0] * 128
    b = [0.0] * 128
    b[0] = UMBRAL + 0.01
    assert coincide(a, b) is False


def test_longitudes_distintas_fallan():
    with pytest.raises(ValueError):
        distancia([0.0] * 128, [0.0] * 64)
