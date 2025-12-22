lint:
	uv sync
	uvx ruff format .
	uvx ruff check --fix .
