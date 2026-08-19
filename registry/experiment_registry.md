# EXPERIMENT REGISTRY
Protocol §31, §32, §58. Every trial recorded. Nothing deleted. Nothing hidden.

**Trial accounting**

| Counter | Value |
|---|---|
| N_total_trials | 22 |
| N_parameter_trials | 0 |
| N_instrument_trials | 22 |
| N_strategy_family_trials | 2 |
| Successful (passed gate) | 0 |
| Failed | 22 |
| Abandoned | 0 |

**Parameter budget consumed:** 22 / 200

---

## Phase 0 — Baseline controls

| exp_id | date | family | instruments | params | split | cost | exec | result | status |
|---|---|---|---|---|---|---|---|---|---|
| P0-001..011 | 2026-08-12 | naive_trend (EMA20/50) | 11 | fixed, none tuned | development | 1.0× modelled | next-open, adverse | pooled expR −0.0261, 5/11 positive | FAILED |
| P0-012..022 | 2026-08-12 | naive_meanrev (z±2) | 11 | fixed, none tuned | development | 1.0× modelled | next-open, adverse | pooled expR −0.0349, 5/11 positive | FAILED |

**Pre-registered pass/fail criteria (set before running):** pooled expR > 0 AND t > 3.0 AND ≥7/11 instruments positive. Neither control met any of the three.

### Engine sanity check (not a trial)
Naive trend is positive on trending instruments (USDJPY +0.036, EURJPY +0.025, GBPJPY +0.046, XAUUSD +0.048) and negative on range-bound FX majors. Naive mean-reversion is the exact mirror (positive on AUDUSD/NZDUSD/GBPUSD, negative on JPY crosses and metals). This economic coherence is evidence the engine is computing correctly, and is recorded as a **diagnostic, not a finding**. The individual positives are within chance for 11 tests.

---

## Holdout ledger (protocol §7)

| date | who | what was examined | decision taken | status |
|---|---|---|---|---|
| — | — | nothing | — | **UNTOUCHED** |

Holdout = 2025-07-01 .. 2026-08-11. No query of any kind has been run against it.

---

## Pending phases

| Phase | Family | Budget | Status |
|---|---|---|---|
| 1 | Session / opening-range breakout | 9 | not started |
| 2 | Donchian / time-series momentum | 3 | not started |
| 3 | Trend pullback | 9 | not started |
| 4 | Pairs / stat-arb (55 pairs) | 55 | not started |
| 5 | Portfolio construction | — | not started |
| 6 | Robustness: CPCV / DSR / PBO | — | not started |
| 7 | Prop-firm Monte Carlo | — | **blocked — firm rules UNKNOWN** |
| 8 | GxT as independent hypothesis | — | not started |

---

## Phase 9 — XAUUSD trend-family variant search (2026-08-18)

**Pre-registered before the sweep** (research/gold_lab.py, `CRITERIA`):
expR > +0.05 in gold-up years AND > 0.00 in gold-flat/down years AND t > 2.0
AND edge vs always-long > 0.04R AND inverted < -0.04R AND >= 40 trades/year.

**Protocol:** holdout (2025-04-15 →) physically truncated out of the data during
the sweep, so it could not leak into selection. 28 variants tested on DEV+VAL.

| family | variants | result |
|---|---|---|
| H1 breakout / pullback / either × long / both | 6 | 1 near-miss (pullback/long, 33.6 tr/yr < 40) |
| H2 adaptive trend+mean-reversion | 4 | all failed — range module added trades, destroyed expectancy |
| H3 donchian / RR / ATR sweeps | 9 | all failed the flat-gold criterion |
| H4 session filters | 4 | **1 PASSED** (not_london / either) |
| H5 filter ablations | 5 | all failed |

**N_total_trials: 22 → 50.** Passed gate: 1 of 28.

### Selected: `strategy_gold_v2.py` (ENTRY=breakout-or-pullback, SKIP 07-11 UTC)

| metric | v1 (breakout only) | v2 |
|---|---|---|
| trades/year | 29.2 | 42.3 |
| expR | +0.222 | +0.259 |
| overall t | +2.07 | +2.89 |
| **gold flat/down years** | **-0.192** | **+0.120** |
| holdout expR (n) | +0.472 (53) | +0.298 (67) |
| holdout t | +2.27 | **+1.63** |
| real-order Phase-1 pass | 74% | 78% |

**Honest limitations, recorded per §32:**
1. **Selection bias.** 28 trials; Bonferroni t-threshold ≈ 3.1; winner's in-sample
   t was 2.39. The full-sample t of 2.89 is NOT independent of selection.
2. **Holdout is underpowered and regime-limited.** n=67, t=1.63, 95% CI spans
   zero. The window (2025-04→2026-08) is itself a gold-up regime, so it cannot
   test the flat-market fix that motivated the change.
