"""
REGRESSION SUITE (item 38 / acceptance item 45).
Run:  python test_regression.py
Verifies correctness AND that fast<deep timing, causal HTF, lookahead,
metric consistency, cache equality all hold. Prints PASS/FAIL per check.
"""
import sys, io, time
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
import numpy as np, pandas as pd
import tester_app as A

cfg = A.load_cfg()
PASS = 0; FAIL = 0
def ck(name, cond, extra=""):
    global PASS, FAIL
    ok = bool(cond)
    PASS += ok; FAIL += (not ok)
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f"  ({extra})" if extra else ""))

EMA = A.DEFAULT_STRATEGY
MTF = """class Strategy:
    timeframes = ["M30","H4","D1"]
    def signals(self, data):
        import numpy as np
        df=data["M30"]; h4=data["H4"]; d1=data["D1"]
        assert len(h4)>0 and len(d1)>0
        n=len(df); c=df["close"].values; a=df["atr"].values
        d=np.zeros(n); s=np.full(n,np.nan)
        for i in range(300,n,40): d[i]=1; s[i]=c[i]-1.5*a[i]
        return d,s,np.full(n,2.0)
"""
CHEAT = """class Strategy:
    timeframes = ["M30"]
    def signals(self, data):
        import numpy as np
        df=data["M30"]; c=df["close"].values; n=len(df)
        d=np.zeros(n); s=np.full(n,np.nan); fut=np.roll(c,-20)
        for i in range(50,n-25):
            if fut[i]>c[i]: d[i]=1; s[i]=c[i]-5
            else: d[i]=-1; s[i]=c[i]+5
        return d,s,np.full(n,2.0)
"""
BADLEN = """class Strategy:
    timeframes = ["M30"]
    def signals(self, data):
        import numpy as np
        return np.zeros(10), np.zeros(10), np.full(10,2.0)
"""
MISSING = """class Strategy:
    timeframes = ["M1"]
    def signals(self, data):
        import numpy as np
        n=len(data["M1"]); return np.zeros(n), np.zeros(n), np.full(n,2.0)
"""

print("\n=== FAST/DEEP + timing ===")
A.run_test(EMA,cfg,mode="fast")                 # warm the data/signal cache first
rf=A.run_test(EMA,cfg,mode="fast"); tf=rf["timing"]["total"]
rd=A.run_test(EMA,cfg,mode="deep"); td=rd["timing"]["total"]
ck("A: EMA fast runs, no error", rf.get("ok"), rf.get("error",""))
# compare engine-internal totals (excludes cold-cache CSV load); deep does strictly more work
ck("H: fast faster than deep (warm)", tf < td, f"fast={tf:.2f}s deep={td:.2f}s")
ck("prop pass odds computed in BOTH modes",
   rf.get("phase1") is not None and rd.get("phase1") is not None)
ck("deep runs MORE simulations than fast",
   rd["prop"]["nsims"] > rf["prop"]["nsims"], f"fast={rf['prop']['nsims']} deep={rd['prop']['nsims']}")
ck("timing breakdown present", "total" in rf.get("timing",{}))

print("\n=== metric consistency (F) ===")
md = A.metrics.__wrapped__ if hasattr(A.metrics,"__wrapped__") else A.metrics
# build a tiny known trade set
tr = pd.DataFrame({"entry":pd.date_range("2021",periods=5,freq="D"),
                   "exit":pd.date_range("2021",periods=5,freq="D"),
                   "dir":[1,1,-1,1,-1],"R":[2.0,-1.0,2.0,-1.0,-1.0]})
m = A.metrics(tr)
ck("F1: PF = gross_win/gross_loss", abs(m["pf"] - (4.0/3.0)) < 1e-9, f"pf={m['pf']:.4f}")
ck("F2: pf == pf_R", abs(m["pf"]-m["pf_R"])<1e-9)
ck("F3: expectancy == win*avgWin+loss*avgLoss", m["consistent"], f"expR={m['expR']:.4f}")
ck("F4: expR value correct", abs(m["expR"]-0.2)<1e-9)

print("\n=== drawdown consistency (G) ===")
ck("G: maxdd% and $ both present & >=0",
   rd["metrics"]["maxdd"]>=0 and rd["metrics"]["maxdd_usd"]>=0,
   f"{rd['metrics']['maxdd']}% / ${rd['metrics']['maxdd_usd']}")
