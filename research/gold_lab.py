"""
GOLD STRATEGY LAB  -  disciplined variant search (protocol SS31/SS32).

Purpose: explore a family of XAUUSD trend/breakout strategies WITHOUT data-mining
the answer. Rules enforced by this module:

  1. Every variant tested is recorded. Nothing is deleted, nothing hidden.
  2. Design and selection happen on DEV + VAL only. The holdout window is
     physically truncated out of the data, so it cannot leak into selection.
  3. Pass/fail criteria are pre-registered BEFORE the sweep runs.
  4. The winner's t-stat is deflated for the number of trials attempted
     (Bonferroni-style), because the best of N tries is biased upward.

Run:  python research/gold_lab.py
"""
import os, sys, re, json
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import tester_app as A


# ---------------------------------------------------------------------------
# PRE-REGISTERED CRITERIA  (fixed before any variant is run)
# ---------------------------------------------------------------------------
CRITERIA = {
    "min_expR_up":      0.05,   # must work when gold trends up
    "min_expR_flat":    0.00,   # AND must not lose when gold is flat/down
    "min_t":            2.00,   # dev+val t-stat
    "min_edge_vs_long": 0.04,   # must beat always-long drift by > exec noise
    "max_inv_expR":    -0.04,   # its own inverse must clearly lose
    "min_trades_year": 40.0,    # enough throughput to pass inside ~1 year
}

