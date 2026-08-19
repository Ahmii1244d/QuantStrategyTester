"""
GOLD PULLBACK MTF  -  canonical Python strategy (PropLab tester format).

Paste the Strategy class below into the tester, or import STRATEGY_CODE.

This file is the REFERENCE IMPLEMENTATION. GoldPullbackMTF.mq5 is a
line-by-line port of it. parity_check.py proves the two agree.

Mechanism
---------
LONG ONLY. On each closed M30 bar:
  1. skip the London window (hours 7-11 inclusive, broker server time)
  2. require volume > 20-bar average volume (average taken BEFORE this bar)
  3. require D1 ADX(14) >= 18 AND rising vs the previous D1 bar
  4. require H4 bullish   : EMA20 > EMA50 AND close > EMA50
  5. require D1 bullish   : close > EMA50
  6. enter on EITHER
       breakout : close > highest high of the previous 20 bars
       pullback : low <= EMA20 AND close > EMA20 AND close > open
  7. stop = close - 2.0 * ATR(14);  target = 2.0 R measured FROM THE FILL

Every higher-timeframe read uses the LAST CLOSED bar (searchsorted - 2),
so there is no look-ahead and no repainting.

Numerical conventions that the MQL5 port MUST match
---------------------------------------------------
  ATR      SIMPLE mean of True Range over 14 bars. NOT Wilder / iATR.
           (median difference 9.7%, 95th pct 35% - a different stop.)
  EMA      alpha = 2/(span+1), seeded at the FIRST bar
           (pandas ewm(adjust=False); NOT iMA, which seeds with an SMA).
  ADX      Wilder: RMA(alpha=1/14) of TR/+DM/-DM, then RMA of DX.
           Seeded at bar 0 with TR = high-low, +DM = -DM = 0.
  Donchian max(high) over the 20 bars BEFORE the signal bar.
  VolMA    mean(volume) over the 20 bars BEFORE the signal bar.
  Hours    taken from the raw bar timestamp = broker server time.

History needed for the live EA to reproduce these values exactly:
  >= 600 D1 bars   (EMA50 and ADX14 seeding converge by then; measured
                    max deviation over the last 60 bars: 7e-08)
  >= 300 H4 bars, >= 300 M30 bars for the EMA20 pullback line.
"""

STRATEGY_CODE = r'''class Strategy:
    timeframes = ["M30", "H4", "D1"]

    DONCHIAN     = 20
    ATR_MULT     = 2.0
    RR           = 2.0
    D1_ADX_MIN   = 18
    PULLBACK_EMA = 20
    SKIP_HOUR_LO = 7
    SKIP_HOUR_HI = 11
    VOL_MA       = 20
    VOL_MULT     = 1.0
    H4_FAST      = 20
    H4_SLOW      = 50
    D1_EMA       = 50
    ADX_PERIOD   = 14
    WARMUP       = 300

    def signals(self, data):
        import numpy as np
        import pandas as pd

        base = data["M30"]
        htf  = data["H4"]
        d1   = data["D1"]
        n    = len(base)

        direction = np.zeros(n)
        stop      = np.full(n, np.nan)
        rr        = np.full(n, self.RR)

        o   = base["open"].to_numpy(float)
        c   = base["close"].to_numpy(float)
        lo  = base["low"].to_numpy(float)
        atr = base["atr"].to_numpy(float)          # tester atr = SMA(TR,14)
        vol = base["volume"].to_numpy(float)

        hour = pd.to_datetime(base["time"]).dt.hour.to_numpy()

        # --- windows measured over the bars BEFORE the signal bar ---
        prev_high = base["high"].rolling(self.DONCHIAN).max().shift(1).to_numpy(float)
        vol_ma    = base["volume"].rolling(self.VOL_MA).mean().shift(1).to_numpy(float)
        # --- pullback line uses the signal bar itself (it is closed) ---
        ema_pb    = base["close"].ewm(span=self.PULLBACK_EMA, adjust=False).mean().to_numpy(float)

        # --- map each M30 bar to the LAST CLOSED H4 / D1 bar ---
        bt = base["time"].to_numpy().astype("int64")
        ht = htf["time"].to_numpy().astype("int64")
        dt = d1["time"].to_numpy().astype("int64")
        pos_h4 = np.searchsorted(ht, bt, side="right") - 2
        pos_d1 = np.searchsorted(dt, bt, side="right") - 2

        h4_c    = htf["close"].to_numpy(float)
        h4_fast = htf["close"].ewm(span=self.H4_FAST, adjust=False).mean().to_numpy(float)
        h4_slow = htf["close"].ewm(span=self.H4_SLOW, adjust=False).mean().to_numpy(float)

        d1_c     = d1["close"].to_numpy(float)
        d1_ema50 = d1["close"].ewm(span=self.D1_EMA, adjust=False).mean().to_numpy(float)
        d1_adx   = self._adx(d1, self.ADX_PERIOD)
        d1_prev  = np.full_like(d1_adx, np.nan)
        d1_prev[1:] = d1_adx[:-1]

        for i in range(self.WARMUP, n):
            ph  = pos_h4[i]
            pdd = pos_d1[i]
            if ph < 1 or pdd < 1:
                continue

            a = atr[i]
            if not np.isfinite(a) or a <= 0:
                continue
            if not np.isfinite(prev_high[i]) or not np.isfinite(ema_pb[i]):
                continue
            if not np.isfinite(vol_ma[i]) or vol[i] <= vol_ma[i] * self.VOL_MULT:
                continue
            if self.SKIP_HOUR_LO <= hour[i] <= self.SKIP_HOUR_HI:
                continue

            d1v = d1_adx[pdd]
            d1p = d1_prev[pdd]
            if not (np.isfinite(d1v) and np.isfinite(d1p)):
                continue
            if d1v < self.D1_ADX_MIN:
                continue
            if not (d1v > d1p):
                continue

            h4_bull = h4_fast[ph] > h4_slow[ph] and h4_c[ph] > h4_slow[ph]
            d1_bull = d1_c[pdd] > d1_ema50[pdd]
            if not (h4_bull and d1_bull):
                continue

            breakout = c[i] > prev_high[i]
            pullback = (lo[i] <= ema_pb[i]) and (c[i] > ema_pb[i]) and (c[i] > o[i])

            if breakout or pullback:
                direction[i] = 1
                stop[i]      = c[i] - self.ATR_MULT * a

        return direction, stop, rr

    def _adx(self, df, period=14):
        """Wilder ADX. Seeded at bar 0 with TR = high-low and +DM = -DM = 0,
        which is what pandas produces because .max(axis=1) skips the NaN
        created by the missing previous close. The MQL5 port seeds the same
        way; verified max|diff| = 0.0 against this implementation."""
        import numpy as np
        import pandas as pd

        h = df["high"]
        l = df["low"]
        c = df["close"]
        prev_c = c.shift(1)

        tr = pd.concat(
            [h - l, (h - prev_c).abs(), (l - prev_c).abs()],
            axis=1,
        ).max(axis=1)

        up_move   = h.diff()
        down_move = -l.diff()

        plus_dm = pd.Series(
            np.where((up_move > down_move) & (up_move > 0), up_move, 0.0),
            index=df.index,
        )
        minus_dm = pd.Series(
            np.where((down_move > up_move) & (down_move > 0), down_move, 0.0),
            index=df.index,
        )

        a = 1.0 / period
        tr_ewm       = tr.ewm(alpha=a, adjust=False).mean()
        plus_dm_ewm  = plus_dm.ewm(alpha=a, adjust=False).mean()
        minus_dm_ewm = minus_dm.ewm(alpha=a, adjust=False).mean()

        plus_di  = 100 * plus_dm_ewm / tr_ewm
        minus_di = 100 * minus_dm_ewm / tr_ewm

        dx  = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)
        adx = dx.ewm(alpha=a, adjust=False).mean()
        return adx.to_numpy()
'''


