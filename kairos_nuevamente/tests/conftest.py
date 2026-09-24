"""Fixtures compartidos de pruebas. Responsable: Diana Dure (QA Tester)."""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

# Antes de importar nuevamente: los tests guardan en una carpeta temporal, no en el
# data/fallback/ real, y sin OCI aunque la máquina tenga ~/.oci/config.
os.environ["FALLBACK_DIR"] = tempfile.mkdtemp(prefix="nuevamente-tests-")
os.environ["OCI_CONFIG_FILE"] = os.path.join(os.environ["FALLBACK_DIR"], "sin-oci")

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pytest

DOCUMENTO_SALUD = """# Lavado de manos
El lavado de manos con agua y jabon durante al menos 20 segundos elimina la mayoria \
de los microorganismos de las manos. Es la medida mas efectiva y economica para \
prevenir infecciones en el personal de salud.

# Equipos de proteccion personal
Los guantes, mascarillas y batas desechables forman parte del equipo de proteccion \
personal, conocido como EPP. El EPP debe usarse correctamente y desecharse tras cada \
procedimiento para evitar contaminacion cruzada entre pacientes.

# Manejo de residuos
Los residuos biocontaminados deben separarse en bolsas rojas y desecharse segun el \
protocolo institucional vigente. El personal debe estar capacitado en la \
clasificacion correcta de residuos para evitar accidentes.
"""


@pytest.fixture
def documento_salud() -> str:
    return DOCUMENTO_SALUD


@pytest.fixture
def api_client():
    from fastapi.testclient import TestClient

    from nuevamente.api.app import app

    return TestClient(app)
