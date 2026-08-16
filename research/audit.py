"""
PHASE 0 - DATA AUDIT
Quant Research Lab v2.0 - protocol sections 2, 3, 4, 6
Reports structural facts only. Repairs nothing. Assumes nothing.
"""
import pandas as pd, numpy as np, os, glob, json, warnings
warnings.filterwarnings('ignore')

DATA = os.path.join(os.path.dirname(__file__), '..', 'data')
OUT  = os.path.join(os.path.dirname(__file__), '..', 'reports')

def load(f):
    d = pd.read_csv(f, encoding='utf-8-sig')
    d['time'] = pd.to_datetime(d['time'])
    return d

def audit_one(path):
    sym = os.path.basename(path).replace('_M30.csv','')
    d = load(path)
    r = {'symbol': sym, 'rows': len(d), 'columns': list(d.columns)}

    # --- 2.1 metadata ---
    r['first_ts'] = str(d.time.min()); r['last_ts'] = str(d.time.max())
    r['span_days'] = (d.time.max()-d.time.min()).days
    r['dup_rows'] = int(d.duplicated().sum())
    r['dup_timestamps'] = int(d.time.duplicated().sum())
    r['monotonic'] = bool(d.time.is_monotonic_increasing)

    # --- timeframe inference (protocol 3) ---
    dt = d.time.diff().dt.total_seconds().dropna()
    r['modal_gap_sec'] = int(dt.mode()[0]) if len(dt) else None
    r['pct_bars_at_modal_gap'] = round(100*float((dt==dt.mode()[0]).mean()),2)

    # --- gaps ---
    step = r['modal_gap_sec']
    big = dt[dt > step*1.5]
    r['n_gaps'] = int(len(big))
    r['max_gap_hours'] = round(float(big.max()/3600),1) if len(big) else 0.0
    # weekend gaps: >=48h
    r['n_weekend_gaps'] = int((big>=47*3600).sum())
    r['n_intraweek_gaps'] = int(((big>step*1.5)&(big<47*3600)).sum())

    # --- OHLC validity (protocol 2.1) ---
    bad_hi = int((d.high < d[['open','close']].max(axis=1)).sum())
    bad_lo = int((d.low  > d[['open','close']].min(axis=1)).sum())
    bad_hl = int((d.high < d.low).sum())
    r['ohlc_violations'] = bad_hi + bad_lo + bad_hl
    r['bad_high'], r['bad_low'], r['bad_highlow'] = bad_hi, bad_lo, bad_hl
    r['nonpositive_px'] = int((d[['open','high','low','close']] <= 0).sum().sum())
    r['nan_count'] = int(d.isna().sum().sum())
    r['inf_count'] = int(np.isinf(d.select_dtypes(np.number)).sum().sum())

    # --- flat / suspicious bars ---
    r['zero_range_bars'] = int((d.high==d.low).sum())
    r['zero_volume_bars'] = int((d.volume==0).sum()) if 'volume' in d else None
    # repeated identical close 5+ in a row
    same = (d.close == d.close.shift()).astype(int)
    runs = same.groupby((same!=same.shift()).cumsum()).sum()
    r['max_identical_close_run'] = int(runs.max()) if len(runs) else 0

    # --- price/precision -> point size inference (protocol 5) ---
    dec = d['close'].astype(str).str.split('.').str[-1].str.len().mode()[0]
    r['digits'] = int(dec)
    r['point_size'] = float(10.0**(-dec))
    r['px_first'] = float(d.close.iloc[0]); r['px_last'] = float(d.close.iloc[-1])

    # --- spread column ---
    if 'spread' in d:
        r['spread_median_pts'] = float(d.spread.median())
        r['spread_p95_pts'] = float(d.spread.quantile(0.95))
        r['spread_max_pts'] = float(d.spread.max())
        r['spread_zero_pct'] = round(100*float((d.spread==0).mean()),2)
    # --- session profile (protocol 4) ---
    d['h'] = d.time.dt.hour
    bh = d.groupby('h').size()
    r['hours_present'] = int((bh>0).sum())
    r['peak_volume_hour'] = int(d.groupby('h')['volume'].mean().idxmax()) if 'volume' in d else None
    r['bars_per_day_median'] = float(d.groupby(d.time.dt.date).size().median())
    r['trading_days'] = int(d.time.dt.date.nunique())
    return r, d

def main():
    files = sorted(glob.glob(os.path.join(DATA,'*_M30.csv')))
    rows = []; frames = {}
    for f in files:
        rr, dd = audit_one(f); rows.append(rr); frames[rr['symbol']] = dd
    A = pd.DataFrame(rows)

    # ---- status assignment ----
    def status(x):
        if x.ohlc_violations>0 or x.nonpositive_px>0 or x.nan_count>0 or not x.monotonic:
            return 'FAIL'
        if x.dup_timestamps>0 or x.max_identical_close_run>=20 or x.n_intraweek_gaps>500:
            return 'WARNING'
        return 'PASS'
    A['status'] = A.apply(status, axis=1)

    pd.set_option('display.width',250)
    print("="*118); print("PHASE 0 - DATA AUDIT"); print("="*118)
    print(A[['symbol','rows','first_ts','last_ts','span_days','trading_days',
             'digits','point_size','status']].to_string(index=False))

    print("\n" + "="*118); print("STRUCTURAL INTEGRITY"); print("="*118)
    print(A[['symbol','monotonic','dup_rows','dup_timestamps','ohlc_violations',
             'nonpositive_px','nan_count','inf_count','zero_range_bars',
             'max_identical_close_run']].to_string(index=False))

    print("\n" + "="*118); print("CONTINUITY / GAPS"); print("="*118)
    print(A[['symbol','modal_gap_sec','pct_bars_at_modal_gap','n_gaps',
             'n_weekend_gaps','n_intraweek_gaps','max_gap_hours',
             'bars_per_day_median']].to_string(index=False))

    print("\n" + "="*118); print("COST INPUTS (observed, not assumed)"); print("="*118)
    print(A[['symbol','px_first','px_last','digits','point_size','spread_median_pts',
             'spread_p95_pts','spread_max_pts','spread_zero_pct','peak_volume_hour']].to_string(index=False))

    A.to_csv(os.path.join(OUT,'phase0_data_audit.csv'), index=False)
    print(f"\n  -> written: reports/phase0_data_audit.csv")
    return A, frames

if __name__ == '__main__':
    main()