# ---------------------------------------------------------------------------
# Loop-based reference implementations. These are what GoldPullbackMTF.mq5
# computes; parity_check.py asserts they equal the pandas versions above.
# ---------------------------------------------------------------------------
def ema_series(x, span):
    """pandas .ewm(span=span, adjust=False).mean(), written as an explicit loop."""
    import numpy as np
    x = np.asarray(x, dtype=float)
    a = 2.0 / (span + 1.0)
    out = np.empty(len(x))
    if len(x) == 0:
        return out
    out[0] = x[0]
    for i in range(1, len(x)):
        out[i] = a * x[i] + (1.0 - a) * out[i - 1]
    return out


def adx_series(high, low, close, period=14):
    """Wilder ADX as an explicit loop, seeded exactly like the pandas version."""
    import numpy as np
    h = np.asarray(high, dtype=float)
    l = np.asarray(low, dtype=float)
    c = np.asarray(close, dtype=float)
    n = len(h)
    a = 1.0 / period
    out = np.full(n, np.nan)
    if n == 0:
        return out

    trs = h[0] - l[0]          # seed: pandas max() skips the NaN prev close
    ps = 0.0
    ms = 0.0
    adxs = 0.0
    seeded = False

    for i in range(1, n):
        up = h[i] - h[i - 1]
        dn = l[i - 1] - l[i]
        pdm = up if (up > dn and up > 0) else 0.0
        mdm = dn if (dn > up and dn > 0) else 0.0
        tr = max(h[i] - l[i], abs(h[i] - c[i - 1]), abs(l[i] - c[i - 1]))

        trs = a * tr + (1 - a) * trs
        ps = a * pdm + (1 - a) * ps
        ms = a * mdm + (1 - a) * ms

        if trs > 0:
            pdi = 100.0 * ps / trs
            mdi = 100.0 * ms / trs
            den = pdi + mdi
            if den > 0:
                dx = 100.0 * abs(pdi - mdi) / den
                if not seeded:
                    adxs = dx
                    seeded = True
                else:
                    adxs = a * dx + (1 - a) * adxs
        out[i] = adxs if seeded else np.nan
    return out


def atr_sma(high, low, close, period=14):
    """SIMPLE mean of True Range - the tester's atr column. NOT Wilder."""
    import numpy as np
    import pandas as pd
    h = pd.Series(np.asarray(high, dtype=float))
    l = pd.Series(np.asarray(low, dtype=float))
    c = pd.Series(np.asarray(close, dtype=float))
    pc = c.shift(1)
    tr = pd.concat([h - l, (h - pc).abs(), (l - pc).abs()], axis=1).max(axis=1)
    return tr.rolling(period).mean().to_numpy(float)


if __name__ == "__main__":
    print(__doc__)
    print("STRATEGY_CODE is %d characters; paste it into the PropLab tester."
          % len(STRATEGY_CODE))