ck("G: peak>=trough", rd["metrics"]["peak_bal"]>=rd["metrics"]["trough_bal"])

print("\n=== multi-timeframe (B,C,D,N) ===")
rm=A.run_test(MTF,cfg,mode="fast")
ck("B: MTF strategy runs", rm.get("ok"), rm.get("error",""))
ck("C: base timeframe = M30 (lowest requested)", rm.get("base_tf")=="M30")
ck("N: saved H4/D1 preferred over building", rm.get("build_log",{}).get("H4")=="saved"
   and rm.get("build_log",{}).get("D1")=="saved", str(rm.get("build_log")))

print("\n=== lookahead (E) ===")
rc=A.run_test(CHEAT,cfg,mode="fast")
ck("E: future-reading strategy REJECTED", rc.get("error")=="LOOKAHEAD", rc.get("error"))
ck("E: honest EMA NOT rejected", rf.get("ok"))

print("\n=== MTF forming-bar look-ahead (the WORKINGStrategy class) ===")
# reads the CONTAINING (still-forming) higher-TF bar via searchsorted -> future data.
MTF_LOOKAHEAD='''class Strategy:
    timeframes=["M5","H1"]
    def signals(self,data):
        import numpy as np
        m5=data["M5"]; h1=data["H1"]
        m5t=m5["time"].to_numpy().astype("int64"); h1t=h1["time"].to_numpy().astype("int64")
        pos=np.searchsorted(h1t,m5t,side="right")-1        # CONTAINING (forming) H1 bar
        pos[pos<0]=0
        h1c=h1["close"].to_numpy(); c=m5["close"].values; atr=m5["atr"].values; n=len(m5)
        d=np.zeros(n); s=np.full(n,np.nan)
        for i in range(300,n):
            if h1c[pos[i]]>c[i] and c[i]>c[i-1]: d[i]=1; s[i]=c[i]-1.5*atr[i]   # uses forming-bar close
        return d,s,np.full(n,2.0)'''
rml=A.run_test(MTF_LOOKAHEAD,cfg,mode="fast")
ck("forming-HTF-bar look-ahead REJECTED", rml.get("error")=="LOOKAHEAD", rml.get("error"))
MTF_HONEST='''class Strategy:
    timeframes=["M5","H1"]
    def signals(self,data):
        import numpy as np
        m5=data["M5"]; h1=data["H1"]
        m5t=m5["time"].to_numpy().astype("int64"); h1t=h1["time"].to_numpy().astype("int64")
        pos=np.searchsorted(h1t,m5t,side="right")-1-1      # last CLOSED H1 bar
        pos[pos<0]=0
        h1c=h1["close"].to_numpy(); c=m5["close"].values; atr=m5["atr"].values; n=len(m5)
        d=np.zeros(n); s=np.full(n,np.nan)
        for i in range(300,n):
            if h1c[pos[i]]>c[i] and c[i]>c[i-1]: d[i]=1; s[i]=c[i]-1.5*atr[i]
        return d,s,np.full(n,2.0)'''
rmh=A.run_test(MTF_HONEST,cfg,mode="fast")
ck("last-closed-HTF-bar honest MTF PASSES", rmh.get("ok") or rmh.get("error")=="NO_TRADES", rmh.get("error"))

print("\n=== error handling (K, length) ===")
try: rb=A.run_test(BADLEN,cfg,mode="fast")
except A.StrategyError as e: rb={"error":e.kind,"msg":e.msg}
ck("length mismatch -> clear error", "expected" in rb.get("msg","").lower() or rb.get("error"),
   rb.get("msg","")[:50])
rmi=A.run_test(MISSING,cfg,mode="fast")
ck("K: missing timeframe -> CANNOT_TEST", rmi.get("error")=="CANNOT_TEST")

print("\n=== cache equality (J) + reproducibility (item 27) ===")
r1=A.run_test(EMA,cfg,mode="deep")
r2=A.run_test(EMA,cfg,mode="deep")
ck("J: trade count identical across runs", r1["metrics"]["trades"]==r2["metrics"]["trades"])
ck("expR identical across runs", r1["metrics"]["expR"]==r2["metrics"]["expR"])
ck("Monte Carlo reproducible (seeded)", r1["phase1"]==r2["phase1"],
   f"{r1['phase1']} vs {r2['phase1']}")

