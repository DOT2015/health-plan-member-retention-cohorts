"""Render README.md and docs/executive_summary.md from templates and reports/results.json.

Every number in those two files comes from this script; nothing is hand-typed.
Placeholders look like {{name}}. A missing key raises an error.
"""
import json
import re

import config as C


def pct(x, d=1):
    return f"{100 * x:.{d}f}%"


def money(x):
    return f"${x / 1e6:.2f}M" if abs(x) >= 1e6 else f"${x / 1e3:,.0f}K"


def build_values(r, t):
    a = r["sizing"]["all_members"]
    d = r["sizing"]["dual_only"]
    km = r["km_landmark_12m"]
    cu, ca = r["cox_unadjusted_pcp"], r["cox_adjusted_pcp"]
    fun = r["funnel"]
    non_online_hra_step = (fun["direct"]["step_hra_given_welcome"] + fun["broker"]["step_hra_given_welcome"]
                           + fun["agent"]["step_hra_given_welcome"]) / 3
    pr = r["outreach_priority"][0]
    v = {
        "n_members": f"{r['n_members']:,}",
        "n_landmark": f"{r['n_landmark']:,}",
        "n_disenrolled": f"{r['n_disenrolled_first_island']:,}",
        "person_months": f"{r['person_months']:,}",
        "ret12_all": pct(r["retention_12m_all_km"]["est"]),
        "ret12_all_lo": pct(r["retention_12m_all_km"]["lo"]),
        "ret12_all_hi": pct(r["retention_12m_all_km"]["hi"]),
        "ret12_2024h1": pct(r["retention_12m_jan_jun_2024"]),
        "km_all_pcp1": pct(km["all_pcp1"]["ret12"]), "km_all_pcp0": pct(km["all_pcp0"]["ret12"]),
        "km_dual_pcp1": pct(km["dual1_pcp1"]["ret12"]), "km_dual_pcp0": pct(km["dual1_pcp0"]["ret12"]),
        "km_nondual_pcp1": pct(km["dual0_pcp1"]["ret12"]), "km_nondual_pcp0": pct(km["dual0_pcp0"]["ret12"]),
        "km_gap_all_pp": f"{100 * (km['all_pcp1']['ret12'] - km['all_pcp0']['ret12']):.1f}",
        "km_gap_dual_pp": f"{100 * (km['dual1_pcp1']['ret12'] - km['dual1_pcp0']['ret12']):.1f}",
        "km_gap_nondual_pp": f"{100 * (km['dual0_pcp1']['ret12'] - km['dual0_pcp0']['ret12']):.1f}",
        "logrank_chi2": f"{r['logrank_pcp']['chi2']:.0f}",
        "hr_adj": f"{ca['hr']:.2f}", "hr_adj_lo": f"{ca['lo']:.2f}", "hr_adj_hi": f"{ca['hi']:.2f}",
        "hr_unadj": f"{cu['hr']:.2f}", "hr_unadj_lo": f"{cu['lo']:.2f}", "hr_unadj_hi": f"{cu['hi']:.2f}",
        "hr_dual": f"{r['cox_adjusted']['dual_eligible_flag']['hr']:.2f}",
        "hr_broker": f"{r['cox_adjusted']['channel_broker']['hr']:.2f}",
        "ph_r": f"{r['ph_check_pcp']['schoenfeld_time_corr']:.3f}", "ph_p": f"{r['ph_check_pcp']['p']:.2f}",
        "cox_n": f"{r['cox_n']:,}", "cox_events": f"{r['cox_events']:,}",
        "pcp90_all": f"{fun['all']['pct_pcp_all']:.1f}%",
        "hra_online": f"{fun['online']['pct_hra_all']:.1f}%",
        "hra_all": f"{fun['all']['pct_hra_all']:.1f}%",
        "hra_step_online": f"{fun['online']['step_hra_given_welcome']:.1f}%",
        "hra_step_other": f"{non_online_hra_step:.1f}%",
        "welcome_all": f"{fun['all']['pct_welcome']:.1f}%",
        "pcp_online": f"{fun['online']['pct_pcp_all']:.1f}%",
        "oep_ratio": f"{r['seasonality']['oep_ratio']:.2f}",
        "oep_rate": f"{r['seasonality']['oep_rate_pct']:.2f}%",
        "non_oep_rate": f"{r['seasonality']['non_oep_rate_pct']:.2f}%",
        "snapshot_undercount": f"{r['seasonality']['snapshot_undercount_pct']:.1f}%",
        "eff_disenroll": f"{r['seasonality']['effective_disenrollments_2024_2025']:,}",
        "snap_disenroll": f"{r['seasonality']['snapshot_disenrollments_2024_2025']:,}",
        "seg_worst": r["segments"]["worst"]["segment"], "seg_worst_ret": f"{r['segments']['worst']['ret12']:.1f}%",
        "seg_worst_n": f"{r['segments']['worst']['n']:,}",
        "seg_best": r["segments"]["best"]["segment"], "seg_best_ret": f"{r['segments']['best']['ret12']:.1f}%",
        "seg_cells": str(r["segments"]["n_cells"]), "seg_suppressed": str(r["segments"]["n_suppressed"]),
        "prio_channel": pr["channel"], "prio_churn": f"{pr['churn_12m_pct']:.1f}%",
        "workload": f"{a['monthly_outreach_workload']:,.0f}", "workload_peak": f"{a['peak_monthly_workload']:,}",
        "fte": f"{a['fte_needed']:.1f}", "fte_peak": f"{a['fte_needed_peak']:.1f}", "fte_funded": str(a["fte_funded"]),
        "staff_cost": money(a["annual_staff_cost"]),
        "new_2024": f"{a['new_members_2024']:,}", "extra_visitors": f"{a['extra_pcp_visitors_per_year']:,.0f}",
        "d_ret12": f"{100 * a['delta_retention_12m_per_converted_member']:.1f}",
        "d_mm": f"{a['delta_member_months_per_converted_member']:.2f}",
        "d_mm24": f"{a['delta_member_months_24m_per_converted_member']:.2f}",
        "breakeven12": pct(a["breakeven_causal_share"], 0), "breakeven24": pct(a["breakeven_causal_share_24m"], 0),
        "dual_workload": f"{d['monthly_outreach_workload']:,.0f}", "dual_fte": f"{d['fte_needed']:.1f}",
        "dual_fte_funded": str(d["fte_funded"]), "dual_cost": money(d["annual_staff_cost"]),
        "dual_breakeven24": pct(d["breakeven_causal_share_24m"], 0),
        "dual_nv_ret": pct(d["no_visit_retention_12m"]), "dual_d_ret12": f"{100 * d['delta_retention_12m_per_converted_member']:.1f}",
        "pilot_n_visit": f"{r['pilot']['n_per_arm_visit_rate']:,}",
        "pilot_n_churn100": f"{r['pilot']['n_per_arm_churn_share_100']:,}",
        "pilot_n_churn50": f"{r['pilot']['n_per_arm_churn_share_50']:,}",
        "pilot_lift": f"{100 * r['pilot']['visit_lift_among_called']:.1f}",
        "pilot_years": f"{2 * r['pilot']['n_per_arm_churn_share_100'] / (12 * a['monthly_outreach_workload']):.0f}",
        "pilot_base": pct(r["pilot"]["baseline_visit_by_day90_among_called"]),
        "nv_share60": pct(r["pilot"]["no_visit_share_day60"], 0),
        "val_pass": str(r["validation_pass"]), "val_total": str(r["validation_total"]),
        "revenue_pmpm": f"${C.REVENUE_PMPM:,}", "fte_annual_cost": f"${C.FTE_ANNUAL_COST:,}",
        "attempts": str(C.ATTEMPTS_PER_MEMBER), "minutes": str(C.MINUTES_PER_ATTEMPT),
        "fte_hours": str(C.PRODUCTIVE_HOURS_PER_FTE_MONTH),
    }
    if a["breakeven_causal_share"] > 1:
        v["first_year_verdict"] = (f"Revenue from the first 12 months does not cover its {money(a['annual_staff_cost'])} "
                                   "annual cost even if the whole association were causal.")
        v["breakeven12_note"] = " (above 100%, so not reachable)"
    else:
        v["first_year_verdict"] = (f"First-year revenue covers its {money(a['annual_staff_cost'])} annual cost only if at "
                                   f"least {pct(a['breakeven_causal_share'], 0)} of the association is causal.")
        v["breakeven12_note"] = ""
    for i, sc in enumerate(a["scenarios"]):
        tag = int(sc["causal_share"] * 100)
        v[f"sc{tag}_ret"] = f"{sc['members_retained_12m']:.0f}"
        v[f"sc{tag}_rev12"] = money(sc["revenue_first_year"])
        v[f"sc{tag}_rev24"] = money(sc["revenue_24m"])
        v[f"sc{tag}_net12"] = money(sc["net_of_staff_cost"])
    dq = r["data_quality"]
    for k, val in dq.items():
        v[f"dq_{k}"] = f"{val:,}"
    v["dq_dup_pct"] = pct(dq["duplicate_events_removed"] / dq["raw_onboarding_events"])
    # validation table
    lines = ["| Planted effect | Kind | Planted / true | Recovered | 95% CI | Pass |", "|---|---|---|---|---|---|"]
    for x in r["validation"]:
        fmt = (lambda z: f"{z:,.0f}") if x["kind"] == "data quality" else (
            (lambda z: f"{z:.4f}") if x["planted"] < 0.05 else (lambda z: f"{z:.3f}"))
        ci = f"{fmt(x['ci_lo'])} - {fmt(x['ci_hi'])}" if x["ci_lo"] is not None else (
            f"tolerance ±{x['tolerance']}" if x["tolerance"] else "exact match")
        lines.append(f"| {x['effect']} | {x['kind']} | {fmt(x['planted'])} | {fmt(x['recovered'])} | {ci} | "
                     f"{'yes' if x['pass'] else 'NO'} |")
    v["validation_table"] = "\n".join(lines)
    # sizing table
    rows = ["| Causal share of the association | Members retained at month 12 | Revenue, months 4-12 | Revenue, months 4-24 |",
            "|---|---|---|---|"]
    for sc in a["scenarios"]:
        rows.append(f"| {int(sc['causal_share'] * 100)}% | {sc['members_retained_12m']:.0f} | "
                    f"{money(sc['revenue_first_year'])} | {money(sc['revenue_24m'])} |")
    v["sizing_table"] = "\n".join(rows)
    return v


def render(template_path, out_path, values):
    text = template_path.read_text()
    missing = set(re.findall(r"\{\{(\w+)\}\}", text)) - set(values)
    if missing:
        raise KeyError(f"{template_path.name}: missing values {sorted(missing)}")
    out_path.write_text(re.sub(r"\{\{(\w+)\}\}", lambda m: values[m.group(1)], text))


def main():
    r = json.loads((C.REPORTS / "results.json").read_text())
    t = json.loads(C.TRUTH.read_text())
    v = build_values(r, t)
    tdir = C.ROOT / "docs" / "templates"
    render(tdir / "README.md.tmpl", C.ROOT / "README.md", v)
    render(tdir / "executive_summary.md.tmpl", C.ROOT / "docs" / "executive_summary.md", v)
    print("rendered README.md and docs/executive_summary.md")


if __name__ == "__main__":
    main()
