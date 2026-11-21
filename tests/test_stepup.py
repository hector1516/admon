"""Token corto que prueba que el usuario acaba de usar su passkey (D3 B).

`/marcar` lo exige: sin passkey verificada hace menos de 2 minutos no se marca.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "api"))

from stepup import PROPOSITO, emitir, validar  # noqa: E402

SECRETO = "clave-de-prueba"


def test_token_valido_devuelve_la_credencial():
    token = emitir(7, "cred-abc", SECRETO)
    assert validar(token, 7, SECRETO) == "cred-abc"


def test_otro_usuario_no_puede_usarlo():
    token = emitir(7, "cred-abc", SECRETO)
    with pytest.raises(ValueError):
        validar(token, 8, SECRETO)


def test_expirado_se_rechaza():
    token = emitir(7, "cred-abc", SECRETO, minutos=-1)
    with pytest.raises(ValueError):
        validar(token, 7, SECRETO)


def test_otro_secreto_se_rechaza():
    token = emitir(7, "cred-abc", SECRETO)
    with pytest.raises(ValueError):
        validar(token, 7, "otro-secreto")


def test_proposito_es_marcado():
    assert PROPOSITO == "marcado"