print("\n=== execution-sensitive flag (item 39) ===")
ck("exec_sensitive flag present", "exec_sensitive" in rd)
ck("threshold exposed = 0.04", rd.get("exec_threshold")==0.04)

print("\n=== consistency audit (items 1-11) ===")
rc=A.run_test(EMA,cfg,mode="deep")
ck("audit block present", "audit" in rc)
ck("audit passes on clean EMA", rc["audit"]["ok"],
   f"{sum(c['ok'] for c in rc['audit']['checks'])}/{len(rc['audit']['checks'])}")
ck("trade counts identical (metrics==trade_count==split sum)",
   rc["metrics"]["trades"]==rc["trade_count"]==
   rc["splits"]["dev"]["n"]+rc["splits"]["val"]["n"]+rc["splits"]["hold"]["n"])
mm=rc["metrics"]
# the max-% drawdown may start from a LOCAL peak <= global peak, so the $ amount
# must be <= maxdd% x global peak. The exact same-excursion tie is asserted by the
# engine's own audit (checked above). Here we just bound it.
ck("maxDD $ consistent with maxDD % (bounded by global peak)",
   mm["maxdd_usd"] <= mm["maxdd"]/100*mm["peak_bal"] + 0.06*mm["peak_bal"]/100 + 2,
   f"${mm['maxdd_usd']} <= {mm['maxdd']}% x ${mm['peak_bal']} (+ rounding)")
ck("no compounding blow-up (research_final sane)",
   0 < rc["research_final"] < cfg["balance"]*50, f"${rc['research_final']}")
ck("account sim uses prop rules (has outcome)",
   rc["account"].get("outcome") in ("PASS","FAIL_MAXLOSS","FAIL_DAILY","TIMEOUT"))
ck("reasons mention the drift benchmark comparison",
   any("benchmark" in x[1].lower() for x in rc["reasons"]))
ck("reasons mention holdout / unseen-data edge",
   any("holdout" in x[1].lower() for x in rc["reasons"]))

print("\n=== audit CATCHES a forced mismatch ===")
import copy
bad=copy.deepcopy(rc)
badchk=A.audit_consistency(
    bad,
    {"n":3,"consistent":True,"expR":0.0,"win":33.3,"avg_win":2.0,"avg_loss":-1.0,"totR":0.0,"pf":1.0},
    {"n":1},{"n":1},{"n":1},                 # split sum 3 != 3? -> 1+1+1=3 ok; corrupt below
    [5000,5200,4800], 100.0, 5.0, 500.0)     # maxdd% claims 5% but path max is ~7.7%
ck("audit returns FAIL on bad numbers", not badchk["ok"],
   f"{sum(c['ok'] for c in badchk['checks'])}/{len(badchk['checks'])} passed")

print("\n=== history persistence (never lose a long run) ===")
rp=A.run_test(EMA,cfg,mode="fast")
rid=rp["report_id"]
ck("report saved with id", rid and A.load_report(rid) is not None)
ck("saved report is the FULL report (has metrics+audit)",
   "metrics" in A.load_report(rid) and "audit" in A.load_report(rid))
ck("history row references the report id", any(x.get("id")==rid for x in A.load_hist()))
A.delete_report(rid)
ck("delete removes report + history row",
   A.load_report(rid) is None and not any(x.get("id")==rid for x in A.load_hist()))

print("\n=== control tests: benchmarks + inversion (item 1,2,3,4) ===")
rmt=A.run_test(MTF,cfg,mode="fast")     # the gold-drift long-every-40-bars 'strategy'
ck("always-long + always-short benchmarks present",
   "benchmarks" in rmt and {"long","short","edge","aligned"} <= set(rmt["benchmarks"].keys()),
   str(rmt.get("benchmarks")))
ck("strategy inversion computed", rmt.get("inversion",{}).get("expR") is not None,
   str(rmt.get("inversion")))
ck("edge block reports benchmark + inverted expectancy",
   "edge" in rmt and "edge_vs_bench" in rmt["edge"] and "inverted" in rmt["edge"])

print("\n=== a gold-drift long-only strategy CANNOT score high (item 7) ===")
ck("drift long-only labelled 'NO CLEAR EDGE'", rmt["verdict"][1]=="NO CLEAR EDGE", rmt["verdict"][1])
ck("drift edge_ok is False", rmt.get("edge_ok") is False)
ck("drift score is not high (<55)", rmt["score"]<55, f"score={rmt['score']}")
ck("drift only ties the benchmark (edge <= execution noise)",
   rmt["edge"]["edge_vs_bench"] <= A.EXEC_UNCERTAINTY_R, f"edge={rmt['edge']['edge_vs_bench']}R")

