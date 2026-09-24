.PHONY: install test run-api run-ui demo

install:
	pip install -e ".[dev,ui]"

test:
	pytest tests/ -v

# API + interfaz web en http://localhost:8000/
run-api:
	uvicorn nuevamente.api.app:app --reload

run-ui:
	streamlit run ui/app.py

demo:
	python scripts/run_demo.py
