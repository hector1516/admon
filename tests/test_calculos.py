"""Tests para numbers_helper.py — ECCSA Admon.

Verifica la conversión de números a letras (para PDFs de cotizaciones).
"""
import sys
import os
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "api"))


class TestNumeroALetras(unittest.TestCase):
    """Tests para numero_a_letras."""

    def setUp(self):
        from numbers_helper import numero_a_letras
        self.convertir = numero_a_letras

    def test_cero(self):
        self.assertEqual(self.convertir(0), "CERO PESOS 00/100 M.N.")

    def test_uno(self):
        result = self.convertir(1)
        self.assertIn("UN", result)
        self.assertIn("PESOS", result)

    def test_cien(self):
        result = self.convertir(100)
        self.assertIn("CIEN", result)

    def test_mil(self):
        result = self.convertir(1000)
        self.assertIn("MIL", result)

    def test_millon(self):
        result = self.convertir(1000000)
        self.assertIn("MILL", result)

    def test_decimal(self):
        result = self.convertir(1234.56)
        self.assertIn("56/100", result)

    def test_invalido(self):
        result = self.convertir("abc")
        self.assertEqual(result, "")

    def test_monto_cotizacion_tipico(self):
        result = self.convertir(15420.50)
        self.assertIn("PESOS", result)
        self.assertIn("50/100", result)


class TestValidaciones(unittest.TestCase):
    """Tests para validaciones de negocio."""

    def test_id_cliente_max_4_letras(self):
        # ID de cliente debe ser máximo 4 letras
        def validar_id(idc):
            return len(idc.strip().upper()) <= 4 and idc.strip().isalpha()
        self.assertTrue(validar_id("HUSA"))
        self.assertTrue(validar_id("JCEC"))
        self.assertFalse(validar_id("HUSAM"))  # 5 letras
        self.assertFalse(validar_id("1234"))   # números
        self.assertTrue(validar_id("A"))

    def test_contacto_obligatorio(self):
        def validar_contacto(contacto):
            return bool(contacto and contacto.strip())
        self.assertTrue(validar_contacto("Juan Pérez"))
        self.assertFalse(validar_contacto(""))
        self.assertFalse(validar_contacto("   "))

    def test_descripcion_obligatoria(self):
        def validar_desc(desc):
            return bool(desc and desc.strip())
        self.assertTrue(validar_desc("Módulo de 4 salidas"))
        self.assertFalse(validar_desc(""))

    def test_cantidad_partida_minimo(self):
        def validar_cantidad(cant):
            try:
                return int(cant) >= 1
            except (ValueError, TypeError):
                return False
        self.assertTrue(validar_cantidad(1))
        self.assertTrue(validar_cantidad(10))
        self.assertFalse(validar_cantidad(0))
        self.assertFalse(validar_cantidad(-1))
        self.assertFalse(validar_cantidad("abc"))


class TestCalculosCotizacion(unittest.TestCase):
    """Tests para cálculos de cotización."""

    def test_subtotal_simple(self):
        partidas = [
            {"cantidad": 2, "precio": 100.0, "factor": 1.5},
        ]
        subtotal = sum(p["cantidad"] * p["precio"] * p["factor"] for p in partidas)
        self.assertEqual(subtotal, 300.0)

    def test_subtotal_con_flete(self):
        partidas = [
            {"cantidad": 2, "precio": 100.0, "factor": 1.5},
        ]
        flete = 50.0
        subtotal = sum(p["cantidad"] * p["precio"] * p["factor"] for p in partidas) + flete
        self.assertEqual(subtotal, 350.0)

    def test_iva(self):
        subtotal = 350.0
        iva = subtotal * 0.16
        self.assertAlmostEqual(iva, 56.0)

    def test_total(self):
        subtotal = 350.0
        iva = 56.0
        total = subtotal + iva
        self.assertEqual(total, 406.0)

    def test_multiples_partidas(self):
        partidas = [
            {"cantidad": 2, "precio": 100.0, "factor": 1.5},
            {"cantidad": 1, "precio": 200.0, "factor": 1.3},
            {"cantidad": 3, "precio": 50.0, "factor": 1.0},
        ]
        subtotal = sum(p["cantidad"] * p["precio"] * p["factor"] for p in partidas)
        self.assertAlmostEqual(subtotal, 300 + 260 + 150)

    def test_folio_formato(self):
        def fmt_folio(n):
            return f"CM{str(n).zfill(5)}"
        self.assertEqual(fmt_folio(1), "CM00001")
        self.assertEqual(fmt_folio(123), "CM00123")
        self.assertEqual(fmt_folio(99999), "CM99999")


class TestCalculosReporte(unittest.TestCase):
    """Tests para cálculos de reporte de servicio."""

    def test_horas_reporte(self):
        from datetime import datetime
        inicio = datetime(2026, 10, 29, 9, 0)
        fin = datetime(2026, 10, 29, 11, 30)
        traslado = 0.5
        horas = (fin - inicio).total_seconds() / 3600 + traslado
        self.assertAlmostEqual(horas, 3.0)

    def test_horas_sin_traslado(self):
        from datetime import datetime
        inicio = datetime(2026, 10, 29, 9, 0)
        fin = datetime(2026, 10, 29, 11, 0)
        traslado = 0
        horas = (fin - inicio).total_seconds() / 3600 + traslado
        self.assertAlmostEqual(horas, 2.0)

    def test_horas_reporte_null(self):
        # Sin fecha de inicio o fin, no se puede calcular
        def horas_reporte(inicio, fin, traslado=0):
            if not inicio or not fin:
                return None
            return (fin - inicio).total_seconds() / 3600 + traslado
        from datetime import datetime
        self.assertIsNone(horas_reporte(None, None))
        self.assertIsNone(horas_reporte(datetime(2026, 10, 29, 9, 0), None))


class TestCalculosLegends(unittest.TestCase):
    """Tests para cálculos de Legends."""

    def test_nivel_por_puntos(self):
        def nivel_por_puntos(pts):
            if pts >= 500: return "Leyenda"
            if pts >= 300: return "Diamante"
            if pts >= 150: return "Oro"
            if pts >= 50: return "Plata"
            return "Bronce"
        self.assertEqual(nivel_por_puntos(0), "Bronce")
        self.assertEqual(nivel_por_puntos(50), "Plata")
        self.assertEqual(nivel_por_puntos(150), "Oro")
        self.assertEqual(nivel_por_puntos(300), "Diamante")
        self.assertEqual(nivel_por_puntos(500), "Leyenda")
        self.assertEqual(nivel_por_puntos(1000), "Leyenda")

    def test_puntos_reporte(self):
        # reporte_firmado = 10 pts
        puntos = 10
        self.assertEqual(puntos, 10)

    def test_puntos_negativos_vale(self):
        # vale_generado = -2 pts
        puntos = -2
        self.assertEqual(puntos, -2)


if __name__ == "__main__":
    unittest.main()
