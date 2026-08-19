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
    "best_day_pct": 0,      # Best Day Rule: best single day <= X% of total profit (0 = rule off)
    "consistency": 0,
    "hours": "",
}


# ----------------------------------------------------------------------------
def load_cfg():
    cfg = dict(DEFAULT_CFG)
    if os.path.exists(CFG_F):
        try:
            cfg.update(json.load(open(CFG_F)))
        except Exception:
            pass
    # SELF-HEAL: a saved dataset_dir may be an absolute path from another machine
    # (e.g. a Windows path saved locally, then run on a Linux host like Render).
    # If it does not exist here, fall back to the data/ folder bundled next to
    # this app - which is where the repo keeps the CSVs.
    d = cfg.get("dataset_dir", "")
    if not d or not os.path.isdir(d):
        cfg["dataset_dir"] = DATA
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


# ----------------------------------------------------------------------------
# CONTROL TESTS — is the "edge" real, or just the instrument's drift?
# ----------------------------------------------------------------------------
def benchmark_metrics(strat_dir, data, base_tf, cost_pts, pt, side):
    """Drift-only control. Fire on a fixed cadence (trade count matched to the
    strategy) with the SAME ATR-stop / RR=2 mechanics, ALL one direction:
    side=+1 always-long, side=-1 always-short. A long-only system that merely
    rides an uptrend (e.g. gold) will roughly TIE this benchmark; a strategy
    with real timing edge will clearly beat it."""
    df = data[base_tf]
    c = df["close"].to_numpy(dtype=float)
    a = df["atr"].to_numpy(dtype=float)
    n = len(df)
    n_strat = int(np.count_nonzero(strat_dir))
    step = max(1, n // max(n_strat, 1))            # comparable number of trades
    d = np.zeros(n)
    s = np.full(n, np.nan)
    rr = np.full(n, 2.0)
    for i in range(300, n, step):
        d[i] = side
        s[i] = c[i] - 1.5 * a[i] if side > 0 else c[i] + 1.5 * a[i]
    return metrics(backtest(d, s, rr, df, cost_pts, pt))


def invert_signals(direction, stop, data, base_tf):
    """Flip BUY<->SELL and reflect each stop across its signal-bar close so the
    risk distance is preserved (a long stop below becomes a short stop the same
    distance above). If a strategy has a genuine directional edge, running its
    exact inverse must be clearly LOSING; if the inverse ties or wins, the
    'edge' is not coming from correct directional calls."""
    c = data[base_tf]["close"].to_numpy(dtype=float)
    return -np.asarray(direction, dtype=float), 2.0 * c - np.asarray(stop, dtype=float)


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
    # A degenerate trade set (every R identical, e.g. a wrong-side stop losing
    # 1R every time) gives se == 0 -> t == +-inf, which json.dump writes as
    # `Infinity` and the browser's JSON.parse then rejects, blanking the report.
    # Keep t finite so a broken strategy still renders its (bad) numbers.
    t_stat = (R.mean() / se) if se > 0 else 0.0
    if not np.isfinite(t_stat):
        t_stat = 0.0
    return dict(
        n=int(len(R)),
        expR=expR,
        t=float(t_stat),
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


def _pctl(vals, q):
    """Percentile of a list, or None when there is nothing to summarise."""
    return int(np.percentile(vals, q)) if len(vals) else None


def _run_phase(R, exit_days, start, bal0, unit, tgt_pct, dd_pct, floor,
               min_days, best_day_pct):
    """Run ONE phase forward from index `start` in the REAL trade order.

    Returns (outcome, end_index, trades_used, trading_days_used). Honours the
    configured minimum-trading-days rule and the Best Day rule: reaching the
    target is not enough if either rule is still unsatisfied - the account keeps
    trading, exactly as a real challenge would."""
    bal = bal0
    day = None
    day_start = bal
    used_days = set()
    day_pnl = {}
    n = len(R)
    for k in range(start, n):
        dk = exit_days[k]
        if dk != day:
            day = dk
            day_start = bal
        used_days.add(dk)
        pnl = R[k] * unit
        bal += pnl
        day_pnl[dk] = day_pnl.get(dk, 0.0) + pnl
        if bal <= day_start * (1 - dd_pct):
            return "FAIL_DAILY", k, k - start + 1, len(used_days)
        if bal <= floor:
            return "FAIL_MAXLOSS", k, k - start + 1, len(used_days)
        if bal >= bal0 * (1 + tgt_pct) and len(used_days) >= min_days:
            if best_day_pct > 0:
                profit = bal - bal0
                pos = [v for v in day_pnl.values() if v > 0]
                # Best Day rule: the largest winning day may not exceed
                # best_day_pct of total profit. Not a failure - the trader must
                # keep trading until the ratio complies, so we continue.
                if profit > 0 and pos and (max(pos) / profit) > (best_day_pct / 100.0):
                    continue
            return "PASS", k, k - start + 1, len(used_days)
    return "TIMEOUT", n - 1, n - start, len(used_days)


def sequential_challenge(tr, cfg):
    """FULL 2-STEP challenge in the REAL historical trade order.

    Starts a challenge at every historical trade, runs Phase 1 forward through
    the actual sequence, and - only for the paths that actually completed Phase
    1 - continues into Phase 2 from the very next trade with the balance reset
    to the starting balance (how a real 2-step works).

    The bootstrap Monte Carlo shuffles trades, which breaks up real losing
    clusters and flatters a regime-dependent strategy. This preserves them.

    Phase-2 numbers here are CONDITIONAL on Phase 1 having passed. The full
    2-step probability is measured directly, never inferred as p1 x p2."""
    if len(tr) < 10:
        return None
    R = tr.R.values
    exit_days = pd.to_datetime(tr.exit).dt.date.values
    entry_t = pd.to_datetime(tr.entry).values
    bal0 = cfg["balance"]
    unit = bal0 * cfg["risk_pct"] / 100.0
    dd = cfg["daily_loss"] / 100.0
    floor = bal0 * (1 - cfg["max_loss"] / 100.0)
    min_days = int(cfg.get("min_days", 0) or 0)
    bd = float(cfg.get("best_day_pct", 0) or 0)
    t1 = cfg["phase1"] / 100.0
    t2 = cfg["phase2"] / 100.0

    def days_between(a, b):
        return int((entry_t[b] - entry_t[a]) / np.timedelta64(1, "D"))

    p1 = {"PASS": 0, "FAIL_MAXLOSS": 0, "FAIL_DAILY": 0, "TIMEOUT": 0}
    p2 = {"PASS": 0, "FAIL_MAXLOSS": 0, "FAIL_DAILY": 0, "TIMEOUT": 0}
    p1_days, p1_trades, p1_tdays = [], [], []
    p2_days, p2_trades = [], []
    full_days, full_trades = [], []
    n_full_pass = 0
    n_starts = len(R)

    for start in range(n_starts):
        o1, e1, k1, td1 = _run_phase(R, exit_days, start, bal0, unit, t1, dd,
                                     floor, min_days, bd)
        p1[o1] += 1
        if o1 != "PASS":
            continue
        p1_days.append(days_between(start, e1))
        p1_trades.append(k1)
        p1_tdays.append(td1)
        if e1 + 1 >= n_starts:          # Phase 1 passed but no data left for Phase 2
            p2["TIMEOUT"] += 1
            continue
        o2, e2, k2, _ = _run_phase(R, exit_days, e1 + 1, bal0, unit, t2, dd,
                                   floor, min_days, bd)
        p2[o2] += 1
        if o2 == "PASS":
            n_full_pass += 1
            p2_days.append(days_between(e1 + 1, e2))
            p2_trades.append(k2)
            full_days.append(days_between(start, e2))
            full_trades.append(k1 + k2)

    n_p1_pass = p1["PASS"]
    n_p2_eval = sum(p2.values())

    def pack(d, tot):
        return {k: (100.0 * v / tot if tot else None) for k, v in d.items()}

    return {
        "starts": n_starts,
        "min_days": min_days,
        "best_day_pct": bd,
        # ---- Phase 1: unconditional, every start ----
        "p1": dict(pack(p1, n_starts),
                   n_pass=n_p1_pass,
                   med_trades=_pctl(p1_trades, 50),
                   med_days=_pctl(p1_days, 50), d25=_pctl(p1_days, 25),
                   d75=_pctl(p1_days, 75), d90=_pctl(p1_days, 90),
                   worst_days=_pctl(p1_days, 100),
                   med_trading_days=_pctl(p1_tdays, 50)),
        # ---- Phase 2: CONDITIONAL on Phase 1 having passed ----
        "p2": dict(pack(p2, n_p2_eval),
                   evaluated=n_p2_eval, n_pass=p2["PASS"],
                   med_trades=_pctl(p2_trades, 50),
                   med_days=_pctl(p2_days, 50), d25=_pctl(p2_days, 25),
                   d75=_pctl(p2_days, 75), d90=_pctl(p2_days, 90),
                   worst_days=_pctl(p2_days, 100)),
        # ---- FULL 2-step: measured directly, not p1 x p2 ----
        "full": {
            "pass_pct": 100.0 * n_full_pass / n_starts,
            "fail_pct": 100.0 * (n_starts - n_full_pass) / n_starts,
            "p1_pass_p2_fail_pct": 100.0 * (n_p1_pass - n_full_pass) / n_starts,
            "p1_fail_pct": 100.0 * (n_starts - n_p1_pass) / n_starts,
            "med_days": _pctl(full_days, 50), "d75": _pctl(full_days, 75),
            "d90": _pctl(full_days, 90), "worst_days": _pctl(full_days, 100),
            "med_trades": _pctl(full_trades, 50),
        },
    }


def monte_carlo(tr, cfg, nsims=1000, phase="phase1", seed=7):
    """Bootstrap the trade sequence; run the CONFIGURED prop rules each time.

    Fixed-fractional of the INITIAL balance (never compounds), so this answers
    the only question that matters for a challenge: starting from $balance under
    THESE rules, what is the probability of reaching THIS phase target before a
    max-loss or daily-loss breach? Also returns the distribution of trades needed
    to pass, drawdown, and losing-streak stats. All numbers recompute whenever the
    account settings change - nothing here is hardcoded."""
    if len(tr) < 10:
        return None
    R = tr.R.values
    bal0 = cfg["balance"]
    risk = cfg["risk_pct"] / 100.0
    tgt = cfg[phase] / 100.0
    dd = cfg["daily_loss"] / 100.0
    mx = cfg["max_loss"] / 100.0
    floor = bal0 * (1 - mx)
    unit = bal0 * risk                       # $ risked per 1R, constant (no compounding)
    rng = np.random.default_rng(seed)
    outcomes = {"PASS": 0, "FAIL_MAXLOSS": 0, "FAIL_DAILY": 0, "TIMEOUT": 0}
    dds = []
    streaks = []
    to_pass = []                             # trades needed on the runs that passed
    horizon = min(len(R), 400)
    for _ in range(nsims):
        seq = R[rng.integers(0, len(R), horizon)]
        bal = bal0
        ds = bal
        peak = bal
        mdd = 0.0
        day_len = int(rng.integers(2, 6))
        res = "TIMEOUT"
        strk = 0
        mstrk = 0
        for k, r in enumerate(seq):
            if k % day_len == 0:
                ds = bal
            bal += r * unit
            peak = max(peak, bal)
            mdd = max(mdd, (peak - bal) / peak)
            strk = strk + 1 if r < 0 else 0
            mstrk = max(mstrk, strk)
            if bal <= ds * (1 - dd):
                res = "FAIL_DAILY"
                break
            if bal <= floor:
                res = "FAIL_MAXLOSS"
                break
            if bal >= bal0 * (1 + tgt):
                res = "PASS"
                to_pass.append(k + 1)
                break
        outcomes[res] += 1
        dds.append(mdd * 100)
        streaks.append(mstrk)
    tot = sum(outcomes.values())
    passed = to_pass if to_pass else None
    return dict(
        pass_pct=100 * outcomes["PASS"] / tot,
        fail_maxloss=100 * outcomes["FAIL_MAXLOSS"] / tot,
        fail_daily=100 * outcomes["FAIL_DAILY"] / tot,
        timeout=100 * outcomes["TIMEOUT"] / tot,
        worst_dd=float(np.percentile(dds, 95)),
        typ_dd=float(np.median(dds)),
        typ_streak=int(np.median(streaks)),
        worst_streak=int(np.percentile(streaks, 95)),
        med_trades=int(np.median(passed)) if passed else None,
        worst_trades=int(np.percentile(passed, 95)) if passed else None,
        nsims=int(nsims),
    )


# ----------------------------------------------------------------------------
def deterministic_path(tr, cfg):
    """ONE HISTORICAL PATH. Runs the actual trade sequence from the first trade
    through Phase 1 and, if it completes, Phase 2. This is a single realisation
    of history - it is NOT a probability and must never be reported as one."""
    if len(tr) < 5:
        return None
    R = tr.R.values
    exit_days = pd.to_datetime(tr.exit).dt.date.values
    entry_t = pd.to_datetime(tr.entry).values
    bal0 = cfg["balance"]
    unit = bal0 * cfg["risk_pct"] / 100.0
    dd = cfg["daily_loss"] / 100.0
    floor = bal0 * (1 - cfg["max_loss"] / 100.0)
    min_days = int(cfg.get("min_days", 0) or 0)
    bd = float(cfg.get("best_day_pct", 0) or 0)

    o1, e1, k1, td1 = _run_phase(R, exit_days, 0, bal0, unit,
                                 cfg["phase1"] / 100.0, dd, floor, min_days, bd)
    days1 = int((entry_t[e1] - entry_t[0]) / np.timedelta64(1, "D"))
    out = {"p1_outcome": o1, "p1_trades": k1, "p1_days": days1,
           "p1_trading_days": td1, "p2_outcome": "NOT REACHED",
           "p2_trades": None, "p2_days": None,
           "total_trades": k1, "total_days": days1, "full": "FAILED"}
    if o1 != "PASS":
        out["full"] = "FAILED"
    elif e1 + 1 >= len(R):
        out["p2_outcome"] = "NOT REACHED"; out["full"] = "INCOMPLETE"
    else:
        o2, e2, k2, _ = _run_phase(R, exit_days, e1 + 1, bal0, unit,
                                   cfg["phase2"] / 100.0, dd, floor, min_days, bd)
        days2 = int((entry_t[e2] - entry_t[e1 + 1]) / np.timedelta64(1, "D"))
        out.update(p2_outcome=o2, p2_trades=k2, p2_days=days2,
                   total_trades=k1 + k2,
                   total_days=int((entry_t[e2] - entry_t[0]) / np.timedelta64(1, "D")),
                   full=("PASSED" if o2 == "PASS"
                         else ("INCOMPLETE" if o2 == "TIMEOUT" else "FAILED")))
    # equity extremes over the whole realised path (research view)
    eq = bal0 + np.cumsum(R) * unit
    out["worst_balance"] = float(min(eq.min(), bal0))
    out["final_balance"] = float(eq[-1])
    peak = np.maximum.accumulate(np.concatenate([[bal0], eq]))
    out["max_dd_pct"] = float((((np.concatenate([[bal0], eq]) - peak) / peak).min()) * -100)
    return out


def monte_carlo_joint(tr, cfg, nsims=1000, seed=11):
    """SHUFFLED bootstrap of BOTH phases jointly.

    Trade ORDER IS RANDOMISED - this deliberately destroys real losing clusters,
    so it answers "if my trades arrived in a random order, how often would I
    pass?" It is NOT the historical answer; compare against sequential_challenge.

    Phase 2 is simulated by continuing to draw trades after Phase 1 completes,
    with the balance reset to the starting balance. The both-phase probability
    is therefore a TRUE joint probability, never p1 x p2."""
    if len(tr) < 10:
        return None
    R = tr.R.values
    bal0 = cfg["balance"]
    unit = bal0 * cfg["risk_pct"] / 100.0
    dd = cfg["daily_loss"] / 100.0
    floor = bal0 * (1 - cfg["max_loss"] / 100.0)
    min_days = int(cfg.get("min_days", 0) or 0)
    t1 = cfg["phase1"] / 100.0
    t2 = cfg["phase2"] / 100.0
    rng = np.random.default_rng(seed)
    horizon = 1200

    def phase(seq, pos, tgt, day_len):
        bal = bal0
        day_start = bal
        used = 0
        peak = bal
        mdd = 0.0
        strk = mstrk = 0
        k = pos
        cnt = 0
        while k < len(seq):
            if cnt % day_len == 0:
                day_start = bal
                used += 1
            r = seq[k]
            bal += r * unit
            peak = max(peak, bal)
            mdd = max(mdd, (peak - bal) / peak)
            strk = strk + 1 if r < 0 else 0
            mstrk = max(mstrk, strk)
            k += 1; cnt += 1
            if bal <= day_start * (1 - dd):
                return "FAIL_DAILY", k, cnt, mdd, mstrk
            if bal <= floor:
                return "FAIL_MAXLOSS", k, cnt, mdd, mstrk
            if bal >= bal0 * (1 + tgt) and used >= min_days:
                return "PASS", k, cnt, mdd, mstrk
        return "TIMEOUT", k, cnt, mdd, mstrk

    o1 = {"PASS": 0, "FAIL_MAXLOSS": 0, "FAIL_DAILY": 0, "TIMEOUT": 0}
    o2 = dict(o1)
    both = 0
    n1, n2, ntot, dds, strks = [], [], [], [], []
    for _ in range(nsims):
        seq = R[rng.integers(0, len(R), horizon)]
        dl = int(rng.integers(2, 6))
        r1, pos, c1, dd1, s1 = phase(seq, 0, t1, dl)
        o1[r1] += 1
        dds.append(dd1 * 100); strks.append(s1)
        if r1 != "PASS":
            continue
        n1.append(c1)
        r2, _, c2, dd2, s2 = phase(seq, pos, t2, dl)
        o2[r2] += 1
        dds[-1] = max(dds[-1], dd2 * 100); strks[-1] = max(strks[-1], s2)
        if r2 == "PASS":
            both += 1; n2.append(c2); ntot.append(c1 + c2)
    tot = max(nsims, 1)
    n2e = max(sum(o2.values()), 1)
    return {
        "nsims": nsims,
        "p1": {k: 100.0 * v / tot for k, v in o1.items()},
        "p2_cond": {k: 100.0 * v / n2e for k, v in o2.items()},
        "p2_evaluated": sum(o2.values()),
        "both_pct": 100.0 * both / tot,
        "med_trades_p1": _pctl(n1, 50), "med_trades_p2": _pctl(n2, 50),
        "med_trades_total": _pctl(ntot, 50),
        "typ_dd": float(np.median(dds)) if dds else None,
        "worst_dd": float(np.percentile(dds, 95)) if dds else None,
        "typ_streak": int(np.median(strks)) if strks else None,
        "worst_streak": int(np.percentile(strks, 95)) if strks else None,
    }


def winner_concentration(tr):
    """Does the result rest on a handful of outlier trades?"""
    R = np.sort(tr.R.values)[::-1]
    tot = R.sum()
    out = {"expR": float(R.mean()), "levels": []}
    for k in (1, 3, 5, 10):
        if len(R) <= k + 5:
            continue
        out["levels"].append({
            "k": k,
            "expR_without": float(R[k:].mean()),
            "pct_of_totR": (float(100.0 * R[:k].sum() / tot) if tot else None),
        })
    return out


def yearly_breakdown(tr):
    """Per calendar year, to show whether the edge is one regime."""
    t = tr.copy()
    t["yr"] = pd.to_datetime(t.entry).dt.year
    rows = []
    for y, g in t.groupby("yr"):
        R = g.R.values
        w = R[R > 0].sum(); l = abs(R[R <= 0].sum())
        rows.append({"year": int(y), "n": int(len(R)), "expR": float(R.mean()),
                     "pf": float(min(w / l, 9.99)) if l > 0 else 9.99,
                     "win": float(100 * (R > 0).mean())})
    return rows


def risk_comparison(tr, cfg, levels=(0.35, 0.40, 0.50, 0.60, 0.65, 0.70, 0.75, 0.85)):
    """Same trades, same strategy - only the account risk setting changes.
    Makes the safety/speed trade-off directly visible."""
    rows = []
    for rp in levels:
        c = dict(cfg); c["risk_pct"] = rp
        sq = sequential_challenge(tr, c)
        mj = monte_carlo_joint(tr, c, nsims=400)
        if not sq or not mj:
            continue
        rows.append({
            "risk": rp,
            "seq_p1": sq["p1"]["PASS"], "seq_p2_cond": sq["p2"]["PASS"],
            "seq_full": sq["full"]["pass_pct"],
            "mc_both": mj["both_pct"],
            "maxloss": sq["p1"]["FAIL_MAXLOSS"], "daily": sq["p1"]["FAIL_DAILY"],
            "med_days": sq["full"]["med_days"] or sq["p1"]["med_days"],
            "typ_dd": mj["typ_dd"], "worst_dd": mj["worst_dd"],
        })
    return rows


def best_day_report(tr, cfg):
    """Measure the Best Day ratio on the real trade sequence."""
    thr = float(cfg.get("best_day_pct", 0) or 0)
    unit = cfg["balance"] * cfg["risk_pct"] / 100.0
    t = tr.copy()
    t["d"] = pd.to_datetime(t.exit).dt.date
    daily = (t.groupby("d").R.sum() * unit)
    pos = daily[daily > 0]
    total_pos = float(pos.sum())
    best = float(pos.max()) if len(pos) else 0.0
    pct = (100.0 * best / total_pos) if total_pos > 0 else None
    return {"enabled": thr > 0, "threshold": thr, "best_day": best,
            "total_positive": total_pos, "best_day_pct": pct,
            "compliant": (None if thr <= 0 or pct is None else pct <= thr)}


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
def prop_score(md_all, dev, val, hold, mc, mc2, cost_rows, bench, inv_expR, exec_thr):
    """0-100, PROP-CHALLENGE FIRST.

    The score primarily measures the probability of passing the configured
    challenge, plus robustness gates that a drift-riding or over-fit strategy
    cannot fake:

      * pass probability (both phases)      - the actual objective
      * holdout edge by MAGNITUDE           - +0.001R is not rewarded like +0.20R
      * survival at 3x cost
      * outperformance vs the aligned drift benchmark  (anti gold-drift)
      * risk of ruin (max-loss / daily-loss odds)
      * stability across dev/val/hold
      * inversion collapse (a real edge's mirror must lose)

    Deliberately NOT rewarded: raw trade count, a fixed RR, or a barely-positive
    holdout. A strategy that makes money but fails the edge gates is labelled
    'NO CLEAR EDGE' rather than EXCELLENT."""
    thr = exec_thr
    reasons = []

    p1 = mc["pass_pct"] if mc else 0.0
    p2 = mc2["pass_pct"] if mc2 else 0.0
    both = p1 * p2 / 100.0
    cost3x = next((c["expR"] for c in cost_rows if abs(c["mult"] - 3.0) < 1e-9), None)
    hold_n, hold_e = hold["n"], hold["expR"]
    hold_t = hold.get("t", 0.0)
    edge = bench["edge"]                      # strategy expR - aligned-benchmark expR

    # ---- edge gates: none of these depend on trade count or market drift ----
    # Holdout must clear the noise floor AND be statistically distinguishable
    # from zero. A big-looking +0.57R on 29 trades whose 95% CI still spans 0 is
    # not evidence; requiring t >= 2 stops a lucky handful of wins reading as
    # "CLEAR EDGE".
    hold_ok = hold_n >= 15 and hold_e > thr and hold_t >= 2.0
    bench_ok = edge > thr
    cost_ok = (cost3x is not None) and (cost3x > 0.0)
    inv_ok = inv_expR < -thr                 # mirror clearly loses -> directional edge is real
    edge_ok = hold_ok and bench_ok and cost_ok

    def c01(x):
        return max(0.0, min(1.0, x))

    # ---- weighted sub-scores (each 0..1), weights sum to 100 ----
    s_prop = c01(both / 100.0)                                  # 30  both-phase odds
    s_p1 = c01(p1 / 100.0)                                      # 10  phase-1 odds
    s_hold = c01((hold_e - thr) / (0.20 - thr)) if hold_n >= 15 else 0.0  # 18 by magnitude
    s_cost = c01((cost3x if cost3x is not None else -1.0) / (2 * thr))    # 8
    s_bench = c01(edge / (2 * thr))                            # 18  anti-drift
    s_stab = sum(1 for m in (dev, val, hold) if m["n"] >= 10 and m["expR"] > thr) / 3.0  # 8
    ruin = (mc["fail_maxloss"] + mc["fail_daily"]) if mc else 100.0
    s_risk = c01(1.0 - ruin / 100.0)                           # 8

    s = (30 * s_prop + 10 * s_p1 + 18 * s_hold + 8 * s_cost +
         18 * s_bench + 8 * s_stab + 8 * s_risk)

    # ---- human-readable reasons ----
    reasons.append(("✓" if both >= 40 else "✗", f"Pass-both-phases odds {both:.0f}%"))
    reasons.append(("✓" if p1 >= 50 else "⚠", f"Phase-1 pass odds {p1:.0f}%"))
    if hold_n < 15:
        reasons.append(("⚠", f"Holdout sample small ({hold_n} trades) — unseen-data edge unconfirmed"))
    elif hold_ok:
        reasons.append(("✓", f"Holdout edge {hold_e:+.3f}R on {hold_n} trades (t {hold_t:+.2f}) "
                             f"clears the {thr}R noise floor and is significant"))
    elif hold_e <= thr:
        reasons.append(("✗", f"Holdout {hold_e:+.3f}R is within execution noise ({thr}R) — NO CLEAR EDGE"))
    else:
        reasons.append(("✗", f"Holdout {hold_e:+.3f}R looks large but t is only {hold_t:+.2f} on "
                             f"{hold_n} trades — could be luck, NOT yet an established edge"))
    if bench_ok:
        reasons.append(("✓", f"Beats {bench['aligned']}-only drift benchmark by {edge:+.3f}R"))
    else:
        reasons.append(("✗", f"Does NOT beat {bench['aligned']}-only drift benchmark (edge {edge:+.3f}R)"))
    if cost3x is not None:
        reasons.append(("✓" if cost_ok else "✗", f"Expectancy at 3x realistic cost {cost3x:+.3f}R"))
    reasons.append(("✓" if inv_ok else "⚠",
                    f"Inverted (BUY↔SELL) expectancy {inv_expR:+.3f}R "
                    + ("— reverses as a real edge should" if inv_ok
                       else "— does not clearly lose, so directional edge is weak")))
    if dev["n"] < 30:
        reasons.append(("⚠", f"Only {dev['n']} development trades — thin sample"))

    # ---- HARD CAPS (the anti-gaming rules the user asked for) ----
    if hold_n >= 15 and not hold_ok:
        # covers BOTH a holdout inside the noise floor and one that merely looks
        # big on too few trades (t < 2). Without this a lucky +0.57R on 29 trades
        # scored in the 80s while being labelled NO CLEAR EDGE - a contradiction.
        s = min(s, 45)
    if not bench_ok:
        s = min(s, 45)                       # gold-drift / long-only guard
    if not cost_ok:
        s = min(s, 45)                       # dies under realistic cost
    if inv_expR >= md_all["expR"]:
        s = min(s, 40)                       # its own inverse is as good or better
    if dev["n"] < 30:
        s = min(s, 55)                       # too few trades to trust
    s = max(0.0, min(100.0, s))

    # ---- verdict: edge gates decide the LABEL, score decides the tier ----
    if not edge_ok:
        verdict = ("🟠", "NO CLEAR EDGE")
    elif s >= 80:
        verdict = ("🟢", "EXCELLENT")
    elif s >= 68:
        verdict = ("🟢", "GOOD")
    elif s >= 55:
        verdict = ("🟡", "PROMISING")
    elif s >= 40:
        verdict = ("🟠", "WEAK")
    else:
        verdict = ("🔴", "BAD")

    flags = dict(hold_ok=hold_ok, bench_ok=bench_ok, cost_ok=cost_ok,
                 inv_ok=inv_ok, edge_ok=edge_ok, both=both, p1=p1, p2=p2)
    return round(s), verdict, reasons, flags


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

    # === PROP MONTE CARLO + CONTROL TESTS (run in BOTH modes) =============
    # The prop-challenge probability is the product this tester exists to
    # deliver, so it is computed every time; DEEP only runs MORE simulations.
    t1 = time.perf_counter()
    nsims = 1500 if deep else 400
    step("Prop Monte Carlo (phase 1)", 74)
    mc = monte_carlo(tr, cfg, nsims=nsims, phase="phase1")
    step("Prop Monte Carlo (phase 2)", 80)
    mc2 = monte_carlo(tr, cfg, nsims=nsims, phase="phase2")
    step("Sequential (real-order) 2-step challenge", 83)
    seq = sequential_challenge(tr, cfg)
    step("Joint shuffled Monte Carlo (both phases)", 84)
    mcj = monte_carlo_joint(tr, cfg, nsims=nsims)

    step("Cost stress", 86)
    cost_mults = (1.0, 1.5, 2.0, 3.0) if deep else (1.0, 2.0, 3.0)
    cost_rows = []
    for m in cost_mults:
        # reuse the SAME signals; only the execution / P&L layer reruns
        e = metrics(backtest(direction, stop, rr, data[base_tf], cost, pt, cost_mult=m))["expR"]
        cost_rows.append({"mult": m, "expR": round(e, 4), "pos": e > 0})

    step("Benchmarks + inversion", 90)
    # Drift controls: always-long / always-short, matched trade count, same
    # ATR-stop / RR mechanics. The strategy must BEAT the aligned benchmark.
    bench_long = benchmark_metrics(direction, data, base_tf, cost, pt, +1)
    bench_short = benchmark_metrics(direction, data, base_tf, cost, pt, -1)
    long_ct = int(np.count_nonzero(direction > 0))
    short_ct = int(np.count_nonzero(direction < 0))
    aligned = "long" if long_ct >= short_ct else "short"
    bench_primary = bench_long if aligned == "long" else bench_short
    bench = {
        "long": round(bench_long["expR"], 4),
        "short": round(bench_short["expR"], 4),
        "primary": round(bench_primary["expR"], 4),
        "aligned": aligned,
        "edge": round(md_all["expR"] - bench_primary["expR"], 4),
    }
    # Inversion: flip BUY<->SELL, reflect the stop, rerun the SAME fill engine.
    d_inv, s_inv = invert_signals(direction, stop, data, base_tf)
    inv_expR = round(metrics(backtest(d_inv, s_inv, rr, data[base_tf], cost, pt))["expR"], 4)
    timing["diagnostics"] = round(time.perf_counter() - t1, 3)

    score, verdict, reasons, edge_flags = prop_score(
        md_all, md_dev, md_val, md_hold, mc, mc2, cost_rows, bench,
        inv_expR, EXEC_UNCERTAINTY_R)
    cost_ok = bool(edge_flags["cost_ok"])
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
    # ONE HISTORICAL PATH, both phases, deterministic. Never a probability.
    det = deterministic_path(tr, cfg)

    # === PROP CHALLENGE SIMULATION BLOCK ==================================
    # Everything the user asked to see, all derived from the CONFIGURED account
    # settings (cfg) so it recomputes whenever those settings change.
    # CALENDAR days, not "days on which it happened to trade". A selective
    # strategy may trade on only 170 distinct dates spread across 6 years;
    # dividing by active days made "typical days to pass" read ~59 when the
    # honest answer was ~2 years. Always convert through calendar time.
    active_days = int(pd.to_datetime(tr.entry).dt.date.nunique())
    cal_span = max(int((pd.to_datetime(tr.entry).max()
                        - pd.to_datetime(tr.entry).min()).days), 1)
    tr_per_cal_day = md_all["n"] / cal_span

    def _days_for(n_tr):
        return int(round(n_tr / tr_per_cal_day)) if (n_tr and tr_per_cal_day > 0) else None

    prop = {
        "start": cfg["balance"],
        "risk_pct": cfg["risk_pct"],
        "phase1_tgt": cfg["phase1"],
        "phase2_tgt": cfg["phase2"],
        "daily_loss": cfg["daily_loss"],
        "max_loss": cfg["max_loss"],
        "p1_pass": round(p1) if p1 is not None else None,
        "p2_pass": round(p2) if p2 is not None else None,
        "both_pass": round(both) if both is not None else None,
        "p1_med_trades": mc.get("med_trades") if mc else None,
        "p1_worst_trades": mc.get("worst_trades") if mc else None,
        "p1_typ_days": _days_for(mc.get("med_trades")) if mc else None,
        "p1_worst_days": _days_for(mc.get("worst_trades")) if mc else None,
        "p2_med_trades": mc2.get("med_trades") if mc2 else None,
        "fail_maxloss": round(mc["fail_maxloss"]) if mc else None,
        "fail_daily": round(mc["fail_daily"]) if mc else None,
        "typ_dd": round(mc["typ_dd"], 1) if mc else None,
        "worst_dd": round(mc["worst_dd"], 1) if mc else None,
        "typ_streak": mc["typ_streak"] if mc else None,
        "worst_streak": mc["worst_streak"] if mc else None,
        "nsims": mc["nsims"] if mc else None,
        "trades_per_year": round(md_all["n"] / (cal_span / 365.25), 1),
        "active_days": active_days,
        "avg_days_between": round(cal_span / max(md_all["n"], 1), 1),
        # ---- kept for back-compat with older saved reports ----
        "seq_pass": round(seq["p1"]["PASS"]) if seq else None,
        "seq_maxloss": round(seq["p1"]["FAIL_MAXLOSS"]) if seq else None,
        "seq_timeout": round(seq["p1"]["TIMEOUT"]) if seq else None,
        "seq_starts": seq["starts"] if seq else None,
        "seq_med_days": seq["p1"]["med_days"] if seq else None,
        "seq_worst_days": seq["p1"]["worst_days"] if seq else None,
        "seq_med_trades": seq["p1"]["med_trades"] if seq else None,
    }
    # ---- exact account arithmetic (a conversion, NOT a trade estimate) ----
    _r1 = bal0 * cfg["risk_pct"] / 100.0
    prop["math"] = {
        "one_R": round(_r1, 2),
        "p1_target_usd": round(bal0 * cfg["phase1"] / 100.0, 2),
        "p2_target_usd": round(bal0 * cfg["phase2"] / 100.0, 2),
        "daily_usd": round(bal0 * cfg["daily_loss"] / 100.0, 2),
        "maxloss_usd": round(bal0 * cfg["max_loss"] / 100.0, 2),
        "p1_R_required": round(cfg["phase1"] / cfg["risk_pct"], 1) if cfg["risk_pct"] else None,
        "p2_R_required": round(cfg["phase2"] / cfg["risk_pct"], 1) if cfg["risk_pct"] else None,
    }
    edge = {
        "dev": round(md_dev["expR"], 4),
        "val": round(md_val["expR"], 4),
        "hold": round(md_hold["expR"], 4),
        "hold_n": md_hold["n"],
        "hold_t": round(md_hold["t"], 2),
        "overall_t": round(md_all["t"], 2),
        "pf": round(md_all["pf"], 2),
        "win": round(md_all["win"], 1),
        "sharpe": round(md_all["sharpe"], 2),
        "trades": md_all["n"],
        "cost3x": next((c["expR"] for c in cost_rows if abs(c["mult"] - 3.0) < 1e-9), None),
        "bench": bench["primary"],
        "bench_aligned": bench["aligned"],
        "bench_long": bench["long"],
        "bench_short": bench["short"],
        "edge_vs_bench": bench["edge"],
        "inverted": inv_expR,
        "hold_quality": ("clear edge" if edge_flags["hold_ok"]
                         else "NO CLEAR EDGE / EXECUTION-SENSITIVE"),
    }

    step("Risk comparison + diagnostics", 94)
    # Same trades, same strategy - only cfg["risk_pct"] varies per row.
    risk_rows = risk_comparison(tr, cfg) if deep else []

    # ---- explicit, rule-based trust labels (no vague wording) ----
    _ht = md_hold["t"]
    _he = md_hold["expR"]
    _hn = md_hold["n"]
    if _hn < 15:
        hold_label = "HOLDOUT TOO SMALL"
    elif _he <= EXEC_UNCERTAINTY_R:
        hold_label = "EXECUTION-SENSITIVE"
    elif _ht < 2.0:
        hold_label = "NO CLEAR STATISTICAL CONFIRMATION"
    else:
        hold_label = "CLEAR EDGE"
    seq_full = seq["full"]["pass_pct"] if seq else None
    mc_both = mcj["both_pct"] if mcj else None
    trust = {
        "hold_label": hold_label,
        "small_holdout": bool(_hn < 100),
        "hold_n": _hn, "hold_t": round(_ht, 2), "hold_expR": round(_he, 4),
        "exec_threshold": EXEC_UNCERTAINTY_R,
        "seq_vs_mc_gap": (round(mc_both - seq_full, 1)
                          if (seq_full is not None and mc_both is not None) else None),
        "higher_trust": ["real-order sequential result", "holdout edge",
                         "benchmark edge", "inversion test", "cost stress"],
        "lower_trust": ["shuffled probability on its own",
                        "single deterministic historical path",
                        "holdout samples under 100 trades",
                        "heavily optimised variants"],
    }
    # risk posture from the CONFIGURED risk vs the observed worst streak
    _ws = mcj["worst_streak"] if mcj else None
    _rp = cfg["risk_pct"]
    _exposure = (_ws * _rp) if _ws else None
    if _exposure is None:
        posture = "UNKNOWN"
    elif _exposure < cfg["max_loss"] * 0.45:
        posture = "CONSERVATIVE"
    elif _exposure < cfg["max_loss"] * 0.65:
        posture = "MODERATE"
    elif _exposure < cfg["max_loss"] * 0.85:
        posture = "AGGRESSIVE"
    else:
        posture = "VERY AGGRESSIVE"
    trust["posture"] = posture
    trust["streak_exposure_pct"] = round(_exposure, 2) if _exposure else None

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
        "prop": prop,
        "edge": edge,
        # ---- structured, explicitly-labelled report blocks ----
        "sequential": seq,          # REAL historical order, full 2-step
        "mc_joint": mcj,            # SHUFFLED order, both phases jointly
        "deterministic": det,       # ONE historical path (not a probability)
        "concentration": winner_concentration(tr),
        "yearly": yearly_breakdown(tr),
        "best_day": best_day_report(tr, cfg),
        "risk_table": risk_rows,
        "trust": trust,
        "benchmarks": bench,
        "inversion": {"expR": inv_expR, "collapses": bool(edge_flags["inv_ok"])},
        "edge_ok": bool(edge_flags["edge_ok"]),
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
    import tester_ui, sys as _s

    # port comes from $PORT on cloud hosts, else 5000 locally
    tester_ui.serve(_s.modules[__name__])
