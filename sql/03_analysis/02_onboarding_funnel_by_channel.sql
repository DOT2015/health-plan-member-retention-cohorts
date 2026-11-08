-- Q2. Onboarding funnel within 90 days, by enrollment channel.
-- Population: members still enrolled at day ~90 (landmark_90d = 1, enrolled at day ~90), so every member had the
-- full 90 days to complete each step. Step conversion = this step / previous step.
-- The funnel is ordered welcome call -> HRA -> first PCP visit. A PCP visit can happen
-- without an HRA, so "pcp_after_hra" isolates the in-sequence path.
SELECT
    channel,
    COUNT(*)                                       AS members,
    SUM(welcome_complete_90d)                      AS welcome_complete,
    SUM(CASE WHEN welcome_complete_90d = 1 AND hra_complete_90d = 1 THEN 1 ELSE 0 END) AS hra_complete,
    SUM(CASE WHEN hra_complete_90d = 1 AND pcp_visit_90d = 1 THEN 1 ELSE 0 END)        AS pcp_after_hra,
    SUM(pcp_visit_90d)                             AS pcp_visit_any,
    ROUND(100.0 * SUM(welcome_complete_90d) / COUNT(*), 2) AS pct_welcome,
    ROUND(100.0 * SUM(CASE WHEN welcome_complete_90d = 1 AND hra_complete_90d = 1 THEN 1 ELSE 0 END)
          / NULLIF(SUM(welcome_complete_90d), 0), 2)                                   AS step_hra_given_welcome,
    ROUND(100.0 * SUM(CASE WHEN hra_complete_90d = 1 AND pcp_visit_90d = 1 THEN 1 ELSE 0 END)
          / NULLIF(SUM(hra_complete_90d), 0), 2)                                       AS step_pcp_given_hra,
    ROUND(100.0 * SUM(hra_complete_90d) / COUNT(*), 2)     AS pct_hra_all,
    ROUND(100.0 * SUM(pcp_visit_90d) / COUNT(*), 2)        AS pct_pcp_all
FROM marts.fct_member_retention
WHERE landmark_90d = 1
GROUP BY channel
UNION ALL
SELECT
    'all',
    COUNT(*),
    SUM(welcome_complete_90d),
    SUM(CASE WHEN welcome_complete_90d = 1 AND hra_complete_90d = 1 THEN 1 ELSE 0 END),
    SUM(CASE WHEN hra_complete_90d = 1 AND pcp_visit_90d = 1 THEN 1 ELSE 0 END),
    SUM(pcp_visit_90d),
    ROUND(100.0 * SUM(welcome_complete_90d) / COUNT(*), 2),
    ROUND(100.0 * SUM(CASE WHEN welcome_complete_90d = 1 AND hra_complete_90d = 1 THEN 1 ELSE 0 END)
          / NULLIF(SUM(welcome_complete_90d), 0), 2),
    ROUND(100.0 * SUM(CASE WHEN hra_complete_90d = 1 AND pcp_visit_90d = 1 THEN 1 ELSE 0 END)
          / NULLIF(SUM(hra_complete_90d), 0), 2),
    ROUND(100.0 * SUM(hra_complete_90d) / COUNT(*), 2),
    ROUND(100.0 * SUM(pcp_visit_90d) / COUNT(*), 2)
FROM marts.fct_member_retention
WHERE landmark_90d = 1
ORDER BY channel;
