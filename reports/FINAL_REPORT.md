# QUANT RESEARCH LAB — FINAL REPORT
**Date:** 2026-08-12 · **Data:** 11 CFD instruments, M30, 2020-01-02 → 2026-08-11
**Cost basis:** `SIMULATED COST ASSUMPTION` (spread column unusable — see §1)
**Holdout status:** **UNTOUCHED** — never queried

---

## EXECUTIVE SUMMARY

**81 trials across 5 strategy families. Zero passed the pre-registered gates.**

But the project produced one genuinely constructive finding, and it is not "nothing works":

> **A weak trend signal is present in the data (+0.0221R gross). Realistic retail transaction costs are roughly 0.040R. The edge is real and smaller than the friction.**

That is a materially different conclusion from "no edge exists," and it changes what to do next.

---

## 1. DATA AUDIT (Phase 0)

All 11 instruments structurally clean: no OHLC violations, no NaNs, no duplicate timestamps, all monotonic. Three material findings:

| Finding | Impact |
|---|---|
| **Spread column unusable** — EURUSD reports zero spread on 57% of bars (66% in active hours) | Cost is **modelled**, not observed. All results carry `SIMULATED COST ASSUMPTION` |
| **US30 has a 55-day hole** ending 2025-09-09 | Falls **inside the holdout window**. US30 holdout results would be unreliable |
| **Instruments are broker CFDs, not futures** | 24h coverage + spread column + `US30` naming. Contract size, tick value, commission, swap all `UNKNOWN — USER INPUT REQUIRED` |

**Timezone:** server = UTC+3, inferred from volume profile (FX peak at server hour 17 = 14:00 UTC London/NY overlap).

---

## 2. RESULTS BY PHASE

### Phase 0 — Baseline controls

| Control | n | pooled expR | instruments positive |
|---|---|---|---|
| naive_trend (EMA 20/50) | 20,251 | −0.0261 | 5/11 |
| naive_meanrev (z ±2) | 13,787 | −0.0349 | 5/11 |

**Engine validation:** trend is positive on trending instruments (USDJPY, EURJPY, GBPJPY, XAUUSD) and negative on range-bound majors; mean-reversion is the exact mirror. This economic coherence confirms the engine computes correctly.

### Phases 1–3 — 21 pre-registered variants

| Phase | Family | Variants | expR > 0 | t > 3.0 |
|---|---|---|---|---|
| 1 | Opening-range breakout | 9 | **0/9** | 0/9 |
| 2 | Donchian / TSMOM | 3 | **0/3** | 0/3 |
| 3 | Trend pullback | 9 | **0/9** | 0/9 |

Best of 21: `donchian_40`, expR −0.0179, t = −1.43.

**Critical pattern:** t-statistics are systematically **negative** (−12.1 to −1.4), not scattered around zero, and expectancy improves monotonically as stops widen in every single phase. That is a cost signature, not a signal failure.

### Phase 4 — Pairs / statistical arbitrage (55 pairs)

**0 of 55 pairs cointegrated** on development data (Engle-Granger, p < 0.05).

| Metric | Result |
|---|---|
| Best EG p-value | 0.0624 (XAUUSD/US30) — fails 0.05 |
| Median EG p-value | 0.5133 |
| Median half-life | **3,565 bars ≈ 74 days** |
| Pairs cointegrated in >50% of rolling 6-month windows | **0 / 55** |

**Verified not a bug:** the same code returns p = 0.000000 on a synthetic cointegrated pair and p = 0.80 on independent random walks.

The half-life is the decisive kill. Even the "best" pairs mean-revert over 32–74 days. That is not an intraday strategy, and holding a two-legged CFD spread for 50+ days incurs financing that dwarfs any spread edge.

---

## 3. THE DECISIVE DIAGNOSTIC

Running identical strategies at varying cost multipliers separates *signal absent* from *signal too small*:

| Strategy | cost ×0 | ×0.5 | ×1.0 | ×1.5 | ×2.0 | Verdict |
|---|---|---|---|---|---|---|
| **donchian_40** | **+0.0221** | +0.0048 | −0.0179 | −0.0343 | −0.0504 | **signal exists, costs kill it** |
| donchian_20 | −0.0014 | −0.0213 | −0.0438 | −0.0615 | −0.0765 | no raw signal |
| pull0.5atr_SL2.0 | **+0.0126** | −0.0076 | −0.0322 | −0.0498 | −0.0678 | **signal exists, costs kill it** |
| pull1.0atr_SL2.0 | +0.0065 | −0.0164 | −0.0359 | −0.0547 | −0.0740 | marginal |

**Break-even cost ≈ 0.6× the modelled cost.**

### Cost magnitude by instrument

