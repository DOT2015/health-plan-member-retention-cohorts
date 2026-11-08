import json
import sys
from pathlib import Path

import duckdb
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
import config as C  # noqa: E402


@pytest.fixture(scope="session")
def con():
    if not C.DB.exists():
        pytest.fail("data/warehouse.duckdb not found: run `make all` first")
    c = duckdb.connect(str(C.DB), read_only=True)
    yield c
    c.close()


@pytest.fixture(scope="session")
def truth():
    return json.loads(C.TRUTH.read_text())


@pytest.fixture(scope="session")
def results():
    return json.loads((C.REPORTS / "results.json").read_text())


def scalar(con, sql):
    return con.execute(sql).fetchone()[0]
