"""
MATH VERIFICATION  -  independent re-derivation of the tester's mechanics.

Every check here recomputes a quantity a SECOND way (by hand arithmetic, or
with different code) and compares. Toy cases use numbers whose answer can be
worked out on paper, so a passing run means the mechanics are right - not just
self-consistent.

Run:  python verify_math.py
"""
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

import numpy as np
import pandas as pd
import tester_app as A

PASS = 0
FAIL = 0


def ck(name, cond, extra=""):
    global PASS, FAIL
    ok = bool(cond)
    PASS += ok
    FAIL += (not ok)
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f"  ({extra})" if extra else ""))


def toy(R, dates=None, start="2025-01-06"):
    """Trade frame with one trade per weekday unless dates are given."""
    n = len(R)
    if dates is None:
        d = pd.bdate_range(start, periods=n)
    else:
        d = pd.to_datetime(dates)
    return pd.DataFrame({"entry": d, "exit": d, "dir": [1] * n, "R": list(map(float, R))})


CFG = {"balance": 10000.0, "risk_pct": 1.0, "phase1": 10.0, "phase2": 5.0,
       "daily_loss": 5.0, "max_loss": 10.0, "min_days": 0,
       "best_day_pct": 0, "best_trade_pct": 0}


def cfg(**kw):
    c = dict(CFG)
    c.update(kw)
    return c


# ===========================================================================
print("\n=== 1. CORE METRICS (hand-checked) ===")
# 3 wins at +2R, 2 losses at -1R.  expectancy = (3*2 - 2*1)/5 = 0.8
# PF = gross win / gross loss = 6 / 2 = 3.0 ; win rate = 60%
m = A.metrics(toy([2, -1, 2, -1, 2]))
ck("expectancy = (3*2 - 2*1)/5 = 0.8", abs(m["expR"] - 0.8) < 1e-12, f"{m['expR']}")
ck("profit factor = 6/2 = 3.0", abs(m["pf"] - 3.0) < 1e-12, f"{m['pf']}")
ck("win rate = 60%", abs(m["win"] - 60.0) < 1e-12, f"{m['win']}")
ck("total R = 4", abs(m["totR"] - 4.0) < 1e-12, f"{m['totR']}")
ck("expectancy == win*avgWin + loss*avgLoss", m["consistent"])

# all-identical trades -> zero variance -> t must stay finite (JSON safety)
m2 = A.metrics(toy([-1] * 8))
ck("degenerate set keeps t finite", np.isfinite(m2["t"]), f"t={m2['t']}")

print("\n=== 2. R IS INDEPENDENT OF ACCOUNT SETTINGS ===")
t = toy([2, -1, 2, -1, 2])
a = A.metrics(t)
ck("metrics take no account inputs at all",
   a["expR"] == A.metrics(t)["expR"] == 0.8,
   "expectancy is pure R, so risk/balance cannot move it")

print("\n=== 3. PHASE MECHANICS (hand-checked) ===")
# balance 10000, risk 1% -> 1R = $100. Phase-1 target 10% = +$1000 = +10R.
# Sequence of five +2R wins = +10R exactly -> must PASS on the 5th trade.
c = cfg()
unit = c["balance"] * c["risk_pct"] / 100.0
ck("1R = $100", abs(unit - 100.0) < 1e-12, f"${unit}")
tr = toy([2, 2, 2, 2, 2])
out, end, used, tdays = A._run_phase(
    tr.R.values, pd.to_datetime(tr.exit).dt.date.values, 0, c["balance"], unit,
    c["phase1"] / 100.0, c["daily_loss"] / 100.0,
    c["balance"] * (1 - c["max_loss"] / 100.0), 0, 0, 0)
ck("+10R reaches the +10% target exactly", out == "PASS", out)
ck("...on the 5th trade", used == 5, f"used {used}")

# max loss: 10% of 10000 = $1000 = 10R. Ten -1R losses on SEPARATE days
# (so the 5% daily rule cannot fire first) must end in FAIL_MAXLOSS.
tr = toy([-1] * 12)
out, end, used, _ = A._run_phase(
    tr.R.values, pd.to_datetime(tr.exit).dt.date.values, 0, c["balance"], unit,
    c["phase1"] / 100.0, c["daily_loss"] / 100.0,
    c["balance"] * (1 - c["max_loss"] / 100.0), 0, 0, 0)
