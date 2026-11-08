-- Staging: enrollment spans.
-- end_date NULL = still enrolled. posted_date = when the record last changed in the source.
-- Flags (not fixes; the fixes happen in marts):
--   is_retro_term   : termination posted 30+ days after its effective end date. Month-end
--                     snapshots taken before posting still show these members as active.
--   overlaps_prior  : span starts on or before the latest end date of an earlier span for the
--                     same member (source error). Merged in marts.int_coverage_island.
DROP TABLE IF EXISTS staging.stg_enrollment_span;
CREATE TABLE staging.stg_enrollment_span AS
WITH typed AS (
    SELECT
        span_id,
        member_id,
        CAST(start_date AS DATE)  AS start_date,
        CAST(end_date AS DATE)    AS end_date,
        disenroll_reason_code,
        plan_id,
        CAST(posted_date AS DATE) AS posted_date
    FROM raw.fact_enrollment_span
),
ordered AS (
    SELECT
        t.*,
        MAX(COALESCE(end_date, DATE '2025-12-31')) OVER (
            PARTITION BY member_id ORDER BY start_date, span_id
            ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING
        ) AS prior_max_end
    FROM typed t
)
SELECT
    span_id,
    member_id,
    start_date,
    end_date,
    disenroll_reason_code,
    plan_id,
    posted_date,
    CASE WHEN end_date IS NOT NULL AND posted_date - end_date >= 30 THEN 1 ELSE 0 END AS is_retro_term,
    CASE WHEN prior_max_end IS NOT NULL AND start_date <= prior_max_end THEN 1 ELSE 0 END AS overlaps_prior
FROM ordered;
