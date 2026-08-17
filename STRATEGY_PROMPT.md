# Strategy-writing prompt for the PropLab tester

Paste everything inside the fence below into any AI, then add your idea in one
sentence at the end (e.g. *"Build a London-session opening-range breakout on
XAUUSD"*). It encodes this engine's real contract, its execution model, and the
exact things that get code rejected — so you get a strategy that **runs, is
causal, and is judged transparently** instead of one that crashes, silently
falls back, or fakes a winner by riding market drift.

---

````text
You are writing a trading strategy for a local prop-firm strategy tester
("PropLab"). Your output must run first time, without crashing, without
look-ahead, and without gaming the scorer. Follow this specification exactly.

=========================================================
1. THE CONTRACT (non-negotiable)
=========================================================
Output ONE Python class named exactly `Strategy`, nothing else around it:

    class Strategy:
        timeframes = ["M30", "H4"]        # data you need
        def signals(self, data):
            ...
            return direction, stop, rr

- `data` is a dict of pandas DataFrames keyed by timeframe string.
- Every DataFrame has columns: time, open, high, low, close, volume, atr
  (`atr` is a precomputed 14-period ATR; its first 13 values are NaN).
- The BASE timeframe is the LOWEST one you list in `timeframes`.
- All three returned arrays MUST have length == len(data[base_tf]).
    direction[i] : +1 long, -1 short, 0 no trade
    stop[i]      : the stop-loss PRICE (a real price level), or np.nan
    rr[i]        : reward:risk multiple, e.g. 2.0 (a scalar is also accepted)
- Import numpy INSIDE `signals` (`import numpy as np`).
- Do NOT read or hardcode account balance, risk %, targets, or loss limits.
  The tester owns those. A strategy that references them is wrong.

=========================================================
2. DATA THAT ACTUALLY EXISTS
=========================================================
- XAUUSD has M5, M15, M30, H1, H4, D1  (M5 ~466k bars, M30 ~78k bars).
- Other symbols have M30 only.
- Higher timeframes are built automatically if no file exists. LOWER ones
  cannot be invented: asking for M1 fails with CANNOT_TEST.
- Prefer M30 as your base unless the idea genuinely needs M5. M5 is ~6x more
  bars and is the main cause of timeouts.

=========================================================
3. HOW THE ENGINE EXECUTES YOUR SIGNALS
=========================================================
Write code that is realistic under THIS execution model:

- A signal on bar i is filled at the OPEN of bar i+1, with spread+slippage
  applied against you. You never get the signal bar's close as your fill.
- risk = |entry - stop|. If that distance is under 1 point the trade is
  SILENTLY SKIPPED. Never use micro-stops.
- Take profit = entry + rr * risk * direction.
- If the stop and target are both touched inside the same bar, it is scored as
  a LOSS (-1R). Adverse tie-breaking is deliberate — do not design setups that
  depend on winning an intrabar race.
- Max hold is 576 bars; after that the trade exits at the close.
- ONE POSITION AT A TIME. After a trade closes the engine resumes at the bar
  AFTER the exit, so any signals you emit while a trade is open are discarded.
  Spamming a signal on every bar does not create more trades — it just means
  the engine takes whichever one comes after the previous exit. Emit signals
  only where the setup is genuinely valid.
- The stop MUST be on the correct side: below entry for longs, above entry for
  shorts. A stop on the wrong side is an instant -1R on every trade.

=========================================================
4. CAUSALITY — THIS IS WHAT GETS CODE REJECTED
=========================================================
The tester re-runs `signals()` on truncated data and compares. If any past
signal changes when the future is hidden, the run is REJECTED with LOOKAHEAD.

- Never index i+1, i+2, `.shift(-1)`, `np.roll(x, -k)`, `[::-1]` lookups, or
  any full-series max/min that includes future bars.
- Using bar i's own OHLC at bar i is allowed (you are filled at i+1).
- HIGHER TIMEFRAMES ARE THE #1 TRAP. A higher-TF bar is only usable once it has
  CLOSED. Saved files are open-timestamped, so the containing bar is still
  forming and its OHLC is not yet knowable. Use the LAST CLOSED bar:

      bt  = base["time"].to_numpy().astype("int64")
      ht  = htf["time"].to_numpy().astype("int64")
      pos = np.searchsorted(ht, bt, side="right") - 2
      #   -1 -> the containing (still forming) bar   <-- REJECTED
      #   -2 -> the last CLOSED bar                  <-- CORRECT
      # then guard: if pos[i] < 0: continue

- `signals()` must be PURE and DETERMINISTIC: no module-level mutable state, no
  caching between calls, no unseeded randomness, no reading files or clocks.
  It is called more than once and must return the same thing for the same input.

=========================================================
5. PERFORMANCE (hard timeouts: 60s fast, 180s deep)
=========================================================
- Precompute every indicator, pivot, session mask and timeframe mapping ONCE,
  as numpy arrays, BEFORE the main loop.
- Then do a SINGLE forward pass. O(n) total.
- Never search or slice history inside the per-bar loop (no `df[:i].max()`, no
  `.rolling()` per bar, no `searchsorted` per bar). That is the #1 timeout cause.
- Start the loop after a warm-up (e.g. `range(300, n)`) and skip bars where ATR
  is NaN or <= 0.

=========================================================
6. WHAT THE SCORER REWARDS (do not try to game it)
=========================================================
The score is mainly the probability of passing the configured prop challenge,
gated by robustness checks that a drift-riding strategy cannot fake:

- BENCHMARK: your expectancy must beat a matched always-long (or always-short)
  benchmark by more than 0.04R. A long-only strategy on an instrument that
  trended up for years will TIE this and be labelled "NO CLEAR EDGE".
  => Trade both directions, or prove genuine timing.
- INVERSION: the tester flips BUY<->SELL and reruns. A real edge's mirror must
  clearly LOSE. If the inverse also makes money, the edge is not directional.
- HOLDOUT: unseen-data expectancy must exceed 0.04R (the engine's execution
  noise floor) with at least 15 holdout trades. +0.001R counts as no edge.
- COST: expectancy must still be positive at 3x modelled cost.
- SAMPLE: fewer than 30 development trades caps the score.
- Trade COUNT, a fixed RR of 2, and a barely-positive holdout earn NOTHING.
  Do not pad trade count to manufacture significance.

Rough sizing intuition: at 0.25% risk on $5,000 each 1R is ~$12.50, so a +8%
Phase-1 target needs about +32R net. Higher expectancy per trade means fewer
trades and fewer days to pass — selective quality beats volume.

=========================================================
7. FAILURE MODES TO AVOID
=========================================================
  CODE ERROR    - syntax error, or the class is not named `Strategy`
  STRATEGY ERROR- exception inside signals(); KeyError = asked for a timeframe
                  or column that does not exist
  length error  - returned arrays not the same length as the base timeframe
  CANNOT_TEST   - requested a timeframe finer than the data
  NO_TRADES     - produced fewer than 5 trades
  LOOKAHEAD     - used future information (see section 4)
  TIMEOUT       - per-bar history search (see section 5)

=========================================================
8. WORKING SKELETON — start from this shape
=========================================================
class Strategy:
    timeframes = ["M30", "H4"]          # base = M30 (the LOWEST one requested)

    ATR_MULT = 1.5
    RR       = 2.0

    def signals(self, data):
        import numpy as np

        base = data["M30"]
        htf  = data["H4"]
        n    = len(base)

        direction = np.zeros(n)
        stop      = np.full(n, np.nan)
        rr        = np.full(n, self.RR)

        c   = base["close"].to_numpy(float)
        atr = base["atr"].to_numpy(float)

        # --- map each base bar to the LAST CLOSED higher-TF bar -------------
        bt  = base["time"].to_numpy().astype("int64")
        ht  = htf["time"].to_numpy().astype("int64")
        pos = np.searchsorted(ht, bt, side="right") - 2

        htf_c   = htf["close"].to_numpy(float)
        htf_ema = htf["close"].ewm(span=20, adjust=False).mean().to_numpy()

        # --- precompute base-TF indicators ONCE (nothing heavy in the loop) -
        ema_f = base["close"].ewm(span=20, adjust=False).mean().to_numpy()
        ema_s = base["close"].ewm(span=50, adjust=False).mean().to_numpy()

        for i in range(300, n):
            p = pos[i]
            if p < 0:
                continue
            a = atr[i]
            if not np.isfinite(a) or a <= 0:
                continue

            up     = htf_c[p] > htf_ema[p]
            down   = htf_c[p] < htf_ema[p]
            x_up   = ema_f[i] > ema_s[i] and ema_f[i-1] <= ema_s[i-1]
            x_down = ema_f[i] < ema_s[i] and ema_f[i-1] >= ema_s[i-1]

            if up and x_up:
                direction[i] = 1
                stop[i]      = c[i] - self.ATR_MULT * a
            elif down and x_down:
                direction[i] = -1
                stop[i]      = c[i] + self.ATR_MULT * a

        return direction, stop, rr

=========================================================
9. SELF-CHECK BEFORE YOU ANSWER
=========================================================
Confirm every line, and say so briefly:
  [ ] class is named `Strategy`; returns 3 arrays of the base-TF length
  [ ] no index beyond i; no shift(-1)/roll(-k)/future slices
  [ ] every higher-TF read uses the last CLOSED bar (searchsorted ... - 2)
  [ ] signals() is pure and deterministic; no global state or RNG
  [ ] all indicators precomputed; single O(n) pass; no history search in loop
  [ ] stops on the correct side, ATR-scaled, never micro-stops
  [ ] no account balance / risk / target values referenced anywhere
  [ ] trades BOTH directions, or explain why the edge is not just drift
  [ ] NaN/warm-up guarded

Then briefly state: the entry logic, the exit logic, why this should have an
edge beyond drift, and roughly how many trades you expect. Do not claim it is
profitable — the tester decides that.
````

---

## After you run it

Read the two cards, in this order:

1. **STRATEGY EDGE → "Edge vs benchmark"** — if this is near zero, the strategy
   is riding drift, not timing. Nothing else on the page matters yet.
2. **STRATEGY EDGE → "Inverted-strategy expectancy"** — should be clearly
   negative. If flipping BUY/SELL also makes money, the direction logic is noise.
3. **Holdout** — must read CLEAR EDGE, not `NO CLEAR EDGE / EXECUTION-SENSITIVE`.
4. Only then look at **PROP CHALLENGE SIMULATION** for pass odds and how many
   trades/days a challenge would realistically take.

A high pass probability with a failed benchmark or inversion check is **not**
evidence of an edge — it is evidence the instrument moved.

### Feeding results back

To iterate, tell the AI what actually failed, e.g.:

> Edge vs benchmark was +0.004R (long-only bias), holdout +0.012R on 41 trades,
> inverted -0.009R. Fix the directional dependence — the edge is drift, not timing.

That is far more useful than "make it score higher", which just invites
overfitting.