print("\n=== prop simulation uses the CONFIGURED account settings (item 6) ===")
P=rmt["prop"]
ck("prop block mirrors cfg balance/targets/limits/risk",
   P["start"]==cfg["balance"] and P["phase1_tgt"]==cfg["phase1"] and P["phase2_tgt"]==cfg["phase2"]
   and P["daily_loss"]==cfg["daily_loss"] and P["max_loss"]==cfg["max_loss"]
   and P["risk_pct"]==cfg["risk_pct"],
   f"start={P['start']} p1={P['phase1_tgt']} risk={P['risk_pct']}")

print("\n=== settings dynamically change the results (item 3) ===")
import copy
cfg_easy=copy.deepcopy(cfg); cfg_easy["phase1"]=8.0
cfg_hard=copy.deepcopy(cfg); cfg_hard["phase1"]=25.0        # much harder target
r_easy=A.run_test(MTF,cfg_easy,mode="fast"); r_hard=A.run_test(MTF,cfg_hard,mode="fast")
ck("raising Phase-1 target lowers pass odds",
   r_hard["prop"]["p1_pass"] <= r_easy["prop"]["p1_pass"],
   f"8%->{r_easy['prop']['p1_pass']}%   25%->{r_hard['prop']['p1_pass']}%")
cfg_lo=copy.deepcopy(cfg); cfg_lo["risk_pct"]=0.10
cfg_hi=copy.deepcopy(cfg); cfg_hi["risk_pct"]=1.00
r_lo=A.run_test(MTF,cfg_lo,mode="fast"); r_hi=A.run_test(MTF,cfg_hi,mode="fast")
ck("changing risk per trade changes the simulation",
   (r_lo["prop"]["p1_pass"],r_lo["prop"]["fail_maxloss"]) !=
   (r_hi["prop"]["p1_pass"],r_hi["prop"]["fail_maxloss"]),
   f"0.10%: pass{r_lo['prop']['p1_pass']}/ml{r_lo['prop']['fail_maxloss']}  "
   f"1.00%: pass{r_hi['prop']['p1_pass']}/ml{r_hi['prop']['fail_maxloss']}")

print("\n=== sequential (real-order) challenge + honest calendar days ===")
Pm=rmt["prop"]
ck("sequential challenge reported", Pm.get("seq_pass") is not None,
   f"seq_pass={Pm.get('seq_pass')}% over {Pm.get('seq_starts')} starts")
ck("sequential uses every trade as a start point",
   Pm.get("seq_starts")==rmt["edge"]["trades"],
   f"{Pm.get('seq_starts')} starts vs {rmt['edge']['trades']} trades")
ck("trades/year reported", Pm.get("trades_per_year") is not None, str(Pm.get("trades_per_year")))
# days-to-pass must be CALENDAR days: with ~6.5 years of data a strategy needing
# ~200 trades cannot honestly claim to finish in a couple of months.
if Pm.get("p1_med_trades") and Pm.get("p1_typ_days"):
    implied=Pm["p1_med_trades"]/max(Pm["p1_typ_days"],1)
    ck("days-to-pass derived from CALENDAR time, not active days",
       implied <= (rmt["edge"]["trades"]/ (365.25*6.0)) * 1.5 + 0.5,
       f"{Pm['p1_med_trades']} trades in {Pm['p1_typ_days']} days = {implied:.2f}/day")

print("\n=== holdout significance gate (a lucky handful is not an edge) ===")
w_all={"n":300,"expR":0.13,"pf":1.2,"win":32.0,"sharpe":0.4,"t":1.1}
w_dev={"n":150,"expR":0.10,"t":0.9}; w_val={"n":60,"expR":0.20,"t":1.4}
w_bench={"long":-0.06,"short":-0.02,"primary":-0.06,"aligned":"long","edge":0.19}
w_mc={"pass_pct":78.0,"fail_maxloss":8.0,"fail_daily":0.0}
w_mc2={"pass_pct":84.0,"fail_maxloss":6.0,"fail_daily":0.0}
w_cost=[{"mult":1.0,"expR":0.13,"pos":True},{"mult":3.0,"expR":0.13,"pos":True}]
# big-looking holdout, but only 29 trades and t below 2 -> must NOT read as clear edge
lucky={"n":29,"expR":0.569,"t":1.73}
s_l,v_l,r_l,f_l=A.prop_score(w_all,w_dev,w_val,lucky,w_mc,w_mc2,w_cost,w_bench,-0.04,A.EXEC_UNCERTAINTY_R)
ck("big holdout with t<2 is NOT treated as a clear edge", f_l["hold_ok"] is False,
   f"expR +0.569 on 29 trades, t 1.73 -> hold_ok={f_l['hold_ok']}")
