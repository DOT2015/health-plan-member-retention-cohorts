-- Q6. Outreach workload: new members per enrollment month who are still enrolled at day 60
-- (covered_months >= 2) and have no PCP visit by day 60. This is the list an onboarding
-- outreach team would call in a given month.
SELECT
    cohort_yyyymm,
    COUNT(*) AS new_members,
    SUM(CASE WHEN covered_months >= 2 THEN 1 ELSE 0 END) AS enrolled_at_day_60,
    SUM(CASE WHEN covered_months >= 2 AND pcp_visit_60d = 0 THEN 1 ELSE 0 END) AS no_pcp_visit_by_day_60,
    SUM(CASE WHEN covered_months >= 2 AND pcp_visit_60d = 0 AND dual_eligible_flag = 1 THEN 1 ELSE 0 END) AS no_visit_dual,
    SUM(CASE WHEN covered_months >= 2 AND pcp_visit_60d = 0 AND channel = 'online' THEN 1 ELSE 0 END) AS no_visit_online
FROM marts.fct_member_retention
GROUP BY cohort_yyyymm
ORDER BY cohort_yyyymm;
