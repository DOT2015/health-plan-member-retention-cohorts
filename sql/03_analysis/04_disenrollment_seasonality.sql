-- Q4. Monthly disenrollment rate: effective-date view vs. month-end snapshot view.
-- effective_disenrollments : first-island terminations whose effective end falls in the month.
-- snapshot_disenrollments  : the same terminations, counted only if posted by the month-end
--                            snapshot (posted_date <= last day of the month). Retro-terms
--                            (posted 30-60 days late) are missing from the snapshot.
-- rate = disenrollments / members enrolled at the start of the month.
WITH active AS (
    SELECT month_start, MAX(is_oep_month) AS is_oep_month, COUNT(*) AS members_at_start,
           SUM(disenrolled) AS effective_disenrollments
    FROM marts.fct_person_month
    GROUP BY month_start
),
snap AS (
    SELECT
        CAST(DATE_TRUNC('month', island_end_eff) AS DATE) AS month_start,
        SUM(CASE WHEN end_posted_date <= island_end_eff THEN 1 ELSE 0 END) AS snapshot_disenrollments,
        SUM(end_is_retro_term) AS retro_terms
    FROM marts.fct_member_retention
    WHERE churned = 1
    GROUP BY CAST(DATE_TRUNC('month', island_end_eff) AS DATE)
)
SELECT
    a.month_start,
    a.is_oep_month,
    a.members_at_start,
    a.effective_disenrollments,
    COALESCE(s.snapshot_disenrollments, 0) AS snapshot_disenrollments,
    COALESCE(s.retro_terms, 0)             AS retro_terms,
    ROUND(100.0 * a.effective_disenrollments / a.members_at_start, 3)            AS effective_rate_pct,
    ROUND(100.0 * COALESCE(s.snapshot_disenrollments, 0) / a.members_at_start, 3) AS snapshot_rate_pct
FROM active a
LEFT JOIN snap s ON s.month_start = a.month_start
ORDER BY a.month_start;
