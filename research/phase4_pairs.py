"""PHASE 4 - PAIRS / STAT-ARB (protocol 18). Selection on DEVELOPMENT only."""
import pandas as pd,numpy as np,itertools,config as C,engine as E,warnings
from statsmodels.tsa.stattools import adfuller
warnings.filterwarnings('ignore'); pd.set_option('display.width',260)

def panel(split):
    fr={}
    for s in C.SYMBOLS:
        d=E.slice_split(E.load(s),split).set_index('time')['close']
        fr[s]=d
    P=pd.DataFrame(fr).dropna()
    return P

DEV=panel('development'); VAL=panel('validation')
print(f"development panel: {DEV.shape}   validation panel: {VAL.shape}")
LDEV=np.log(DEV); LVAL=np.log(VAL)

# ---------- Stage A/B: discovery on DEVELOPMENT ONLY ----------
rows=[]
for a,b in itertools.combinations(C.SYMBOLS,2):
    x=LDEV[b].values; y=LDEV[a].values
    beta=np.polyfit(x,y,1)[0]
    sp=y-beta*x
    try: p=adfuller(sp,maxlag=12,autolag=None)[1]
    except Exception: p=1.0
    # half-life via AR(1)
    ds=np.diff(sp); ls=sp[:-1]
    k=np.polyfit(ls,ds,1)[0]
    hl=-np.log(2)/k if k<0 else np.inf
    rows.append(dict(a=a,b=b,beta=beta,adf_p=p,half_life=hl,
                     corr=np.corrcoef(LDEV[a],LDEV[b])[0,1]))
S=pd.DataFrame(rows)
# pre-registered qualification thresholds (set BEFORE seeing validation)
QUAL=(S.adf_p<0.05)&(S.half_life>5)&(S.half_life<500)
print(f"\nPairs tested: {len(S)}   qualified on DEV (adf_p<0.05, 5<HL<500): {QUAL.sum()}")
print(S[QUAL].sort_values('adf_p')[['a','b','beta','adf_p','half_life','corr']]
      .head(15).to_string(index=False,float_format=lambda x:f'{x:8.3f}'))

# ---------- Stage D: fixed trading rule, applied to DEV and VAL ----------
def run_pair(P,a,b,beta,zwin=100,zin=2.0,zout=0.5,zstop=4.0,maxhold=96):
    y=np.log(P[a].values); x=np.log(P[b].values); sp=y-beta*x
    s=pd.Series(sp); m=s.rolling(zwin).mean(); sd=s.rolling(zwin).std()
    z=((s-m)/sd).values
    ca=(C.SPREAD_MODEL_POINTS[a]+2*C.SLIPPAGE_POINTS[a])*C.POINT[a]/P[a].mean()
    cb=(C.SPREAD_MODEL_POINTS[b]+2*C.SLIPPAGE_POINTS[b])*C.POINT[b]/P[b].mean()
    rt=ca+abs(beta)*cb                       # round-trip cost, BOTH legs, in spread units
    n=len(z); out=[]; i=zwin+1
    while i<n-1:
        if np.isnan(z[i]): i+=1; continue
        d=0
        if z[i]>zin: d=-1
        elif z[i]<-zin: d=1
        if d==0: i+=1; continue
        ent=sp[i+1]; j=i+1; R=None
        while j<min(n,i+1+maxhold):
            if d*(z[j])>=zstop*0 and abs(z[j])>=zstop: R=-1.0; break
            if abs(z[j])<=zout: R=1.0; break
            j+=1
        if R is None: R=0.0
        # convert to cost-adjusted: profit ~ |entry z - exit z| * sd, cost = rt
        gain=abs(sp[i+1]-sp[min(j,n-1)])
        net=(gain if R>0 else -gain)-2*rt
        risk=max(sd.values[i]*zstop,1e-9)
        out.append((P.index[i+1],d,net/risk))
        i=j+1
    return pd.DataFrame(out,columns=['entry','dir','R'])

print("\n"+"="*118)
print("STAGE D - fixed rule (z>2 entry, |z|<0.5 exit, |z|>4 stop), costs on BOTH legs")
print("="*118)
res=[]
for _,r in S[QUAL].iterrows():
    td=run_pair(DEV,r.a,r.b,r.beta); tv=run_pair(VAL,r.a,r.b,r.beta)
    if len(td)<30 or len(tv)<15: continue
    res.append(dict(pair=f"{r.a}/{r.b}",adf_p=r.adf_p,hl=r.half_life,
                    dev_n=len(td),dev_expR=td.R.mean(),
                    val_n=len(tv),val_expR=tv.R.mean()))
R=pd.DataFrame(res)
if len(R):
    R=R.sort_values('dev_expR',ascending=False)
    print(R.to_string(index=False,float_format=lambda x:f'{x:9.4f}'))
    print(f"\n  DEV positive : {(R.dev_expR>0).sum()}/{len(R)}")
    print(f"  VAL positive : {(R.val_expR>0).sum()}/{len(R)}")
    if len(R)>2:
        c=np.corrcoef(R.dev_expR,R.val_expR)[0,1]
        print(f"  DEV->VAL expectancy correlation: {c:+.3f}   "
              f"{'SIGNAL' if c>0.4 else 'NOISE - dev performance does not predict val'}")
    R.to_csv('../reports/phase4_pairs.csv',index=False)
else:
    print("  no pair produced enough trades under the fixed rule")