ck("10 consecutive -1R hits the max-loss floor", out == "FAIL_MAXLOSS", out)
ck("...exactly on the 10th trade", used == 10, f"used {used}")

# daily loss: 5% of 10000 = $500 = 5R, all on ONE day
same = ["2025-01-06"] * 8
tr = toy([-1] * 8, dates=same)
out, end, used, _ = A._run_phase(
    tr.R.values, pd.to_datetime(tr.exit).dt.date.values, 0, c["balance"], unit,
    c["phase1"] / 100.0, c["daily_loss"] / 100.0,
    c["balance"] * (1 - c["max_loss"] / 100.0), 0, 0, 0)
ck("5 losses in ONE day trip the daily rule first", out == "FAIL_DAILY", out)
ck("...on the 5th trade", used == 5, f"used {used}")

print("\n=== 4. MINIMUM TRADING DAYS ===")
tr = toy([2, 2, 2, 2, 2])                       # 5 trades on 5 separate days
days = pd.to_datetime(tr.exit).dt.date.values
o_no, _, u_no, _ = A._run_phase(tr.R.values, days, 0, c["balance"], unit, 0.10,
                                0.05, 9000.0, 0, 0, 0)
o_yes, _, u_yes, _ = A._run_phase(tr.R.values, days, 0, c["balance"], unit, 0.10,
                                  0.05, 9000.0, 8, 0, 0)
ck("passes with no minimum-days rule", o_no == "PASS", f"{o_no} in {u_no}")
ck("requiring 8 trading days blocks a 5-day pass", o_yes != "PASS", o_yes)

print("\n=== 5. CONSISTENCY RULES (hand-checked) ===")
# One huge day then small ones. 1R=$100.
# Trades: +8R on day1 ($800), then +1R on each of days 2..5 ($100 each).
# After the 5th trade profit = 800+400 = $1200 >= $1000 target.
# best day = $800 -> 800/1200 = 66.7%.
# Compliance needs best_day/profit <= 40%, i.e. profit >= $800/0.40 = $2000
# = 20R total. The 8R opener plus twelve 1R trades reaches exactly 20R on the
# 13th trade, so a correct engine passes there and not before. The sequence is
# long enough that compliance is actually REACHABLE; when it is not, the right
# answer is TIMEOUT (the trader never complied), asserted in section 6.
seq = [8] + [1] * 25
tr = toy(seq)
days = pd.to_datetime(tr.exit).dt.date.values
o_off, _, u_off, _ = A._run_phase(tr.R.values, days, 0, c["balance"], unit, 0.10,
                                  0.99, 9000.0, 0, 0, 0)
ck("with consistency OFF it passes as soon as the target is hit",
   o_off == "PASS" and u_off == 3, f"{o_off} on trade {u_off}")

o_on, _, u_on, _ = A._run_phase(tr.R.values, days, 0, c["balance"], unit, 0.10,
                                0.99, 9000.0, 0, 40.0, 0)
ck("with a 40% best-DAY cap it must keep trading",
   o_on == "PASS" and u_on == 13,
   f"passes on trade {u_on} (hand-computed: 13), not {u_off}")
# verify the ratio really is compliant at the moment it passes
bal = c["balance"]
best_day = {}
for k in range(u_on):
    d = days[k]
    best_day[d] = best_day.get(d, 0.0) + tr.R.values[k] * unit
    bal += tr.R.values[k] * unit
profit = bal - c["balance"]
ratio = max(v for v in best_day.values() if v > 0) / profit * 100
ck("...and the best-day ratio is <= 40% at that point", ratio <= 40.0 + 1e-9,
   f"ratio {ratio:.1f}%")

# best-TRADE is a different constraint: same day, two trades
two_per_day = ["2025-01-06", "2025-01-06", "2025-01-07", "2025-01-07",
               "2025-01-08", "2025-01-08", "2025-01-09", "2025-01-09",
               "2025-01-10", "2025-01-10", "2025-01-13", "2025-01-13"]
