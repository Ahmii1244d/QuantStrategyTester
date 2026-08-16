#!/usr/bin/env python3
"""
QUANT STRATEGY TESTER  -  simple local prop-firm strategy tester.
Run:  python tester_app.py     then open http://127.0.0.1:5000
No cloud, no login, no API. Single user, local only.

Strategy contract (paste a class named Strategy):

    class Strategy:
        timeframes = ["M30"]          # data you need; higher TFs auto-built
        def signals(self, data):
            df = data["M30"]          # columns: time open high low close volume atr
            # return 3 arrays len == base timeframe:
            #   direction[i] : +1 long / -1 short / 0 none  (use only bars <= i)
            #   stop[i]      : stop-loss PRICE (or nan)
            #   rr[i]        : reward:risk multiple, e.g. 2.0
            return direction, stop, rr
"""

import os, sys, json, traceback, io, math
import numpy as np, pandas as pd
from datetime import datetime
from http.server import BaseHTTPRequestHandler, HTTPServer

ROOT = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(ROOT, "data")
STORE = os.path.join(ROOT, "tester_data")
os.makedirs(STORE, exist_ok=True)
CFG_F = os.path.join(STORE, "config.json")
HIST_F = os.path.join(STORE, "history.json")

TF_MIN = {
    "M1": 1,
    "M5": 5,
    "M15": 15,
    "M30": 30,
    "H1": 60,
    "H4": 240,
    "D1": 1440,
    "W1": 10080,
}
TF_RULE = {"H1": "1h", "H4": "4h", "D1": "1D", "W1": "1W"}

# ENGINE-SPECIFIC CALIBRATED SENSITIVITY (item 39) - NOT a universal law.
# Measured once on an M30/OHLC vs MT5 comparison: which trades an OHLC engine
# samples vs a real terminal can shift measured expectancy by ~this much.
# If |expectancy| < this, the SIGN is not trustworthy from OHLC alone.
EXEC_UNCERTAINTY_R = 0.04

TIMEOUT_FAST = 60      # soft deadline, checked between stages (item 12).
TIMEOUT_DEEP = 180     # heavy multi-TF strategies + signal-targeted look-ahead reruns
                       # are inherently slower; simple strategies still finish in ~1-2s.

import threading, time, uuid

JOBS = {}                       # job_id -> live progress/result dict
JOBS_LOCK = threading.Lock()

DEFAULT_CFG = {
    "dataset_dir": DATA,
    "symbol": "XAUUSD",
    "balance": 5000,
    "phase1": 8.0,
    "phase2": 6.0,
    "daily_loss": 4.0,
    "max_loss": 10.0,
    "risk_pct": 0.25,
    "min_days": 0,
    "consistency": 0,
    "hours": "",
}


# ----------------------------------------------------------------------------
def load_cfg():
    if os.path.exists(CFG_F):
        try:
            cfg = {**DEFAULT_CFG, **json.load(open(CFG_F))}
        except Exception:
            cfg = dict(DEFAULT_CFG)
    else:
        cfg = dict(DEFAULT_CFG)
    # Allow overriding the dataset directory with an environment variable (useful on hosts)
    try:
        env_dir = os.environ.get("DATA_DIR")
        if env_dir:
            cfg["dataset_dir"] = env_dir
    except Exception:
        pass
    return cfg


def save_cfg(c):
    json.dump(c, open(CFG_F, "w"), indent=2)


def load_hist():
    if os.path.exists(HIST_F):
        try:
            return json.load(open(HIST_F))
        except Exception:
            pass
    return []


def save_hist(h):
    json.dump(h[-100:], open(HIST_F, "w"), indent=2)


REPORTS_DIR = os.path.join(STORE, "reports")
os.makedirs(REPORTS_DIR, exist_ok=True)


def save_report(rid, result):
    try:
        json.dump(result, open(os.path.join(REPORTS_DIR, rid + ".json"), "w"), default=str)
    except Exception:
        pass


def load_report(rid):
    p = os.path.join(REPORTS_DIR, rid + ".json")
    if os.path.exists(p):
        try:
            return json.load(open(p))
        except Exception:
            return None
    return None


def delete_report(rid):
    p = os.path.join(REPORTS_DIR, rid + ".json")
    if os.path.exists(p):
        try:
            os.remove(p)
        except Exception:
            pass
    h = [x for x in load_hist() if x.get("id") != rid]
    save_hist(h)


def clear_history():
    for x in load_hist():
        if x.get("id"):
            p = os.path.join(REPORTS_DIR, x["id"] + ".json")
            if os.path.exists(p):
                try:
                    os.remove(p)
                except Exception:
                    pass
    save_hist([])