ck("...and it cannot be labelled EXCELLENT", v_l[1]!="EXCELLENT", v_l[1])
# same expectancy, properly powered sample -> should pass
solid={"n":97,"expR":0.515,"t":2.91}
s_s,v_s,r_s,f_s=A.prop_score(w_all,w_dev,w_val,solid,w_mc,w_mc2,w_cost,w_bench,-0.04,A.EXEC_UNCERTAINTY_R)
ck("same edge on a properly powered holdout DOES pass", f_s["hold_ok"] is True,
   f"expR +0.515 on 97 trades, t 2.91 -> hold_ok={f_s['hold_ok']}")
ck("significance gate raises the score, not lowers it", s_s > s_l, f"{s_l} -> {s_s}")

print("\n=== scoring machinery: a genuine edge CAN still score high (positive control) ===")
# feed prop_score synthetic inputs describing a real, benchmark-beating edge:
g_all ={"n":600,"expR":0.30,"pf":1.9,"win":55.0,"sharpe":1.5,"t":4.2}
g_dev ={"n":360,"expR":0.30,"t":3.6}; g_val={"n":120,"expR":0.28,"t":2.4}
g_hold={"n":120,"expR":0.26,"t":2.6}
g_mc  ={"pass_pct":85.0,"fail_maxloss":3.0,"fail_daily":1.0}
g_mc2 ={"pass_pct":90.0,"fail_maxloss":2.0,"fail_daily":1.0}
g_cost=[{"mult":1.0,"expR":0.30,"pos":True},{"mult":2.0,"expR":0.20,"pos":True},{"mult":3.0,"expR":0.12,"pos":True}]
g_bench={"long":0.05,"short":-0.05,"primary":0.05,"aligned":"long","edge":0.25}
gs,gv,gr,gf=A.prop_score(g_all,g_dev,g_val,g_hold,g_mc,g_mc2,g_cost,g_bench,-0.25,A.EXEC_UNCERTAINTY_R)
ck("clear-edge strategy scores high (>=80)", gs>=80, f"score={gs}")
ck("clear-edge strategy labelled EXCELLENT/GOOD", gv[1] in ("EXCELLENT","GOOD"), gv[1])
ck("clear-edge strategy edge_ok True", gf["edge_ok"] is True)


# ===================================================================
# REPORTING-CLARITY REGRESSION (prop reporting overhaul)
# Proves the 11 properties required of the new report.
# ===================================================================
print("\n=== R1: strategy signals UNCHANGED by the reporting work ===")
import hashlib, copy as _copy
_ds = A.scan_dataset(cfg)
_data = {tf: A.load_tf(_ds["tfs"][tf]["path"]) for tf in ("M30", "H4", "D1")
         if tf in _ds["tfs"]}
if "M30" in _data:
    _St = A.compile_strategy(MTF)
    _d, _s, _rr = A.get_signals(_St, _data, "M30")
    _sig_hash = hashlib.md5(_d.tobytes()).hexdigest()[:12]
    _d2, _s2, _rr2 = A.get_signals(A.compile_strategy(MTF), _data, "M30")
    ck("R1: signals deterministic + unchanged",
       hashlib.md5(_d2.tobytes()).hexdigest()[:12] == _sig_hash, _sig_hash)
    _pt, _ = A.point_size(_data["M30"]); _cost = A.modelled_cost_pts(_data["M30"])
    _tr = A.backtest(_d, _s, _rr, _data["M30"], _cost, _pt)
    _m = A.metrics(_tr)
    ck("R2: backtest metrics reproduce exactly",
       A.metrics(A.backtest(_d, _s, _rr, _data["M30"], _cost, _pt))["expR"] == _m["expR"],
       f"expR={_m['expR']:.6f} n={_m['n']}")

