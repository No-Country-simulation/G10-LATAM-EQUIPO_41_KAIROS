"""Toda variable de entorno que lee el código debe estar documentada en .env.example."""

import re
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
LECTURAS = re.compile(
    r'(?:getenv|_env_float|_env_int|_env_tuple_keys|_env_latencias|environ\.get|_modelos_de)\(\s*"([A-Z][A-Z0-9_]+)"'
)


def test_todas_las_variables_estan_en_env_example():
    usadas = set()
    for archivo in (RAIZ / "src").rglob("*.py"):
        usadas |= set(LECTURAS.findall(archivo.read_text(encoding="utf-8")))
    documentadas = set(re.findall(r"^#?\s?([A-Z][A-Z0-9_]+)=", (RAIZ / ".env.example").read_text(encoding="utf-8"), re.M))
    faltan = sorted(usadas - documentadas)
    assert not faltan, f"Agrega estas variables a .env.example: {faltan}"


def test_env_example_no_trae_llaves_reales():
    for linea in (RAIZ / ".env.example").read_text(encoding="utf-8").splitlines():
        if re.match(r"^[A-Z_]*(API_KEY|API_KEYS)=", linea):
            assert linea.split("=", 1)[1] == "", f"La llave debe ir vacía en .env.example: {linea.split('=')[0]}"
