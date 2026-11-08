"""Survival and regression analysis, sizing, and validation against planted values.

Reads marts from DuckDB and SQL outputs from data/outputs/, writes reports/results.json.
Kaplan-Meier and the log-rank test are implemented here (no lifelines dependency);
the Cox model uses statsmodels PHReg.
"""
import json

import duckdb
import numpy as np
import pandas as pd
import statsmodels.api as sm
import statsmodels.formula.api as smf
from scipy import stats
from statsmodels.duration.hazard_regression import PHReg

import config as C

HORIZON = 12   # months since enrollment
LANDMARK = 4   # landmark population: enrolled at the start of coverage month 4 (day ~90), i.e. covered_months >= 4


# ----------------------------------------------------------------------------- KM
def kaplan_meier(T, E, start=0, horizon=HORIZON):
    """Discrete monthly Kaplan-Meier.

    T = covered months (enrollment month = month 1 of coverage); E = 1 if the member
    disenrolled after T months, 0 if censored (still enrolled on 2025-12-31).
    retention_k = P(T >= k), "completed k months of enrollment", conditional on T >= start.
    A disenrollment after exactly j months is an event at time j; it lowers retention_{j+1}.
    Returns k = start..horizon with Greenwood log(-log) 95% CI.
    """
    T = np.asarray(T)
    E = np.asarray(E)
    rows = [{"month": start, "retention": 1.0, "lo": 1.0, "hi": 1.0, "at_risk": int((T >= start).sum()), "events": 0}]
    s, gw = 1.0, 0.0
    for j in range(start, horizon):
        n = int((T >= j).sum())
        d = int(((T == j) & (E == 1)).sum()) if j > 0 else 0
        if n > 0:
            s *= 1 - d / n
            if n > d:
                gw += d / (n * (n - d))
        if 0 < s < 1:
            se = np.sqrt(gw) / abs(np.log(s))
            lo, hi = s ** np.exp(1.96 * se), s ** np.exp(-1.96 * se)
        else:
            lo = hi = s
        rows.append({"month": j + 1, "retention": s, "lo": lo, "hi": hi, "at_risk": n, "events": d})
    return pd.DataFrame(rows)


def logrank(T, E, g, start=0, horizon=HORIZON):
    """Two-group log-rank test on monthly event times start..horizon-1 (same events as the KM)."""
    T, E, g = map(np.asarray, (T, E, g))
    o_minus_e, var = 0.0, 0.0
    for j in range(max(start, 1), horizon):
        at = T >= j
        ev = (T == j) & (E == 1)
        n, d = at.sum(), ev.sum()
        n1, d1 = (at & (g == 1)).sum(), (ev & (g == 1)).sum()
        if n < 2 or d == 0:
            continue
        o_minus_e += d1 - d * n1 / n
        var += d * (n1 / n) * (1 - n1 / n) * (n - d) / (n - 1)
    chi2 = o_minus_e ** 2 / var
    return float(chi2), float(stats.chi2.sf(chi2, 1))


# ----------------------------------------------------------------------------- Cox
def cox(df, formula_terms, strata="cohort_yyyymm"):
    X = pd.get_dummies(df[formula_terms], drop_first=True, dtype=float)
    model = PHReg(df["time"].values, X, status=df["status"].values,
                  strata=df[strata].values, ties="efron")
    res = model.fit()
    out = pd.DataFrame({"term": X.columns, "coef": res.params, "se": res.bse})
    out["hr"] = np.exp(out.coef)
    out["lo"] = np.exp(out.coef - 1.96 * out.se)
    out["hi"] = np.exp(out.coef + 1.96 * out.se)
    out["p"] = res.pvalues
    return res, out.reset_index(drop=True), X


def ph_check(res, X, df, term):
    """Correlation of scaled Schoenfeld residuals with event-time rank (Grambsch-Therneau style)."""
    sr = res.schoenfeld_residuals
    col = list(X.columns).index(term)
    mask = ~np.isnan(sr[:, col])
    r, p = stats.pearsonr(stats.rankdata(df["time"].values[mask]), sr[mask, col])
    return float(r), float(p)


