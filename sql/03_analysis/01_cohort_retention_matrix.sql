-- Q1. Cohort retention matrix: enrollment cohort (month) x months since enrollment.
-- retention_pct at month k = share of the cohort that completed k months of continuous
-- enrollment (covered_months >= k). k = 12 is 12-month retention.
-- Censoring: all members of a cohort enroll on the same day, so a cell is shown only when
-- the cohort's k-th month is fully observed (ends on or before 2025-12-31). Unobserved cells are omitted, not zero.
WITH cohorts AS (
    SELECT cohort_yyyymm, MIN(enroll_date) AS cohort_start, COUNT(*) AS cohort_size
    FROM marts.fct_member_retention
    GROUP BY cohort_yyyymm
),
k_values AS (
    -- months since enrollment 0..36, built from the date dimension (portable, no generate_series)
    SELECT DISTINCT
        CAST((EXTRACT(YEAR FROM month_start) - 2023) * 12 + EXTRACT(MONTH FROM month_start) - 1 AS INTEGER) AS k
    FROM staging.stg_date
    UNION ALL SELECT 36
),
grid AS (
    SELECT c.cohort_yyyymm, c.cohort_start, c.cohort_size, k.k
    FROM cohorts c
    CROSS JOIN k_values k
    WHERE k.k >= 1
      AND (EXTRACT(YEAR FROM c.cohort_start) - 2023) * 12 + EXTRACT(MONTH FROM c.cohort_start) - 1 + k.k - 1 <= 35
)
SELECT
    g.cohort_yyyymm,
    g.k AS months_since_enroll,
    g.cohort_size,
    SUM(CASE WHEN r.covered_months >= g.k THEN 1 ELSE 0 END) AS retained,
    ROUND(100.0 * SUM(CASE WHEN r.covered_months >= g.k THEN 1 ELSE 0 END) / g.cohort_size, 2) AS retention_pct
FROM grid g
JOIN marts.fct_member_retention r ON r.cohort_yyyymm = g.cohort_yyyymm
GROUP BY g.cohort_yyyymm, g.k, g.cohort_size
ORDER BY g.cohort_yyyymm, g.k;
