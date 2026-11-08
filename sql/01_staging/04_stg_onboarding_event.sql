-- Staging: onboarding events.
-- Fixes:
--   (1) Time zones. vendor feed timestamps are UTC; CRM feed timestamps are US/Eastern local
--       (with DST). Both are converted to UTC. `ts AT TIME ZONE 'America/New_York'` reads a
--       naive timestamp as Eastern local time and returns a timestamptz; `AT TIME ZONE 'UTC'`
--       turns that back into a naive UTC timestamp. Same semantics in PostgreSQL.
--   (2) Cross-feed duplicates. The same event can arrive from both feeds within 5 minutes.
--       After UTC conversion, a row is a duplicate when the previous row for the same member
--       and event type came from the other feed no more than 5 minutes earlier.
--   (3) pcp_first_visit dated before enroll_date (visit under prior coverage): flagged and
--       excluded downstream.
DROP TABLE IF EXISTS staging.stg_onboarding_event;
CREATE TABLE staging.stg_onboarding_event AS
WITH typed AS (
    SELECT
        e.event_id,
        e.member_id,
        e.event_type,
        e.source_system,
        CAST(e.event_ts AS TIMESTAMP) AS event_ts_raw,
        CASE
            WHEN e.source_system = 'CRM'
                THEN CAST((CAST(e.event_ts AS TIMESTAMP) AT TIME ZONE 'America/New_York') AT TIME ZONE 'UTC' AS TIMESTAMP)
            ELSE CAST(e.event_ts AS TIMESTAMP)
        END AS event_ts_utc
    FROM raw.fact_onboarding_event e
),
ordered AS (
    SELECT
        t.*,
        LAG(event_ts_utc)  OVER w AS prev_ts_utc,
        LAG(source_system) OVER w AS prev_source
    FROM typed t
    WINDOW w AS (PARTITION BY member_id, event_type ORDER BY event_ts_utc, event_id)
)
SELECT
    o.event_id,
    o.member_id,
    o.event_type,
    o.source_system,
    o.event_ts_raw,
    o.event_ts_utc,
    CAST(o.event_ts_utc AS DATE) AS event_date_utc,
    CASE
        WHEN o.prev_ts_utc IS NOT NULL
         AND o.prev_source <> o.source_system
         AND o.event_ts_utc - o.prev_ts_utc <= INTERVAL '5 minutes'
        THEN 1 ELSE 0
    END AS is_cross_feed_duplicate,
    CASE WHEN CAST(o.event_ts_utc AS DATE) < m.enroll_date THEN 1 ELSE 0 END AS is_before_enrollment
FROM ordered o
JOIN staging.stg_member m ON m.member_id = o.member_id;
