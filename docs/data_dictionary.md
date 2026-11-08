# Data dictionary

All tables are synthetic, produced by `src/generate_data.py` (seed 42). Raw CSVs land in `data/raw/` and load into DuckDB schema `raw` as text. Staging (`staging.*`) types and cleans them; marts (`marts.*`) hold the modeled tables.

## Time conventions

| Field | Time zone / format |
|---|---|
| `enroll_date`, `start_date`, `end_date`, `posted_date` | Calendar dates, no time zone. Coverage starts on the 1st and ends on the last day of a month. |
| `fact_onboarding_event.event_ts` (source_system = `vendor`) | UTC, `YYYY-MM-DD HH:MM:SS`, no offset in the string |
| `fact_onboarding_event.event_ts` (source_system = `CRM`) | US/Eastern local time with daylight saving, same format, no offset in the string |
| `staging.stg_onboarding_event.event_ts_utc` | UTC after conversion |
| Observation end | 2025-12-31. Open spans are censored there. |

## Raw tables

### dim_member (28,000 rows)
| Column | Description |
|---|---|
| member_id | `M######`, primary key |
| enroll_date | First day of the first coverage month (2023-01-01 to 2025-06-01). January is weighted ~3x (Annual Enrollment Period); later cohorts are larger (plan growth). |
| plan_id | Plan at enrollment, FK to dim_plan |
| county_fips | Synthetic 5-character code (`9xxxx`, not a real FIPS). **1.5% null (planted).** |
| age | 65-99, 65 + Gamma(2, 4.5) |
| sex | F (55%) / M |
| dual_eligible_flag | 1 = Medicare-Medicaid dual eligible (22%) |
| lis_flag | Low-income subsidy; 1 for all duals, 8% of non-duals |
| enrollment_channel | direct 35%, broker 30%, online 15%, agent 20%. **15% arrive as non-standard variants: 'Broker', 'BROKER', 'brkr', ' broker', 'Direct ', 'dir', 'web', 'On-line', 'agt', 'agent ' (planted).** |

### dim_plan (12 rows)
plan_id, plan_type (HMO x5, PPO x4, D-SNP x3), monthly_premium (USD), star_rating.

### dim_county (40 rows)
county_fips, county_name_synthetic, urban_rural (25 urban, 15 rural).

### dim_date (1,096 rows)
date (2023-01-01 to 2025-12-31), year, month, month_start, quarter, day_of_week (1 = Monday), is_oep_month (1 for January-March).

### fact_enrollment_span (~30,000 rows)
| Column | Description |
|---|---|
| span_id | `S#######`, primary key |
| member_id | FK |
| start_date / end_date | end_date null = active at 2025-12-31 |
| disenroll_reason_code | VOL_SWITCH, MOVED, DEATH, NONPAY, OTHER for terminations; PLAN_CHANGE when the member moved to another plan of the same organization (next span starts the next day); null for open spans |
| plan_id | Plan for the span |
| posted_date | When the record last changed. Normal terminations post 0-25 days before end_date. **2% of terminations are retro-terms posted 30-60 days after end_date (planted).** |

Planted extras: ~6% of members change plan on a 1 January (contiguous spans, not churn); 8% of leavers re-enroll after a 2-8 month gap (new span); **0.8% of members have an extra span that overlaps their first span (source error, planted).**

### fact_member_month (~480,000 rows)
member_id, month_start, plan_id, active_flag. A **month-end snapshot that is never restated**: members whose termination had not posted by month end still show `active_flag = 1` (planted). Includes up to two months after termination. Analyses rebuild member-months from coverage instead (`marts.fct_person_month`).

### fact_onboarding_event (~195,000 rows)
| Column | Description |
|---|---|
| event_id | `E#######` |
| member_id | FK |
| event_type | welcome_call_attempt, welcome_call_complete, hra_complete, pcp_assigned, pcp_first_visit, portal_registered |
| event_ts | See time conventions |
| source_system | `vendor` (welcome calls, HRA) or `CRM` (PCP assignment and visits, portal) |

Planted: **3% of events are duplicated into the other feed within 0-4 minutes** (with that feed's time zone). **0.3% of members have a pcp_first_visit dated 5-60 days before enrollment.** Events after a member's coverage ends are never generated.

## Generator model (planted signals)

- Funnel (first 90 days, each step conditional on the previous): welcome call complete 0.68; HRA 0.60 given welcome call (0.45 for online); first PCP visit 0.85 given HRA, 0.15 without; dual members' PCP probabilities x0.8.
- Plan type: P(D-SNP) = 0.20 for non-duals, 0.32 for duals (1.6x).
- Monthly disenrollment hazard = 0.012 x 2.0 (Jan-Mar) x 1.90 (dual) x channel (broker 1.25, online 1.10, agent 1.00, direct 1.00) x 0.55 (from the first month that starts after a PCP visit within 90 days). Plan type and age have no effect.
- About 40% of members without a 90-day visit have a later first visit (days 91-365); it does not change the hazard.
- Realized values are in `data/truth/planted_effects.json`.

## Staging and mart tables

| Table | Grain | Notes |
|---|---|---|
| staging.stg_member | member | `channel` (4 clean codes), `channel_raw`, `county_fips` ('UNKNOWN' for null), `age_band`, flags `county_was_null`, `channel_was_nonstandard` |
| staging.stg_enrollment_span | span | typed; flags `is_retro_term`, `overlaps_prior` |
| staging.stg_onboarding_event | event | `event_ts_utc`; flags `is_cross_feed_duplicate`, `is_before_enrollment` |
| marts.dim_member | member | stg_member + plan_type + urban_rural |
| marts.int_coverage_island | member x island | contiguous/overlapping spans merged |
| marts.fct_member_onboarding | member | first-day-of-step and 60/90-day flags, from clean events |
| marts.fct_member_retention | member | first island: covered_months, churned, landmark_90d, retained_12m, onboarding flags |
| marts.fct_person_month | member x month | covered months of the first island; `disenrolled`, time-varying `pcp_visited`, `is_oep_month` |
