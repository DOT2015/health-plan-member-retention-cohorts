"""Static PNG charts for the README and docs (matplotlib)."""
import json

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

import config as C

BLUE, ORANGE, AQUA, GRAY = "#2a78d6", "#eb6834", "#1baf7a", "#8a8984"
INK, INK2 = "#0b0b0b", "#52514e"
plt.rcParams.update({
    "figure.dpi": 110, "savefig.dpi": 150, "font.size": 10, "axes.titlesize": 12,
    "axes.titleweight": "bold", "axes.edgecolor": "#c9c8c2", "axes.labelcolor": INK2,
    "xtick.color": INK2, "ytick.color": INK2, "axes.grid": True, "grid.color": "#ecebe7",
    "grid.linewidth": 0.8, "axes.spines.top": False, "axes.spines.right": False,
    "legend.frameon": False, "figure.facecolor": "white",
})


def save(fig, name):
    C.FIGURES.mkdir(exist_ok=True)
    fig.savefig(C.FIGURES / name, bbox_inches="tight")
    plt.close(fig)


def km_headline(r):
    km = pd.read_csv(C.OUTPUTS / "km_curves_landmark.csv")
    fig, axes = plt.subplots(1, 2, figsize=(10, 4.2), sharey=True)
    for ax, dual, title in [(axes[0], 0, "Non-dual members"), (axes[1], 1, "Dual-eligible members")]:
        for pcp, color, label in [(1, BLUE, "PCP visit within 90 days"), (0, ORANGE, "No PCP visit within 90 days")]:
            k = km[(km.dual == dual) & (km.pcp_visit_90d == pcp)]
            ax.step(k.month, 100 * k.retention, where="post", color=color, lw=2, label=label)
            ax.fill_between(k.month, 100 * k.lo, 100 * k.hi, step="post", color=color, alpha=0.18, lw=0)
            last = k.iloc[-1]
            ax.annotate(f"{100 * last.retention:.1f}%", (12, 100 * last.retention), xytext=(4, 0),
                        textcoords="offset points", va="center", color=INK, fontsize=9)
        ax.set_title(title, loc="left")
        ax.set_xlabel("Months of continuous enrollment")
        ax.set_xticks(range(4, 13))
        ax.set_xlim(4, 12.9)
    axes[0].set_ylabel("Still enrolled (%)")
    axes[0].set_ylim(75, 100.5)
    axes[0].legend(loc="lower left")
    hr = r["cox_adjusted_pcp"]
    fig.suptitle("12-month retention by first PCP visit within 90 days (landmark: enrolled at day 90)",
                 x=0.01, ha="left", fontsize=12, fontweight="bold", y=1.07)
    fig.text(0.01, 0.995, f"Kaplan-Meier with 95% CI bands. Adjusted Cox HR {hr['hr']:.2f} "
             f"(95% CI {hr['lo']:.2f}-{hr['hi']:.2f}). Synthetic data.", color=INK2, fontsize=9)
    save(fig, "km_retention_pcp_by_dual.png")


def cohort_heatmap():
    cm = pd.read_csv(C.OUTPUTS / "01_cohort_retention_matrix.csv")
    cm = cm[cm.months_since_enroll <= 24]
    piv = cm.pivot(index="cohort_yyyymm", columns="months_since_enroll", values="retention_pct")
    fig, ax = plt.subplots(figsize=(10, 7))
    im = ax.imshow(piv.values, aspect="auto", cmap="Blues", vmin=60, vmax=100)
    ax.set_yticks(range(len(piv.index)))
    ax.set_yticklabels([f"{str(c)[:4]}-{str(c)[4:]}" for c in piv.index], fontsize=8)
    ax.set_xticks([c - piv.columns[0] for c in range(3, 25, 3)])
    ax.set_xticklabels(range(3, 25, 3))
    ax.set_xlabel("Months of continuous enrollment completed")
    ax.set_ylabel("Enrollment cohort")
    ax.grid(False)
    cb = fig.colorbar(im, ax=ax, shrink=0.8)
    cb.set_label("Retention (%)")
    ax.set_title("Cohort retention: share of each enrollment cohort still enrolled after k months", loc="left")
    save(fig, "cohort_retention_heatmap.png")


def funnel():
    f = pd.read_csv(C.OUTPUTS / "02_onboarding_funnel_by_channel.csv")
    f = f[f.channel != "all"].set_index("channel").loc[["direct", "broker", "agent", "online"]]
    steps = [("pct_welcome", "Welcome call complete", BLUE), ("pct_hra_all", "HRA complete", ORANGE),
             ("pct_pcp_all", "First PCP visit", AQUA)]
    x = np.arange(len(f))
    w = 0.26
    fig, ax = plt.subplots(figsize=(9, 4.2))
    for i, (col, label, color) in enumerate(steps):
        bars = ax.bar(x + (i - 1) * w, f[col], w - 0.02, color=color, label=label)
        for b, v in zip(bars, f[col]):
            ax.text(b.get_x() + b.get_width() / 2, v + 1, f"{v:.0f}", ha="center", fontsize=8, color=INK)
    ax.set_xticks(x)
    ax.set_xticklabels([c.capitalize() for c in f.index])
    ax.set_ylabel("Members completing step within 90 days (%)")
    ax.set_ylim(0, 85)
    ax.legend(ncol=3, loc="upper right")
    ax.set_title("Onboarding funnel by channel: online members drop off at the HRA step", loc="left")
    save(fig, "onboarding_funnel_by_channel.png")