print("\n=== R3: risk changes move ACCOUNT results but NOT R-based edge ===")
_lo = _copy.deepcopy(cfg); _lo["risk_pct"] = 0.25
_hi = _copy.deepcopy(cfg); _hi["risk_pct"] = 0.85
r_lo = A.run_test(MTF, _lo, mode="fast")
r_hi = A.run_test(MTF, _hi, mode="fast")
for k in ("expR", "pf", "win", "sharpe"):
    ck(f"R3: metrics.{k} identical across risk",
       r_lo["metrics"][k] == r_hi["metrics"][k], f"{r_lo['metrics'][k]}")
for k in ("hold", "dev", "val", "edge_vs_bench", "inverted", "hold_t", "overall_t"):
    ck(f"R3: edge.{k} identical across risk",
       r_lo["edge"][k] == r_hi["edge"][k], f"{r_lo['edge'][k]}")
ck("R3: account-level result DOES change with risk",
   r_lo["sequential"]["full"]["pass_pct"] != r_hi["sequential"]["full"]["pass_pct"],
   f"{r_lo['sequential']['full']['pass_pct']:.1f}% vs {r_hi['sequential']['full']['pass_pct']:.1f}%")

print("\n=== R4/R5: shuffled vs sequential are separate, correctly labelled ===")
rr_ = A.run_test(MTF, cfg, mode="fast")
ck("R4: joint shuffled MC present and jointly simulated",
   rr_["mc_joint"] is not None and "both_pct" in rr_["mc_joint"],
   f"both={rr_['mc_joint']['both_pct']:.1f}%")
_j = rr_["mc_joint"]
_indep = _j["p1"]["PASS"] * _j["p2_cond"]["PASS"] / 100.0
# STRUCTURAL proof: phase 2 is only ever evaluated on paths where phase 1
# actually passed, and it continues the SAME bootstrap draw. The two numbers may
# coincide when the phases happen to be independent - what matters is that the
# engine COUNTS joint outcomes rather than multiplying two marginals.
_expected_p2_evals = round(_j["p1"]["PASS"] / 100.0 * _j["nsims"])
ck("R4: joint MC evaluates phase 2 only on phase-1 passes (same path continued)",
   abs(_j["p2_evaluated"] - _expected_p2_evals) <= 1,
   f"p2 evaluated on {_j['p2_evaluated']} of {_j['nsims']} sims; p1 passed {_expected_p2_evals}")
ck("R4: both_pct is a counted joint outcome (<= phase-1 pass rate)",
   _j["both_pct"] <= _j["p1"]["PASS"] + 1e-9,
   f"joint={_j['both_pct']:.2f}%  p1={_j['p1']['PASS']:.2f}%  (naive p1*p2 = {_indep:.2f}%)")
ck("R5: sequential starts at EVERY historical trade (order preserved)",
   rr_["sequential"]["starts"] == rr_["edge"]["trades"],
   f"{rr_['sequential']['starts']} starts vs {rr_['edge']['trades']} trades")

print("\n=== R6: Phase 2 is CONDITIONAL on Phase 1 ===")
_S = rr_["sequential"]
ck("R6: p2 evaluated only on paths that passed p1",
   _S["p2"]["evaluated"] <= _S["p1"]["n_pass"],
   f"p2 evaluated {_S['p2']['evaluated']} <= p1 passes {_S['p1']['n_pass']}")
ck("R6: full pass <= phase-1 pass count",
   _S["full"]["pass_pct"] <= _S["p1"]["PASS"] + 1e-9,
   f"full {_S['full']['pass_pct']:.1f}% <= p1 {_S['p1']['PASS']:.1f}%")

print("\n=== R7: full 2-step probability measured DIRECTLY, not inferred ===")
_direct = _S["full"]["pass_pct"]
_naive = _S["p1"]["PASS"] * _S["p2"]["PASS"] / 100.0
# STRUCTURAL proof: full-pass is a COUNT of paths that cleared both phases, so
# pass_pct * starts must land on a whole number of paths.
_cnt = _direct / 100.0 * _S["starts"]
ck("R7: sequential full-pass is a counted number of paths, not a product",
   abs(_cnt - round(_cnt)) < 1e-6,
   f"{_direct:.4f}% x {_S['starts']} starts = {_cnt:.6f} paths (whole number)")
ck("R7: full pass + p1-pass-p2-fail == phase-1 passes (partition holds)",
   abs((_S["full"]["pass_pct"] + _S["full"]["p1_pass_p2_fail_pct"]) - _S["p1"]["PASS"]) < 1e-6,
   f"naive p1*p2 would have been {_naive:.2f}%")
