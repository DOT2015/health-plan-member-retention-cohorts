"""Seeded generator for a synthetic Medicare Advantage member-retention dataset.

Writes CSVs to data/raw/, a <=1,000-row sample per table to data/sample/, and the
realized planted values to data/truth/planted_effects.json.

All data is synthetic. No real members, plans, or counties.
"""
import json
import shutil

import numpy as np
import pandas as pd

import config as C

rng = np.random.default_rng(C.SEED)
MONTH0 = np.datetime64(C.FIRST_ENROLL, "M")
OBS_END = np.datetime64(C.OBS_END, "D")


def D(k):
    return np.timedelta64(int(k), "D")


def month_start(idx):
    return (MONTH0 + np.asarray(idx)).astype("datetime64[D]")


def month_end(idx):
    return (MONTH0 + np.asarray(idx) + np.timedelta64(1, "M")).astype("datetime64[D]") - D(1)


# ----------------------------------------------------------------------------- dims
def make_dim_date():
    d = pd.date_range("2023-01-01", "2025-12-31", freq="D")
    return pd.DataFrame({
        "date": d.date,
        "year": d.year,
        "month": d.month,
        "month_start": d.to_period("M").to_timestamp().date,
        "quarter": d.quarter,
        "day_of_week": d.dayofweek + 1,
        "is_oep_month": d.month.isin([1, 2, 3]).astype(int),
    })


def make_dim_county():
    n = 40
    fips = [f"9{str(i).zfill(4)}" for i in range(1, 2 * n, 2)]  # synthetic 9xxxx codes
    urban = np.array(["urban"] * 25 + ["rural"] * 15)
    rng.shuffle(urban)
    names = [f"Synthetic County {chr(65 + i // 26)}{chr(65 + i % 26)}" for i in range(n)]
    weight = np.where(urban == "urban", rng.uniform(2, 6, n), rng.uniform(0.5, 1.5, n))
    return pd.DataFrame({"county_fips": fips, "county_name_synthetic": names,
                         "urban_rural": urban}), weight / weight.sum()


def make_dim_plan():
    rows = []
    for i in range(12):
        ptype = "HMO" if i < 5 else ("PPO" if i < 9 else "D-SNP")
        prem = {"HMO": [0, 0, 19, 35, 49], "PPO": [29, 59, 89, 119], "D-SNP": [0, 0, 0]}[ptype]
        idx = i if i < 5 else (i - 5 if i < 9 else i - 9)
        rows.append({"plan_id": f"P{str(i + 1).zfill(2)}", "plan_type": ptype,
                     "monthly_premium": float(prem[idx]),
                     "star_rating": float(rng.choice([3.5, 4.0, 4.0, 4.5, 4.5, 5.0]))})
    return pd.DataFrame(rows)


# ----------------------------------------------------------------------------- members
def make_members(plans, county_df, county_w):
    n = C.N_MEMBERS
    w = np.ones(C.N_ENROLL_MONTHS)
    for m in range(C.N_ENROLL_MONTHS):
        # AEP January peak, OEP switchers in Feb-Mar, and a growing plan (more recent cohorts are larger)
        w[m] = {0: 3.0, 1: 1.2, 2: 1.2}.get(m % 12, 1.0) * (1.0 + 0.04 * m)
    enroll_idx = rng.choice(C.N_ENROLL_MONTHS, size=n, p=w / w.sum())
    enroll_idx.sort()
    dual = rng.random(n) < C.P_DUAL
    lis = np.where(dual, 1, (rng.random(n) < 0.08).astype(int))
    channel = rng.choice(["direct", "broker", "online", "agent"], size=n, p=[0.35, 0.30, 0.15, 0.20])
    p_dsnp = np.where(dual, C.P_DSNP_NONDUAL * C.DUAL_DSNP_MULT, C.P_DSNP_NONDUAL)
    is_dsnp = rng.random(n) < p_dsnp
    is_hmo = rng.random(n) < 0.60
    plan_id = np.where(is_dsnp, rng.choice(["P10", "P11", "P12"], n),
                       np.where(is_hmo, rng.choice(["P01", "P02", "P03", "P04", "P05"], n),
                                rng.choice(["P06", "P07", "P08", "P09"], n)))
    age = np.clip(65 + rng.gamma(2.0, 4.5, n).round().astype(int), 65, 99)
    sex = np.where(rng.random(n) < 0.55, "F", "M")
    county = rng.choice(county_df.county_fips.values, size=n, p=county_w)
    return pd.DataFrame({
        "member_id": [f"M{str(i + 1).zfill(6)}" for i in range(n)],
        "enroll_idx": enroll_idx, "plan_id": plan_id, "county_fips": county, "age": age,
        "sex": sex, "dual_eligible_flag": dual.astype(int), "lis_flag": lis, "channel": channel,
    })


