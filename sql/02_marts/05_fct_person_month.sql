-- Mart: one row per member per covered month of the first island (discrete-time survival).
-- disenrolled = 1 in the last covered month of a churned island.
-- pcp_visited = 1 from the first month that starts after a within-90-day PCP visit
-- (time-varying exposure, so months before the visit are not credited to it).
DROP TABLE IF EXISTS marts.fct_person_month;
CREATE TABLE marts.fct_person_month AS
WITH months AS (
    SELECT DISTINCT month_start, month, is_oep_month FROM staging.stg_date
)
SELECT
    r.member_id,
    m.month_start,
    m.month AS calendar_month,
    m.is_oep_month,
    CAST((EXTRACT(YEAR FROM m.month_start) - EXTRACT(YEAR FROM r.enroll_date)) * 12
         + EXTRACT(MONTH FROM m.month_start) - EXTRACT(MONTH FROM r.enroll_date) AS INTEGER) AS month_index,
    r.dual_eligible_flag,
    r.channel,
    r.plan_type,
    r.age_band,
    CASE WHEN r.pcp_visit_90d = 1 AND r.pcp_first_visit_date < m.month_start THEN 1 ELSE 0 END AS pcp_visited,
    CASE WHEN r.churned = 1 AND m.month_start = CAST(DATE_TRUNC('month', r.island_end_eff) AS DATE) THEN 1 ELSE 0 END AS disenrolled
FROM marts.fct_member_retention r
JOIN months m
  ON m.month_start >= r.enroll_date
 AND m.month_start <= r.island_end_eff;
