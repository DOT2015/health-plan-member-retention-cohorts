# Methodology

All data is synthetic (`src/generate_data.py`, seed 42). Numbers quoted in the README come from `reports/results.json`; this file describes definitions, methods, and assumptions.

## Metric definitions

| Metric | Definition |
|---|---|
| Continuous coverage (island) | Enrollment spans for a member merged when they overlap or touch (next start = prior end + 1 day). A gap of one or more days starts a new island. |
| Disenrollment (churn) | End of the member's **first** island on or before 2025-12-31. Plan changes inside the organization are not churn. A member who leaves and later re-enrolls counts as churned at the first exit. Deaths count as churn in this simulation. |
| covered_months (T) | Calendar months in the first island, counting the enrollment month as 1. |
| k-month retention | P(T >= k): share of members who completed k months of continuous enrollment. 12-month retention = P(T >= 12). |
| Censoring | Members still enrolled on 2025-12-31 are censored at their observed T. |
| Landmark population | Members enrolled at the start of coverage month 4 (about day 90): T >= 4. |
| PCP visit within 90 days | A de-duplicated, post-enrollment `pcp_first_visit` event on days 0-89 after enroll_date. |
| Funnel steps | Welcome call complete, HRA complete, first PCP visit, each within 90 days; measured on the landmark population so everyone had 90 days to complete them. |
| Monthly disenrollment rate | Disenrollments effective in the month / members enrolled at the start of the month. The snapshot variant only counts terminations posted by month end. |
| Outreach workload | New members still enrolled at day 60 with no PCP visit by day 60, per enrollment month. |

## Why a landmark design

A member who leaves in month 1 cannot have a PCP visit in month 2. Comparing "visited within 90 days" vs. "did not" across all members would credit the visit group with survival they had to have to visit (immortal-time bias). The analysis measures exposure in days 0-89 and starts follow-up at day 90, only for members enrolled at that point. The Poisson model takes the other route: it codes the visit as a time-varying exposure from the first month that starts after the visit.

## Methods

1. **Kaplan-Meier** (discrete monthly times), implemented in `src/analysis.py`. Greenwood variance with a log(-log) 95% CI.
2. **Log-rank test** for visit vs. no visit, months 4-11, overall and within dual strata.
3. **Cox proportional hazards** (`statsmodels` PHReg, Efron ties) on the landmark population, follow-up to month 12. Stratified by enrollment cohort month, so the baseline hazard absorbs calendar seasonality (calendar month = cohort + months since enrollment). Three models: visit only (unadjusted), visit + dual, and visit + dual + channel + plan type + age band (adjusted). The planted confounder is dual status: duals are less likely to visit and more likely to leave.
4. **Proportional-hazards check:** correlation between the Schoenfeld residuals for the visit term and the rank of event time.
5. **Poisson GLM on person-months** (log link): disenrolled ~ OEP month + dual + channel + time-varying PCP visit. With monthly hazards near 1%, the rate ratios approximate the generator's hazard multipliers, so every planted parameter can be checked.
6. **Small-cell rule:** segment cells with fewer than 30 members show counts but no rate.

## Sizing

- Workload: average monthly outreach list for 2024 enrollment cohorts (SQL file 06).
- Staffing: 3 call attempts x 15 minutes per member; 120 productive hours per FTE-month; simulated loaded cost of $65,000 per FTE-year. All are assumptions in `src/config.py`.
- Benefit: a 10 pp rise in the 90-day PCP-visit rate across one year of new members (2024 enrollments, scaled by the share still enrolled at day 90). For each converted member, retention in months 4-12 moves from the no-visit KM curve S0(k) to S0(k)^HR, with HR the adjusted Cox estimate. Member-months gained = sum over k of S0(k)^HR - S0(k). The 24-month view extends the no-visit KM curve to month 24 and assumes the HR persists.
- Revenue: simulated $1,000 per member-month. This is revenue, not margin.
- Causal share: 25%, 50%, 100% of the association treated as causal. Break-even share = staff cost / revenue at 100%.
- Pilot power: two-proportion test, alpha 0.05 two-sided, power 0.80 (`statsmodels` NormalIndPower with Cohen's h). Two outcomes: the 90-day visit rate among members without a visit by day 60, and 12-month churn.

## Limitations

- Synthetic data with a known, simple data-generating process. Real retention has more causes (provider network, premiums, benefits, marketing) than this simulation includes.
- Unmeasured confounding can remain after adjustment; the pilot exists to address it.
- Deaths are not separated as a competing risk.
- The 12-month horizon and the first-island definition are choices; a plan that counts re-enrollment as retained would get different numbers.
- Sizing ignores medical cost, risk-adjusted revenue, Star-rating effects, and ramp-up time for new staff.
