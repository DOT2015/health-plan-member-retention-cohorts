-- Q3. 12-month retention by first PCP visit within 90 days, stratified by dual status.
-- Population: landmark members (enrolled at day ~90) whose cohort has 12 observable months
-- (enrolled 2023-01 through 2025-01). Raw rates; the confounding by dual status is handled
-- in src/analysis.py (Cox model). The 'all' rows show the crude, unstratified gap.
WITH pop AS (
    SELECT * FROM marts.fct_member_retention
    WHERE landmark_90d = 1 AND retained_12m IS NOT NULL
)
SELECT
    CASE WHEN dual_eligible_flag = 1 THEN 'dual' ELSE 'non-dual' END AS dual_status,
    pcp_visit_90d,
    COUNT(*)                                   AS members,
    SUM(retained_12m)                          AS retained_12m,
    ROUND(100.0 * SUM(retained_12m) / COUNT(*), 2) AS retention_12m_pct
FROM pop
GROUP BY dual_eligible_flag, pcp_visit_90d
UNION ALL
SELECT 'all', pcp_visit_90d, COUNT(*), SUM(retained_12m), ROUND(100.0 * SUM(retained_12m) / COUNT(*), 2)
FROM pop
GROUP BY pcp_visit_90d
ORDER BY dual_status, pcp_visit_90d;
