UV ?= uv
SEED ?= 42
START ?= 2026-11-01
DAYS ?= 1
OUT ?= data/raw
INCIDENT ?= none
TRUNCATE_PCT ?= 0.6

PROJECT ?= $(shell gcloud config get-value project 2>/dev/null)
export GCP_PROJECT ?= $(PROJECT)
export BQ_LOCATION ?= US

DBT = cd warehouse && $(UV) run dbt
DBT_FLAGS ?= --profiles-dir .

.PHONY: install hooks test lint fmt gen gen-day load validate \
	dbt-debug dbt-run dbt-test dbt-build dbt-docs dbt-docs-serve docs-site clean

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

# --- warehouse --------------------------------------------------------------

dbt-debug:
	$(DBT) debug $(DBT_FLAGS)

dbt-run:
	$(DBT) run $(DBT_FLAGS)

dbt-test:
	$(DBT) test $(DBT_FLAGS)

dbt-build:
	$(DBT) build $(DBT_FLAGS)

dbt-docs:
	$(DBT) docs generate $(DBT_FLAGS)

dbt-docs-serve:
	$(DBT) docs serve $(DBT_FLAGS)

docs-site: dbt-docs
	mkdir -p docs/dbt
	cp warehouse/target/index.html warehouse/target/manifest.json \
		warehouse/target/catalog.json docs/dbt/

clean:
	rm -rf data/raw .pytest_cache .ruff_cache warehouse/target warehouse/logs
