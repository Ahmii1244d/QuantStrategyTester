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

print("\n=== scoring machinery: a genuine edge CAN still score high (positive control) ===")
# feed prop_score synthetic inputs describing a real, benchmark-beating edge:
g_all ={"n":600,"expR":0.30,"pf":1.9,"win":55.0,"sharpe":1.5}
g_dev ={"n":360,"expR":0.30}; g_val={"n":120,"expR":0.28}; g_hold={"n":120,"expR":0.26}
g_mc  ={"pass_pct":85.0,"fail_maxloss":3.0,"fail_daily":1.0}
g_mc2 ={"pass_pct":90.0,"fail_maxloss":2.0,"fail_daily":1.0}
g_cost=[{"mult":1.0,"expR":0.30,"pos":True},{"mult":2.0,"expR":0.20,"pos":True},{"mult":3.0,"expR":0.12,"pos":True}]
g_bench={"long":0.05,"short":-0.05,"primary":0.05,"aligned":"long","edge":0.25}
gs,gv,gr,gf=A.prop_score(g_all,g_dev,g_val,g_hold,g_mc,g_mc2,g_cost,g_bench,-0.25,A.EXEC_UNCERTAINTY_R)
ck("clear-edge strategy scores high (>=80)", gs>=80, f"score={gs}")
ck("clear-edge strategy labelled EXCELLENT/GOOD", gv[1] in ("EXCELLENT","GOOD"), gv[1])
ck("clear-edge strategy edge_ok True", gf["edge_ok"] is True)

print("\n" + "="*50)
print(f"  RESULT: {PASS} passed, {FAIL} failed")
print("="*50)
sys.exit(1 if FAIL else 0)
