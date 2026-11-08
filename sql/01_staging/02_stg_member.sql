-- Staging: members.
-- Fixes: (1) enrollment_channel arrives in mixed case, with stray spaces and
-- abbreviations ('Broker', 'BROKER', 'brkr', 'Direct ', 'web'); mapped to four codes.
-- (2) 1.5% of county_fips are null; mapped to 'UNKNOWN' and kept (not dropped).
DROP TABLE IF EXISTS staging.stg_member;
CREATE TABLE staging.stg_member AS
WITH typed AS (
    SELECT
        member_id,
        CAST(enroll_date AS DATE)          AS enroll_date,
        plan_id,
        county_fips                        AS county_fips_raw,
        CAST(age AS INTEGER)               AS age,
        sex,
        CAST(dual_eligible_flag AS INTEGER) AS dual_eligible_flag,
        CAST(lis_flag AS INTEGER)          AS lis_flag,
        enrollment_channel                 AS channel_raw,
        LOWER(TRIM(REPLACE(enrollment_channel, '-', ''))) AS channel_key
    FROM raw.dim_member
)
SELECT
    member_id,
    enroll_date,
    plan_id,
    COALESCE(NULLIF(TRIM(county_fips_raw), ''), 'UNKNOWN') AS county_fips,
    CASE WHEN county_fips_raw IS NULL OR TRIM(county_fips_raw) = '' THEN 1 ELSE 0 END AS county_was_null,
    age,
    CASE
        WHEN age < 70 THEN '65-69'
        WHEN age < 75 THEN '70-74'
        WHEN age < 80 THEN '75-79'
        WHEN age < 85 THEN '80-84'
        ELSE '85+'
    END AS age_band,
    sex,
    dual_eligible_flag,
    lis_flag,
    channel_raw,
    CASE
        WHEN channel_key IN ('direct', 'dir')           THEN 'direct'
        WHEN channel_key IN ('broker', 'brkr')          THEN 'broker'
        WHEN channel_key IN ('online', 'web')           THEN 'online'
        WHEN channel_key IN ('agent', 'agt')            THEN 'agent'
        ELSE 'unknown'
    END AS channel,
    CASE WHEN channel_raw IN ('direct', 'broker', 'online', 'agent') THEN 0 ELSE 1 END AS channel_was_nonstandard
FROM typed;
