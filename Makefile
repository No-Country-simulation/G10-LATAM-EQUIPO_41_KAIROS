.PHONY: install test run-api run-ui demo requirements pruebas-matriz pruebas-matriz-web

install:
	pip install -e ".[dev,ui,gemini]"

test:
	pytest tests/ -v

# API + interfaz web en http://localhost:8000/
run-api:
	uvicorn nuevamente.api.app:app --reload

run-ui:
	streamlit run ui/app.py

demo:
	python scripts/run_demo.py

# Matriz de pruebas: 4 tipos de archivo × 6 formatos × 3 perfiles (nicho Salud).
# Genera docs/pruebas/evidencia/ con JSON + PNG + reporte por cada una de las 72 pruebas.
pruebas-matriz:
	python scripts/pruebas_matriz.py --proveedor gemini

# Capturas reales de la interfaz web (requiere: pip install playwright).
pruebas-matriz-web:
	python scripts/pruebas_matriz.py --capturas-web

# Regenera requirements.txt con las versiones instaladas (ver scripts/generar_requirements.py)
requirements:
	python scripts/generar_requirements.py