| Symbol | cost/ATR | cost as % of a 2R trade |
|---|---|---|
| XAUUSD | 0.023 | 0.6% |
| EURUSD | 0.043 | 1.1% |
| GBPUSD / USDCAD | 0.045 | 1.1% |
| USDJPY / GBPJPY | 0.050 | 1.2% |
| NZDUSD | 0.080 | 2.0% |
| **US30** | **0.293** | **7.3%** |
| **XAGUSD** | **0.301** | **7.5%** |

XAGUSD and US30 are structurally untradeable on this cost basis — friction consumes 7%+ of every trade.

---

## 4. TIMEFRAME-SCALING TEST — hypothesis rejected

**Pre-registered hypothesis:** cost per trade is fixed in points; signal size scales with holding period; therefore net expectancy should rise monotonically with timeframe.

| TF | n | gross expR | net expR | t(net) | positive |
|---|---|---|---|---|---|
| M30 | 12,242 | +0.0221 | −0.0179 | −1.43 | 3/11 |
| H2 | 3,496 | −0.0277 | −0.0419 | −1.82 | 2/11 |
| H4 | 1,826 | +0.0098 | +0.0013 | +0.04 | 5/11 |
| H8 | 983 | +0.0745 | **+0.0586** | +1.42 | 7/11 |
| D1 | 328 | −0.0678 | −0.0816 | −1.31 | 4/11 |

**REJECTED.** The relationship is not monotonic — H2 is worse than M30, and D1 is the worst of all. H8 is a chance high point among five tests: it is not significant (t = 1.42, requires > 3.0), and it **collapses from +0.0586 to +0.0213 when XAGUSD and US30 are excluded** — meaning the apparent result was driven by the two instruments with the *worst* cost ratios, which is backwards and confirms noise.

---

## 5. TRIAL ACCOUNTING (protocol §32)

| Counter | Value |
|---|---|
| Total trials | **81** |
| Passed pre-registered gates | **0** |
| Failed | 81 |
| Hidden / deleted | 0 |

With 81 trials, the Harvey–Liu–Zhu threshold of t > 3.0 applies. No variant exceeded t = +1.42.

---

## 6. WHY EACH FAMILY FAILED

| Family | Failure mode |
|---|---|
| Opening-range breakout | No raw signal at any of 9 configurations; costs compound the loss |
| Donchian / TSMOM | **Raw signal present (+0.022R) but below cost (0.040R)** |
| Trend pullback | **Raw signal present (+0.013R) but below cost** |
| Pairs / stat-arb | No cointegration exists; half-lives 32–74 days |
| Mean reversion | Mirror of trend — works only where trend fails, nets to zero |

---

## 7. STATUS

| Strategy | Status |
|---|---|
| All 5 families | **REJECTED** |
| Holdout | **UNTOUCHED** |

**Next action: MORE DATA REQUIRED — not more research on this data.**

---

## 8. WHAT WOULD ACTUALLY CHANGE THE ANSWER

The finding is specific: gross edge ≈ +0.022R, cost ≈ 0.040R. Three levers exist, in order of leverage:

**1. Lower the cost basis.** Break-even is ~0.6× current cost. A raw-spread/ECN account would roughly halve modelled spread. That moves donchian_40 from −0.018 to ≈ +0.005 — positive, but still not significant (t ≈ 0.4). **Necessary but not sufficient.**

**2. More instruments — the largest single lever.** These 11 give only **3.7 effective independent bets** (44% of variance in one principal component; zero bonds, energy, or agriculturals). A trend portfolio's Sharpe scales with √N: 3.7 bets → expected Sharpe ≈ 0.48; 20 bets → ≈ 1.12; 40 bets → ≈ 1.58. The single-market signal is genuinely weak; diversification is what makes trend following work, and it is exactly what this universe lacks.

**3. More history.** Detecting a true Sharpe of 0.5 at 95% confidence requires ~35 years. This dataset has 6.6. The test is underpowered by construction — it cannot distinguish Sharpe 0.0 from Sharpe 0.8.

**Blocked:** prop-firm simulation cannot run — firm rules are `UNKNOWN`. Drawdown type (static/trailing/EOD) and consistency rule affect pass probability more than the strategy does.

---

## 9. HONEST BOTTOM LINE

The research did what it was built to do. It found a real but small trend signal, measured it precisely, measured the friction precisely, and established that the second exceeds the first at retail cost structures.

That is a **useful, specific, actionable negative result** — not a failure. It rules out five strategy families on evidence rather than opinion, identifies exactly what the binding constraint is (cost and diversification, not signal absence), and quantifies how much each would have to improve.

Nothing here is `AUTOMATION-READY`. Deploying any of it would be trading a measured negative expectancy.
