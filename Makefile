PY ?= python3

.PHONY: all clean generate load staging marts analysis model figures dashboard powerbi report test

all: clean generate load staging marts analysis model figures dashboard powerbi report test

clean:
	rm -rf data/raw data/outputs data/warehouse.duckdb data/warehouse.duckdb.wal

generate:
	$(PY) src/generate_data.py

load:
	$(PY) src/load.py

staging:
	$(PY) src/run_sql.py 01_staging

marts:
	$(PY) src/run_sql.py 02_marts

analysis:
	$(PY) src/run_sql.py 03_analysis

model:
	$(PY) src/analysis.py

figures:
	$(PY) src/figures.py

dashboard:
	$(PY) src/dashboard.py

powerbi:
	$(PY) src/export_powerbi.py

report:
	$(PY) src/report.py

test:
	$(PY) -m pytest -q