# ----------------------------------------------------------------------------- funnel
def make_funnel(mem):
    n = len(mem)
    dual = mem.dual_eligible_flag.values == 1
    online = mem.channel.values == "online"
    wc = rng.random(n) < C.P_WELCOME
    p_hra = np.where(online, C.P_HRA_ONLINE, C.P_HRA)
    hra = wc & (rng.random(n) < p_hra)
    p_pcp = np.where(hra, C.P_PCP_GIVEN_HRA, C.P_PCP_NO_HRA) * np.where(dual, C.DUAL_PCP_MULT, 1.0)
    pcp = rng.random(n) < p_pcp
    # timing (days since enrollment)
    first_attempt = rng.integers(2, 11, n)
    n_attempts = np.where(wc, rng.integers(1, 6, n), rng.integers(3, 9, n))
    gaps = rng.integers(2, 6, (n, 8))
    attempt_days = first_attempt[:, None] + np.concatenate([np.zeros((n, 1), int), np.cumsum(gaps[:, :7], 1)], 1)
    wc_day = np.where(wc, attempt_days[np.arange(n), n_attempts - 1], -1)
    hra_day = np.where(hra, np.minimum(wc_day + rng.integers(3, 41, n), 80), -1)
    lo = np.where(hra, hra_day + 2, 10)
    pcp_day = np.where(pcp, lo + (rng.random(n) * (89 - lo + 1)).astype(int), -1)
    pcp_day = np.where(pcp, np.minimum(pcp_day, 89), -1)
    late_pcp = (~pcp) & (rng.random(n) < 0.40)
    late_day = np.where(late_pcp, rng.integers(91, 366, n), -1)
    return dict(wc=wc, hra=hra, pcp=pcp, attempt_days=attempt_days, n_attempts=n_attempts,
                wc_day=wc_day, hra_day=hra_day, pcp_day=pcp_day, late_day=late_day)


# ----------------------------------------------------------------------------- hazard
def simulate_disenrollment(mem, fun):
    n = len(mem)
    e = mem.enroll_idx.values
    hz_static = C.BASE_HAZARD * np.where(mem.dual_eligible_flag.values == 1, C.DUAL_MULT, 1.0) \
        * mem.channel.map(C.CHANNEL_MULT).values
    alive = np.ones(n, bool)
    exit_idx = np.full(n, -1)
    plan_change = {}  # member row -> list of calendar month idx where a new plan starts
    start_days = month_start(e)
    for m in range(C.N_CAL_MONTHS):
        c = e + m
        active = alive & (c < C.N_CAL_MONTHS)
        if not active.any():
            break
        # plan change on Jan 1 (not churn)
        jan = active & (m > 0) & (c % 12 == 0) & (rng.random(n) < 0.06)
        for i in np.where(jan)[0]:
            plan_change.setdefault(i, []).append(int(c[i]))
        offset = (month_start(np.minimum(c, C.N_CAL_MONTHS - 1)) - start_days).astype(int)
        visited = fun["pcp"] & (fun["pcp_day"] < offset)
        h = hz_static * np.where(c % 12 < 3, C.OEP_MULT, 1.0) * np.where(visited, C.PCP90_MULT, 1.0)
        ev = active & (rng.random(n) < h)
        exit_idx[ev] = c[ev]
        alive &= ~ev
    return exit_idx, plan_change


