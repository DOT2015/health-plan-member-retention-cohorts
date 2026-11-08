"""Run every .sql file in a folder against the warehouse, in file-name order.

Staging and mart files create tables. Analysis files are single SELECT statements;
their results are written to data/outputs/<file stem>.csv.
"""
import sys
from pathlib import Path

import duckdb

import config as C


def main(folder: str):
    con = duckdb.connect(str(C.DB))
    files = sorted((C.ROOT / "sql" / folder).glob("*.sql"))
    is_analysis = folder.startswith("03")
    C.OUTPUTS.mkdir(parents=True, exist_ok=True)
    for f in files:
        sql = f.read_text()
        if is_analysis:
            df = con.execute(sql).fetchdf()
            df.to_csv(C.OUTPUTS / f"{f.stem}.csv", index=False)
            print(f"{f.name}: {len(df):,} rows -> data/outputs/{f.stem}.csv")
        else:
            con.execute(sql)
            print(f"{f.name}: ok")
    con.close()


if __name__ == "__main__":
    main(sys.argv[1])
