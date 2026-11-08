-- Mart: one row per member, first coverage island, with onboarding flags.
-- Metric definitions:
--   covered_months  = calendar months in the first island (enroll month counts as month 0).
--   churned         = 1 if the first island has a termination on or before 2025-12-31.
--   Censoring       : open islands are censored at 2025-12-31.
--   landmark_90d    = 1 if enrolled at the start of coverage month 4 (day ~90, covered_months >= 4).
--                     Exposure
--                     (PCP visit within 90 days) is only defined for these members, which
--                     avoids immortal-time bias.
--   retained_12m    = covered_months >= 12; only defined when 12 months were observable.
DROP TABLE IF EXISTS marts.fct_member_retention;
CREATE TABLE marts.fct_member_retention AS
WITH first_island AS (
    SELECT * FROM marts.int_coverage_island WHERE island_no = 1
),
base AS (
    SELECT
        d.*,
        i.island_start,
        i.island_end_eff,
        CASE WHEN i.is_open = 1 THEN 0 ELSE 1 END AS churned,
        i.end_reason_code,
        i.end_posted_date,
        i.end_is_retro_term,
        (EXTRACT(YEAR FROM i.island_end_eff) - EXTRACT(YEAR FROM i.island_start)) * 12
          + EXTRACT(MONTH FROM i.island_end_eff) - EXTRACT(MONTH FROM i.island_start) + 1 AS covered_months,
        (2025 - EXTRACT(YEAR FROM i.island_start)) * 12
          + 12 - EXTRACT(MONTH FROM i.island_start) + 1 AS observable_months,
        CAST(CAST(EXTRACT(YEAR FROM i.island_start) AS INTEGER) * 100
             + CAST(EXTRACT(MONTH FROM i.island_start) AS INTEGER) AS INTEGER) AS cohort_yyyymm
    FROM marts.dim_member d
    JOIN first_island i ON i.member_id = d.member_id
)
SELECT
    b.member_id,
    b.enroll_date,
    b.cohort_yyyymm,
    b.plan_id,
    b.plan_type,
    b.county_fips,
    b.urban_rural,
    b.age,
    b.age_band,
    b.sex,
    b.dual_eligible_flag,
    b.lis_flag,
    b.channel,
    b.island_end_eff,
    b.churned,
    b.end_reason_code,
    b.end_posted_date,
    b.end_is_retro_term,
    CAST(b.covered_months AS INTEGER)    AS covered_months,
    CAST(b.observable_months AS INTEGER) AS observable_months,
    CASE WHEN b.covered_months >= 4 THEN 1 ELSE 0 END AS landmark_90d,
    CASE WHEN b.observable_months >= 12 THEN CASE WHEN b.covered_months >= 12 THEN 1 ELSE 0 END END AS retained_12m,
    o.welcome_attempts_90d,
    o.welcome_complete_90d,
    o.hra_complete_90d,
    o.pcp_visit_90d,
    o.pcp_visit_60d,
    o.portal_90d,
    o.day_pcp_first_visit,
    CASE WHEN o.day_pcp_first_visit IS NOT NULL THEN b.enroll_date + CAST(o.day_pcp_first_visit AS INTEGER) END AS pcp_first_visit_date
FROM base b
JOIN marts.fct_member_onboarding o ON o.member_id = b.member_id;
