"""Revisa que no se suban llaves ni archivos de credenciales al repositorio.

Uso:
    python scripts/revisar_secretos.py            # archivos preparados para el commit (git add)
    python scripts/revisar_secretos.py --todos    # todos los archivos del repositorio

Como gancho antes de cada commit:
    python scripts/revisar_secretos.py --instalar

Nunca imprime la llave encontrada: solo el archivo, la línea y el tipo.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]

# Archivos que nunca deben subirse, sea cual sea su contenido.
ARCHIVOS_PROHIBIDOS = re.compile(r"(^|/)(\.env|.*\.pem|.*\.p12|.*\.pfx|id_rsa|id_ed25519)$")
PERMITIDOS = {".env.example"}

PATRONES = {
    "llave privada": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----"),
    "llave de Google / Gemini": re.compile(r"AIza[0-9A-Za-z_\-]{35}"),
    "llave de OpenAI": re.compile(r"sk-(?:proj-)?[A-Za-z0-9_\-]{32,}"),
    "llave de OpenRouter": re.compile(r"sk-or-v1-[A-Za-z0-9]{32,}"),
    "llave de Groq": re.compile(r"gsk_[A-Za-z0-9]{40,}"),
    "llave de Cerebras": re.compile(r"csk-[A-Za-z0-9]{32,}"),
    "llave de Anthropic": re.compile(r"sk-ant-[A-Za-z0-9_\-]{32,}"),
    "token de GitHub": re.compile(r"gh[pousr]_[A-Za-z0-9]{36,}"),
}

GANCHO = """#!/bin/sh
# Instalado por scripts/revisar_secretos.py --instalar
python3 scripts/revisar_secretos.py || exit 1
"""


def _git(*args: str) -> list[str]:
    salida = subprocess.run(["git", *args], cwd=RAIZ, capture_output=True, text=True, check=True).stdout
    return [linea for linea in salida.splitlines() if linea]


def revisar(rutas: list[str]) -> list[str]:
    hallazgos = []
    for ruta in rutas:
        if ARCHIVOS_PROHIBIDOS.search(ruta) and Path(ruta).name not in PERMITIDOS:
            hallazgos.append(f"{ruta}: archivo de credenciales, no debe subirse")
            continue
        archivo = RAIZ / ruta
        if not archivo.is_file() or archivo.stat().st_size > 2_000_000:
            continue
        try:
            texto = archivo.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue  # binarios: imágenes, audio, docx…
        for numero, linea in enumerate(texto.splitlines(), start=1):
            for tipo, patron in PATRONES.items():
                if patron.search(linea):
                    hallazgos.append(f"{ruta}:{numero}: posible {tipo}")
    return hallazgos


def main(argv: list[str]) -> int:
    if "--instalar" in argv:
        gancho = RAIZ / ".git" / "hooks" / "pre-commit"
        gancho.write_text(GANCHO, encoding="utf-8")
        gancho.chmod(0o755)
        print(f"Gancho instalado en {gancho.relative_to(RAIZ)}")
        return 0
    rutas = _git("ls-files") if "--todos" in argv else _git("diff", "--cached", "--name-only", "--diff-filter=ACMR")
    hallazgos = revisar(rutas)
    if hallazgos:
        print("Se encontraron posibles secretos. Quítalos antes de subir:")
        for h in hallazgos:
            print(f"  - {h}")
        return 1
    print(f"Sin secretos en {len(rutas)} archivo(s).")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
