"""Load raw CSVs into DuckDB (data/warehouse.duckdb), schema `raw`, all columns as text.

Typing and cleaning happen in sql/01_staging so every cast is visible and reviewable.
"""
import duckdb

import config as C


def main():
    if C.DB.exists():
        C.DB.unlink()
    con = duckdb.connect(str(C.DB))
    for schema in ["raw", "staging", "marts"]:
        con.execute(f"CREATE SCHEMA IF NOT EXISTS {schema}")
    for path in sorted(C.RAW.glob("*.csv")):
        con.execute(
            f"CREATE TABLE raw.{path.stem} AS SELECT * FROM read_csv('{path.as_posix()}', header = true, all_varchar = true)"
        )
        n = con.execute(f"SELECT COUNT(*) FROM raw.{path.stem}").fetchone()[0]
        print(f"raw.{path.stem}: {n:,} rows")
    con.close()


if __name__ == "__main__":
    main()
