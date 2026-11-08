"""Recovered estimates vs. the generator's planted values (data/truth/planted_effects.json)."""
import re

import pytest

import config as C


def test_all_validation_rows_pass(results):
    failed = [v["effect"] for v in results["validation"] if not v["pass"]]
    assert not failed, failed


def test_cox_adjusted_ci_covers_planted(results, truth):
    hp = truth["hazard_parameters"]["pcp_visit_90d_multiplier"]
    x = results["cox_adjusted_pcp"]
    assert x["lo"] <= hp <= x["hi"]


def test_confounding_direction(results):
    # dual members visit less and leave more, so the crude HR is further below 1 than the adjusted HR
    assert results["cox_unadjusted_pcp"]["hr"] < results["cox_adjusted_pcp"]["hr"]


@pytest.mark.parametrize("term,key", [
    ("is_oep_month", "oep_multiplier"), ("dual_eligible_flag", "dual_multiplier"),
    ("channel[T.broker]", "broker_multiplier"), ("channel[T.online]", "online_multiplier"),
    ("pcp_visited", "pcp_visit_90d_multiplier"),
])
def test_poisson_rate_ratios_cover_planted(results, truth, term, key):
    x = results["poisson_rate_ratios"][term]
    assert x["lo"] <= truth["hazard_parameters"][key] <= x["hi"]


def test_retention_matches_realized(results, truth):
    assert abs(results["retention_12m_jan_jun_2024"] - truth["realized"]["retention_12m_jan_jun_2024_cohorts"]) < 0.005


def test_online_hra_leak(results):
    f = results["funnel"]
    others = [f[c]["step_hra_given_welcome"] for c in ["direct", "broker", "agent"]]
    assert f["online"]["step_hra_given_welcome"] < min(others) - 8


@pytest.mark.parametrize("tkey,rkey", [
    ("duplicate_onboarding_events", "duplicate_events_removed"),
    ("retro_terminations", "retro_terminations"),
    ("members_with_overlapping_spans", "members_with_overlapping_spans"),
    ("null_county_fips", "null_county_fips"),
    ("members_pcp_visit_before_enroll", "members_pcp_visit_before_enroll"),
    ("nonstandard_channel_codes", "nonstandard_channel_codes"),
])
def test_data_quality_counts_match_truth(results, truth, tkey, rkey):
    assert results["data_quality"][rkey] == truth["data_quality"][tkey]


def test_readme_claims_hold(results):
    km = results["km_landmark_12m"]
    # "the gap is widest for dual-eligible members"
    assert km["dual1_pcp1"]["ret12"] - km["dual1_pcp0"]["ret12"] > km["dual0_pcp1"]["ret12"] - km["dual0_pcp0"]["ret12"]
    # "dual-eligible broker enrollees lose the most"
    top = results["outreach_priority"][0]
    assert top["dual"] == 1 and top["channel"] == "broker"
    # executive summary says first-year revenue at 100% causal is below staff cost
    assert results["sizing"]["all_members"]["breakeven_causal_share"] > 1


def test_rendered_docs_have_no_placeholders():
    for p in [C.ROOT / "README.md", C.ROOT / "docs" / "executive_summary.md"]:
        assert not re.search(r"\{\{\w+\}\}", p.read_text()), p.name