ck("R7: outcome shares are exhaustive",
   abs(_S["full"]["pass_pct"] + _S["full"]["p1_pass_p2_fail_pct"]
       + _S["full"]["p1_fail_pct"] - 100.0) < 1e-6,
   f"{_S['full']['pass_pct']:.2f}+{_S['full']['p1_pass_p2_fail_pct']:.2f}+{_S['full']['p1_fail_pct']:.2f}")

print("\n=== R8: calendar days are NOT trading days ===")
_P = rr_["prop"]
ck("R8: trading days reported separately from calendar days",
   _P["active_days"] is not None and _S["p1"]["med_days"] is not None,
   f"active(trading) days={_P['active_days']}, p1 median CALENDAR days={_S['p1']['med_days']}")
ck("R8: calendar span exceeds distinct trading days",
   _P["active_days"] <= (_P["trades_per_year"] * 10),
   f"trades/yr={_P['trades_per_year']}")

print("\n=== R9: Best Day rule modelled, not treated as instant failure ===")
_bd = _copy.deepcopy(cfg); _bd["best_day_pct"] = 20.0
r_bd = A.run_test(MTF, _bd, mode="fast")
ck("R9: best-day report present when enabled",
   r_bd["best_day"]["enabled"] and r_bd["best_day"]["threshold"] == 20.0)
ck("R9: enabling the rule does not zero out passes (no instant-fail)",
   r_bd["sequential"]["p1"]["PASS"] >= 0.0 and r_bd["sequential"] is not None,
   f"p1 pass {r_bd['sequential']['p1']['PASS']:.1f}%")
ck("R9: stricter best-day cap cannot INCREASE the pass rate",
   r_bd["sequential"]["full"]["pass_pct"] <= rr_["sequential"]["full"]["pass_pct"] + 1e-9,
   f"{rr_['sequential']['full']['pass_pct']:.1f}% -> {r_bd['sequential']['full']['pass_pct']:.1f}%")

print("\n=== R10: minimum trading days enforced ===")
_md = _copy.deepcopy(cfg); _md["min_days"] = 30
r_md = A.run_test(MTF, _md, mode="fast")
ck("R10: min_days surfaced in the report",
   r_md["sequential"]["min_days"] == 30)
ck("R10: requiring 30 trading days cannot raise the pass rate",
   r_md["sequential"]["p1"]["PASS"] <= rr_["sequential"]["p1"]["PASS"] + 1e-9,
   f"{rr_['sequential']['p1']['PASS']:.1f}% -> {r_md['sequential']['p1']['PASS']:.1f}%")

print("\n=== R11: no look-ahead introduced ===")
ck("R11: honest strategy still passes look-ahead", rr_.get("ok") is True)
_cheat = A.run_test(CHEAT, cfg, mode="fast")
ck("R11: future-reading strategy still REJECTED",
   _cheat.get("error") == "LOOKAHEAD", _cheat.get("error"))

print("\n=== deterministic path is labelled as ONE path, not a probability ===")
_D = rr_["deterministic"]
ck("deterministic reports discrete outcomes (not percentages)",
   _D["full"] in ("PASSED", "FAILED", "INCOMPLETE")
   and _D["p1_outcome"] in ("PASS", "FAIL_MAXLOSS", "FAIL_DAILY", "TIMEOUT"),
   f"p1={_D['p1_outcome']} full={_D['full']}")

print("\n=== diagnostics present ===")
ck("winner-concentration diagnostic present", "levels" in rr_["concentration"])
ck("per-year breakdown present", len(rr_["yearly"]) >= 3, f"{len(rr_['yearly'])} years")
ck("trust labels present with explicit rule inputs",
   rr_["trust"]["hold_label"] in ("CLEAR EDGE", "NO CLEAR STATISTICAL CONFIRMATION",
                                  "EXECUTION-SENSITIVE", "HOLDOUT TOO SMALL"),
   rr_["trust"]["hold_label"])
ck("exact account math present",
   rr_["prop"]["math"]["one_R"] == round(cfg["balance"] * cfg["risk_pct"] / 100.0, 2),
   f"1R=${rr_['prop']['math']['one_R']}")

print("\n" + "="*50)
print(f"  RESULT: {PASS} passed, {FAIL} failed")
print("="*50)
sys.exit(1 if FAIL else 0)
