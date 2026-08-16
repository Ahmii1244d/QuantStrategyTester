"""
BACKTEST ENGINE - protocol 11, 12, 13, 62
Enforces: closed-bar signals only, next-bar-open fills, adverse intrabar
ambiguity, modelled costs. No look-ahead by construction.
"""
import pandas as pd, numpy as np, os, config as C

_CACHE = {}

def load(sym):
    if sym in _CACHE: return _CACHE[sym]
    d = pd.read_csv(os.path.join(C.DATA, f'{sym}_M30.csv'), encoding='utf-8-sig')
    d['time'] = pd.to_datetime(d['time'])
    d = d.sort_values('time').reset_index(drop=True)
    tr = np.maximum(d.high-d.low,
         np.maximum((d.high-d.close.shift()).abs(), (d.low-d.close.shift()).abs()))
    d['atr'] = tr.rolling(14).mean()
    d['h']   = d.time.dt.hour
    d['date']= d.time.dt.date
    _CACHE[sym] = d
    return d

def slice_split(d, split):
    a,b = C.SPLITS[split]
    return d[(d.time>=a)&(d.time<=b+' 23:59')].reset_index(drop=True)

def cost_points(sym, mult=1.0):
    """Round-trip cost in POINTS. Modelled, not observed. See config."""
    return (C.SPREAD_MODEL_POINTS[sym] + 2*C.SLIPPAGE_POINTS[sym]) * mult

def simulate(d, sig_dir, sig_sl, sym, rr=2.0, cost_mult=1.0,
             max_hold=None, one_per_day=False, min_stop_pts=5, reentry_gap=1):
    """
    sig_dir : int array, +1/-1/0, evaluated on CLOSED bar i
    sig_sl  : float array, stop price for signal at bar i
    Fill at open[i+1] plus cost. Adverse intrabar ambiguity.

    MT5-lifecycle notes (calibrated against a live tester run, 2026-08-12):
      * ONE position at a time is enforced by advancing i past the exit bar.
      * min_stop_pts rejects trades whose stop is closer than the broker's
        SYMBOL_TRADE_STOPS_LEVEL would allow (set per broker; default 5).
      * reentry_gap = bars to wait after an exit before the next entry.
      * CALIBRATION LIMIT: absolute trade COUNT and currency P&L are NOT
        reproducible from OHLC (MT5 samples ~58% of raw signals vs this
        engine's ~83%, the gap living in tick-level fill sequencing).
        WIN RATE, PF and DIRECTION BALANCE match MT5 to <0.5pt.
      * EXPECTANCY NOISE FLOOR (measured 2026-08-12): the trades that differ
        between engine and MT5 are NOT distributionally identical - a
        bootstrap on the marginal set put their mean R ~0.25R above the core
        (underpowered, n=74, CI crossed 0). Keeping vs dropping them shifts
        full-set expectancy by ~0.039R. THEREFORE: treat any |expectancy|
        < ~0.04R reported here as INSIDE execution-sampling noise - its SIGN
        is not trustworthy. Only expectancies well outside +/-0.04R, sign
        flips across splits, or non-trade metrics (Sharpe, cointegration p)
        are safe to rank on. Take absolute count / P&L / drawdown from MT5.
    Returns trade dataframe.
    """
    if max_hold is None: max_hold = C.MAX_HOLD_BARS
    o,h,l,c = d.open.values, d.high.values, d.low.values, d.close.values
    t, dts  = d.time.values, d.date.values
    pt   = C.POINT[sym]
    cpts = cost_points(sym, cost_mult)
    n = len(d); out = []; i = 30; used = set()

    while i < n-2:
        if sig_dir[i] == 0 or np.isnan(sig_sl[i]):
            i += 1; continue
        if one_per_day and dts[i] in used:
            i += 1; continue
        D  = int(sig_dir[i])
        # entry: next bar open, cost paid on entry side
        ent = o[i+1] + (cpts*pt if D > 0 else -cpts*pt)
        sl  = sig_sl[i]
        risk = abs(ent-sl)
        if risk <= 0 or risk/pt < min_stop_pts:
            i += 1; continue
        tp = ent + rr*risk*D
        if one_per_day: used.add(dts[i])

        end = min(n, i+1+max_hold); R = None; jx = end-1
        for j in range(i+1, end):
            hit_sl = (l[j] <= sl) if D > 0 else (h[j] >= sl)
            hit_tp = (h[j] >= tp) if D > 0 else (l[j] <= tp)
            if hit_sl and hit_tp:            # ADVERSE ordering, fixed a priori
                R = -1.0; jx = j; break
            if hit_sl: R = -1.0; jx = j; break
            if hit_tp: R =  rr;  jx = j; break
        if R is None:
            jx = end-1
            exitpx = c[jx] - (cpts*pt if D > 0 else -cpts*pt)   # cost on exit
            R = ((exitpx-ent) if D > 0 else (ent-exitpx)) / risk
        out.append((t[i+1], t[jx], D, float(R), float(risk/pt), int(d.h.values[i+1])))
        i = jx + reentry_gap

    return pd.DataFrame(out, columns=['entry','exit','dir','R','risk_pts','hour'])

def stats(tr):
    if len(tr) == 0:
        return dict(n=0, expR=0.0, tstat=0.0, pf=0.0, win=0.0, totR=0.0, maxDD=0.0)
    R = tr.R.values
    w, ls = R[R > 0], R[R <= 0]
    pf = w.sum()/abs(ls.sum()) if len(ls) and ls.sum() != 0 else np.inf
    eq = np.cumsum(R); dd = (eq - np.maximum.accumulate(eq)).min()
    se = R.std(ddof=1)/np.sqrt(len(R)) if len(R) > 1 else np.inf
    return dict(n=len(R), expR=R.mean(), tstat=(R.mean()/se if se > 0 else 0.0),
                pf=pf, win=100*len(w)/len(R), totR=R.sum(), maxDD=dd)
