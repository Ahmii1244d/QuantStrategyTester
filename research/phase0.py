"""PHASE 0 - BASELINE CONTROLS (protocol 14)"""
import pandas as pd,numpy as np,config as C,engine as E,warnings
warnings.filterwarnings('ignore'); pd.set_option('display.width',250)

def ctrl_trend(d):
    e20=d.close.ewm(span=20).mean(); e50=d.close.ewm(span=50).mean()
    D=np.where(e20>e50,1,np.where(e20<e50,-1,0)).astype(float)
    D=np.roll(D,0); D[:60]=0
    sl=np.where(D>0,d.close-2*d.atr,d.close+2*d.atr)
    return D,sl

def ctrl_meanrev(d):
    m=d.close.rolling(20).mean(); s=d.close.rolling(20).std()
    z=(d.close-m)/s
    D=np.where(z<-2,1,np.where(z>2,-1,0)).astype(float); D[:60]=0
    sl=np.where(D>0,d.low-2*d.atr,d.high+2*d.atr)
    return D,sl

print("="*112); print("PHASE 0 - BASELINE CONTROLS  [SIMULATED COST ASSUMPTION]"); print("="*112)
print("Split: DEVELOPMENT only (2020-01-02..2023-12-31). Validation/Holdout untouched.\n")

rows=[]
for sym in C.SYMBOLS:
    d=E.slice_split(E.load(sym),'development')
    # buy & hold
    bh=(d.close.iloc[-1]/d.close.iloc[0]-1)*100
    for nm,fn in [('naive_trend',ctrl_trend),('naive_meanrev',ctrl_meanrev)]:
        D,sl=fn(d)
        tr=E.simulate(d,D,sl,sym,rr=2.0)
        st=E.stats(tr); st.update(symbol=sym,strategy=nm,buyhold_pct=bh)
        rows.append(st)
B=pd.DataFrame(rows)
print(B[['symbol','strategy','n','expR','tstat','pf','win','totR','buyhold_pct']]
      .to_string(index=False,float_format=lambda x:f'{x:8.3f}'))

print("\n"+"="*112); print("POOLED (all instruments)"); print("="*112)
for nm,g in B.groupby('strategy'):
    tot=g.n.sum(); we=(g.expR*g.n).sum()/tot
    print(f"  {nm:16s} n={tot:6d}  expR={we:+.4f}  instruments positive: {(g.expR>0).sum()}/{len(g)}")

# ---- 14.2 random-entry control, 1000 seeds ----
print("\n"+"="*112); print("RANDOM-ENTRY CONTROL - 1000 seeds, matched trade count & holding period"); print("="*112)
rng=np.random.default_rng(42)
print(f"{'symbol':8s} {'strat_expR':>11} {'rand_mean':>10} {'rand_p95':>9} {'percentile':>11}  verdict")
for sym in C.SYMBOLS:
    d=E.slice_split(E.load(sym),'development')
    D,sl=ctrl_trend(d); tr=E.simulate(d,D,sl,sym,rr=2.0)
    if len(tr)<30: continue
    real=tr.R.mean(); nT=len(tr)
    sims=[]
    o,h,l,c=d.open.values,d.high.values,d.low.values,d.close.values
    atr=d.atr.values; pt=C.POINT[sym]; cp=E.cost_points(sym)
    valid=np.where(~np.isnan(atr))[0]; valid=valid[(valid>30)&(valid<len(d)-100)]
    for s in range(1000):
        idx=rng.choice(valid,nT,replace=True); dirs=rng.choice([-1,1],nT)
        Rs=[]
        for k,i in enumerate(idx):
            Dd=dirs[k]; ent=o[i+1]+(cp*pt if Dd>0 else -cp*pt)
            slp=ent-2*atr[i]*Dd; risk=abs(ent-slp)
            if risk<=0: continue
            tp=ent+2*risk*Dd; R=None
            for j in range(i+1,min(len(d),i+97)):
                hs=(l[j]<=slp) if Dd>0 else (h[j]>=slp)
                ht=(h[j]>=tp) if Dd>0 else (l[j]<=tp)
                if hs: R=-1.0;break
                if ht: R=2.0;break
            if R is None:
                j=min(len(d)-1,i+96); R=((c[j]-ent) if Dd>0 else (ent-c[j]))/risk
            Rs.append(R)
        sims.append(np.mean(Rs))
    sims=np.array(sims); pct=100*(sims<real).mean()
    v='beats random' if pct>95 else ('indistinguishable' if pct>5 else 'WORSE than random')
    print(f"{sym:8s} {real:+11.4f} {sims.mean():+10.4f} {np.percentile(sims,95):+9.4f} {pct:10.1f}%  {v}")
B.to_csv('../reports/phase0_baselines.csv',index=False)
