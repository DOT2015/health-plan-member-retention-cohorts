"""Export a star schema to powerbi/ as CSV (dimension tables + member-grain and month-grain facts)."""
import duckdb

import config as C

EXPORTS = {
    "dim_member": "SELECT member_id, enroll_date, cohort_yyyymm, plan_id, county_fips, age_band, sex, "
                  "dual_eligible_flag, lis_flag, channel FROM marts.fct_member_retention",
    "dim_plan": "SELECT * FROM staging.stg_plan",
    "dim_county": "SELECT * FROM staging.stg_county",
    "dim_month": "SELECT DISTINCT month_start, year, month, quarter, is_oep_month FROM staging.stg_date ORDER BY month_start",
    "fact_member_retention": "SELECT member_id, churned, island_end_eff AS coverage_end_date, end_reason_code, "
                             "end_is_retro_term, covered_months, observable_months, landmark_90d, retained_12m, "
                             "welcome_complete_90d, hra_complete_90d, pcp_visit_90d, pcp_visit_60d, portal_90d "
                             "FROM marts.fct_member_retention",
    "fact_monthly_disenrollment": "SELECT * FROM read_csv('{out}/04_disenrollment_seasonality.csv')",
    "fact_cohort_retention": "SELECT * FROM read_csv('{out}/01_cohort_retention_matrix.csv')",
}


def main():
    C.POWERBI.mkdir(exist_ok=True)
    con = duckdb.connect(str(C.DB), read_only=True)
    total = 0
    for name, sql in EXPORTS.items():
        path = C.POWERBI / f"{name}.csv"
        con.execute(sql.format(out=C.OUTPUTS.as_posix())).fetchdf().to_csv(path, index=False)
        total += path.stat().st_size
    con.close()
    print(f"powerbi exports: {total / 1e6:.1f} MB")


if __name__ == "__main__":
    main()