# ---------------------------------------------------------------------------
# FLEXIBLE STRATEGY TEMPLATE
# Variants are produced by overriding the class constants. All logic is causal:
# base bar i uses only bars <= i, higher timeframes use the last CLOSED bar.
# ---------------------------------------------------------------------------
TEMPLATE = r'''class Strategy:
    timeframes = ["M30", "H4", "D1"]

    ENTRY          = "breakout"   # breakout | pullback | either
    SIDE           = "long"       # long | both
    REGIME         = "trend"      # trend | adaptive
    SESSION        = "all"        # all | not_london | pm_only
    DONCHIAN       = 20
    ATR_MULT       = 2.0
    RR             = 2.0
    H4_ADX_MIN     = 20
    D1_ADX_MIN     = 18
    USE_ADX_RISING = 1
    USE_VOL        = 0
    USE_D1_EMA     = 1
    PULLBACK_EMA   = 20
    RANGE_ADX_MAX  = 18
    RANGE_Z        = 2.0

    def signals(self, data):
        import numpy as np
        base = data["M30"]; htf = data["H4"]; d1 = data["D1"]
        n = len(base)
        direction = np.zeros(n); stop = np.full(n, np.nan); rr = np.full(n, self.RR)

        o = base["open"].to_numpy(float); c = base["close"].to_numpy(float)
        hi = base["high"].to_numpy(float); lo = base["low"].to_numpy(float)
        atr = base["atr"].to_numpy(float); vol = base["volume"].to_numpy(float)
        hour = base["time"].dt.hour.to_numpy()

        prev_high = base["high"].rolling(self.DONCHIAN).max().shift(1).to_numpy(float)
        prev_low  = base["low"].rolling(self.DONCHIAN).min().shift(1).to_numpy(float)
        vol_ma    = base["volume"].rolling(20).mean().shift(1).to_numpy(float)
        ema_pb    = base["close"].ewm(span=self.PULLBACK_EMA, adjust=False).mean().to_numpy(float)
        ma50      = base["close"].rolling(50).mean().to_numpy(float)
        sd50      = base["close"].rolling(50).std().to_numpy(float)

        bt = base["time"].to_numpy().astype("int64")
        ht = htf["time"].to_numpy().astype("int64")
        dt = d1["time"].to_numpy().astype("int64")
        pos_h4 = np.searchsorted(ht, bt, side="right") - 2
        pos_d1 = np.searchsorted(dt, bt, side="right") - 2

        h4_c    = htf["close"].to_numpy(float)
        h4_fast = htf["close"].ewm(span=20, adjust=False).mean().to_numpy(float)
        h4_slow = htf["close"].ewm(span=50, adjust=False).mean().to_numpy(float)
        h4_adx  = self._adx(htf, 14)
        h4_adx_p = np.full_like(h4_adx, np.nan); h4_adx_p[1:] = h4_adx[:-1]

        d1_c     = d1["close"].to_numpy(float)
        d1_ema50 = d1["close"].ewm(span=50, adjust=False).mean().to_numpy(float)
        d1_adx   = self._adx(d1, 14)
        d1_adx_p = np.full_like(d1_adx, np.nan); d1_adx_p[1:] = d1_adx[:-1]

        for i in range(300, n):
            ph = pos_h4[i]; pd_ = pos_d1[i]
            if ph < 1 or pd_ < 1: continue
            a = atr[i]
            if not np.isfinite(a) or a <= 0: continue
            if not np.isfinite(prev_high[i]) or not np.isfinite(prev_low[i]): continue

            if self.SESSION == "not_london" and 7 <= hour[i] <= 11: continue
            if self.SESSION == "pm_only" and hour[i] < 12: continue

            if self.USE_VOL:
                if not np.isfinite(vol_ma[i]) or vol[i] <= vol_ma[i]: continue

            h4v = h4_adx[ph]; h4p = h4_adx_p[ph]
            d1v = d1_adx[pd_]; d1p = d1_adx_p[pd_]
            if not (np.isfinite(h4v) and np.isfinite(h4p) and np.isfinite(d1v) and np.isfinite(d1p)):
                continue

            h4_bull = h4_fast[ph] > h4_slow[ph] and h4_c[ph] > h4_slow[ph]
            h4_bear = h4_fast[ph] < h4_slow[ph] and h4_c[ph] < h4_slow[ph]
            d1_bull = (d1_c[pd_] > d1_ema50[pd_]) if self.USE_D1_EMA else True
            d1_bear = (d1_c[pd_] < d1_ema50[pd_]) if self.USE_D1_EMA else True

            trending = (h4v >= self.H4_ADX_MIN) and (d1v >= self.D1_ADX_MIN)
            rising = ((h4v > h4p) and (d1v > d1p)) if self.USE_ADX_RISING else True

            # ---------------- TREND MODE ----------------
            if trending and rising:
                brk_up = c[i] > prev_high[i]
                brk_dn = c[i] < prev_low[i]
                pb_up = (lo[i] <= ema_pb[i]) and (c[i] > ema_pb[i]) and (c[i] > o[i])
                pb_dn = (hi[i] >= ema_pb[i]) and (c[i] < ema_pb[i]) and (c[i] < o[i])
                if self.ENTRY == "breakout":
                    sig_up, sig_dn = brk_up, brk_dn
                elif self.ENTRY == "pullback":
                    sig_up, sig_dn = pb_up, pb_dn
                else:
                    sig_up, sig_dn = (brk_up or pb_up), (brk_dn or pb_dn)

                if d1_bull and h4_bull and sig_up:
                    direction[i] = 1; stop[i] = c[i] - self.ATR_MULT * a; continue
                if self.SIDE == "both" and d1_bear and h4_bear and sig_dn:
                    direction[i] = -1; stop[i] = c[i] + self.ATR_MULT * a; continue

            # ---------------- RANGE MODE (adaptive only) ----------------
            if self.REGIME == "adaptive" and (h4v < self.RANGE_ADX_MAX):
                m = ma50[i]; sd = sd50[i]
                if not np.isfinite(m) or not np.isfinite(sd) or sd <= 0: continue
                z = (c[i] - m) / sd
                if z <= -self.RANGE_Z and c[i] > o[i]:
                    direction[i] = 1; stop[i] = c[i] - self.ATR_MULT * a
                elif self.SIDE == "both" and z >= self.RANGE_Z and c[i] < o[i]:
                    direction[i] = -1; stop[i] = c[i] + self.ATR_MULT * a

        return direction, stop, rr

    def _adx(self, df, period=14):
        import numpy as np, pandas as pd
        h = df["high"]; l = df["low"]; c = df["close"]; pc = c.shift(1)
        tr = pd.concat([h - l, (h - pc).abs(), (l - pc).abs()], axis=1).max(axis=1)
        up = h.diff(); dn = -l.diff()
        pdm = pd.Series(np.where((up > dn) & (up > 0), up, 0.0), index=df.index)
        mdm = pd.Series(np.where((dn > up) & (dn > 0), dn, 0.0), index=df.index)
        tre = tr.ewm(alpha=1/period, adjust=False).mean()
        pde = pdm.ewm(alpha=1/period, adjust=False).mean()
        mde = mdm.ewm(alpha=1/period, adjust=False).mean()
        pi = 100 * pde / tre; mi = 100 * mde / tre
        dx = 100 * (pi - mi).abs() / (pi + mi).replace(0, np.nan)
        return dx.ewm(alpha=1/period, adjust=False).mean().to_numpy()
'''