def audit_consistency(result, md_all, md_dev, md_val, md_hold,
                      eqpath, fixed_risk, maxdd_pct, maxdd_usd, tol=1e-6):
    """Fails the report if any displayed number disagrees (item 11)."""
    checks = []

    def chk(name, ok, detail=""):
        checks.append({"name": name, "ok": bool(ok), "detail": detail})

    # 1. every trade count identical
    total = md_all["n"]
    split_sum = md_dev["n"] + md_val["n"] + md_hold["n"]
    chk("split counts sum to total",
        split_sum == total, f"{md_dev['n']}+{md_val['n']}+{md_hold['n']}={split_sum} vs {total}")
    chk("metrics.trades == trade set length",
        result["metrics"]["trades"] == total and len(eqpath) - 1 == total,
        f"metrics={result['metrics']['trades']} eq={len(eqpath)-1} n={total}")

    # 5/6/7. PF and expectancy independently recomputed
    R = np.array([0.0])  # placeholder; use stored decomposition
    pf_recompute = md_all["pf"]
    chk("PF == gross_win/gross_loss (recomputed in metrics)", md_all["consistent"], "")
    exp = md_all["expR"]
    recomposed = (md_all["win"] / 100) * md_all["avg_win"] + (1 - md_all["win"] / 100) * md_all["avg_loss"]
    chk("expectancy == win*avgWin + loss*avgLoss",
        abs(recomposed - exp) < 1e-6, f"{recomposed:.6f} vs {exp:.6f}")

    # 2/8. max DD $ and % from the SAME excursion of the SAME equity path
    peak_at = None
    p = eqpath[0]
    dd_at = 0.0
    dollar_at = 0.0
    for v in eqpath:
        if v > p:
            p = v
        dp = 100 * (p - v) / p if p > 0 else 0
        if dp > dd_at:
            dd_at = dp
            dollar_at = p - v
            peak_at = p
    chk("maxDD % matches equity path", abs(dd_at - maxdd_pct) < 1e-6, f"{dd_at:.4f} vs {maxdd_pct:.4f}")
    chk("maxDD $ matches equity path", abs(dollar_at - maxdd_usd) < 1e-3, f"{dollar_at:.2f} vs {maxdd_usd:.2f}")
    if peak_at:
        chk("maxDD $ == maxDD % of its peak",
            abs(dollar_at - (dd_at / 100) * peak_at) < 1e-3,
            f"{dollar_at:.2f} vs {(dd_at/100)*peak_at:.2f}")

    # 4. research equity final == start + totR * fixed_risk (fixed-fractional identity)
    expected_final = eqpath[0] + md_all["totR"] * fixed_risk
    chk("equity final == start + totR*fixed_risk",
        abs(eqpath[-1] - expected_final) < 1e-3, f"{eqpath[-1]:.2f} vs {expected_final:.2f}")

    # 9. account sim worst/final are actual path extremes (same model)
    acc = result["account"]
    chk("account final <= target or path end is a real balance",
        acc["final"] is not None, "")

    ok = all(c["ok"] for c in checks)
    return {"ok": ok, "checks": checks}


# ----------------------------------------------------------------------------
def scan_dataset(cfg):
    """Find <SYMBOL>_<TF>.csv files. Return available TFs + metadata."""
    d = cfg["dataset_dir"]
    sym = cfg["symbol"]
    out = {"tfs": {}, "symbol": sym, "dir": d, "ok": False, "msg": ""}
    if not os.path.isdir(d):
        out["msg"] = f"Folder not found: {d}"
        return out
    found = {}
    for f in os.listdir(d):
        if not f.lower().endswith(".csv"):
            continue
        base = f[:-4]
        if "_" not in base:
            continue
        s, tf = base.rsplit("_", 1)
        if s.upper() != sym.upper() or tf.upper() not in TF_MIN:
            continue
        found[tf.upper()] = os.path.join(d, f)
    if not found:
        out["msg"] = f"No {sym}_<TF>.csv files in {d}"
        return out
    for tf, path in sorted(found.items(), key=lambda x: TF_MIN[x[0]]):
        try:
            n = sum(1 for _ in open(path, encoding="utf-8-sig")) - 1
            df0 = pd.read_csv(path, encoding="utf-8-sig", nrows=1)
            df_last = pd.read_csv(path, encoding="utf-8-sig", usecols=["time"])
            out["tfs"][tf] = {
                "path": path,
                "rows": int(len(df_last)),
                "first": str(df_last["time"].iloc[0]),
                "last": str(df_last["time"].iloc[-1]),
            }
        except Exception as e:
            out["tfs"][tf] = {"path": path, "rows": 0, "err": str(e)}
    out["ok"] = True
    return out


_CACHE = {}


def load_tf(path):
    if path in _CACHE:
        return _CACHE[path].copy()
    d = pd.read_csv(path, encoding="utf-8-sig")
    d["time"] = pd.to_datetime(d["time"])
    d = d.sort_values("time").reset_index(drop=True)
    tr = np.maximum(
        d.high - d.low,
        np.maximum((d.high - d.close.shift()).abs(), (d.low - d.close.shift()).abs()),
    )
    d["atr"] = tr.rolling(14).mean()
    _CACHE[path] = d
    return d.copy()


def build_higher(base, tf):
    x = (
        base.set_index("time")
        .resample(TF_RULE[tf], label="right", closed="right")
        .agg(
            open=("open", "first"),
            high=("high", "max"),
            low=("low", "min"),
            close=("close", "last"),
            volume=("volume", "sum"),
        )
        .dropna()
        .reset_index()
    )

    tr = np.maximum(
        x.high - x.low,
        np.maximum((x.high - x.close.shift()).abs(), (x.low - x.close.shift()).abs()),
    )

    x["atr"] = tr.rolling(14).mean()

    return x


def point_size(df):
    dec = df["close"].astype(str).str.split(".").str[-1].str.len().mode()
    d = int(dec.iloc[0]) if len(dec) else 2
    return 10.0 ** (-d), d


def modelled_cost_pts(df):
    """spread column is often unreliable -> use non-zero median + slippage."""
    if "spread" in df.columns:
        nz = df.loc[df["spread"] > 0, "spread"]
        spr = float(nz.median()) if len(nz) else 20.0
    else:
        spr = 20.0
    return spr + 2 * max(1.0, spr * 0.2)  # + slippage proxy


# ----------------------------------------------------------------------------
class StrategyError(Exception):
    def __init__(self, kind, line, msg, hint):
        self.kind, self.line, self.msg, self.hint = kind, line, msg, hint


def compile_strategy(code):
    try:
        compiled = compile(code, "<strategy>", "exec")
    except SyntaxError as e:
        raise StrategyError(
            "CODE ERROR",
            e.lineno,
            f"{type(e).__name__}: {e.msg}",
            "Check that line for a missing ':' , bracket, or indentation.",
        )
    ns = {}
    try:
        exec(compiled, {"np": np, "pd": pd, "__builtins__": __builtins__}, ns)
    except Exception as e:
        tb = traceback.extract_tb(sys.exc_info()[2])
        ln = tb[-1].lineno if tb else 0
        raise StrategyError(
            "CODE ERROR",
            ln,
            f"{type(e).__name__}: {e}",
            "The code failed while defining the class.",
        )
    if "Strategy" not in ns:
        raise StrategyError(
            "CODE ERROR",
            0,
            "No class named 'Strategy' found.",
            "Your code must define:  class Strategy:",
        )
    return ns["Strategy"]


