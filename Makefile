.PHONY: install run test lint format load build-data

install:  ## Install dependencies into .venv
	uv sync

run:  ## Start the dev server on :8000
	uv run python manage.py runserver

test:  ## Run the test suite (network is blocked)
	uv run pytest

lint:  ## Check lint and formatting
	uv run ruff check .
	uv run ruff format --check .

format:  ## Apply lint fixes and formatting
	uv run ruff check --fix .
	uv run ruff format .

load:  ## Create the database and load Stations (offline, ~1 s)
	uv run python manage.py migrate
	uv run python manage.py load_stations

build-data:  ## Rebuild the committed city coordinate files (needs internet; maintainers only)
	uv run python manage.py build_city_coords
