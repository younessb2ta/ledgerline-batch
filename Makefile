UV ?= uv
SEED ?= 42
START ?= 2026-11-01
DAYS ?= 1
OUT ?= data/raw
INCIDENT ?= none
TRUNCATE_PCT ?= 0.6

.PHONY: install hooks test lint fmt gen gen-day clean

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

clean:
	rm -rf data/raw .pytest_cache .ruff_cache