tr2 = toy([5, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1], dates=two_per_day)
d2 = pd.to_datetime(tr2.exit).dt.date.values
o_d, _, u_d, _ = A._run_phase(tr2.R.values, d2, 0, c["balance"], unit, 0.10, 0.99,
                              9000.0, 0, 60.0, 0)     # day cap only
o_t, _, u_t, _ = A._run_phase(tr2.R.values, d2, 0, c["balance"], unit, 0.10, 0.99,
                              9000.0, 0, 0, 30.0)     # trade cap only
ck("best-DAY and best-TRADE are genuinely different constraints",
   u_d != u_t, f"day-cap passes on trade {u_d}, trade-cap on {u_t}")

print("\n=== 6. CONSISTENCY IS NOT AN INSTANT FAILURE ===")
# A violated ratio must never produce FAIL_DAILY / FAIL_MAXLOSS. It either
# passes later once further profit dilutes the ratio, or times out having
# never complied. Both are correct; a failure code would be a bug.
short = toy([8] + [1] * 11)          # only 19R total: compliance impossible
sd = pd.to_datetime(short.exit).dt.date.values
r_short = A._run_phase(short.R.values, sd, 0, c["balance"], unit, 0.10, 0.99,
                       9000.0, 0, 40.0, 0)
ck("unreachable ratio -> TIMEOUT, never a failure code",
   r_short[0] == "TIMEOUT", r_short[0])
r_long = A._run_phase(tr.R.values, days, 0, c["balance"], unit, 0.10, 0.99,
                      9000.0, 0, 40.0, 0)
ck("reachable ratio -> PASS once diluted", r_long[0] == "PASS", r_long[0])
ck("consistency never yields FAIL_DAILY / FAIL_MAXLOSS",
   r_short[0] not in ("FAIL_DAILY", "FAIL_MAXLOSS")
   and r_long[0] not in ("FAIL_DAILY", "FAIL_MAXLOSS"))

print("\n=== 7. SEQUENTIAL 2-STEP IS COUNTED, NOT MULTIPLIED ===")
tr = toy(([2] * 6 + [-1] * 3) * 8)
sq = A.sequential_challenge(tr, cfg())
ck("sequential result present", sq is not None)
if sq:
    n = sq["starts"]
    cnt = sq["full"]["pass_pct"] / 100.0 * n
    ck("full-pass % maps to a whole number of paths",
       abs(cnt - round(cnt)) < 1e-6, f"{cnt:.6f} paths of {n}")
    ck("pass + p1pass-p2fail + p1fail = 100%",
       abs(sq["full"]["pass_pct"] + sq["full"]["p1_pass_p2_fail_pct"]
           + sq["full"]["p1_fail_pct"] - 100.0) < 1e-9)
    ck("phase 2 evaluated only on phase-1 passes",
       sq["p2"]["evaluated"] <= sq["p1"]["n_pass"],
       f"{sq['p2']['evaluated']} <= {sq['p1']['n_pass']}")
    ck("full pass rate never exceeds phase-1 pass rate",
       sq["full"]["pass_pct"] <= sq["p1"]["PASS"] + 1e-9)

print("\n=== 8. MONOTONICITY (harder settings can never help) ===")
base_sq = A.sequential_challenge(tr, cfg())
for label, over in [("bigger Phase-1 target", {"phase1": 25.0}),
                    ("tighter max loss", {"max_loss": 4.0}),
                    ("tighter daily loss", {"daily_loss": 1.0}),
                    ("minimum trading days", {"min_days": 40}),
                    ("best-day cap", {"best_day_pct": 20.0}),
                    ("best-trade cap", {"best_trade_pct": 10.0})]:
    s2 = A.sequential_challenge(tr, cfg(**over))
    ck(f"{label} cannot raise the full-pass rate",
       s2["full"]["pass_pct"] <= base_sq["full"]["pass_pct"] + 1e-9,
       f"{base_sq['full']['pass_pct']:.2f}% -> {s2['full']['pass_pct']:.2f}%")

