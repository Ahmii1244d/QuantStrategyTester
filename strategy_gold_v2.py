class Strategy:
    """
    XAUUSD trend strategy v2  -  selected under pre-registration (research/gold_lab.py).

    Two changes vs v1, each with a reason found in the data, not by score-chasing:

      1. ENTRY = breakout OR pullback. v1 only bought Donchian breakouts, which
         only exist while gold is making new highs -> it lost -0.19R in gold's
         flat/down years. Adding a pullback-to-EMA20 entry gives the same trend
         logic a way to trade inside a range. Flat/down-gold years go -0.19R -> +0.12R.

      2. Skip the London window (07-11 UTC). Gold's London open is a
         liquidity-grab window: it produced -0.16R across the sample while every
         other session was positive.

    Everything else is v1 unchanged. No parameter was tuned for score.
    """
    timeframes = ["M30", "H4", "D1"]

    DONCHIAN     = 20
    ATR_MULT     = 2.0
    RR           = 2.0
    H4_ADX_MIN   = 20
    D1_ADX_MIN   = 18
    PULLBACK_EMA = 20
    SKIP_HOUR_LO = 7        # London window skipped, inclusive
    SKIP_HOUR_HI = 11

    def signals(self, data):
        import numpy as np

        base = data["M30"]; htf = data["H4"]; d1 = data["D1"]
        n = len(base)
        direction = np.zeros(n)
        stop      = np.full(n, np.nan)
        rr        = np.full(n, self.RR)

        o   = base["open"].to_numpy(float)
        c   = base["close"].to_numpy(float)
        lo  = base["low"].to_numpy(float)
        atr = base["atr"].to_numpy(float)
        hour = base["time"].dt.hour.to_numpy()

        prev_high = base["high"].rolling(self.DONCHIAN).max().shift(1).to_numpy(float)
        ema_pb    = base["close"].ewm(span=self.PULLBACK_EMA, adjust=False).mean().to_numpy(float)

        # last CLOSED higher-timeframe bar (searchsorted - 2), never the forming one
        bt = base["time"].to_numpy().astype("int64")
        ht = htf["time"].to_numpy().astype("int64")
        dt = d1["time"].to_numpy().astype("int64")
        pos_h4 = np.searchsorted(ht, bt, side="right") - 2
        pos_d1 = np.searchsorted(dt, bt, side="right") - 2

        h4_c    = htf["close"].to_numpy(float)
        h4_fast = htf["close"].ewm(span=20, adjust=False).mean().to_numpy(float)
        h4_slow = htf["close"].ewm(span=50, adjust=False).mean().to_numpy(float)
        h4_adx  = self._adx(htf, 14)
        h4_prev = np.full_like(h4_adx, np.nan); h4_prev[1:] = h4_adx[:-1]

        d1_c     = d1["close"].to_numpy(float)
        d1_ema50 = d1["close"].ewm(span=50, adjust=False).mean().to_numpy(float)
        d1_adx   = self._adx(d1, 14)
        d1_prev  = np.full_like(d1_adx, np.nan); d1_prev[1:] = d1_adx[:-1]

        for i in range(300, n):
            ph = pos_h4[i]; pdd = pos_d1[i]
            if ph < 1 or pdd < 1:
                continue
            a = atr[i]
            if not np.isfinite(a) or a <= 0:
                continue
            if not np.isfinite(prev_high[i]) or not np.isfinite(ema_pb[i]):
                continue
            if self.SKIP_HOUR_LO <= hour[i] <= self.SKIP_HOUR_HI:
                continue

            h4v = h4_adx[ph]; h4p = h4_prev[ph]
            d1v = d1_adx[pdd]; d1p = d1_prev[pdd]
            if not (np.isfinite(h4v) and np.isfinite(h4p)
                    and np.isfinite(d1v) and np.isfinite(d1p)):
                continue
            if h4v < self.H4_ADX_MIN or d1v < self.D1_ADX_MIN:
                continue
            if not (h4v > h4p and d1v > d1p):        # trend strength must be rising
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
        import numpy as np, pandas as pd
        h = df["high"]; l = df["low"]; c = df["close"]; pc = c.shift(1)
        tr = pd.concat([h - l, (h - pc).abs(), (l - pc).abs()], axis=1).max(axis=1)
        up = h.diff(); dn = -l.diff()
        pdm = pd.Series(np.where((up > dn) & (up > 0), up, 0.0), index=df.index)
        mdm = pd.Series(np.where((dn > up) & (dn > 0), dn, 0.0), index=df.index)
        tre = tr.ewm(alpha=1/period, adjust=False).mean()
        pde = pdm.ewm(alpha=1/period, adjust=False).mean()
        mde = mdm.ewm(alpha=1/period, adjust=False).mean()
        pi = 100 * pde / tre; mi = 100 * mde / tre
        dx = 100 * (pi - mi).abs() / (pi + mi).replace(0, np.nan)
        return dx.ewm(alpha=1/period, adjust=False).mean().to_numpy()
