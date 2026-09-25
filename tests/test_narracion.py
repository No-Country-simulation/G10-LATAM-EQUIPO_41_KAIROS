"""Tests de la narración del video. Responsable: Diana Dure (QA Tester)."""
from nuevamente.exports.narracion import preparar_texto


def test_fechas_iso_se_leen_en_palabras():
    assert "24 de septiembre de 2026" in preparar_texto("Entrega el 2026-09-24.")
    # fecha partida por la extracción del PDF
    assert "2 de octubre de 2026" in preparar_texto("Programa 2026-10- 2 listo")


def test_abreviaturas_y_simbolos_se_expanden():
    texto = preparar_texto("Usar EPP, p. ej. guantes (máx. 10 min) en el 90% de los casos.")
    assert "por ejemplo" in texto
    assert "máximo 10 minutos" in texto
    assert "90 por ciento" in texto
    assert "E P P" in texto  # sigla deletreada
    assert "(" not in texto and ")" not in texto


def test_listas_se_leen_como_frases_separadas():
    assert preparar_texto("- Lavado de manos\n- Uso de **EPP**") == "Lavado de manos. Uso de E P P."


def test_no_pasa_comandos_de_voz_desde_el_documento():
    assert "[[" not in preparar_texto("Texto con [[volm 0]] comandos inyectados")


def test_texto_normal_no_cambia_de_sentido():
    original = "El lavado de manos elimina la mayoría de los microorganismos."
    assert preparar_texto(original) == original
