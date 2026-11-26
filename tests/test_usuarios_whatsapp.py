"""tests/test_usuarios_whatsapp.py — Normalización del WhatsApp del usuario.

La regla es la misma que aplica `openwa_client.normalizar_chat_id` al mandar un
aviso: 10 dígitos = México (52 + los 10), 12 a 15 se respetan tal cual y un 11
dígitos que empieza con 1 se rechaza por ambiguo. Si esta regla se separa de la
de WorkersAdmon, el número guardado deja de coincidir con el que se usa para
escribir.

Corre: python3 tests/test_usuarios_whatsapp.py
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from api import usuarios_whatsapp as ws  # noqa: E402


class NormalizarTelefonoTest(unittest.TestCase):
    def test_diez_digitos_se_asume_mexico(self):
        self.assertEqual(ws.normalizar_telefono("8121234567"), "528121234567")

    def test_con_espacios_y_mas(self):
        self.assertEqual(ws.normalizar_telefono("+52 81 2123 4567"), "528121234567")

    def test_con_guiones_y_parentesis(self):
        self.assertEqual(ws.normalizar_telefono("(81) 2123-4567"), "528121234567")

    def test_ya_con_pais(self):
        self.assertEqual(ws.normalizar_telefono("528121234567"), "528121234567")

    def test_once_digitos_con_uno_se_rechaza(self):
        with self.assertRaises(ValueError):
            ws.normalizar_telefono("18123456789")

    def test_letras_se_rechazan(self):
        with self.assertRaises(ValueError):
            ws.normalizar_telefono("abc")

    def test_corto_se_rechaza(self):
        with self.assertRaises(ValueError):
            ws.normalizar_telefono("8121234")

    def test_vacio_es_sin_whatsapp(self):
        self.assertEqual(ws.normalizar_telefono(""), "")
        self.assertEqual(ws.normalizar_telefono(None), "")
        self.assertEqual(ws.normalizar_telefono("   "), "")


if __name__ == "__main__":
    unittest.main()