def build(**over):
    code = TEMPLATE
    for k, v in over.items():
        val = '"%s"' % v if isinstance(v, str) else str(v)
        code = re.sub(r"^    %s\s*=.*$" % k, "    %s = %s" % (k, val), code, flags=re.M)
    return code


# ---------------------------------------------------------------------------
def load_data(cfg):
    ds = A.scan_dataset(cfg)
    return {tf: A.load_tf(ds["tfs"][tf]["path"]) for tf in ("M30", "H4", "D1")}


def split_points(base):
    lo, hi = base.time.min(), base.time.max()
    sp = (hi - lo).days
    return lo + pd.Timedelta(days=int(sp * 0.6)), lo + pd.Timedelta(days=int(sp * 0.8))


def truncate(data, cutoff):
    """Physically remove everything at/after cutoff so the holdout cannot leak."""
    return {tf: df[df.time < cutoff].reset_index(drop=True).copy() for tf, df in data.items()}


def evaluate(code, data, cost, pt, gold_year_ret, label=""):
    """Backtest a variant and return the pre-registered measurements."""
    try:
        St = A.compile_strategy(code)
        d, s, rr = A.get_signals(St, data, "M30")
    except Exception as e:
        return {"label": label, "error": "%s: %s" % (type(e).__name__, e)}
    base = data["M30"]
    tr = A.backtest(d, s, rr, base, cost, pt)
    if len(tr) < 20:
        return {"label": label, "error": "only %d trades" % len(tr)}
    R = tr.R.values
    tr = tr.copy()
    tr["entry"] = pd.to_datetime(tr.entry)
    yr = tr.entry.dt.year
    up_years = [y for y, v in gold_year_ret.items() if v > 0.05]
    fl_years = [y for y, v in gold_year_ret.items() if v <= 0.05]
    gu = tr[yr.isin(up_years)].R.values
    gf = tr[yr.isin(fl_years)].R.values
    span = max((tr.entry.max() - tr.entry.min()).days, 1)
    se = R.std(ddof=1) / np.sqrt(len(R)) if len(R) > 1 else 1e9

    # matched always-long drift control, same stop/RR mechanics
    bench = A.benchmark_metrics(d, data, "M30", cost, pt, +1)["expR"]
    d_inv, s_inv = A.invert_signals(d, s, data, "M30")
    inv = A.metrics(A.backtest(d_inv, s_inv, rr, base, cost, pt))["expR"]

    return {
        "label": label, "n": len(R), "expR": float(R.mean()),
        "t": float(R.mean() / se), "win": float(100 * (R > 0).mean()),
        "tr_year": float(len(R) / (span / 365.25)),
        "expR_up": float(gu.mean()) if len(gu) else float("nan"),
        "n_up": int(len(gu)),
        "expR_flat": float(gf.mean()) if len(gf) else float("nan"),
        "n_flat": int(len(gf)),
        "bench": float(bench), "edge_vs_long": float(R.mean() - bench),
        "inv": float(inv),
    }


def passes(r):
    if "error" in r:
        return False, ["error: " + r["error"]]
    fails = []
    C = CRITERIA
    if not (r["expR_up"] > C["min_expR_up"]):
        fails.append("expR in gold-up years %.3f <= %.2f" % (r["expR_up"], C["min_expR_up"]))
    if not (r["expR_flat"] > C["min_expR_flat"]):
        fails.append("expR in gold-flat/down years %.3f <= %.2f" % (r["expR_flat"], C["min_expR_flat"]))
    if not (r["t"] > C["min_t"]):
        fails.append("t %.2f <= %.2f" % (r["t"], C["min_t"]))
    if not (r["edge_vs_long"] > C["min_edge_vs_long"]):
        fails.append("edge vs long-only %.3f <= %.2f" % (r["edge_vs_long"], C["min_edge_vs_long"]))
    if not (r["inv"] < C["max_inv_expR"]):
        fails.append("inverted %.3f not clearly negative" % r["inv"])
    if not (r["tr_year"] >= C["min_trades_year"]):
        fails.append("%.1f trades/yr < %.0f" % (r["tr_year"], C["min_trades_year"]))
    return (len(fails) == 0), fails
