-- Mart: continuous coverage "islands" per member (gaps-and-islands).
-- Spans that touch (next start = prior end + 1 day, e.g. a January plan change) or overlap
-- (source error) are merged into one island. A new island starts only after a real gap.
-- Retention is measured on the FIRST island: a plan change inside the organization is not
-- churn, and a member who leaves and later re-enrolls counts as churned at the first exit.
DROP TABLE IF EXISTS marts.int_coverage_island;
CREATE TABLE marts.int_coverage_island AS
WITH s AS (
    SELECT
        span_id,
        member_id,
        start_date,
        end_date,
        COALESCE(end_date, DATE '2025-12-31') AS end_eff,
        disenroll_reason_code,
        posted_date,
        is_retro_term
    FROM staging.stg_enrollment_span
),
o AS (
    SELECT
        s.*,
        MAX(end_eff) OVER (
            PARTITION BY member_id ORDER BY start_date, span_id
            ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING
        ) AS prior_max_end
    FROM s
),
flagged AS (
    SELECT
        o.*,
        CASE WHEN prior_max_end IS NULL OR start_date > prior_max_end + 1 THEN 1 ELSE 0 END AS new_island
    FROM o
),
numbered AS (
    SELECT
        f.*,
        SUM(new_island) OVER (
            PARTITION BY member_id ORDER BY start_date, span_id
            ROWS UNBOUNDED PRECEDING
        ) AS island_no
    FROM flagged f
),
ranked AS (
    -- the span that defines how the island ends (latest end; open spans sort last)
    SELECT
        n.*,
        ROW_NUMBER() OVER (
            PARTITION BY member_id, island_no
            ORDER BY CASE WHEN end_date IS NULL THEN 1 ELSE 0 END DESC, end_eff DESC, span_id DESC
        ) AS rn_end
    FROM numbered n
)
SELECT
    member_id,
    island_no,
    MIN(start_date)                                              AS island_start,
    MAX(end_eff)                                                 AS island_end_eff,
    MAX(CASE WHEN end_date IS NULL THEN 1 ELSE 0 END)            AS is_open,
    MAX(CASE WHEN rn_end = 1 THEN disenroll_reason_code END)     AS end_reason_code,
    MAX(CASE WHEN rn_end = 1 THEN posted_date END)               AS end_posted_date,
    MAX(CASE WHEN rn_end = 1 THEN is_retro_term ELSE 0 END)      AS end_is_retro_term,
    COUNT(*)                                                     AS n_spans
FROM ranked
GROUP BY member_id, island_no;