def seasonality():
    s = pd.read_csv(C.OUTPUTS / "04_disenrollment_seasonality.csv", parse_dates=["month_start"])
    s = s[s.month_start >= "2023-07-01"]
    fig, ax = plt.subplots(figsize=(10, 4))
    for year in sorted(s.month_start.dt.year.unique()):
        jan = pd.Timestamp(f"{year}-01-01")
        if jan >= s.month_start.min():
            ax.axvspan(jan, pd.Timestamp(f"{year}-03-31"), color="#ecebe7", lw=0)
    ax.plot(s.month_start, s.effective_rate_pct, color=BLUE, lw=2, marker="o", ms=4, label="By effective end date")
    ax.plot(s.month_start, s.snapshot_rate_pct, color=ORANGE, lw=2, ls="--", label="Month-end snapshot (posted only)")
    ax.set_ylabel("Monthly disenrollment rate (%)")
    ax.set_xlabel("Month")
    ax.set_ylim(0, None)
    ax.legend(loc="upper right")
    ax.set_title("Disenrollment doubles in Jan-Mar (OEP, shaded); snapshots miss retro-terminations", loc="left")
    save(fig, "disenrollment_seasonality.png")


def forest(r):
    rows = [("PCP visit <=90d (unadjusted)", r["cox_unadjusted_pcp"], 0.55)]
    labels = {"pcp_visit_90d": ("PCP visit <=90d (adjusted)", 0.55), "dual_eligible_flag": ("Dual-eligible", 1.90),
              "channel_broker": ("Broker channel", 1.25), "channel_online": ("Online channel", 1.10),
              "channel_agent": ("Agent channel", 1.00), "plan_type_PPO": ("PPO plan", 1.0),
              "plan_type_D-SNP": ("D-SNP plan", 1.0)}
    for k, (lab, planted) in labels.items():
        rows.append((lab, r["cox_adjusted"][k], planted))
    fig, ax = plt.subplots(figsize=(8, 4.4))
    for i, (lab, x, planted) in enumerate(rows[::-1]):
        ax.plot([x["lo"], x["hi"]], [i, i], color=BLUE, lw=2)
        ax.plot(x["hr"], i, "o", color=BLUE, ms=7)
        ax.plot(planted, i, "|", color=ORANGE, ms=14, mew=2)
    ax.axvline(1, color=GRAY, lw=1)
    ax.set_yticks(range(len(rows)))
    ax.set_yticklabels([r_[0] for r_ in rows[::-1]])
    ax.set_xscale("log")
    ax.set_xticks([0.4, 0.6, 0.8, 1, 1.5, 2, 2.5])
    ax.get_xaxis().set_major_formatter(matplotlib.ticker.ScalarFormatter())
    ax.set_xlabel("Hazard ratio of disenrollment, months 4-12 (log scale)")
    ax.plot([], [], "o-", color=BLUE, label="Estimate with 95% CI")
    ax.plot([], [], "|", color=ORANGE, ms=12, mew=2, label="Planted generator value")
    ax.legend(loc="lower right")
    ax.set_title("Cox model: hazard ratios vs. planted values", loc="left")
    save(fig, "cox_hazard_ratios.png")


def sizing(r):
    s = r["sizing"]["all_members"]
    sc = pd.DataFrame(s["scenarios"])
    x = np.arange(len(sc))
    fig, ax = plt.subplots(figsize=(8, 4))
    ax.bar(x - 0.2, sc.revenue_first_year / 1e3, 0.38, color=BLUE, label="Revenue, first 12 months")
    ax.bar(x + 0.2, sc.revenue_24m / 1e3, 0.38, color=AQUA, label="Revenue, first 24 months")
    ax.axhline(s["annual_staff_cost"] / 1e3, color=ORANGE, lw=2, ls="--",
               label=f"Annual cost of {s['fte_funded']} outreach FTE")
    ax.set_xticks(x)
    ax.set_xticklabels([f"{int(100 * c)}% causal" for c in sc.causal_share])
    ax.set_ylabel("Simulated USD (thousands)")
    ax.legend(loc="upper left")
    ax.set_title("+10 pp PCP-visit rate: retained revenue vs. outreach cost (one enrollment year)", loc="left")
    save(fig, "sizing_scenarios.png")


def main():
    r = json.loads((C.REPORTS / "results.json").read_text())
    km_headline(r)
    cohort_heatmap()
    funnel()
    seasonality()
    forest(r)
    sizing(r)
    print("figures written:", sorted(p.name for p in C.FIGURES.glob("*.png")))


if __name__ == "__main__":
    main()