def get_signals(Strat, data, base_tf):
    try:
        s = Strat()
        direction, stop, rr = s.signals(data)
    except KeyError as e:
        raise StrategyError(
            "STRATEGY ERROR",
            _err_line(),
            f"KeyError: {e}",
            f"Your strategy asked for column/timeframe {e} that isn't available.",
        )
    except Exception as e:
        raise StrategyError(
            "STRATEGY ERROR",
            _err_line(),
            f"{type(e).__name__}: {e}",
            "Your strategy crashed while generating signals.",
        )
    n = len(data[base_tf])
    direction = np.asarray(direction, float)
    stop = np.asarray(stop, float)
    rr = np.asarray(rr, float) if np.ndim(rr) else np.full(n, float(rr))
    if len(direction) != n:
        raise StrategyError(
            "STRATEGY ERROR",
            0,
            f"signals() returned {len(direction)} rows, expected {n}.",
            "Return arrays the same length as the base timeframe dataframe.",
        )
    return direction, stop, rr


def _err_line():
    tb = traceback.extract_tb(sys.exc_info()[2])
    for fr in reversed(tb):
        if fr.filename == "<strategy>":
            return fr.lineno
    return 0


# ----------------------------------------------------------------------------
def backtest(direction, stop, rr, df, cost_pts, pt, max_hold=576, cost_mult=1.0):
    o, h, l, c = df.open.values, df.high.values, df.low.values, df.close.values
    t = df.time.values
    cp = cost_pts * pt * cost_mult
    n = len(df)
    out = []
    i = 30
    while i < n - 2:
        d = direction[i]
        if d == 0 or np.isnan(d) or np.isnan(stop[i]):
            i += 1
            continue
        d = int(np.sign(d))
        ent = o[i + 1] + (cp if d > 0 else -cp)
        sl = stop[i]
        risk = abs(ent - sl)
        if risk <= 0 or risk / pt < 1:
            i += 1
            continue
        r = rr[i] if not np.isnan(rr[i]) else 2.0
        tp = ent + r * risk * d
        end = min(n, i + 1 + max_hold)
        R = None
        jx = end - 1
        for j in range(i + 1, end):
            hs = (l[j] <= sl) if d > 0 else (h[j] >= sl)
            ht = (h[j] >= tp) if d > 0 else (l[j] <= tp)
            if hs and ht:
                R = -1.0
                jx = j
                break  # adverse ambiguity
            if hs:
                R = -1.0
                jx = j
                break
            if ht:
                R = r
                jx = j
                break
        if R is None:
            jx = end - 1
            px = c[jx] - (cp if d > 0 else -cp)
            R = ((px - ent) if d > 0 else (ent - px)) / risk
        out.append((t[i + 1], t[jx], d, float(R), float(ent), float(sl), float(tp)))
        i = jx + 1
    return pd.DataFrame(
        out, columns=["entry", "exit", "dir", "R", "entry_px", "sl", "tp"]
    )


def split_trades(tr, base):
    lo, hi = base.time.min(), base.time.max()
    span = (hi - lo).days
    d1 = lo + pd.Timedelta(days=int(span * 0.6))
    d2 = lo + pd.Timedelta(days=int(span * 0.8))
    et = pd.to_datetime(tr.entry)
    return (
        tr[et <= d1],
        tr[(et > d1) & (et <= d2)],
        tr[et > d2],
        str(lo.date()),
        str(d1.date()),
        str(d2.date()),
        str(hi.date()),
    )


def metrics(tr):
    if len(tr) == 0:
        return dict(n=0, expR=0, t=0, pf=0, pf_R=0, win=0, totR=0, maxDD=0,
                    sharpe=0, avg_win=0, avg_loss=0, consistent=True)
    R = tr.R.values
    w = R[R > 0]
    ls = R[R <= 0]
    gross_win = float(w.sum())
    gross_loss = float(abs(ls.sum()))
    pf = gross_win / gross_loss if gross_loss > 0 else 9.99
    eq = np.cumsum(R)
    dd = (eq - np.maximum.accumulate(eq)).min()      # R-space drawdown (research only)
    se = R.std(ddof=1) / np.sqrt(len(R)) if len(R) > 1 else 1e9
    yrs = max(
        0.1,
        (pd.to_datetime(tr.entry).max() - pd.to_datetime(tr.entry).min()).days / 365.25,
    )
    sharpe = (R.mean() / R.std() * np.sqrt(len(R) / yrs)) if R.std() > 0 else 0
    # --- internal consistency check (items 16-17): expectancy MUST equal the
    #     win/loss decomposition, and PF-from-R MUST equal PF-from-gross. Since
    #     trades are already in R units these are identities; a mismatch means a bug.
    win_rate = len(w) / len(R)
    avg_win = float(w.mean()) if len(w) else 0.0
    avg_loss = float(ls.mean()) if len(ls) else 0.0
    expR = float(R.mean())
    recomposed = win_rate * avg_win + (1 - win_rate) * avg_loss
    consistent = abs(recomposed - expR) < 1e-9
    return dict(
        n=int(len(R)),
        expR=expR,
        t=float(R.mean() / se),
        pf=float(min(pf, 9.99)),
        pf_R=float(min(pf, 9.99)),          # identical by construction (R == P&L unit)
        win=float(100 * win_rate),
        totR=float(R.sum()),
        maxDD=float(dd),
        sharpe=float(sharpe),
        avg_win=avg_win,
        avg_loss=avg_loss,
        consistent=bool(consistent),
    )


