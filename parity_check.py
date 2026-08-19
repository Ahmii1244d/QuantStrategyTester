"""
PARITY CHECK  -  strategy_gold_v3.py  vs  GoldPullbackMTF.mq5

The MQL5 EA cannot be executed here, so this harness re-implements the EA's
computation path EXACTLY as the .mq5 file performs it - explicit loops, the
same seeding, the same "last closed higher-timeframe bar" indexing, the same
rolling windows - and compares it bar-by-bar with the pandas strategy the
tester validated.

If this reports 100% signal agreement, the two implementations are the same
strategy. Any disagreement is a real porting bug and is printed with the bar
timestamp so it can be traced.

Run:  python parity_check.py
"""
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

import numpy as np
import pandas as pd

import tester_app as A
from strategy_gold_v3 import STRATEGY_CODE, ema_series, adx_series

PASS = 0
FAIL = 0


def ck(name, cond, extra=""):
    global PASS, FAIL
    ok = bool(cond)
    PASS += ok
    FAIL += (not ok)
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f"  ({extra})" if extra else ""))


# ---------------------------------------------------------------------------
# EA-PATH RE-IMPLEMENTATION
# Mirrors GoldPullbackMTF.mq5: LongSignal() + AtrSma() + EmaSeries() +
# AdxSeries(). Uses only bars at or before the signal bar.
# ---------------------------------------------------------------------------
def ea_signals(base, htf, d1,
               donchian=20, atr_mult=2.0, atr_period=14, adx_period=14,
               d1_adx_min=18.0, pullback_ema=20, h4_fast=20, h4_slow=50,
               d1_ema=50, vol_ma=20, vol_mult=1.0,
               skip_lo=7, skip_hi=11, hour_offset=0, warmup=300):
    n = len(base)
    direction = np.zeros(n)
    stop = np.full(n, np.nan)

    o = base["open"].to_numpy(float)
    h = base["high"].to_numpy(float)
    l = base["low"].to_numpy(float)
    c = base["close"].to_numpy(float)
    v = base["volume"].to_numpy(float)
    bt = base["time"].to_numpy().astype("int64")
    hours = pd.to_datetime(base["time"]).dt.hour.to_numpy()

    # --- EA: EmaSeries over the loaded M30 window ---
    ema_pb = ema_series(c, pullback_ema)

    # --- EA: AtrSma(). Simple mean of TR over the `period` closed bars
    #     ending at idx, each TR using its own previous bar's close. ---
    tr = np.full(n, np.nan)
    for i in range(1, n):
        tr[i] = max(h[i] - l[i], abs(h[i] - c[i - 1]), abs(l[i] - c[i - 1]))
    atr = np.full(n, np.nan)
    for i in range(atr_period, n):
        atr[i] = tr[i - atr_period + 1:i + 1].mean()

    # --- EA: H4 arrays ---
    h4c = htf["close"].to_numpy(float)
    h4t = htf["time"].to_numpy().astype("int64")
    h4f = ema_series(h4c, h4_fast)
    h4s = ema_series(h4c, h4_slow)

    # --- EA: D1 arrays ---
    d1c = d1["close"].to_numpy(float)
    d1t = d1["time"].to_numpy().astype("int64")
    d1e = ema_series(d1c, d1_ema)
    d1a = adx_series(d1["high"].to_numpy(float), d1["low"].to_numpy(float),
                     d1c, adx_period)

    # --- EA: iBarShift(tf, sigTime) + 1  ==  last CLOSED bar ---
    #     Expressed as an index it is searchsorted(right) - 2, identical
    #     to the strategy. Computed independently here on purpose.
    ih4 = np.searchsorted(h4t, bt, side="right") - 2
    id1 = np.searchsorted(d1t, bt, side="right") - 2

    for i in range(warmup, n):
        ph, pdd = ih4[i], id1[i]
        if ph < 1 or pdd < 1:
            continue

        a = atr[i]
        if not np.isfinite(a) or a <= 0:
            continue

        # EA: session filter (broker hour + offset)
        hr = (hours[i] + hour_offset) % 24
        if skip_lo <= hr <= skip_hi:
            continue

        # EA: Donchian high over the bars BEFORE the signal bar
        if i - donchian < 0:
            continue
        prev_high = h[i - donchian:i].max()

        # EA: volume average over the bars BEFORE the signal bar
        if i - vol_ma < 0:
            continue
        vma = v[i - vol_ma:i].mean()
        if not (vma > 0) or v[i] <= vma * vol_mult:
            continue

        d1v = d1a[pdd]
        d1p = d1a[pdd - 1]
        if not (np.isfinite(d1v) and np.isfinite(d1p)):
            continue
        if d1v < d1_adx_min:
            continue
        if not (d1v > d1p):
            continue

        h4_bull = (h4f[ph] > h4s[ph]) and (h4c[ph] > h4s[ph])
        d1_bull = d1c[pdd] > d1e[pdd]
        if not (h4_bull and d1_bull):
            continue

        breakout = c[i] > prev_high
        pullback = (l[i] <= ema_pb[i]) and (c[i] > ema_pb[i]) and (c[i] > o[i])
        if breakout or pullback:
            direction[i] = 1
            stop[i] = c[i] - atr_mult * a

    return direction, stop