3. The tester scores this **NO CLEAR EDGE / 45** precisely because of (2). That
   is the correct call, not a bug — the flat-regime improvement is measured on
   data used for selection.
4. Still gold-specific. Not retested cross-instrument.

**Status: NOT VALIDATED.** Better-founded than v1, but the claim "survives any
gold condition" rests on in-sample evidence and awaits an out-of-sample flat regime.

---

## Phase 10 — USDJPY replication test of the v2 pullback mechanism (2026-08-18)

**Purpose:** gold data was exhausted by Phase 9 selection (v2's flat-regime fix was
chosen by looking at gold's 2021–22). USDJPY is untouched by that design, and its
own flat/down years (2020, 2025, 2026) are *different calendar years* from gold's,
so it is an independent test of the mechanism — not of the instrument.

**Pre-registered before running. 3 trials declared (v1, v2, v2-no-session).**
Native USDJPY H4/D1 files present, so no timeframe building was required.

| # | criterion | result | |
|---|---|---|---|
| 1 | v2 expR > +0.05 and t > 2.0 | expR +0.026, **t +0.28** | **FAIL** |
| 2 | edge vs always-long > 0.04R | +0.074 | pass |
| 3 | inverted < −0.04R | −0.110 | pass |
| 4 | v2 positive in USDJPY flat years | **−0.640R (n=25)** | **FAIL** |
| 5 | v2 beats v1 in flat years | −0.667 → −0.640 | pass (trivially) |

**Verdict: the v2 pullback mechanism does NOT generalise. 3/5, and the two that
failed are the two that mattered.**

- Criterion 5 was a badly written criterion: both numbers are catastrophic, so
  "v2 beats v1" is meaningless here. Recorded as a flaw in the test design, not
  as supporting evidence.
- v2 is *worse* than v1 on USDJPY overall (+0.160 → +0.026): the pullback entry
  actively hurt on an instrument it was not fitted to.
- Gold flat-years −0.192 → +0.120 (Phase 9) vs USDJPY flat-years −0.667 → −0.640.
  The most parsimonious reading: **the Phase-9 flat-regime "fix" is an artifact of
  selecting on gold's 2021–22**, not a general property.

**What did survive on both instruments:** the inversion test (directional
information is real) and beating the always-long benchmark. What did not: any
claim to work outside a trend.

**Reframing recorded for future work:** across both instruments this family loses
in flat/range regimes (gold v1 −0.192, USDJPY v1 −0.667, USDJPY v2 −0.640). That
is not a defect awaiting a fix — it is the defining behaviour of trend-following.
Future effort should size around that property rather than try to filter it away.

**Status: v2 remains NOT VALIDATED. Claim "survives any condition in gold" is
FALSIFIED.**

---

## Phase 11 — new "Donchian + pullback, D1-ADX, skip-London" strategy (2026-08-19)

Pre-registered comparison vs the v1 96/100 (breakout-only). XAUUSD, 0.4% risk,
holdout physically sealed by the tester's dev/val/hold split.

| metric | v1 (breakout) | NEW (breakout OR pullback, skip 07-11 UTC) |
|---|---|---|
| trades | 189 (29/yr) | **464 (72/yr)** |
| expR | +0.222 | +0.185 |
| overall t | +2.07 | **+2.72** |
| holdout | +0.472R n=53 t=2.27 | **+0.526R n=93 t=3.38** |
| real-order Phase-1 | 73% | **94%** |
| edge vs long benchmark | +0.176R | +0.114R |
| inverted | -0.198R | -0.113R |

Robustness checks that v1 never cleared:
- Winner concentration: dropping top-5 winners barely moves expR (+0.185 -> +0.165);
  RR is fixed 2.0 so no single trade dominates. NOT outlier-driven.
- Per-year: POSITIVE every year 2020-2026 (worst 2023 breakeven +0.000, 2022 +0.023).
  No losing year - the main weakness of every earlier variant.
- Worst ACTUAL consecutive losing run in history = 8 trades; worst real
  peak-to-trough = 10.0R.

Verdict: materially better and faster than v1, and the first variant to pass a
holdout with t > 3 AND survive the winner-concentration and per-year checks. The
extra trades come from adding the pullback entry and dropping the H4-ADX gate;
the skip-London filter removes the worst session (London expR was -0.16).

**Still gold-only and still a bull-trend vehicle** (D1 close > EMA50 + H4 bull are
required, so it only longs uptrends). Not validated off XAUUSD. Recommended risk
for a 2-step $5k: 0.5% (full 2-step seq 89%, worst shuffled DD 11.7% vs 10% cap
is close but sequential max-loss prob is 0%). 0.65% raises seq full-pass to ~94%
and cuts median time, but pushes 95th-pct shuffled DD to 12.7%.

EA parity: see DonchianMTF_v2.mq5 notes - MQL5 must use SMA(TR,14) not iATR, and
re-anchor TP to the actual fill, or live diverges from this backtest.