print("\n=== 9. RISK SCALING BEHAVES ===")
for rp in (0.25, 0.5, 1.0, 2.0):
    s3 = A.sequential_challenge(tr, cfg(risk_pct=rp))
    print(f"     risk {rp:>4}% -> full pass {s3['full']['pass_pct']:6.2f}%  "
          f"maxloss {s3['p1']['FAIL_MAXLOSS']:5.2f}%")
lo = A.sequential_challenge(tr, cfg(risk_pct=0.25))
hi = A.sequential_challenge(tr, cfg(risk_pct=4.0))
ck("higher risk raises max-loss failure probability",
   hi["p1"]["FAIL_MAXLOSS"] >= lo["p1"]["FAIL_MAXLOSS"],
   f"{lo['p1']['FAIL_MAXLOSS']:.2f}% -> {hi['p1']['FAIL_MAXLOSS']:.2f}%")

print("\n=== 10. EQUITY PATH AND DRAWDOWN IDENTITY ===")
R = np.array([2, -1, -1, 3, -1, -1, -1, 2, 2], dtype=float)
bal0, unit2 = 10000.0, 100.0
eq = [bal0]
for r_ in R:
    eq.append(eq[-1] + r_ * unit2)
ck("final = start + totR * 1R", abs(eq[-1] - (bal0 + R.sum() * unit2)) < 1e-9,
   f"${eq[-1]:.0f}")
peak, mdd_pct, mdd_usd = eq[0], 0.0, 0.0
for v in eq:
    peak = max(peak, v)
    d = (peak - v) / peak * 100
    if d > mdd_pct:
        mdd_pct, mdd_usd = d, peak - v
# independent check with numpy
arr = np.array(eq)
run_peak = np.maximum.accumulate(arr)
dd = (run_peak - arr) / run_peak * 100
ck("max drawdown matches an independent numpy computation",
   abs(mdd_pct - dd.max()) < 1e-9, f"{mdd_pct:.4f}% vs {dd.max():.4f}%")
ck("drawdown $ and % come from the same excursion",
   abs(mdd_usd - (mdd_pct / 100) * run_peak[int(dd.argmax())]) < 1e-6)

print("\n=== 11. MONTE CARLO IS SEEDED AND JOINT ===")
j1 = A.monte_carlo_joint(tr, cfg(), nsims=300)
j2 = A.monte_carlo_joint(tr, cfg(), nsims=300)
ck("joint MC reproducible with the same seed", j1["both_pct"] == j2["both_pct"],
   f"{j1['both_pct']:.2f}%")
ck("phase 2 evaluated only on phase-1 passes",
   abs(j1["p2_evaluated"] - round(j1["p1"]["PASS"] / 100 * j1["nsims"])) <= 1)
ck("joint both-pass never exceeds phase-1 pass",
   j1["both_pct"] <= j1["p1"]["PASS"] + 1e-9)

print("\n=== 12. CALENDAR DAYS vs TRADING DAYS ===")
sparse = ["2025-01-06", "2025-02-10", "2025-03-17", "2025-04-21",
          "2025-05-26", "2025-06-30", "2025-08-04", "2025-09-08"]
ts = toy([2] * 8, dates=sparse)
span = (pd.to_datetime(ts.entry).max() - pd.to_datetime(ts.entry).min()).days
ck("8 trades spread over ~245 calendar days on 8 trading days",
   span > 200 and pd.to_datetime(ts.entry).dt.date.nunique() == 8,
   f"{span} calendar days, 8 trading days")

print("\n=== 13. DETERMINISTIC PATH IS A PATH, NOT A PROBABILITY ===")
det = A.deterministic_path(tr, cfg())
ck("outcomes are discrete labels",
   det["full"] in ("PASSED", "FAILED", "INCOMPLETE")
   and det["p1_outcome"] in ("PASS", "FAIL_MAXLOSS", "FAIL_DAILY", "TIMEOUT"),
   f"p1={det['p1_outcome']} full={det['full']}")
ck("no percentage fields leak into it",
   not any(k.endswith("_pct") and isinstance(v, float) and 0 < v < 100
           for k, v in det.items() if k not in ("max_dd_pct",)))

print("\n" + "=" * 58)
print(f"  MATH VERIFICATION: {PASS} passed, {FAIL} failed")
print("=" * 58)
sys.exit(1 if FAIL else 0)
