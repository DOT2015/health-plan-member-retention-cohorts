"""Shared paths, generator parameters, and sizing assumptions.

Every value here is a design input for the simulation, not a real-world figure.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
SAMPLE = ROOT / "data" / "sample"
TRUTH = ROOT / "data" / "truth" / "planted_effects.json"
OUTPUTS = ROOT / "data" / "outputs"
DB = ROOT / "data" / "warehouse.duckdb"
REPORTS = ROOT / "reports"
FIGURES = ROOT / "figures"
DASHBOARD = ROOT / "dashboard"
POWERBI = ROOT / "powerbi"

SEED = 42
N_MEMBERS = 28_000
FIRST_ENROLL = "2023-01"          # first enrollment cohort (month)
N_ENROLL_MONTHS = 30              # 2023-01 .. 2025-06
OBS_END = "2025-12-31"            # end of observation (right censoring)
N_CAL_MONTHS = 36                 # 2023-01 .. 2025-12

# --- planted hazard model (monthly, discrete time) ---
BASE_HAZARD = 0.012
OEP_MULT = 2.0                    # Jan-Mar
DUAL_MULT = 1.90
CHANNEL_MULT = {"direct": 1.00, "broker": 1.25, "online": 1.10, "agent": 1.00}
PCP90_MULT = 0.55

# --- planted funnel (first 90 days, each conditional on the previous step) ---
P_WELCOME = 0.68
P_HRA = 0.60
P_HRA_ONLINE = 0.45
P_PCP_GIVEN_HRA = 0.85
P_PCP_NO_HRA = 0.15
DUAL_PCP_MULT = 0.80
DUAL_DSNP_MULT = 1.60
P_DSNP_NONDUAL = 0.20
P_DUAL = 0.22

# --- planted data-quality rates ---
DQ_DUP_EVENT_RATE = 0.03
DQ_RETRO_TERM_RATE = 0.02
DQ_OVERLAP_MEMBER_RATE = 0.008
DQ_NULL_FIPS_RATE = 0.015
DQ_PCP_BEFORE_ENROLL_RATE = 0.003

# --- sizing assumptions (simulated) ---
REVENUE_PMPM = 1_000              # simulated revenue per member-month, USD
PCP_UPLIFT_PP = 0.10              # PCP-visit rate increase tested
CAUSAL_SHARES = [0.25, 0.50, 1.00]
ATTEMPTS_PER_MEMBER = 3           # outreach call attempts per member
MINUTES_PER_ATTEMPT = 15          # incl. documentation and scheduling
PRODUCTIVE_HOURS_PER_FTE_MONTH = 120
FTE_ANNUAL_COST = 65_000          # simulated loaded cost per outreach FTE, USD
SMALL_CELL_N = 30
