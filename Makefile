UV ?= uv
SEED ?= 42
START ?= 2026-11-01
DAYS ?= 1
OUT ?= data/raw
INCIDENT ?= none
TRUNCATE_PCT ?= 0.6

PROJECT ?= $(shell gcloud config get-value project 2>/dev/null)

.PHONY: install hooks test lint fmt gen gen-day load validate clean

install:
	$(UV) sync

hooks:
	$(UV) run pre-commit install

test:
	$(UV) run pytest

lint:
	$(UV) run ruff check .
	$(UV) run ruff format --check .

fmt:
	$(UV) run ruff format .
	$(UV) run ruff check --fix .

gen:
	$(UV) run eventforge batch --seed $(SEED) --start $(START) --days $(DAYS) --out $(OUT)

gen-day:
	$(UV) run eventforge batch --seed $(SEED) --start $(START) --days 1 \
		--out $(OUT) --incident $(INCIDENT) --truncate-pct $(TRUNCATE_PCT)

load: validate
	$(UV) run python -m ingest.load_day --day-dir $(OUT)/$(START) --project $(PROJECT)

validate:
	$(UV) run python -m ingest.validate --day-dir $(OUT)/$(START) --project $(PROJECT)

clean:
	rm -rf data/raw .pytest_cache .ruff_cache