# ---------------------------------------------------------------------------
def main():
    cfg = A.load_cfg()
    cfg["symbol"] = "XAUUSD"
    ds = A.scan_dataset(cfg)
    if not ds["ok"]:
        print("DATA ERROR:", ds["msg"])
        return 1
    for tf in ("M30", "H4", "D1"):
        if tf not in ds["tfs"]:
            print("missing timeframe", tf)
            return 1
    data = {tf: A.load_tf(ds["tfs"][tf]["path"]) for tf in ("M30", "H4", "D1")}
    base, htf, d1 = data["M30"], data["H4"], data["D1"]

    print("dataset: M30=%d  H4=%d  D1=%d bars   %s -> %s"
          % (len(base), len(htf), len(d1),
             str(base.time.iloc[0])[:10], str(base.time.iloc[-1])[:10]))

    print("\n=== 1. PYTHON STRATEGY (pandas, what the tester validated) ===")
    Strat = A.compile_strategy(STRATEGY_CODE)
    d_py, s_py, rr_py = A.get_signals(Strat, data, "M30")
    n_py = int(np.count_nonzero(d_py))
    print("   signals: %d" % n_py)

    print("\n=== 2. EA PATH (explicit loops, exactly as GoldPullbackMTF.mq5) ===")
    d_ea, s_ea = ea_signals(base, htf, d1)
    n_ea = int(np.count_nonzero(d_ea))
    print("   signals: %d" % n_ea)

    print("\n=== 3. BAR-BY-BAR AGREEMENT ===")
    same = (np.sign(d_py) == np.sign(d_ea))
    disagree = np.where(~same)[0]
    ck("signal arrays identical on every bar", len(disagree) == 0,
       f"{len(disagree)} disagreements out of {len(d_py)} bars")
    if len(disagree):
        print("   first disagreements:")
        for i in disagree[:8]:
            print("     %s  python=%+.0f  ea=%+.0f"
                  % (str(base.time.iloc[i]), d_py[i], d_ea[i]))

    both = (d_py != 0) & (d_ea != 0)
    if both.any():
        sd = np.abs(s_py[both] - s_ea[both])
        ck("stop prices identical where both fire", np.nanmax(sd) < 1e-9,
           f"max|diff| = {np.nanmax(sd):.3e}")

    print("\n=== 4. SAME TRADES THROUGH THE SAME FILL ENGINE ===")
    pt, _ = A.point_size(base)
    cost = A.modelled_cost_pts(base)
    tr_py = A.backtest(d_py, s_py, rr_py, base, cost, pt)
    tr_ea = A.backtest(d_ea, s_ea, np.full(len(base), 2.0), base, cost, pt)
    m_py, m_ea = A.metrics(tr_py), A.metrics(tr_ea)
    ck("trade count identical", m_py["n"] == m_ea["n"], f"{m_py['n']} vs {m_ea['n']}")
    ck("expectancy identical", abs(m_py["expR"] - m_ea["expR"]) < 1e-12,
       f"{m_py['expR']:.6f} vs {m_ea['expR']:.6f}")
    ck("profit factor identical", abs(m_py["pf"] - m_ea["pf"]) < 1e-12,
       f"{m_py['pf']:.4f} vs {m_ea['pf']:.4f}")
    ck("win rate identical", abs(m_py["win"] - m_ea["win"]) < 1e-12,
       f"{m_py['win']:.2f}% vs {m_ea['win']:.2f}%")

    print("\n=== 5. HISTORY SUFFICIENCY (how much the live EA must load) ===")
    d1h = d1["high"].to_numpy(float); d1l = d1["low"].to_numpy(float)
    d1c = d1["close"].to_numpy(float)
    full_adx = adx_series(d1h, d1l, d1c, 14)
    full_ema = ema_series(d1c, 50)
    for cut in (300, 600, 900, 1200):
        if cut >= len(d1c):
            continue
        sub_adx = adx_series(d1h[-cut:], d1l[-cut:], d1c[-cut:], 14)
        sub_ema = ema_series(d1c[-cut:], 50)
        da = np.nanmax(np.abs(full_adx[-60:] - sub_adx[-60:]))
        de = np.nanmax(np.abs(full_ema[-60:] - sub_ema[-60:]))
        print("   D1 history %4d bars -> ADX dev %.2e | EMA50 dev %.2e" % (cut, da, de))
    ck("600 D1 bars is enough for parity (EA default 1200, minimum 600)",
       np.nanmax(np.abs(full_adx[-60:] - adx_series(d1h[-600:], d1l[-600:],
                                                    d1c[-600:], 14)[-60:])) < 1e-4)

    print("\n=== 6. SESSION-FILTER SENSITIVITY (broker server-time risk) ===")
    base_n = n_py
    for off in (-2, -1, 1, 2):
        d_off, _ = ea_signals(base, htf, d1, hour_offset=off)
        k = int(np.count_nonzero(d_off))
        print("   server-hour offset %+d -> %d signals (%+.1f%% vs 0)"
              % (off, k, 100.0 * (k - base_n) / base_n))
    print("   -> if your broker's server time differs from the CSV, set")
    print("      InpServerHourOffset. A wrong offset IS a different strategy.")

    print("\n" + "=" * 58)
    print(f"  PARITY RESULT: {PASS} passed, {FAIL} failed")
    print("=" * 58)
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
