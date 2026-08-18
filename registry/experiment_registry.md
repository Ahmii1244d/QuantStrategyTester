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