def main():
    C.RAW.mkdir(parents=True, exist_ok=True)
    C.SAMPLE.mkdir(parents=True, exist_ok=True)
    C.TRUTH.parent.mkdir(parents=True, exist_ok=True)

    dim_date = make_dim_date()
    dim_county, county_w = make_dim_county()
    dim_plan = make_dim_plan()
    mem = make_members(dim_plan, dim_county, county_w)
    fun = make_funnel(mem)
    exit_idx, plan_change = simulate_disenrollment(mem, fun)
    n = len(mem)
    e = mem.enroll_idx.values
    enroll_date = month_start(e)
    churned = exit_idx >= 0
    end_date = np.where(churned, month_end(np.maximum(exit_idx, 0)), np.datetime64("NaT", "D"))
    cover_end = np.where(churned, end_date, OBS_END)  # true end of first coverage island

    # ---------------- enrollment spans
    reasons = rng.choice(["VOL_SWITCH", "MOVED", "DEATH", "NONPAY", "OTHER"], size=n,
                         p=[0.60, 0.12, 0.10, 0.08, 0.10])
    retro = churned & (rng.random(n) < C.DQ_RETRO_TERM_RATE)
    all_plans = dim_plan.plan_id.tolist()
    spans = []
    plans_seq = {}
    churn_post = {}
    for i in range(n):
        cur_plan = mem.plan_id.iat[i]
        plans_seq[i] = [cur_plan]
        seg_start = enroll_date[i]
        changes = plan_change.get(i, [])
        for cm in changes:
            seg_end = month_start(cm) - D(1)
            spans.append((i, seg_start, seg_end, "PLAN_CHANGE", cur_plan,
                          seg_end - D(rng.integers(0, 21))))
            cur_plan = rng.choice([p for p in all_plans if p != cur_plan])
            plans_seq[i].append(cur_plan)
            seg_start = month_start(cm)
        if churned[i]:
            post = end_date[i] + D(rng.integers(30, 61) if retro[i] else -rng.integers(0, 26))
            churn_post[i] = post
            spans.append((i, seg_start, end_date[i], reasons[i], cur_plan, post))
        else:
            spans.append((i, seg_start, np.datetime64("NaT", "D"), None, cur_plan,
                          seg_start - D(rng.integers(5, 31))))
    span_df = pd.DataFrame(spans, columns=["row", "start_date", "end_date", "disenroll_reason_code",
                                           "plan_id", "posted_date"])
    # re-enrollment after a gap (counts as churn at first exit)
    reenroll = churned & (rng.random(n) < 0.08)
    re_rows = []
    for i in np.where(reenroll)[0]:
        gap = int(rng.integers(2, 9))
        sm = exit_idx[i] + gap
        if sm < C.N_CAL_MONTHS:
            st = month_start(sm)
            re_rows.append((i, st, np.datetime64("NaT", "D"), None, mem.plan_id.iat[i], st - D(rng.integers(5, 31))))
    # overlapping spans (data error): a second span that starts inside the first island
    overlap_members = rng.choice(n, size=int(round(C.DQ_OVERLAP_MEMBER_RATE * n)), replace=False)
    ov_rows = []
    for i in overlap_members:
        first = span_df[span_df.row == i].iloc[0]
        st = np.datetime64(first.start_date, "D") + D(rng.integers(10, 25))
        ov_rows.append((i, st, first.end_date, first.disenroll_reason_code, first.plan_id, st + D(3)))
    span_df = pd.concat([span_df, pd.DataFrame(re_rows + ov_rows, columns=span_df.columns)], ignore_index=True)
    span_df = span_df.sort_values(["row", "start_date"]).reset_index(drop=True)
    span_df["member_id"] = mem.member_id.values[span_df.row.values]
    span_df.insert(0, "span_id", [f"S{str(k + 1).zfill(7)}" for k in range(len(span_df))])
    fact_span = span_df[["span_id", "member_id", "start_date", "end_date", "disenroll_reason_code",
                         "plan_id", "posted_date"]].copy()

    # ---------------- member months (month-end snapshot, not restated)
    mm = []
    for i in range(n):
        last = exit_idx[i] if churned[i] else C.N_CAL_MONTHS - 1
        changes = set(plan_change.get(i, []))
        seq = plans_seq[i]
        k = 0
        cur = seq[0]
        for c in range(e[i], last + 1):
            if c in changes:
                k += 1
                cur = seq[k]
            mm.append((i, c, cur, 1))
        if churned[i]:
            post = churn_post[i]
            for c in range(last + 1, min(last + 3, C.N_CAL_MONTHS)):
                active = 1 if post > month_end(c) else 0  # retro-term not yet posted at snapshot
                mm.append((i, c, cur, active))
    mm = np.array(mm, dtype=object)
    fact_mm = pd.DataFrame({
        "member_id": mem.member_id.values[mm[:, 0].astype(int)],
        "month_start": month_start(mm[:, 1].astype(int)),
        "plan_id": mm[:, 2], "active_flag": mm[:, 3].astype(int)})

    # ---------------- onboarding events (true UTC timestamps, then feed-specific storage)
    ev = []
    plan_type = mem.plan_id.map(dim_plan.set_index("plan_id").plan_type).values

    def add(i, etype, day, src):
        d = enroll_date[i] + D(day)
        if d > cover_end[i] or d > OBS_END:
            return  # member left before the event could happen
        ev.append((i, etype, d, src))

    for i in range(n):
        for a in range(fun["n_attempts"][i]):
            add(i, "welcome_call_attempt", fun["attempt_days"][i, a], "vendor")
        if fun["wc"][i]:
            add(i, "welcome_call_complete", fun["wc_day"][i], "vendor")
        if fun["hra"][i]:
            add(i, "hra_complete", fun["hra_day"][i], "vendor")
        if plan_type[i] != "PPO" or rng.random() < 0.6:
            if plan_type[i] == "PPO" or rng.random() < 0.97:
                add(i, "pcp_assigned", rng.integers(0, 16), "CRM")
        if fun["pcp"][i]:
            add(i, "pcp_first_visit", fun["pcp_day"][i], "CRM")
        elif fun["late_day"][i] > 0:
            add(i, "pcp_first_visit", fun["late_day"][i], "CRM")
        if rng.random() < 0.45:
            add(i, "portal_registered", rng.integers(1, 200), "CRM")
    # pcp_first_visit dated before enrollment (data error), only for members with no 90-day visit
    cand = np.where(~fun["pcp"] & (fun["late_day"] < 0))[0]
    pre_members = rng.choice(cand, size=int(round(C.DQ_PCP_BEFORE_ENROLL_RATE * n)), replace=False)
    for i in pre_members:
        ev.append((i, "pcp_first_visit", enroll_date[i] - D(rng.integers(5, 61)), "CRM"))
    ev = pd.DataFrame(ev, columns=["row", "event_type", "date", "source_system"])
    secs = rng.integers(9 * 3600, 17 * 3600, len(ev))  # business hours, US/Eastern
    local = pd.to_datetime(ev.date.values) + pd.to_timedelta(secs, unit="s")
    utc = local.tz_localize("America/New_York", nonexistent="shift_forward", ambiguous=False).tz_convert("UTC")
    ev["ts_utc"] = utc.tz_localize(None)
    ev["is_duplicate"] = 0
    dup = ev.sample(frac=C.DQ_DUP_EVENT_RATE, random_state=C.SEED).copy()
    dup["source_system"] = np.where(dup.source_system == "CRM", "vendor", "CRM")
    dup["ts_utc"] = dup.ts_utc + pd.to_timedelta(rng.integers(0, 241, len(dup)), unit="s")
    dup["is_duplicate"] = 1
    ev = pd.concat([ev, dup], ignore_index=True)
    stored = ev.ts_utc.copy()
    crm = ev.source_system == "CRM"
    stored[crm] = ev.loc[crm, "ts_utc"].dt.tz_localize("UTC").dt.tz_convert("America/New_York").dt.tz_localize(None)
    ev["event_ts"] = stored.dt.strftime("%Y-%m-%d %H:%M:%S")
    ev = ev.sort_values(["row", "ts_utc", "is_duplicate"]).reset_index(drop=True)
    ev["member_id"] = mem.member_id.values[ev.row.values]
    ev.insert(0, "event_id", [f"E{str(k + 1).zfill(7)}" for k in range(len(ev))])
    fact_ev = ev[["event_id", "member_id", "event_type", "event_ts", "source_system"]]

    # ---------------- dim_member with messy channel codes and null county
    variants = {"direct": ["Direct", "DIRECT", "Direct ", "dir"], "broker": ["Broker", "BROKER", "brkr", " broker"],
                "online": ["Online", "ONLINE", "web", "On-line"], "agent": ["Agent", "AGENT", "agt", "agent "]}
    raw_channel = mem.channel.copy()
    messy = rng.random(n) < 0.15
    raw_channel[messy] = [rng.choice(variants[c]) for c in mem.channel[messy]]
    county = mem.county_fips.astype(object).copy()
    null_fips = rng.random(n) < C.DQ_NULL_FIPS_RATE
    county[null_fips] = None
    dim_member = pd.DataFrame({
        "member_id": mem.member_id, "enroll_date": enroll_date, "plan_id": mem.plan_id,
        "county_fips": county, "age": mem.age, "sex": mem.sex,
        "dual_eligible_flag": mem.dual_eligible_flag, "lis_flag": mem.lis_flag,
        "enrollment_channel": raw_channel})

    tables = {"dim_member": dim_member, "dim_plan": dim_plan, "dim_county": dim_county,
              "fact_enrollment_span": fact_span, "fact_member_month": fact_mm,
              "fact_onboarding_event": fact_ev, "dim_date": dim_date}
    for name, df in tables.items():
        df.to_csv(C.RAW / f"{name}.csv", index=False)
    if C.SAMPLE.exists():
        shutil.rmtree(C.SAMPLE)
    C.SAMPLE.mkdir(parents=True)
    sample_ids = set(rng.choice(mem.member_id.values, 300, replace=False))
    for name, df in tables.items():
        if "member_id" in df.columns:
            s = df[df.member_id.isin(sample_ids)].head(1000)
        else:
            s = df.head(1000)
        s.to_csv(C.SAMPLE / f"{name}.csv", index=False)

    # ---------------- realized truth
    landmark = cover_end >= month_end(e + 3)  # enrolled at the start of coverage month 4 (day ~90)
    feasible = lambda arr_day, flag: flag & ((enroll_date + np.maximum(arr_day, 0).astype("timedelta64[D]")) <= cover_end)
    wc_r = feasible(fun["wc_day"], fun["wc"])
    hra_r = feasible(fun["hra_day"], fun["hra"])
    pcp_r = feasible(fun["pcp_day"], fun["pcp"])
    online = mem.channel.values == "online"
    cov_months = np.where(churned, exit_idx - e + 1, C.N_CAL_MONTHS - e)
    coh = (e >= 12) & (e <= 17)
    retained12 = cov_months[coh] >= 12
    exp_mm = cov_months
    truth = {
        "seed": C.SEED,
        "description": "Realized planted values from src/generate_data.py. Synthetic data only.",
        "row_counts": {k: int(len(v)) for k, v in tables.items()},
        "hazard_parameters": {
            "baseline_monthly_hazard": C.BASE_HAZARD, "oep_multiplier": C.OEP_MULT,
            "dual_multiplier": C.DUAL_MULT, "broker_multiplier": C.CHANNEL_MULT["broker"],
            "online_multiplier": C.CHANNEL_MULT["online"], "agent_multiplier": C.CHANNEL_MULT["agent"],
            "pcp_visit_90d_multiplier": C.PCP90_MULT},
        "funnel_parameters": {
            "p_welcome_call_complete": C.P_WELCOME, "p_hra_given_welcome": C.P_HRA,
            "p_hra_given_welcome_online": C.P_HRA_ONLINE, "p_pcp_given_hra": C.P_PCP_GIVEN_HRA,
            "p_pcp_no_hra": C.P_PCP_NO_HRA, "dual_pcp_multiplier": C.DUAL_PCP_MULT,
            "dual_dsnp_multiplier": C.DUAL_DSNP_MULT},
        "realized": {
            "retention_12m_jan_jun_2024_cohorts": float(retained12.mean()),
            "n_jan_jun_2024_cohorts": int(coh.sum()),
            "landmark_members": int(landmark.sum()),
            "welcome_complete_rate_landmark": float(wc_r[landmark].mean()),
            "hra_rate_landmark": float(hra_r[landmark].mean()),
            "hra_rate_online_landmark": float(hra_r[landmark & online].mean()),
            "hra_rate_non_online_landmark": float(hra_r[landmark & ~online].mean()),
            "pcp90_rate_landmark": float(pcp_r[landmark].mean()),
            "pcp90_given_hra_landmark": float(pcp_r[landmark & hra_r].mean()),
            "pcp90_given_no_hra_landmark": float(pcp_r[landmark & ~hra_r].mean()),
            "dual_share": float(mem.dual_eligible_flag.mean()),
            "dsnp_share_dual": float((mem.plan_id[mem.dual_eligible_flag == 1].isin(["P10", "P11", "P12"])).mean()),
            "dsnp_share_nondual": float((mem.plan_id[mem.dual_eligible_flag == 0].isin(["P10", "P11", "P12"])).mean()),
            "first_island_disenrollments": int(churned.sum()),
            "mean_covered_months": float(exp_mm.mean()),
        },
        "data_quality": {
            "duplicate_onboarding_events": int(ev.is_duplicate.sum()),
            "retro_terminations": int(retro.sum()),
            "members_with_overlapping_spans": int(len(overlap_members)),
            "null_county_fips": int(null_fips.sum()),
            "members_pcp_visit_before_enroll": int(len(pre_members)),
            "nonstandard_channel_codes": int(messy.sum()),
            "plan_change_spans": int(sum(len(v) for v in plan_change.values())),
            "reenrollment_spans": int(len(re_rows)),
        },
    }
    C.TRUTH.write_text(json.dumps(truth, indent=2))
    print(json.dumps(truth["row_counts"]))


if __name__ == "__main__":
    main()
