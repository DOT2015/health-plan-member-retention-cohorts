"""Self-contained interactive dashboard (dashboard/index.html). Plotly JS is inlined once; no CDN."""
import json

import pandas as pd
import plotly.graph_objects as go

import config as C

BLUE, ORANGE, AQUA, GRAY = "#2a78d6", "#eb6834", "#1baf7a", "#8a8984"
LAYOUT = dict(template="plotly_white", font=dict(family="Inter, Segoe UI, Arial, sans-serif", size=12, color="#0b0b0b"),
              margin=dict(l=70, r=30, t=60, b=60), hoverlabel=dict(bgcolor="white"))


def heatmap():
    cm = pd.read_csv(C.OUTPUTS / "01_cohort_retention_matrix.csv")
    cm["cohort"] = cm.cohort_yyyymm.astype(str).str[:4] + "-" + cm.cohort_yyyymm.astype(str).str[4:]
    piv = cm.pivot(index="cohort", columns="months_since_enroll", values="retention_pct")
    size = cm.groupby("cohort").cohort_size.first().reindex(piv.index)
    custom = [[size.loc[c]] * piv.shape[1] for c in piv.index]
    fig = go.Figure(go.Heatmap(
        z=piv.values, x=piv.columns, y=piv.index, colorscale="Blues", zmin=60, zmax=100,
        customdata=custom, colorbar=dict(title="Retained %"),
        hovertemplate="Cohort %{y}<br>Month %{x}<br>Retained %{z:.1f}%<br>Cohort size %{customdata:,}<extra></extra>"))
    fig.update_layout(**LAYOUT, height=640, title="Cohort retention (blank cells are not yet observable)",
                      xaxis_title="Months of continuous enrollment completed", yaxis_title="Enrollment cohort",
                      yaxis=dict(autorange="reversed"))
    return fig


def funnel():
    f = pd.read_csv(C.OUTPUTS / "02_onboarding_funnel_by_channel.csv")
    order = ["all", "direct", "broker", "agent", "online"]
    f = f.set_index("channel").loc[order].reset_index()
    fig = go.Figure()
    steps = [("members", "Landmark members", GRAY), ("welcome_complete", "Welcome call complete", BLUE),
             ("hra_complete", "HRA complete", ORANGE), ("pcp_after_hra", "PCP visit after HRA", AQUA)]
    for col, label, color in steps:
        pct = 100 * f[col] / f.members
        fig.add_bar(x=f.channel.str.capitalize(), y=pct, name=label, marker_color=color,
                    customdata=f[col], hovertemplate=f"{label}<br>%{{x}}: %{{y:.1f}}% (n=%{{customdata:,}})<extra></extra>")
    fig.update_layout(**LAYOUT, barmode="group", height=430, yaxis_title="% of members (within 90 days)",
                      title="Onboarding funnel by channel. Step conversion HRA|welcome: " + ", ".join(
                          f"{c} {v:.0f}%" for c, v in zip(f.channel, f.step_hra_given_welcome)),
                      legend=dict(orientation="h", y=-0.15))
    return fig


def trend():
    s = pd.read_csv(C.OUTPUTS / "04_disenrollment_seasonality.csv", parse_dates=["month_start"])
    s = s[s.month_start >= "2023-07-01"]
    fig = go.Figure()
    for y in [2024, 2025]:
        fig.add_vrect(x0=f"{y}-01-01", x1=f"{y}-03-31", fillcolor="#ecebe7", line_width=0, layer="below",
                      annotation_text="OEP", annotation_position="top left")
    fig.add_scatter(x=s.month_start, y=s.effective_rate_pct, name="Effective end date", mode="lines+markers",
                    line=dict(color=BLUE, width=2), customdata=s[["effective_disenrollments", "members_at_start"]],
                    hovertemplate="%{x|%b %Y}<br>%{y:.2f}% (%{customdata[0]:,} of %{customdata[1]:,})<extra></extra>")
    fig.add_scatter(x=s.month_start, y=s.snapshot_rate_pct, name="Month-end snapshot (posted only)", mode="lines",
                    line=dict(color=ORANGE, width=2, dash="dash"), customdata=s.retro_terms,
                    hovertemplate="%{x|%b %Y}<br>%{y:.2f}%<br>retro-terms missed: %{customdata}<extra></extra>")
    fig.update_layout(**LAYOUT, height=400, title="Monthly disenrollment rate", yaxis_title="% of members enrolled at month start",
                      yaxis_rangemode="tozero", legend=dict(orientation="h", y=-0.2))
    return fig


