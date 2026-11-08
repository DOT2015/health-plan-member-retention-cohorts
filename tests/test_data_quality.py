"""Data-quality checks on the warehouse: row counts, keys, referential integrity, nulls."""
import pytest

from conftest import scalar


@pytest.mark.parametrize("table,lo,hi", [
    ("raw.dim_member", 28_000, 28_000),
    ("raw.dim_plan", 12, 12),
    ("raw.dim_county", 40, 40),
    ("raw.dim_date", 1_096, 1_096),
    ("raw.fact_enrollment_span", 29_000, 33_000),
    ("raw.fact_member_month", 400_000, 500_000),
    ("raw.fact_onboarding_event", 150_000, 250_000),
])
def test_raw_row_counts(con, table, lo, hi):
    n = scalar(con, f"SELECT COUNT(*) FROM {table}")
    assert lo <= n <= hi, f"{table}: {n}"


@pytest.mark.parametrize("table,key", [
    ("staging.stg_member", "member_id"),
    ("staging.stg_plan", "plan_id"),
    ("staging.stg_county", "county_fips"),
    ("staging.stg_date", "date"),
    ("staging.stg_enrollment_span", "span_id"),
    ("staging.stg_onboarding_event", "event_id"),
    ("marts.dim_member", "member_id"),
    ("marts.fct_member_retention", "member_id"),
    ("marts.fct_member_onboarding", "member_id"),
])
def test_primary_keys_unique_and_not_null(con, table, key):
    n, d, nulls = con.execute(
        f"SELECT COUNT(*), COUNT(DISTINCT {key}), SUM(CASE WHEN {key} IS NULL THEN 1 ELSE 0 END) FROM {table}").fetchone()
    assert n == d and (nulls or 0) == 0


def test_person_month_key_unique(con):
    n, d = con.execute("SELECT COUNT(*), COUNT(DISTINCT member_id || '|' || CAST(month_start AS VARCHAR)) "
                       "FROM marts.fct_person_month").fetchone()
    assert n == d


@pytest.mark.parametrize("child,col,parent,pcol", [
    ("staging.stg_enrollment_span", "member_id", "staging.stg_member", "member_id"),
    ("staging.stg_onboarding_event", "member_id", "staging.stg_member", "member_id"),
    ("staging.stg_member", "plan_id", "staging.stg_plan", "plan_id"),
    ("staging.stg_member", "county_fips", "staging.stg_county", "county_fips"),
    ("staging.stg_enrollment_span", "plan_id", "staging.stg_plan", "plan_id"),
    ("marts.fct_person_month", "member_id", "marts.fct_member_retention", "member_id"),
])
def test_referential_integrity(con, child, col, parent, pcol):
    orphans = scalar(con, f"SELECT COUNT(*) FROM {child} c LEFT JOIN {parent} p ON c.{col} = p.{pcol} WHERE p.{pcol} IS NULL")
    assert orphans == 0


def test_every_member_has_one_retention_row(con):
    assert scalar(con, "SELECT COUNT(*) FROM marts.fct_member_retention") == scalar(con, "SELECT COUNT(*) FROM staging.stg_member")


def test_null_thresholds(con):
    n = scalar(con, "SELECT COUNT(*) FROM staging.stg_member")
    assert scalar(con, "SELECT SUM(county_was_null) FROM staging.stg_member") / n <= 0.02
    assert scalar(con, "SELECT COUNT(*) FROM staging.stg_member WHERE channel = 'unknown'") == 0
    assert scalar(con, "SELECT COUNT(*) FROM staging.stg_onboarding_event WHERE event_ts_utc IS NULL") == 0
    assert scalar(con, "SELECT COUNT(*) FROM staging.stg_enrollment_span WHERE start_date IS NULL") == 0


def test_dates_valid(con):
    assert scalar(con, "SELECT COUNT(*) FROM staging.stg_enrollment_span WHERE end_date < start_date") == 0
    assert scalar(con, "SELECT COUNT(*) FROM marts.fct_member_retention WHERE covered_months < 1") == 0
    assert scalar(con, "SELECT MAX(island_end_eff) FROM marts.fct_member_retention") <= __import__("datetime").date(2025, 12, 31)


def test_islands_do_not_overlap(con):
    bad = scalar(con, """
        SELECT COUNT(*) FROM marts.int_coverage_island a JOIN marts.int_coverage_island b
          ON a.member_id = b.member_id AND b.island_no = a.island_no + 1
        WHERE b.island_start <= a.island_end_eff + 1""")
    assert bad == 0


def test_person_months_reconcile_to_members(con):
    assert scalar(con, "SELECT SUM(disenrolled) FROM marts.fct_person_month") == \
        scalar(con, "SELECT SUM(churned) FROM marts.fct_member_retention")
    assert scalar(con, "SELECT COUNT(*) FROM marts.fct_person_month") == \
        scalar(con, "SELECT SUM(covered_months) FROM marts.fct_member_retention")


def test_clean_events_have_no_duplicates_left(con):
    left = scalar(con, """
        WITH clean AS (SELECT * FROM staging.stg_onboarding_event WHERE is_cross_feed_duplicate = 0)
        SELECT COUNT(*) FROM clean a JOIN clean b
          ON a.member_id = b.member_id AND a.event_type = b.event_type AND a.event_id < b.event_id
         AND a.source_system <> b.source_system
         AND ABS(EXTRACT(EPOCH FROM (a.event_ts_utc - b.event_ts_utc))) <= 300""")
    assert left == 0


def test_sample_files_small():
    import config as C
    for f in C.SAMPLE.glob("*.csv"):
        with open(f) as fh:
            assert sum(1 for _ in fh) - 1 <= 1000, f.name