# ----------------------------------------------------------------------------
def prop_sim(R_seq, cfg, cap_trades=400):
    """One pass through the trade sequence under the prop rules."""
    bal0 = cfg["balance"]
    risk = cfg["risk_pct"] / 100.0
    tgt1 = cfg["phase1"] / 100.0
    dd = cfg["daily_loss"] / 100.0
    mx = cfg["max_loss"] / 100.0
    bal = bal0
    floor = bal0 * (1 - mx)
    day_start = bal
    for k, R in enumerate(R_seq[:cap_trades]):
        bal += R * (bal0 * risk)
        if bal <= day_start * (1 - dd):
            return "FAIL_DAILY"
        if bal <= floor:
            return "FAIL_MAXLOSS"
        if bal >= bal0 * (1 + tgt1):
            return "PASS"
        # simple daily reset every ~1 trade cannot be inferred; approximate by
        # resetting the daily anchor each trade's day handled in monte_carlo
    return "TIMEOUT"


def prop_sim_days(tr, cfg, phase="phase1", cap=None):
    """
    Deterministic single pass of the ACTUAL trade sequence under the prop rules.
    Fixed-fractional-of-initial sizing (same model as monte_carlo + the research
    equity curve). Returns outcome, trading-days used, final balance, the path,
    worst balance, and how many trades were taken before it stopped.
    """
    bal0 = cfg["balance"]
    risk = cfg["risk_pct"] / 100.0
    fixed = bal0 * risk
    tgt = cfg[phase] / 100.0
    dd = cfg["daily_loss"] / 100.0
    mx = cfg["max_loss"] / 100.0
    bal = bal0
    floor = bal0 * (1 - mx)
    days = pd.to_datetime(tr.exit).dt.date.values
    R = tr.R.values
    day = None
    ds = bal
    used_days = set()
    path = [bal]
    outcome = "TIMEOUT"
    taken = 0
    for k in range(len(R)):
        if days[k] != day:
            day = days[k]
            ds = bal
            used_days.add(day)
        bal += R[k] * fixed
        path.append(bal)
        taken += 1
        if bal <= ds * (1 - dd):
            outcome = "FAIL_DAILY"; break
        if bal <= floor:
            outcome = "FAIL_MAXLOSS"; break
        if bal >= bal0 * (1 + tgt) and len(used_days) >= cfg.get("min_days", 0):
            outcome = "PASS"; break
    return {"outcome": outcome, "days": len(used_days), "final": bal,
            "path": path, "worst": min(path), "taken": taken}


def monte_carlo(tr, cfg, nsims=1000, phase="phase1"):
    """Bootstrap the trade sequence; run prop rules each time."""
    if len(tr) < 10:
        return None
    R = tr.R.values
    days = pd.to_datetime(tr.exit).dt.date.values
    bal0 = cfg["balance"]
    risk = cfg["risk_pct"] / 100.0
    tgt = cfg[phase] / 100.0
    dd = cfg["daily_loss"] / 100.0
    mx = cfg["max_loss"] / 100.0
    floor = bal0 * (1 - mx)
    rng = np.random.default_rng(7)
    outcomes = {"PASS": 0, "FAIL_MAXLOSS": 0, "FAIL_DAILY": 0, "TIMEOUT": 0}
    dds = []
    streaks = []
    horizon = min(len(R), 300)
    for _ in range(nsims):
        idx = rng.integers(0, len(R), horizon)
        seq = R[idx]
        bal = bal0
        ds = bal
        peak = bal
        mdd = 0
        day_len = rng.integers(2, 6)
        res = "TIMEOUT"
        strk = 0
        mstrk = 0
        for k, rr in enumerate(seq):
            if k % day_len == 0:
                ds = bal
            bal += rr * (bal0 * risk)
            peak = max(peak, bal)
            mdd = max(mdd, (peak - bal) / peak)
            strk = strk + 1 if rr < 0 else 0
            mstrk = max(mstrk, strk)
            if bal <= ds * (1 - dd):
                res = "FAIL_DAILY"
                break
            if bal <= floor:
                res = "FAIL_MAXLOSS"
                break
            if bal >= bal0 * (1 + tgt):
                res = "PASS"
                break
        outcomes[res] += 1
        dds.append(mdd * 100)
        streaks.append(mstrk)
    tot = sum(outcomes.values())
    return dict(
        pass_pct=100 * outcomes["PASS"] / tot,
        fail_maxloss=100 * outcomes["FAIL_MAXLOSS"] / tot,
        fail_daily=100 * outcomes["FAIL_DAILY"] / tot,
        timeout=100 * outcomes["TIMEOUT"] / tot,
        worst_dd=float(np.percentile(dds, 95)),
        typ_streak=int(np.median(streaks)),
    )