def segment_table():
    seg = pd.read_csv(C.OUTPUTS / "05_segment_risk_table.csv")
    seg = seg.sort_values("retention_12m_pct")
    fmt = lambda v: "suppressed" if pd.isna(v) else f"{v:.1f}%"
    fig = go.Figure(go.Table(
        header=dict(values=["Channel", "Plan type", "Dual status", "Members", "12-mo retention", "PCP visit <=90d"],
                    fill_color="#f0efec", align="left", font=dict(size=12)),
        cells=dict(values=[seg.channel, seg.plan_type, seg.dual_status, seg.members.map("{:,}".format),
                           seg.retention_12m_pct.map(fmt), seg.pcp_visit_90d_pct.map(fmt)],
                   align="left", height=24)))
    fig.update_layout(**{**LAYOUT, "margin": dict(l=10, r=10, t=50, b=10)}, height=700,
                      title="Segment risk table (lowest retention first; cells with n < 30 suppressed)")
    return fig


def main():
    r = json.loads((C.REPORTS / "results.json").read_text())
    figs = [("cohorts", "1. Cohort retention", heatmap()), ("funnel", "2. Onboarding funnel", funnel()),
            ("trend", "3a. Disenrollment trend", trend()), ("segments", "3b. Segment risk", segment_table())]
    parts = []
    for i, (anchor, title, fig) in enumerate(figs):
        html = fig.to_html(include_plotlyjs=(i == 0), full_html=False, div_id=f"{anchor}-plot",
                           config={"displaylogo": False})
        parts.append(f'<section id="{anchor}"><h2>{title}</h2>{html}</section>')
    hr = r["cox_adjusted_pcp"]
    tiles = [
        ("12-month retention", f"{100 * r['retention_12m_all_km']['est']:.1f}%", "all cohorts, Kaplan-Meier"),
        ("PCP visit within 90 days", f"{r['funnel']['all']['pct_pcp_all']:.1f}%", "of members enrolled at day 90"),
        ("Hazard ratio, PCP visit", f"{hr['hr']:.2f}", f"95% CI {hr['lo']:.2f}-{hr['hi']:.2f}, adjusted"),
        ("OEP vs rest of year", f"{r['seasonality']['oep_ratio']:.2f}x", "monthly disenrollment rate"),
    ]
    tile_html = "".join(f'<div class="tile"><div class="k">{a}</div><div class="v">{b}</div><div class="s">{c}</div></div>'
                        for a, b, c in tiles)
    nav = " | ".join(f'<a href="#{a}">{t}</a>' for a, t, _ in figs)
    page = f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"><title>Member retention dashboard (synthetic data)</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
body {{ font-family: Inter, 'Segoe UI', Arial, sans-serif; margin: 0 auto; max-width: 1150px; padding: 24px; color: #0b0b0b; background: #fcfcfb; }}
h1 {{ font-size: 22px; margin-bottom: 4px; }} h2 {{ font-size: 17px; margin-top: 36px; border-bottom: 1px solid #e4e3df; padding-bottom: 6px; }}
.note {{ color: #52514e; font-size: 13px; }} nav a {{ color: #2a78d6; text-decoration: none; font-size: 14px; }}
.tiles {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; margin: 18px 0; }}
.tile {{ background: white; border: 1px solid #e4e3df; border-radius: 8px; padding: 12px 14px; }}
.tile .k {{ font-size: 12px; color: #52514e; }} .tile .v {{ font-size: 26px; font-weight: 600; margin: 4px 0; }} .tile .s {{ font-size: 11px; color: #52514e; }}
</style></head><body>
<h1>Medicare Advantage new-member retention</h1>
<div class="note">All data is synthetic, generated by <code>src/generate_data.py</code> (seed 42). No real members, plans, or organizations.
Built by Adedeji M. Olugboja.</div>
<div class="tiles">{tile_html}</div>
<nav>{nav}</nav>
{''.join(parts)}
</body></html>"""
    C.DASHBOARD.mkdir(exist_ok=True)
    (C.DASHBOARD / "index.html").write_text(page)
    print(f"dashboard: {(C.DASHBOARD / 'index.html').stat().st_size / 1e6:.1f} MB")


if __name__ == "__main__":
    main()
