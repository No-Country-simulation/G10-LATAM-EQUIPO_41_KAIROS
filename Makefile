.PHONY: install test run-api run-ui demo requirements

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

# Regenera requirements.txt con las versiones instaladas (ver scripts/generar_requirements.py)
requirements:
	python scripts/generar_requirements.py