def main():
    con = duckdb.connect(str(C.DB), read_only=True)
    ret = con.execute("SELECT * FROM marts.fct_member_retention").fetchdf()
    pm = con.execute("SELECT * FROM marts.fct_person_month").fetchdf()
    dq = {
        "duplicate_events_removed": con.execute(
            "SELECT SUM(is_cross_feed_duplicate) FROM staging.stg_onboarding_event").fetchone()[0],
        "retro_terminations": con.execute(
            "SELECT SUM(is_retro_term) FROM staging.stg_enrollment_span").fetchone()[0],
        "members_with_overlapping_spans": con.execute(
            "SELECT COUNT(DISTINCT member_id) FROM staging.stg_enrollment_span WHERE overlaps_prior = 1").fetchone()[0],
        "null_county_fips": con.execute("SELECT SUM(county_was_null) FROM staging.stg_member").fetchone()[0],
        "members_pcp_visit_before_enroll": con.execute(
            "SELECT COUNT(DISTINCT member_id) FROM staging.stg_onboarding_event "
            "WHERE is_before_enrollment = 1 AND event_type = 'pcp_first_visit'").fetchone()[0],
        "nonstandard_channel_codes": con.execute(
            "SELECT SUM(channel_was_nonstandard) FROM staging.stg_member").fetchone()[0],
        "unmapped_channel_codes": con.execute(
            "SELECT COUNT(*) FROM staging.stg_member WHERE channel = 'unknown'").fetchone()[0],
        "plan_change_spans_merged": con.execute(
            "SELECT COUNT(*) FROM staging.stg_enrollment_span WHERE disenroll_reason_code = 'PLAN_CHANGE'").fetchone()[0],
        "raw_member_month_rows": con.execute("SELECT COUNT(*) FROM raw.fact_member_month").fetchone()[0],
        "raw_member_month_active_after_term": con.execute("""
            SELECT COUNT(*) FROM raw.fact_member_month mm
            JOIN marts.fct_member_retention r ON r.member_id = mm.member_id
            WHERE r.churned = 1 AND CAST(mm.active_flag AS INTEGER) = 1
              AND CAST(mm.month_start AS DATE) > r.island_end_eff""").fetchone()[0],
        "raw_onboarding_events": con.execute("SELECT COUNT(*) FROM raw.fact_onboarding_event").fetchone()[0],
        "raw_enrollment_spans": con.execute("SELECT COUNT(*) FROM raw.fact_enrollment_span").fetchone()[0],
    }
    dq = {k: int(v) for k, v in dq.items()}
    con.close()
    truth = json.loads(C.TRUTH.read_text())
    out = {"data_quality": dq}

    # ------------------------------------------------------------- overall retention
    coh = ret[(ret.cohort_yyyymm >= 202401) & (ret.cohort_yyyymm <= 202406)]
    km_all = kaplan_meier(coh.covered_months, coh.churned)
    out["retention_12m_jan_jun_2024"] = float(km_all.loc[km_all.month == 12, "retention"].iloc[0])
    km_full = kaplan_meier(ret.covered_months, ret.churned)
    r12 = km_full.loc[km_full.month == 12].iloc[0]
    out["retention_12m_all_km"] = {"est": float(r12.retention), "lo": float(r12.lo), "hi": float(r12.hi)}
    out["n_members"] = int(len(ret))
    out["n_disenrolled_first_island"] = int(ret.churned.sum())

    # ------------------------------------------------------------- landmark KM by PCP x dual
    lm = ret[ret.landmark_90d == 1].copy()
    out["n_landmark"] = int(len(lm))
    km_curves = []
    km_summary = {}
    for dual in [0, 1]:
        for pcp in [0, 1]:
            sub = lm[(lm.dual_eligible_flag == dual) & (lm.pcp_visit_90d == pcp)]
            k = kaplan_meier(sub.covered_months, sub.churned, start=LANDMARK)
            k["dual"] = dual
            k["pcp_visit_90d"] = pcp
            km_curves.append(k)
            row = k.loc[k.month == 12].iloc[0]
            km_summary[f"dual{dual}_pcp{pcp}"] = {"n": int(len(sub)), "ret12": float(row.retention),
                                                   "lo": float(row.lo), "hi": float(row.hi)}
    km_curves = pd.concat(km_curves)
    C.OUTPUTS.mkdir(exist_ok=True, parents=True)
    km_curves.to_csv(C.OUTPUTS / "km_curves_landmark.csv", index=False)
    out["km_landmark_12m"] = km_summary
    for pcp in [0, 1]:
        sub = lm[lm.pcp_visit_90d == pcp]
        k = kaplan_meier(sub.covered_months, sub.churned, start=LANDMARK)
        km_summary[f"all_pcp{pcp}"] = {"n": int(len(sub)), "ret12": float(k.retention.iloc[-1]),
                                        "lo": float(k.lo.iloc[-1]), "hi": float(k.hi.iloc[-1])}
    chi2, p = logrank(lm.covered_months, lm.churned, lm.pcp_visit_90d, start=LANDMARK)
    out["logrank_pcp"] = {"chi2": chi2, "p": p}
    for dual in [0, 1]:
        sub = lm[lm.dual_eligible_flag == dual]
        c2, pp = logrank(sub.covered_months, sub.churned, sub.pcp_visit_90d, start=LANDMARK)
        out[f"logrank_pcp_dual{dual}"] = {"chi2": c2, "p": pp}

    # ------------------------------------------------------------- Cox (landmark, 12-month horizon)
    cx = lm.copy()
    # time since landmark; events are disenrollments after 3..11 covered months (the ones that
    # break 12-month retention); everyone else is censored at the 12-month horizon.
    cx["time"] = np.minimum(cx.covered_months, HORIZON) - LANDMARK + 1
    cx["status"] = ((cx.churned == 1) & (cx.covered_months < HORIZON)).astype(int)
    cx["channel"] = pd.Categorical(cx.channel, ["direct", "agent", "broker", "online"])
    cx["plan_type"] = pd.Categorical(cx.plan_type, ["HMO", "PPO", "D-SNP"])
    cx["age_band"] = pd.Categorical(cx.age_band, ["65-69", "70-74", "75-79", "80-84", "85+"])
    res_u, tab_u, _ = cox(cx, ["pcp_visit_90d"])
    res_d, tab_d, _ = cox(cx, ["pcp_visit_90d", "dual_eligible_flag"])
    res_a, tab_a, Xa = cox(cx, ["pcp_visit_90d", "dual_eligible_flag", "channel", "plan_type", "age_band"])
    pick = lambda t, term: {k: float(t.loc[t.term == term, k].iloc[0]) for k in ["hr", "lo", "hi", "p"]}
    out["cox_unadjusted_pcp"] = pick(tab_u, "pcp_visit_90d")
    out["cox_dual_only_pcp"] = pick(tab_d, "pcp_visit_90d")
    out["cox_adjusted"] = {r.term: {"hr": r.hr, "lo": r.lo, "hi": r.hi, "p": r.p} for r in tab_a.itertuples()}
    out["cox_adjusted_pcp"] = pick(tab_a, "pcp_visit_90d")
    r_ph, p_ph = ph_check(res_a, Xa, cx, "pcp_visit_90d")
    out["ph_check_pcp"] = {"schoenfeld_time_corr": r_ph, "p": p_ph}
    out["cox_n"] = int(len(cx))
    out["cox_events"] = int(cx.status.sum())
    tab_a.to_csv(C.OUTPUTS / "cox_adjusted.csv", index=False)

    # ------------------------------------------------------------- Poisson GLM on person-months
    pm["channel"] = pd.Categorical(pm.channel, ["direct", "agent", "broker", "online"])
    glm = smf.glm("disenrolled ~ is_oep_month + dual_eligible_flag + channel + pcp_visited",
                  data=pm, family=sm.families.Poisson()).fit()
    ci = glm.conf_int()
    rr = {}
    for term in glm.params.index:
        rr[term] = {"rr": float(np.exp(glm.params[term])), "lo": float(np.exp(ci.loc[term, 0])),
                    "hi": float(np.exp(ci.loc[term, 1]))}
    out["poisson_rate_ratios"] = rr
    out["person_months"] = int(len(pm))
    glm_u = smf.glm("disenrolled ~ pcp_visited", data=pm, family=sm.families.Poisson()).fit()
    out["poisson_unadjusted_pcp_rr"] = float(np.exp(glm_u.params["pcp_visited"]))

    # ------------------------------------------------------------- funnel and seasonality from SQL outputs
    fun = pd.read_csv(C.OUTPUTS / "02_onboarding_funnel_by_channel.csv").set_index("channel")
    out["funnel"] = {ch: {k: float(fun.loc[ch, k]) for k in
                          ["members", "pct_welcome", "step_hra_given_welcome", "step_pcp_given_hra",
                           "pct_hra_all", "pct_pcp_all"]} for ch in fun.index}
    # funnel recovered on the generator's scale (step probabilities)
    lmf = lm.copy()
    out["funnel_recovered"] = {
        "welcome_complete_rate": float(lmf.welcome_complete_90d.mean()),
        "hra_rate": float(lmf.hra_complete_90d.mean()),
        "hra_rate_online": float(lmf.loc[lmf.channel == "online", "hra_complete_90d"].mean()),
        "hra_rate_non_online": float(lmf.loc[lmf.channel != "online", "hra_complete_90d"].mean()),
        "pcp90_rate": float(lmf.pcp_visit_90d.mean()),
        "pcp90_given_hra": float(lmf.loc[lmf.hra_complete_90d == 1, "pcp_visit_90d"].mean()),
        "pcp90_given_no_hra": float(lmf.loc[lmf.hra_complete_90d == 0, "pcp_visit_90d"].mean()),
    }
    sea = pd.read_csv(C.OUTPUTS / "04_disenrollment_seasonality.csv", parse_dates=["month_start"])
    s2 = sea[sea.month_start >= "2024-01-01"]
    oep = s2[s2.is_oep_month == 1]
    non = s2[s2.is_oep_month == 0]
    oep_rate = oep.effective_disenrollments.sum() / oep.members_at_start.sum()
    non_rate = non.effective_disenrollments.sum() / non.members_at_start.sum()
    out["seasonality"] = {
        "oep_rate_pct": float(100 * oep_rate), "non_oep_rate_pct": float(100 * non_rate),
        "oep_ratio": float(oep_rate / non_rate),
        "effective_disenrollments_2024_2025": int(s2.effective_disenrollments.sum()),
        "snapshot_disenrollments_2024_2025": int(s2.snapshot_disenrollments.sum()),
        "snapshot_undercount_pct": float(100 * (1 - s2.snapshot_disenrollments.sum() / s2.effective_disenrollments.sum())),
    }

    # ------------------------------------------------------------- segments
    seg = pd.read_csv(C.OUTPUTS / "05_segment_risk_table.csv")
    shown = seg[seg.suppressed == 0]
    worst = shown.sort_values("retention_12m_pct").iloc[0]
    best = shown.sort_values("retention_12m_pct").iloc[-1]
    out["segments"] = {
        "n_cells": int(len(seg)), "n_suppressed": int(seg.suppressed.sum()),
        "worst": {"segment": f"{worst.channel} / {worst.plan_type} / {worst.dual_status}",
                  "ret12": float(worst.retention_12m_pct), "n": int(worst.members)},
        "best": {"segment": f"{best.channel} / {best.plan_type} / {best.dual_status}",
                 "ret12": float(best.retention_12m_pct), "n": int(best.members)},
    }
    q3 = pd.read_csv(C.OUTPUTS / "03_retention_by_pcp_visit_and_dual.csv")
    get = lambda ds, p: float(q3[(q3.dual_status == ds) & (q3.pcp_visit_90d == p)].retention_12m_pct.iloc[0])
    out["raw_retention_12m"] = {f"{ds}_pcp{p}": get(ds, p) for ds in ["all", "dual", "non-dual"] for p in [0, 1]}

    # priority segments for outreach: expected 12-month disenrollments among no-visit members
    nv = lm[(lm.pcp_visit_90d == 0) & lm.retained_12m.notna()]
    pri = nv.groupby(["channel", "dual_eligible_flag"]).agg(n=("member_id", "size"),
                                                            churn=("retained_12m", lambda s: 1 - s.mean()))
    pri["expected_losses_per_100"] = 100 * pri.churn
    pri = pri.sort_values("churn", ascending=False).reset_index()
    pri.to_csv(C.OUTPUTS / "outreach_priority.csv", index=False)
    out["outreach_priority"] = [{"channel": r.channel, "dual": int(r.dual_eligible_flag), "n": int(r.n),
                                 "churn_12m_pct": float(100 * r.churn)} for r in pri.itertuples()]

    # ------------------------------------------------------------- sizing
    # Two outreach scopes: every new member without a PCP visit by day 60, or dual-eligible
    # members only. For each: workload -> FTE -> cost, and retained members/revenue if the
    # PCP-visit rate in that scope rises by PCP_UPLIFT_PP, under several causal-share scenarios.
    outreach = pd.read_csv(C.OUTPUTS / "06_outreach_volume_sizing.csv")
    o24 = outreach[(outreach.cohort_yyyymm >= 202401) & (outreach.cohort_yyyymm <= 202412)]
    hr = out["cox_adjusted_pcp"]["hr"]
    ret24 = ret[(ret.cohort_yyyymm >= 202401) & (ret.cohort_yyyymm <= 202412)]

    def size(scope_mask_lm, scope_mask_24, workload_col):
        nv_lm = lm[scope_mask_lm & (lm.pcp_visit_90d == 0)]
        k0 = kaplan_meier(nv_lm.covered_months, nv_lm.churned, start=LANDMARK).set_index("month").retention
        k1 = k0 ** hr
        d_ret12 = float(k1.loc[HORIZON] - k0.loc[HORIZON])
        d_mm = float((k1 - k0).loc[LANDMARK + 1:HORIZON].sum())
        # 24-month window: assumes the hazard ratio persists into year 2 (stated as an assumption)
        k0l = kaplan_meier(nv_lm.covered_months, nv_lm.churned, start=LANDMARK, horizon=24).set_index("month").retention
        d_mm24 = float((k0l ** hr - k0l).loc[LANDMARK + 1:24].sum())
        scope_24 = ret24[scope_mask_24]
        new_members = int(len(scope_24))
        reach = float((scope_24.covered_months >= LANDMARK).mean())
        extra = C.PCP_UPLIFT_PP * new_members * reach
        workload = float(o24[workload_col].mean())
        peak = int(o24[workload_col].max())
        hours = workload * C.ATTEMPTS_PER_MEMBER * C.MINUTES_PER_ATTEMPT / 60
        fte = hours / C.PRODUCTIVE_HOURS_PER_FTE_MONTH
        fte_peak = peak * C.ATTEMPTS_PER_MEMBER * C.MINUTES_PER_ATTEMPT / 60 / C.PRODUCTIVE_HOURS_PER_FTE_MONTH
        funded = int(np.ceil(fte))
        cost = funded * C.FTE_ANNUAL_COST
        scen = []
        for share in C.CAUSAL_SHARES:
            revenue = extra * d_mm * share * C.REVENUE_PMPM
            revenue24 = extra * d_mm24 * share * C.REVENUE_PMPM
            scen.append({"causal_share": share, "members_retained_12m": float(extra * d_ret12 * share),
                         "member_months_first_year": float(extra * d_mm * share),
                         "revenue_first_year": float(revenue), "net_of_staff_cost": float(revenue - cost),
                         "revenue_24m": float(revenue24)})
        return {"new_members_2024": new_members, "monthly_outreach_workload": workload,
                "peak_monthly_workload": peak, "outreach_hours_per_month": float(hours),
                "fte_needed": float(fte), "fte_needed_peak": float(fte_peak), "fte_funded": funded,
                "annual_staff_cost": float(cost), "no_visit_retention_12m": float(k0.loc[HORIZON]),
                "delta_retention_12m_per_converted_member": d_ret12,
                "delta_member_months_per_converted_member": d_mm,
                "extra_pcp_visitors_per_year": float(extra), "scenarios": scen,
                "delta_member_months_24m_per_converted_member": d_mm24,
                "breakeven_causal_share": float(cost / (extra * d_mm * C.REVENUE_PMPM)),
                "breakeven_causal_share_24m": float(cost / (extra * d_mm24 * C.REVENUE_PMPM))}

    out["sizing"] = {
        "hr_used": hr,
        "all_members": size(lm.member_id.notna(), ret24.member_id.notna(), "no_pcp_visit_by_day_60"),
        "dual_only": size(lm.dual_eligible_flag == 1, ret24.dual_eligible_flag == 1, "no_visit_dual"),
        "assumptions": {"revenue_pmpm": C.REVENUE_PMPM, "uplift_pp": C.PCP_UPLIFT_PP,
                        "attempts_per_member": C.ATTEMPTS_PER_MEMBER, "minutes_per_attempt": C.MINUTES_PER_ATTEMPT,
                        "productive_hours_per_fte_month": C.PRODUCTIVE_HOURS_PER_FTE_MONTH,
                        "fte_annual_cost": C.FTE_ANNUAL_COST},
    }

    # ------------------------------------------------------------- pilot sizing (randomized outreach)
    from statsmodels.stats.power import NormalIndPower
    from statsmodels.stats.proportion import proportion_effectsize
    nv_share = float(o24.no_pcp_visit_by_day_60.sum() / o24.enrolled_at_day_60.sum())
    conv = C.PCP_UPLIFT_PP / nv_share  # visit-rate lift needed among called members to move the whole cohort 10 pp
    am = out["sizing"]["all_members"]
    called = lm[lm.pcp_visit_60d == 0]
    pv0 = float(called.pcp_visit_90d.mean())
    n_visit = NormalIndPower().solve_power(abs(proportion_effectsize(pv0 + conv, pv0)), alpha=0.05, power=0.8)
    p0 = 1 - am["no_visit_retention_12m"]
    pilot = {"no_visit_share_day60": nv_share, "visit_lift_among_called": conv,
             "baseline_visit_by_day90_among_called": pv0, "n_per_arm_visit_rate": int(np.ceil(n_visit))}
    for share in C.CAUSAL_SHARES:
        p1 = p0 - conv * am["delta_retention_12m_per_converted_member"] * share
        n = NormalIndPower().solve_power(abs(proportion_effectsize(p0, p1)), alpha=0.05, power=0.8)
        pilot[f"n_per_arm_churn_share_{int(share * 100)}"] = int(np.ceil(n))
        pilot[f"churn_reduction_pp_share_{int(share * 100)}"] = float(100 * (p0 - p1))
    pilot["baseline_churn_12m_no_visit"] = float(p0)
    out["pilot"] = pilot

    # ------------------------------------------------------------- validation vs planted
    hp = truth["hazard_parameters"]
    real = truth["realized"]
    tq = truth["data_quality"]
    fr = out["funnel_recovered"]
    V = []

    def v(name, planted, recovered, lo=None, hi=None, tol=None, kind="parameter"):
        if lo is not None:
            ok = lo <= planted <= hi
        else:
            ok = abs(recovered - planted) <= tol
        V.append({"effect": name, "kind": kind, "planted": planted, "recovered": recovered,
                  "ci_lo": lo, "ci_hi": hi, "tolerance": tol, "pass": bool(ok)})

    pc = out["cox_adjusted_pcp"]
    v("PCP visit within 90 days, hazard ratio (Cox, adjusted)", hp["pcp_visit_90d_multiplier"], pc["hr"], pc["lo"], pc["hi"])
    for name, term, key in [("OEP (Jan-Mar) rate ratio", "is_oep_month", "oep_multiplier"),
                            ("Dual-eligible rate ratio", "dual_eligible_flag", "dual_multiplier"),
                            ("Broker channel rate ratio", "channel[T.broker]", "broker_multiplier"),
                            ("Online channel rate ratio", "channel[T.online]", "online_multiplier"),
                            ("Agent channel rate ratio", "channel[T.agent]", "agent_multiplier"),
                            ("PCP visit rate ratio (Poisson, time-varying)", "pcp_visited", "pcp_visit_90d_multiplier")]:
        x = rr[term]
        v(name, hp[key], x["rr"], x["lo"], x["hi"])
    v("Baseline monthly hazard (Apr-Dec, reference group)", hp["baseline_monthly_hazard"],
      rr["Intercept"]["rr"], rr["Intercept"]["lo"], rr["Intercept"]["hi"])
    v("12-month retention, Jan-Jun 2024 cohorts", real["retention_12m_jan_jun_2024_cohorts"],
      out["retention_12m_jan_jun_2024"], tol=0.005, kind="realized")
    v("Welcome call completion (landmark)", real["welcome_complete_rate_landmark"], fr["welcome_complete_rate"], tol=0.005, kind="realized")
    v("HRA completion, all (landmark)", real["hra_rate_landmark"], fr["hra_rate"], tol=0.005, kind="realized")
    v("HRA completion, online (landmark)", real["hra_rate_online_landmark"], fr["hra_rate_online"], tol=0.005, kind="realized")
    v("PCP visit within 90 days (landmark)", real["pcp90_rate_landmark"], fr["pcp90_rate"], tol=0.005, kind="realized")
    v("PCP visit given HRA (landmark)", real["pcp90_given_hra_landmark"], fr["pcp90_given_hra"], tol=0.005, kind="realized")
    v("PCP visit without HRA (landmark)", real["pcp90_given_no_hra_landmark"], fr["pcp90_given_no_hra"], tol=0.005, kind="realized")
    for name, tk, dk in [("Cross-feed duplicate events", "duplicate_onboarding_events", "duplicate_events_removed"),
                         ("Retro-terminations", "retro_terminations", "retro_terminations"),
                         ("Members with overlapping spans", "members_with_overlapping_spans", "members_with_overlapping_spans"),
                         ("Null county_fips", "null_county_fips", "null_county_fips"),
                         ("PCP visit before enrollment", "members_pcp_visit_before_enroll", "members_pcp_visit_before_enroll"),
                         ("Non-standard channel codes", "nonstandard_channel_codes", "nonstandard_channel_codes")]:
        v(name, tq[tk], dq[dk], tol=0, kind="data quality")
    out["validation"] = V
    out["validation_pass"] = int(sum(x["pass"] for x in V))
    out["validation_total"] = len(V)

    C.REPORTS.mkdir(exist_ok=True)
    (C.REPORTS / "results.json").write_text(json.dumps(out, indent=2, default=float))
    print(f"validation: {out['validation_pass']}/{out['validation_total']} pass")
    for x in V:
        if not x["pass"]:
            print("FAIL", x)


if __name__ == "__main__":
    main()