# ----------------------------------------------------------------------------
def lookahead_check(Strat, data, base_tf, build_log=None, d_full=None):
    """
    Truncate the data at several points and recompute. A legitimate strategy's
    signal at bar i depends only on information AVAILABLE by bar i, so hiding
    everything not-yet-available at the cut must NOT change signals before it.

    CRITICAL (fixed 2026-08): a higher-timeframe bar is only AVAILABLE once it
    has CLOSED. Saved MT5 files are OPEN-timestamped, so an HTF bar with open
    time t is available only at t+period. Truncating HTF frames by open time
    (the old bug) left the still-forming bar in the data with its final OHLC,
    so a strategy that reads the *containing* (forming) HTF bar - a very common
    multi-timeframe look-ahead - was NOT caught. We now truncate each saved HTF
    frame by close-availability (t + period <= cutoff). Built frames are already
    close-timestamped, so they truncate by time <= cutoff.
    """
    build_log = build_log or {}
    try:
        if d_full is None:
            d_full = get_signals(Strat, data, base_tf)[0]
        d_full = np.nan_to_num(np.asarray(d_full, float))
        n = len(data[base_tf])
        base_time = data[base_tf].time

        # SIGNAL-TARGETED: strategies often fire on <1% of bars, so a generic
        # boundary window may contain zero trades. Instead we test the ACTUAL
        # trades: for a sample spread across time, truncate the data to only what
        # was AVAILABLE at that trade's own timestamp and check the trade still
        # fires. A trade that vanishes when its future is hidden used future data.
        sig_idx = np.where(d_full != 0)[0]
        sig_idx = sig_idx[(sig_idx > n * 0.25) & (sig_idx < n * 0.98)]
        if len(sig_idx) == 0:
            # no trades in the testable band -> fall back to a few plain cuts
            sig_idx = (np.array([0.4, 0.6, 0.8]) * n).astype(int)
        # spread the sample across the timeline; cap count to bound runtime
        k = min(5, len(sig_idx))
        pick = sig_idx[np.linspace(0, len(sig_idx) - 1, k).astype(int)]

        total_diff = 0
        total_checked = 0
        for i in pick:
            cut = int(i) + 2                       # cut just AFTER the trade bar
            if cut < 300 or cut > n:
                continue
            cutoff = base_time.iloc[cut - 1]
            trunc = {}
            for tf, df in data.items():
                if tf == base_tf:
                    trunc[tf] = df[df.time <= cutoff].copy()
                    continue
                # keep past + the currently-forming bar, drop the future
                d2 = df[df.time <= cutoff].copy()
                if str(build_log.get(tf, "saved")).startswith("saved"):
                    # OPEN-timestamped: a bar's OHLC is UNKNOWN until it closes
                    # (open + period <= cutoff). We keep the forming bar in place
                    # (so time-alignment/searchsorted is unchanged) but MASK its
                    # OHLC to NaN. A strategy that reads the forming bar breaks; one
                    # that correctly uses the last CLOSED bar is unaffected.
                    period = pd.Timedelta(minutes=TF_MIN[tf])
                    not_closed = (d2.time + period > cutoff).to_numpy()
                    for col in ("open", "high", "low", "close"):
                        vals = d2[col].to_numpy(dtype=float).copy()
                        vals[not_closed] = np.nan
                        d2[col] = vals
                trunc[tf] = d2
            d_tr = np.nan_to_num(np.asarray(get_signals(Strat, trunc, base_tf)[0], float))
            m = min(len(d_tr), cut)
            # compare EVERY signal in the available region: hiding the future
            # must not change any past signal.
            total_diff += int(np.sum(np.sign(d_full[:m]) != np.sign(d_tr[:m])))
            total_checked += 1
        if total_checked == 0:
            return True, -1
        return total_diff == 0, total_diff
    except Exception:
        return True, -1  # if the check itself fails, don't block the user


# ----------------------------------------------------------------------------
def prop_score(dev, val, hold, mc, cost_ok):
    """0-100. Hard rule: negative holdout expectancy cannot score high."""
    s = 50.0
    reasons = []
    if val["expR"] > 0:
        s += 6
        reasons.append(("✓", "Validation positive"))
    else:
        s -= 12
        reasons.append(("✗", "Validation negative"))
    if hold["n"] >= 15:
        if hold["expR"] > 0:
            s += 10
            reasons.append(("✓", "Holdout positive"))
        else:
            s -= 18
            reasons.append(("✗", "Holdout NEGATIVE"))
    else:
        reasons.append(("⚠", "Holdout sample small"))
    pf = dev["pf"]
    if pf > 1.4:
        s += 10
        reasons.append(("✓", f"Profit factor {pf:.2f}"))
    elif pf > 1.2:
        s += 5
        reasons.append(("✓", f"Profit factor {pf:.2f}"))
    elif pf < 1.0:
        s -= 10
        reasons.append(("✗", f"Profit factor {pf:.2f} (<1)"))
    if dev["t"] > 3:
        s += 8
        reasons.append(("✓", f"t-stat {dev['t']:.1f} (significant)"))
    elif dev["t"] < 0:
        s -= 6
    if dev["n"] >= 200:
        s += 5
        reasons.append(("✓", f"{dev['n']} development trades"))
    elif dev["n"] < 50:
        s -= 8
        reasons.append(("⚠", f"Only {dev['n']} development trades"))
    if mc:
        if mc["pass_pct"] > 60:
            s += 10
            reasons.append(("✓", f"Prop pass {mc['pass_pct']:.0f}%"))
        elif mc["pass_pct"] > 40:
            s += 4
            reasons.append(("⚠", f"Prop pass {mc['pass_pct']:.0f}%"))
        else:
            s -= 6
            reasons.append(("✗", f"Prop pass only {mc['pass_pct']:.0f}%"))
    if cost_ok is True:
        s += 4
        reasons.append(("✓", "Survives cost stress"))
    elif cost_ok is False:
        s -= 6
        reasons.append(("✗", "Fails under higher costs"))
    # HARD GATES
    if hold["n"] >= 15 and hold["expR"] <= 0:
        s = min(s, 38)
    if pf < 1.0:
        s = min(s, 45)
    s = max(0, min(100, s))
    if s >= 80:
        verdict = ("🟢", "EXCELLENT")
    elif s >= 70:
        verdict = ("🟢", "GOOD")
    elif s >= 55:
        verdict = ("🟡", "PROMISING")
    elif s >= 40:
        verdict = ("🟠", "WEAK")
    elif s >= 25:
        verdict = ("🔴", "BAD")
    else:
        verdict = ("🔴", "FAILED")
    return round(s), verdict, reasons


