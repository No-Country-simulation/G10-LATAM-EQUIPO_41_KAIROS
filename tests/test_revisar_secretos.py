"""El revisor de secretos detecta llaves sin imprimirlas."""

import importlib.util
from pathlib import Path

RUTA = Path(__file__).resolve().parents[1] / "scripts" / "revisar_secretos.py"
_spec = importlib.util.spec_from_file_location("revisar_secretos", RUTA)
revisar_secretos = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(revisar_secretos)


def test_detecta_llaves_y_archivos_de_credenciales(tmp_path, monkeypatch):
    monkeypatch.setattr(revisar_secretos, "RAIZ", tmp_path)
    llave = "AIza" + "x" * 35
    (tmp_path / "config.py").write_text(f'CLAVE = "{llave}"\n', encoding="utf-8")
    (tmp_path / "limpio.py").write_text("print('hola')\n", encoding="utf-8")
    hallazgos = revisar_secretos.revisar(["config.py", "limpio.py", "clave_oci.pem", ".env", ".env.example"])
    assert hallazgos == [
        "config.py:1: posible llave de Google / Gemini",
        "clave_oci.pem: archivo de credenciales, no debe subirse",
        ".env: archivo de credenciales, no debe subirse",
    ]
    assert all(llave not in h for h in hallazgos)
