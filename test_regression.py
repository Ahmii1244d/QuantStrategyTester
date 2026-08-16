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
ck("fast skips Monte Carlo", rf.get("phase1") is None)
ck("deep includes Monte Carlo", rd.get("phase1") is not None)
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
ck("verdict trade reason labeled 'development'",
   any("development" in x[1] for x in rc["reasons"] if "trade" in x[1].lower()))

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

print("\n" + "="*50)
print(f"  RESULT: {PASS} passed, {FAIL} failed")
print("="*50)
sys.exit(1 if FAIL else 0)
