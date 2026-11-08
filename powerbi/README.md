# Power BI model

`make all` (or `python src/export_powerbi.py`) writes these CSVs. They are committed so the model can be built without running Python. All data is synthetic.

## Tables

| File | Role | Grain | Key |
|---|---|---|---|
| dim_member.csv | Dimension | member | member_id |
| dim_plan.csv | Dimension | plan | plan_id |
| dim_county.csv | Dimension | county | county_fips |
| dim_month.csv | Dimension (date) | month | month_start |
| fact_member_retention.csv | Fact | member (first coverage island) | member_id |
| fact_monthly_disenrollment.csv | Fact | calendar month | month_start |
| fact_cohort_retention.csv | Fact (pre-aggregated) | cohort x months completed | cohort_yyyymm, months_since_enroll |

## Relationships (all single-direction, many-to-one)

- fact_member_retention[member_id] -> dim_member[member_id] (one-to-one; set cross-filter to single)
- dim_member[plan_id] -> dim_plan[plan_id]
- dim_member[county_fips] -> dim_county[county_fips]
- fact_monthly_disenrollment[month_start] -> dim_month[month_start]

Mark `dim_month` as the date table.

## Measures (DAX)

```DAX
Members = COUNTROWS ( fact_member_retention )

Landmark Members = CALCULATE ( [Members], fact_member_retention[landmark_90d] = 1 )

12-Month Retention % =
DIVIDE (
    CALCULATE ( SUM ( fact_member_retention[retained_12m] ), fact_member_retention[landmark_90d] = 1 ),
    CALCULATE ( COUNT ( fact_member_retention[retained_12m] ), fact_member_retention[landmark_90d] = 1 )
)

PCP Visit 90d % =
DIVIDE ( CALCULATE ( SUM ( fact_member_retention[pcp_visit_90d] ) ), [Landmark Members] )
    -- apply with a landmark_90d = 1 page filter

HRA 90d % = DIVIDE ( SUM ( fact_member_retention[hra_complete_90d] ), [Members] )

Disenrollment Rate % =
DIVIDE ( SUM ( fact_monthly_disenrollment[effective_disenrollments] ),
         SUM ( fact_monthly_disenrollment[members_at_start] ) )

Snapshot Undercount % =
1 - DIVIDE ( SUM ( fact_monthly_disenrollment[snapshot_disenrollments] ),
             SUM ( fact_monthly_disenrollment[effective_disenrollments] ) )

Small Cell Flag = IF ( [Members] < 30, "suppressed", "shown" )
```

`retained_12m` is blank when 12 months were not observable, so COUNT (not COUNTROWS) gives the correct denominator.

## Suggested pages

1. Cohort retention: matrix visual on fact_cohort_retention (rows cohort_yyyymm, columns months_since_enroll, values retention_pct) with conditional formatting.
2. Onboarding funnel: clustered bar of welcome/HRA/PCP rates by dim_member[channel], page filter landmark_90d = 1.
3. Disenrollment trend: line chart of Disenrollment Rate % by month, with is_oep_month as a legend or background band; table of 12-Month Retention % by channel x plan_type x dual with Small Cell Flag.
