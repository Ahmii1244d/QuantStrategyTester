"""
RESEARCH CONFIGURATION - frozen 2026-08-12
Protocol sections 4, 5, 7, 11, 12.
Anything not derivable from the CSVs is marked UNKNOWN and must not be
silently replaced with a guess.
"""
import os
DATA = os.path.join(os.path.dirname(__file__), '..', 'data')

SYMBOLS = ['EURUSD','GBPUSD','AUDUSD','NZDUSD','USDCAD','USDJPY',
           'EURJPY','GBPJPY','XAUUSD','XAGUSD','US30']

# --------------------------------------------------------------------
# TIMEZONE (protocol 4)
# Inferred from volume profile: FX peak at server hour 17.
# True EURUSD volume peak is the London/NY overlap ~14:00 UTC.
# => server = UTC+3. Consistent across all FX symbols.
# --------------------------------------------------------------------
SERVER_UTC_OFFSET = 3
TIMESTAMP_CONVENTION = 'BAR_OPEN'   # verified: modal gap 1800s, first bar 06:00
BAR_SECONDS = 1800

# --------------------------------------------------------------------
# INSTRUMENT TYPE (protocol 5, 57)
# 24h coverage + spread column + 'US30' naming => broker CFD feed.
# NOT exchange futures. No contract/roll metadata exists in these files.
# --------------------------------------------------------------------
INSTRUMENT_TYPE = 'CFD_BROKER_FEED'

# point size inferred from decimal precision (verified in audit)
POINT = {'EURUSD':1e-5,'GBPUSD':1e-5,'AUDUSD':1e-5,'NZDUSD':1e-5,'USDCAD':1e-5,
         'USDJPY':1e-3,'EURJPY':1e-3,'GBPJPY':1e-3,
         'XAUUSD':1e-2,'XAGUSD':1e-3,'US30':1e-1}

# --------------------------------------------------------------------
# UNKNOWN - USER INPUT REQUIRED (protocol 5)
# These MUST be supplied from the broker contract spec before any
# result may be reported as executable rather than indicative.
# --------------------------------------------------------------------
UNKNOWN_REQUIRED = {
    'contract_size'      : 'UNKNOWN - USER INPUT REQUIRED',
    'tick_value'         : 'UNKNOWN - USER INPUT REQUIRED',
    'commission_per_side': 'UNKNOWN - USER INPUT REQUIRED',
    'swap_rates'         : 'UNKNOWN - USER INPUT REQUIRED',
    'min_lot_step'       : 'UNKNOWN - USER INPUT REQUIRED',
    'broker_name'        : 'UNKNOWN - USER INPUT REQUIRED',
    'prop_firm_rules'    : 'UNKNOWN - VERIFY WITH FIRM',
}

# --------------------------------------------------------------------
# COST MODEL (protocol 11)  *** SIMULATED COST ASSUMPTION ***
# The spread column is NOT usable as observed cost: 57% of EURUSD bars
# report spread == 0, which is not physically possible. Therefore cost
# is MODELLED from the non-zero median, not read from the file.
# All results carry the SIMULATED COST ASSUMPTION label.
# --------------------------------------------------------------------
SPREAD_MODEL_POINTS = {   # median of NON-ZERO observations, from audit
    'EURUSD':2.0,'GBPUSD':4.0,'AUDUSD':4.0,'NZDUSD':5.0,'USDCAD':3.0,
    'USDJPY':3.0,'EURJPY':5.0,'GBPJPY':7.0,
    'XAUUSD':5.0,'XAGUSD':13.0,'US30':120.0,
}
SLIPPAGE_POINTS = {s:(1.0 if POINT[s]<=1e-3 else 1.0) for s in SYMBOLS}
SLIPPAGE_POINTS['US30'] = 20.0
SLIPPAGE_POINTS['XAGUSD'] = 5.0
COST_MULTIPLIERS = [0.5, 1.0, 1.5, 2.0]      # stress grid
COST_LABEL = 'SIMULATED COST ASSUMPTION'

# --------------------------------------------------------------------
# EXECUTION MODEL (protocol 12) - fixed BEFORE any test
# --------------------------------------------------------------------
EXEC_SIGNAL_BAR   = 'CLOSED_BAR_ONLY'
EXEC_FILL         = 'NEXT_BAR_OPEN'
INTRABAR_AMBIGUITY= 'ADVERSE'   # if SL and TP both reachable in one bar -> SL wins
MAX_HOLD_BARS     = 96

# --------------------------------------------------------------------
# DATA SPLITS (protocol 7) - date-based, chronological, frozen
# Full span 2020-01-02 .. 2026-08-11
# --------------------------------------------------------------------
SPLITS = {
    'development': ('2020-01-02', '2023-12-31'),   # ~60%
    'validation' : ('2024-01-01', '2025-06-30'),   # ~20%
    'holdout'    : ('2025-07-01', '2026-08-11'),   # ~20%  UNTOUCHED
}
HOLDOUT_STATUS = 'UNTOUCHED'

# --------------------------------------------------------------------
# KNOWN DATA DEFECTS (protocol 6) - never silently repaired
# --------------------------------------------------------------------
DATA_DEFECTS = {
    'US30': [
        'GAP: 1324h (55 days) ending 2025-09-09 14:30 - falls inside HOLDOUT. '
        'US30 holdout results are NOT reliable and must be reported separately.',
        'max identical-close run = 15 bars (illiquid/stale quotes)',
    ],
    'XAGUSD': ['67 zero-range bars; 1216 intraweek gaps (daily maintenance break at hour 0)'],
    'XAUUSD': ['1371 intraweek gaps (daily maintenance break at hour 0)'],
    'ALL_FX': ['spread column unreliable (zero on 17-57% of bars) - cost is modelled'],
}

# --------------------------------------------------------------------
# PARAMETER BUDGET (protocol 60) - declared before testing
# --------------------------------------------------------------------
PARAM_BUDGET = {
    'phase0_controls'  : 4,
    'phase1_breakout'  : 9,    # 3 OR windows x 3 stop mults
    'phase2_donchian'  : 3,    # lookback 10/20/40
    'phase3_pullback'  : 9,    # 3 pullback x 3 stop
    'phase4_pairs'     : 55,   # all pairs, single fixed rule
    'max_total_trials' : 200,
}
