"""
XAU MTF STRATEGY - mechanical implementation of the user's discretionary process.
Chain: 1D+4H trend -> 1H structure/key levels -> 15m CHOCH->BOS -> 15m fib zone
       -> 5m structure align -> 5m displacement (FVG) -> FVG retest -> entry.
Every stage logs rejections so we can see WHERE candidates die (funnel diagnostic).
No look-ahead: every signal uses only CLOSED bars; fills at next bar open.
"""
import pandas as pd, numpy as np, os, warnings
warnings.filterwarnings('ignore')
D = os.path.join(os.path.dirname(__file__), '..', 'data')
PT = 0.01                      # XAUUSD point
SPREAD_PTS = 5.0               # modelled (spread column unreliable), + slippage below
SLIP_PTS = 2.0

def load(tf):
    d = pd.read_csv(os.path.join(D, f'XAUUSD_{tf}.csv'), encoding='utf-8-sig')
    d['time'] = pd.to_datetime(d['time'])
    d = d.sort_values('time').reset_index(drop=True)
    tr = np.maximum(d.high-d.low,
         np.maximum((d.high-d.close.shift()).abs(), (d.low-d.close.shift()).abs()))
    d['atr'] = tr.rolling(14).mean()
    return d

def resample(d, rule):
    x = d.set_index('time').resample(rule).agg(
        open=('open','first'), high=('high','max'),
        low=('low','min'), close=('close','last')).dropna().reset_index()
    tr = np.maximum(x.high-x.low,
         np.maximum((x.high-x.close.shift()).abs(), (x.low-x.close.shift()).abs()))
    x['atr'] = tr.rolling(14).mean()
    return x

def swings(h, l, k=2):
    """Confirmed fractal swings. Strict-left / non-strict-right (earliest wins).
       Confirmed only k bars later -> no look-ahead."""
    n = len(h); sh = np.zeros(n, bool); sl = np.zeros(n, bool)
    for i in range(k, n-k):
        if all(h[i] >  h[i-j] for j in range(1,k+1)) and \
           all(h[i] >= h[i+j] for j in range(1,k+1)): sh[i] = True
        if all(l[i] <  l[i-j] for j in range(1,k+1)) and \
           all(l[i] <= l[i+j] for j in range(1,k+1)): sl[i] = True
    return sh, sl

def trend_state(x, k=2):
    """HH/HL = up, LH/LL = down, else 0. Uses only confirmed swings."""
    h, l = x.high.values, x.low.values
    sh, sl = swings(h, l, k)
    n = len(x); st = np.zeros(n)
    lastH = lastH2 = lastL = lastL2 = np.nan
    for i in range(n):
        if i >= k and sh[i-k]:
            lastH2, lastH = lastH, h[i-k]
        if i >= k and sl[i-k]:
            lastL2, lastL = lastL, l[i-k]
        if not (np.isnan(lastH) or np.isnan(lastH2) or np.isnan(lastL) or np.isnan(lastL2)):
            if lastH > lastH2 and lastL > lastL2: st[i] = 1
            elif lastH < lastH2 and lastL < lastL2: st[i] = -1
    return st, sh, sl

def map_to(base_times, src_times, src_vals):
    """Forward-fill a higher-TF series onto lower-TF bars, shifted so only
       CLOSED higher-TF bars are visible."""
    s = pd.Series(src_vals, index=src_times).shift(1)
    return s.reindex(base_times, method='ffill').values
