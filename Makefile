run:
	uvicorn src.app.main:app --reload

test:
	pytest -q