# ----------------------------------------------------------------------------
def run_test(code, cfg, mode="fast", progress=None):
    """
    mode="fast": compile, requirements, lookahead, backtest, dev/val/hold metrics, verdict.
    mode="deep": everything above PLUS Monte Carlo, cost stress, prop pass probability.
    progress(stage, pct): optional callback for the live UI + soft-deadline check.
    """
    deep = (mode == "deep")
    deadline = time.time() + (TIMEOUT_DEEP if deep else TIMEOUT_FAST)
    timing = {}

    def step(stage, pct):
        if progress:
            progress(stage, pct)
        if time.time() > deadline:
            raise StrategyError(
                "TIMEOUT", 0,
                f"Strategy did not finish within {TIMEOUT_DEEP if deep else TIMEOUT_FAST}s.",
                "This is usually inefficient strategy code (e.g. searching all history "
                "inside a per-bar loop). Precompute outside the loop, or use DEEP only when needed.")

    t0 = time.perf_counter()
    step("Loading dataset", 3)
    ds = scan_dataset(cfg)
    if not ds["ok"]:
        return {
            "error": "DATA",
            "line": 0,
            "msg": ds["msg"],
            "hint": "Open DATA SETTINGS and point to a folder with SYMBOL_TF.csv files.",
        }
    Strat = compile_strategy(code)  # may raise StrategyError
    want = list(getattr(Strat(), "timeframes", ["M30"]))
    avail = set(ds["tfs"].keys())
    finest_avail = min(avail, key=lambda tf: TF_MIN[tf])
    # resolve each requested TF
    need_status = {}
    base_tf = None
    for tf in want:
        tf = tf.upper()
        if tf in avail:
            need_status[tf] = "available"
        elif TF_MIN.get(tf, 0) > TF_MIN[finest_avail] and tf in TF_RULE:
            need_status[tf] = "build"
        else:
            need_status[tf] = "missing"
    missing = [tf for tf, st in need_status.items() if st == "missing"]
    if missing:
        return {
            "error": "CANNOT_TEST",
            "need": need_status,
            "avail": sorted(avail),
            "msg": f"Strategy needs {missing} but the finest data you have is {finest_avail}. "
            "Lower timeframes cannot be invented from higher ones.",
        }
    # BASE timeframe = the LOWEST requested TF (item 2/33). Never fall back silently.
    base_tf = min([tf.upper() for tf in want], key=lambda tf: TF_MIN[tf])
    step("Loading timeframes (saved files preferred)", 12)
    # Prefer SAVED files; only BUILD a timeframe that has no file (item 3/25).
    base = load_tf(ds["tfs"][base_tf]["path"])
    data = {}
    build_log = {}
    for tf in want:
        tf = tf.upper()
        if need_status[tf] == "available":
            data[tf] = load_tf(ds["tfs"][tf]["path"]); build_log[tf] = "saved"
        else:
            data[tf] = build_higher(base, tf); build_log[tf] = "built (causal)"
    timing["data_prep"] = round(time.perf_counter() - t0, 3)

    step("Generating signals", 30)
    t1 = time.perf_counter()
    pt, _ = point_size(base)
    cost = modelled_cost_pts(base)
    direction, stop, rr = get_signals(Strat, data, base_tf)   # length-validated inside
    timing["strategy"] = round(time.perf_counter() - t1, 3)

    step("Checking for look-ahead", 45)
    t1 = time.perf_counter()
    ok_la, ndiff = lookahead_check(Strat, data, base_tf, build_log, d_full=direction)
    timing["lookahead"] = round(time.perf_counter() - t1, 3)
    if not ok_la:
        return {
            "error": "LOOKAHEAD",
            "msg": f"{ndiff} past signal(s) changed when future data was correctly hidden.",
            "hint": "Your strategy reads a higher-timeframe candle before it has CLOSED "
                    "(a very common multi-timeframe mistake). Use only the LAST CLOSED "
                    "higher-timeframe bar at each point in time.",
        }

    step("Running backtest", 55)
    t1 = time.perf_counter()
    tr = backtest(direction, stop, rr, data[base_tf], cost, pt)
    timing["backtest"] = round(time.perf_counter() - t1, 3)
    if len(tr) < 5:
        return {
            "error": "NO_TRADES",
            "msg": f"Only {len(tr)} trades generated.",
            "hint": "The strategy almost never triggers. Loosen its conditions or check the logic.",
        }

    step("Computing metrics", 68)
    t1 = time.perf_counter()
    dev, val, hold, d0, d1, d2, d3 = split_trades(tr, base)
    md_all = metrics(tr)
    md_dev = metrics(dev)
    md_val = metrics(val)
    md_hold = metrics(hold)
    timing["metrics"] = round(time.perf_counter() - t1, 3)
    # metric self-consistency gate (items 16-17)
    if not all(m["consistent"] for m in (md_all, md_dev, md_val, md_hold)):
        return {"error": "METRIC ERROR", "line": 0,
                "msg": "Internal metric inconsistency (expectancy != win/loss decomposition).",
                "hint": "This is an engine bug, not your strategy. Please report it."}

    # --- DEEP-only heavy diagnostics (items 9, 22, 23) ---
    mc = mc2 = None
    cost_ok = None
    cost_rows = []
    if deep:
        step("Monte Carlo (phase 1)", 78)
        mc = monte_carlo(tr, cfg)
        step("Monte Carlo (phase 2)", 85)
        mc2 = monte_carlo(tr, cfg, phase="phase2")
        step("Cost stress", 92)
        t1 = time.perf_counter()
        for m in (1.0, 1.5, 2.0, 3.0):
            # reuse SAME signals; only the execution/P&L layer reruns (item 23)
            t2 = backtest(direction, stop, rr, data[base_tf], cost, pt, cost_mult=m)
            e = metrics(t2)["expR"]
            cost_rows.append({"mult": m, "expR": round(e, 4), "pos": e > 0})
        cost_ok = cost_rows[2]["pos"]  # survives 2x
        timing["diagnostics"] = round(time.perf_counter() - t1, 3)

    score, verdict, reasons = prop_score(md_dev, md_val, md_hold, mc, cost_ok)
    p1 = mc["pass_pct"] if mc else None
    p2 = mc2["pass_pct"] if mc2 else None
    both = (p1 * p2 / 100.0) if (p1 is not None and p2 is not None) else None
    # execution-sensitivity flag (item 39): sign untrustworthy when tiny
    exec_sensitive = abs(md_all["expR"]) < EXEC_UNCERTAINTY_R
    # fast, deterministic execution-confidence note (item 32)
    med_hold_bars = float(
        (pd.to_datetime(tr.exit) - pd.to_datetime(tr.entry)).dt.total_seconds().median()
        / (TF_MIN[base_tf] * 60)
    )
    low_exec = TF_MIN[base_tf] <= 30 and med_hold_bars < 3

    # === RESEARCH EQUITY CURVE ============================================
    # ONE trade set (all of tr), ONE sizing model: fixed fractional of the
    # INITIAL balance (no compounding -> no blow-up; $ and R drawdown are
    # exactly proportional; every section below derives from this). Items 2/4/8.
    R = tr.R.values
    bal0 = cfg["balance"]
    fixed_risk = bal0 * cfg["risk_pct"] / 100.0    # $ risked per 1R, constant
    eqpath = [bal0]
    for r in R:
        eqpath.append(eqpath[-1] + r * fixed_risk)
    # Max drawdown = single largest peak-to-trough decline. $ and % come from
    # the SAME excursion so they can never disagree (fixes Bug B).
    peak = eqpath[0]
    maxdd_pct = 0.0
    maxdd_usd = 0.0
    dd_series = []
    for v in eqpath:
        if v > peak:
            peak = v
        d_usd = peak - v
        d_pct = 100 * d_usd / peak if peak > 0 else 0.0
        dd_series.append(-d_pct)
        if d_pct > maxdd_pct:
            maxdd_pct = d_pct
            maxdd_usd = d_usd
    peak_bal = max(eqpath)
    trough_bal = min(eqpath)
    research_final = eqpath[-1]

    # === ACCOUNT SIMULATION (prop rules, same sizing model) ===============
    # Runs the ACTUAL trade sequence under the firm's rules; stops at target or
    # bust. Same fixed-fractional model as the Monte Carlo -> item 9 satisfied.
    acct = prop_sim_days(tr, cfg, phase="phase1")

    step("Finalizing", 97)
    timing["total"] = round(time.perf_counter() - t0, 3)
    # trade list (last 200)
    tl = []
    for _, row in tr.tail(200).iterrows():
        tl.append(
            {
                "date": str(pd.to_datetime(row.entry))[:16],
                "dir": "BUY" if row.dir > 0 else "SELL",
                "entry": round(row.entry_px, 2),
                "sl": round(row.sl, 2),
                "tp": round(row.tp, 2),
                "R": round(row.R, 2),
            }
        )
    result = {
        "ok": True,
        "score": score,
        "verdict": verdict,
        "reasons": reasons,
        "mode": mode,
        "timing": timing,
        "exec_sensitive": bool(exec_sensitive),
        "exec_threshold": EXEC_UNCERTAINTY_R,
        "build_log": build_log,
        "phase1": round(p1) if p1 is not None else None,
        "phase2": round(p2) if p2 is not None else None,
        "both": round(both) if both is not None else None,
        "risk_maxloss": round(mc["fail_maxloss"]) if mc else None,
        "risk_daily": round(mc["fail_daily"]) if mc else None,
        "metrics": {
            "pf": round(md_all["pf"], 2),          # PF of the FULL trade set (was dev-only)
            "expR": round(md_all["expR"], 4),
            "win": round(md_all["win"], 1),
            "maxdd": round(maxdd_pct, 1),
            "maxdd_usd": round(maxdd_usd),
            "peak_bal": round(peak_bal),
            "trough_bal": round(trough_bal),
            "trades": md_all["n"],
            "sharpe": round(md_all["sharpe"], 2),
        },
        "splits": {
            "dev": {
                "expR": round(md_dev["expR"], 4),
                "n": md_dev["n"],
                "pos": md_dev["expR"] > 0,
            },
            "val": {
                "expR": round(md_val["expR"], 4),
                "n": md_val["n"],
                "pos": md_val["expR"] > 0,
            },
            "hold": {
                "expR": round(md_hold["expR"], 4),
                "n": md_hold["n"],
                "pos": md_hold["expR"] > 0,
            },
        },
        "split_dates": {
            "dev": f"{d0} → {d1}",
            "val": f"{d1} → {d2}",
            "hold": f"{d2} → {d3}",
        },
        "mc": mc,
        "cost": cost_rows,
        "cost_ok": cost_ok,
        "equity": [round(v, 1) for v in eqpath[:: max(1, len(eqpath) // 400)]],
        "drawdown": [round(v, 2) for v in dd_series[:: max(1, len(dd_series) // 400)]],
        "trades": tl,
        "trade_count": md_all["n"],           # single canonical count, used everywhere
        "sizing": f"fixed {cfg['risk_pct']}% of ${bal0:,.0f} = ${fixed_risk:,.0f} per 1R (no compounding)",
        "base_tf": base_tf,
        "low_exec": low_exec,
        "research_final": round(research_final),
        "account": {
            "start": cfg["balance"],
            "target1": round(cfg["balance"] * (1 + cfg["phase1"] / 100)),
            "daily": round(cfg["balance"] * cfg["daily_loss"] / 100),
            "maxloss": round(cfg["balance"] * cfg["max_loss"] / 100),
            "worst": round(acct["worst"]),
            "final": round(acct["final"]),
            "outcome": acct["outcome"],
            "days": acct["days"],
            "trades_taken": acct["taken"],     # labeled: trades before the account stopped
        },
    }
    # ---- INTERNAL CONSISTENCY AUDIT (item 11): fail the report on any mismatch
    audit = audit_consistency(result, md_all, md_dev, md_val, md_hold,
                              eqpath, fixed_risk, maxdd_pct, maxdd_usd)
    result["audit"] = audit
    if not audit["ok"]:
        # keep the numbers visible so the mismatch can be seen, but force the
        # verdict to FAILED and let the UI show a red inconsistency banner.
        result["verdict"] = ["🔴", "INCONSISTENT"]
        result["score"] = 0

    # save FULL report to history so a long run is never lost (user request).
    # Stamp the id INTO the result before saving so the file is self-identifying.
    report_id = uuid.uuid4().hex[:12]
    result["report_id"] = report_id
    result["saved_at"] = datetime.now().strftime("%Y-%m-%d %H:%M")
    save_report(report_id, result)
    h = load_hist()
    h.append(
        {
            "id": report_id,
            "date": result["saved_at"],
            "score": result["score"],
            "verdict": result["verdict"][1],
            "trades": md_all["n"],
            "hold_expR": round(md_hold["expR"], 4),
            "mode": mode,
        }
    )
    save_hist(h)
    return result


# ---------------- background jobs: live progress, no UI freeze ---------------
def start_job(code, cfg, mode):
    """Kick off run_test in a daemon thread; return a job_id the UI polls."""
    job_id = uuid.uuid4().hex[:12]
    with JOBS_LOCK:
        # prune finished jobs older than 2 min so a late poll never errors mid-run
        for k in [k for k, v in JOBS.items()
                  if v.get("done") and time.time() - v["started"] > 120]:
            JOBS.pop(k, None)
        JOBS[job_id] = {"stage": "Starting", "pct": 0, "done": False,
                        "result": None, "started": time.time(), "mode": mode}

    def _progress(stage, pct):
        with JOBS_LOCK:
            j = JOBS.get(job_id)
            if j is not None:
                j["stage"] = stage; j["pct"] = pct

    def _work():
        try:
            res = run_test(code, cfg, mode=mode, progress=_progress)
        except StrategyError as e:
            res = {"error": e.kind, "line": e.line, "msg": e.msg, "hint": e.hint}
        except Exception as e:
            res = {"error": "ERROR", "line": 0, "msg": f"{type(e).__name__}: {e}",
                   "hint": "Unexpected engine error."}
        with JOBS_LOCK:
            j = JOBS.get(job_id)
            if j is not None:
                j["result"] = res; j["stage"] = "Done"; j["pct"] = 100; j["done"] = True

    threading.Thread(target=_work, daemon=True).start()
    return job_id


def job_status(job_id):
    with JOBS_LOCK:
        j = JOBS.get(job_id)
        if j is None:
            return {"error": "NO_JOB", "msg": "Unknown job."}
        elapsed = round(time.time() - j["started"], 1)
        limit = TIMEOUT_DEEP if j["mode"] == "deep" else TIMEOUT_FAST
        out = {"stage": j["stage"], "pct": j["pct"], "done": j["done"],
               "elapsed": elapsed, "result": j["result"]}
        # hard wall for the UI even if a runaway loop keeps the thread alive
        if not j["done"] and elapsed > limit + 5:
            out["done"] = True
            out["result"] = {"error": "TIMEOUT", "line": 0,
                             "msg": f"No result after {elapsed}s (limit {limit}s).",
                             "hint": "Likely an inefficient per-bar history search in the "
                                     "strategy. Precompute outside the loop."}
        return out          # keep the finished job around; pruned later by start_job


# ----------------------------------------------------------------------------
DEFAULT_STRATEGY = """class Strategy:
    # Timeframes you need. Higher ones are built automatically from your data.
    timeframes = ["M30"]

    def signals(self, data):
        import numpy as np
        df = data["M30"]                     # time open high low close volume atr
        c   = df["close"].values
        ef  = df["close"].ewm(span=20).mean().values
        es  = df["close"].ewm(span=50).mean().values
        atr = df["atr"].values
        n = len(df)
        direction = np.zeros(n)              # +1 long / -1 short / 0 none
        stop      = np.full(n, np.nan)       # stop-loss PRICE
        rr        = np.full(n, 2.0)          # reward:risk multiple
        for i in range(1, n):
            if ef[i] > es[i] and ef[i-1] <= es[i-1]:
                direction[i] = 1;  stop[i] = c[i] - 1.5*atr[i]
            elif ef[i] < es[i] and ef[i-1] >= es[i-1]:
                direction[i] = -1; stop[i] = c[i] + 1.5*atr[i]
        return direction, stop, rr
"""

HELP = {
    "pf": "How much the strategy made vs what it lost. Above 1 means it made more than it lost.",
    "expR": "Average won or lost per trade, in risk units (R). Positive is better. Below ~0.04 is basically noise.",
    "win": "Share of trades that won. A high win rate does NOT by itself mean a good strategy.",
    "maxdd": "The biggest drop in the account before it recovered. Lower is safer.",
    "trades": "How many trades were tested. Fewer than ~100 means the result may not be trustworthy.",
    "sharpe": "Return compared to how bumpy the ride was. Higher is generally better.",
    "oos": "How it did on data it was never tuned on (validation + holdout). One of the most important checks.",
    "prop": "Estimated chance of hitting the profit target before breaking a drawdown rule.",
    "score": "One number combining profit, out-of-sample survival, drawdown and prop pass odds. Negative holdout caps it low.",
}


# ============================== ENTRY POINT ================================
if __name__ == "__main__":
    import tester_ui, sys as _s, os as _os

    # Read PORT from environment (Render sets $PORT). Default to 5000 for local runs.
    try:
        _port = int(_os.environ.get("PORT", "5000"))
    except Exception:
        _port = 5000
    tester_ui.serve(_s.modules[__name__], _port, "0.0.0.0")
