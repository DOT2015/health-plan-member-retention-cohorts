-- Mart: one row per member with first-90-day onboarding milestones.
-- Uses de-duplicated, UTC-normalized events; drops events dated before enrollment.
DROP TABLE IF EXISTS marts.fct_member_onboarding;
CREATE TABLE marts.fct_member_onboarding AS
WITH ev AS (
    SELECT e.member_id, e.event_type, e.event_date_utc, m.enroll_date,
           e.event_date_utc - m.enroll_date AS day_n
    FROM staging.stg_onboarding_event e
    JOIN staging.stg_member m ON m.member_id = e.member_id
    WHERE e.is_cross_feed_duplicate = 0
      AND e.is_before_enrollment = 0
),
firsts AS (
    SELECT
        member_id,
        COUNT(CASE WHEN event_type = 'welcome_call_attempt' AND day_n < 90 THEN 1 END) AS welcome_attempts_90d,
        MIN(CASE WHEN event_type = 'welcome_call_complete' THEN day_n END) AS day_welcome_complete,
        MIN(CASE WHEN event_type = 'hra_complete'          THEN day_n END) AS day_hra_complete,
        MIN(CASE WHEN event_type = 'pcp_assigned'          THEN day_n END) AS day_pcp_assigned,
        MIN(CASE WHEN event_type = 'pcp_first_visit'       THEN day_n END) AS day_pcp_first_visit,
        MIN(CASE WHEN event_type = 'portal_registered'     THEN day_n END) AS day_portal_registered
    FROM ev
    GROUP BY member_id
)
SELECT
    m.member_id,
    COALESCE(f.welcome_attempts_90d, 0) AS welcome_attempts_90d,
    f.day_welcome_complete,
    f.day_hra_complete,
    f.day_pcp_assigned,
    f.day_pcp_first_visit,
    f.day_portal_registered,
    CASE WHEN f.day_welcome_complete < 90 THEN 1 ELSE 0 END AS welcome_complete_90d,
    CASE WHEN f.day_hra_complete     < 90 THEN 1 ELSE 0 END AS hra_complete_90d,
    CASE WHEN f.day_pcp_first_visit  < 90 THEN 1 ELSE 0 END AS pcp_visit_90d,
    CASE WHEN f.day_pcp_first_visit  < 60 THEN 1 ELSE 0 END AS pcp_visit_60d,
    CASE WHEN f.day_portal_registered < 90 THEN 1 ELSE 0 END AS portal_90d
FROM staging.stg_member m
LEFT JOIN firsts f ON f.member_id = m.member_id;
