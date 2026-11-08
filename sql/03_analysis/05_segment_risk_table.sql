-- Q5. 12-month retention by channel x plan type x dual status.
-- Population: landmark members with 12 observable months (same as Q3).
-- Small-cell rule: cells with fewer than 30 members show counts but a NULL rate.
SELECT
    channel,
    plan_type,
    CASE WHEN dual_eligible_flag = 1 THEN 'dual' ELSE 'non-dual' END AS dual_status,
    COUNT(*)                         AS members,
    SUM(retained_12m)                AS retained_12m,
    SUM(1 - pcp_visit_90d)           AS no_pcp_visit_90d,
    CASE WHEN COUNT(*) >= 30 THEN ROUND(100.0 * SUM(retained_12m) / COUNT(*), 2) END AS retention_12m_pct,
    CASE WHEN COUNT(*) >= 30 THEN ROUND(100.0 * SUM(pcp_visit_90d) / COUNT(*), 2) END AS pcp_visit_90d_pct,
    CASE WHEN COUNT(*) < 30 THEN 1 ELSE 0 END AS suppressed
FROM marts.fct_member_retention
WHERE landmark_90d = 1 AND retained_12m IS NOT NULL
GROUP BY channel, plan_type, dual_eligible_flag
ORDER BY retention_12m_pct NULLS LAST, members DESC;
