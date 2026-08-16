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
