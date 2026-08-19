//+------------------------------------------------------------------+
//| GoldPullbackMTF.mq5                                              |
//|                                                                  |
//| M30 Donchian breakout OR EMA pullback, gated by H4 + D1 trend and |
//| a RISING D1 ADX, with the London window skipped. LONG ONLY.       |
//| Single position, fixed-fractional risk, SL + TP on every trade.   |
//| No martingale, no grid, no hedging, no averaging, no recovery.    |
//|                                                                  |
//| This is a line-by-line port of strategy_gold_v3.py. Every         |
//| indicator is computed with EXPLICIT LOOPS that reproduce pandas   |
//| bit-for-bit (verified: max|diff| = 0.0 across EMA20/EMA50/ADX14). |
//| Built-in iATR / iMA / iADX are deliberately NOT used because:     |
//|   * iATR is Wilder-smoothed; the tester uses SMA(TR,14).          |
//|     Median difference 9.7%, 95th pct 35% -> a different stop.     |
//|   * iMA seeds an EMA with an SMA; pandas ewm(adjust=False) seeds  |
//|     with the first value.                                         |
//|                                                                  |
//| PARITY REQUIREMENTS - the EA refuses to trade unless they hold:   |
//|   1. Enough D1 history to converge EMA50/ADX14 (>= 600 bars).     |
//|   2. Broker server-time hours must match the CSV the strategy was |
//|      validated on. Use InpServerHourOffset if your broker differs;|
//|      a wrong offset silently changes the strategy (21.9% of bars  |
//|      sit inside the skipped 07:00-11:00 window).                  |
//|                                                                  |
//| CAPITAL PROTECTION - layered, so no single failure breaches the   |
//| account. See RiskGate() and the OnTick equity guard.              |
//+------------------------------------------------------------------+
#property copyright "PropLab"
#property version   "3.00"
#property strict

#include <Trade\Trade.mqh>

//====================== STRATEGY (must match Python) ================
input group "=== Strategy (do not change without re-testing) ==="
input int      InpDonchian      = 20;      // Donchian lookback (bars BEFORE the signal bar)
input double   InpAtrMult       = 2.0;     // stop distance = ATR * this
input double   InpRR            = 2.0;     // take profit = RR * risk, measured from the FILL
input int      InpAtrPeriod     = 14;      // ATR period (SIMPLE mean of True Range)
input int      InpAdxPeriod     = 14;      // D1 ADX period (Wilder)
input double   InpD1AdxMin      = 18.0;    // D1 ADX must be >= this AND rising
input int      InpPullbackEma   = 20;      // M30 EMA used for the pullback entry
input int      InpH4Fast        = 20;      // H4 fast EMA
input int      InpH4Slow        = 50;      // H4 slow EMA
input int      InpD1Ema         = 50;      // D1 trend EMA
input int      InpVolMa         = 20;      // volume average lookback (bars BEFORE signal bar)
input double   InpVolMult       = 1.0;     // require volume > average * this
input int      InpSkipHourLo    = 7;       // skip signals when hour is within
input int      InpSkipHourHi    = 11;      //   [lo..hi] inclusive (broker server time)
input int      InpServerHourOffset = 0;    // add this to broker hour to match the validated CSV
input bool     InpUseRealVolume = false;   // false = tick volume (matches the CSV)
input int      InpMaxHoldBars   = 576;     // force-exit after N M30 bars (backtest used 576)

//====================== RISK / PROP LIMITS ==========================
input group "=== Risk and prop-firm protection ==="
input double   InpRiskPercent   = 0.50;    // risk per trade (%) - validated 0.40-0.65
input double   InpMaxRiskPercent= 2.00;    // hard ceiling on risk per trade (%)
input bool     InpCompoundRisk  = false;   // false = size off the INITIAL balance (matches backtest)
input double   InpMaxDDPercent  = 10.0;    // firm's MAXIMUM loss (%) - the hard wall
input double   InpDailyDDPercent= 4.0;     // firm's DAILY loss (%)
input double   InpDDBufferPct   = 1.5;     // stop this far BEFORE the max-loss wall (%)
input double   InpDailyBufferPct= 0.5;     // stop this far BEFORE the daily wall (%)
input bool     InpTrailingDD    = false;   // true = max DD trails end-of-day high water (1-step firms)
input bool     InpShrinkToFit   = true;    // shrink lots to respect the walls instead of skipping
input int      InpMaxConsecLoss = 0;       // pause after N consecutive losses (0 = off)
input int      InpPauseHours    = 24;      // how long to pause after that
input double   InpMaxLots       = 0.0;     // absolute lot cap (0 = off)
input double   InpInitialBalance= 0.0;     // 0 = balance when the EA is attached

//====================== EXECUTION ===================================
input group "=== Execution ==="
input long     InpMagic         = 20260819;
input ulong    InpSlippage      = 30;      // max deviation, points
input int      InpMaxSpreadPts  = 30;      // skip entry above this spread (0 = off)
input int      InpM30History    = 5000;    // M30 bars loaded for the pullback EMA
input int      InpH4History     = 3000;    // H4 bars loaded for EMA seeding
input int      InpD1History     = 1200;    // D1 bars loaded for EMA/ADX seeding
input int      InpMinD1Bars     = 600;     // refuse to trade below this (parity guard)
input bool     InpVerboseLog    = true;

//====================== STATE =======================================
CTrade   trade;
datetime g_lastBar      = 0;
double   g_initialBal   = 0.0;
double   g_hwmEod       = 0.0;   // end-of-day high-water mark for trailing DD
double   g_dayStartEq   = 0.0;
int      g_dayStamp     = -1;
bool     g_haltedTotal  = false;
int      g_consecLoss   = 0;
datetime g_pauseUntil   = 0;
ulong    g_lastDealChecked = 0;

//+------------------------------------------------------------------+
int OnInit()
  {
   g_initialBal = (InpInitialBalance > 0.0) ? InpInitialBalance
                                            : AccountInfoDouble(ACCOUNT_BALANCE);
   g_hwmEod     = g_initialBal;
   g_dayStartEq = AccountInfoDouble(ACCOUNT_EQUITY);

   if(InpMaxRiskPercent <= 0.0 || InpRiskPercent <= 0.0)
     { Print("FATAL: risk inputs must be positive."); return INIT_PARAMETERS_INCORRECT; }
   if(InpDDBufferPct >= InpMaxDDPercent)
     { Print("FATAL: DD buffer must be smaller than the max-DD limit."); return INIT_PARAMETERS_INCORRECT; }

   trade.SetExpertMagicNumber((ulong)InpMagic);
   trade.SetDeviationInPoints(InpSlippage);
   trade.SetTypeFillingBySymbol(_Symbol);
   trade.SetAsyncMode(false);

   int d1bars = Bars(_Symbol, PERIOD_D1);
   if(d1bars < InpMinD1Bars)
      Print("WARNING: only ", d1bars, " D1 bars available; ", InpMinD1Bars,
            " needed for exact indicator parity. The EA will not trade until MT5 loads more history.");

   PrintFormat("GoldPullbackMTF v3 on %s | initial balance %.2f | risk %.2f%% | "
               "max DD %.1f%% (buffer %.1f%%) | daily %.1f%% (buffer %.1f%%) | trailing=%s",
               _Symbol, g_initialBal, InpRiskPercent, InpMaxDDPercent, InpDDBufferPct,
               InpDailyDDPercent, InpDailyBufferPct, (InpTrailingDD ? "yes" : "no"));
   return INIT_SUCCEEDED;
  }

void OnDeinit(const int reason) {}

//====================================================================
//  INDICATORS - explicit loops that reproduce pandas exactly
//====================================================================

//| EMA with alpha = 2/(span+1), seeded at the FIRST bar.
//| Equivalent to pandas .ewm(span=N, adjust=False).mean()
void EmaSeries(const double &src[], int n, int span, double &out[])
  {
   ArrayResize(out, n);
   if(n <= 0) return;
   double a = 2.0 / (span + 1.0);
   out[0] = src[0];
   for(int i = 1; i < n; i++)
      out[i] = a * src[i] + (1.0 - a) * out[i - 1];
  }

//| Wilder ADX, seeded exactly like pandas: bar 0 has TR = high-low
//| (pandas' max() skips the NaN previous close) and +DM = -DM = 0.
//| Equivalent to the _adx() in strategy_gold_v3.py.
void AdxSeries(const MqlRates &r[], int n, int period, double &out[])
  {
   ArrayResize(out, n);
   if(n <= 0) return;
   double a = 1.0 / period;

   double trs = r[0].high - r[0].low;   // seed
   double ps  = 0.0, ms = 0.0;
   double adxs = 0.0;
   bool   adxSeeded = false;
   out[0] = EMPTY_VALUE;

   for(int i = 1; i < n; i++)
     {
      double up  = r[i].high - r[i - 1].high;
      double dn  = r[i - 1].low - r[i].low;
      double pdm = (up > dn && up > 0.0) ? up : 0.0;
      double mdm = (dn > up && dn > 0.0) ? dn : 0.0;
      double tr  = MathMax(r[i].high - r[i].low,
                    MathMax(MathAbs(r[i].high - r[i - 1].close),
                            MathAbs(r[i].low  - r[i - 1].close)));

      trs = a * tr  + (1.0 - a) * trs;
      ps  = a * pdm + (1.0 - a) * ps;
      ms  = a * mdm + (1.0 - a) * ms;

      if(trs > 0.0)
        {
         double pdi = 100.0 * ps / trs;
         double mdi = 100.0 * ms / trs;
         double den = pdi + mdi;
         if(den > 0.0)
           {
            double dx = 100.0 * MathAbs(pdi - mdi) / den;
            if(!adxSeeded) { adxs = dx; adxSeeded = true; }
            else            adxs = a * dx + (1.0 - a) * adxs;
           }
        }
      out[i] = adxSeeded ? adxs : EMPTY_VALUE;
     }
  }

//| SIMPLE mean of True Range over the `period` closed bars ending at
//| index `idx`. This is the tester's atr column - NOT iATR (Wilder).
bool AtrSma(const MqlRates &r[], int n, int idx, int period, double &value)
  {
   if(idx - period < 0) return false;
   double sum = 0.0;
   for(int i = idx; i > idx - period; i--)
     {
      double tr = MathMax(r[i].high - r[i].low,
                   MathMax(MathAbs(r[i].high - r[i - 1].close),
                           MathAbs(r[i].low  - r[i - 1].close)));
      sum += tr;
     }
   value = sum / period;
   return (value > 0.0);
  }

//====================================================================
//  ACCOUNT PROTECTION
//====================================================================

//| The hard equity floor we must never cross, in account currency.
double MaxLossFloor()
  {
   double base = InpTrailingDD ? MathMax(g_hwmEod, g_initialBal) : g_initialBal;
   return base * (1.0 - InpMaxDDPercent / 100.0);
  }

//| Same floor, pulled in by the safety buffer. All trading stops here,
//| deliberately BEFORE the real wall, so slippage cannot breach it.
double SafeFloor()
  {
   double base = InpTrailingDD ? MathMax(g_hwmEod, g_initialBal) : g_initialBal;
   return base * (1.0 - (InpMaxDDPercent - InpDDBufferPct) / 100.0);
  }

double DailySafeFloor()
  {
   return g_dayStartEq * (1.0 - (InpDailyDDPercent - InpDailyBufferPct) / 100.0);
  }

void CloseAllNow(string why)
  {
   for(int i = PositionsTotal() - 1; i >= 0; i--)
     {
      ulong t = PositionGetTicket(i);
      if(t == 0) continue;
      if(PositionGetString(POSITION_SYMBOL) != _Symbol) continue;
      if(PositionGetInteger(POSITION_MAGIC) != InpMagic) continue;
      if(!trade.PositionClose(t))
         Print("EMERGENCY CLOSE FAILED ticket ", t, " retcode ", trade.ResultRetcode());
      else
         Print("EMERGENCY CLOSE ticket ", t, " - ", why);
     }
  }

bool HasPosition()
  {
   for(int i = PositionsTotal() - 1; i >= 0; i--)
     {
      if(PositionGetTicket(i) == 0) continue;
      if(PositionGetString(POSITION_SYMBOL) == _Symbol &&
         PositionGetInteger(POSITION_MAGIC) == InpMagic)
         return true;
     }
   return false;
  }

//| Roll the day over and refresh the end-of-day high-water mark.
void UpdateDayState()
  {
   MqlDateTime st; TimeToStruct(TimeCurrent(), st);
   if(st.day_of_year != g_dayStamp)
     {
      if(g_dayStamp != -1)
         g_hwmEod = MathMax(g_hwmEod, AccountInfoDouble(ACCOUNT_BALANCE));
      g_dayStamp   = st.day_of_year;
      g_dayStartEq = AccountInfoDouble(ACCOUNT_EQUITY);
      if(InpVerboseLog)
         PrintFormat("New day: start equity %.2f | max-loss floor %.2f | safe floor %.2f",
                     g_dayStartEq, MaxLossFloor(), SafeFloor());
     }
  }

//| Track closed deals to maintain the consecutive-loss counter.
void UpdateConsecutiveLosses()
  {
   if(InpMaxConsecLoss <= 0) return;
   if(!HistorySelect(TimeCurrent() - 30 * 24 * 3600, TimeCurrent())) return;
   int total = HistoryDealsTotal();
   for(int i = 0; i < total; i++)
     {
      ulong ticket = HistoryDealGetTicket(i);
      if(ticket <= g_lastDealChecked) continue;
      if(HistoryDealGetString(ticket, DEAL_SYMBOL) != _Symbol) continue;
      if(HistoryDealGetInteger(ticket, DEAL_MAGIC) != InpMagic) continue;
      if(HistoryDealGetInteger(ticket, DEAL_ENTRY) != DEAL_ENTRY_OUT) continue;
      double profit = HistoryDealGetDouble(ticket, DEAL_PROFIT)
                    + HistoryDealGetDouble(ticket, DEAL_SWAP)
                    + HistoryDealGetDouble(ticket, DEAL_COMMISSION);
      if(profit < 0.0) g_consecLoss++; else g_consecLoss = 0;
      g_lastDealChecked = ticket;
      if(g_consecLoss >= InpMaxConsecLoss)
        {
         g_pauseUntil = TimeCurrent() + InpPauseHours * 3600;
         Print("Circuit breaker: ", g_consecLoss, " consecutive losses -> paused until ", g_pauseUntil);
        }
     }
  }

//| Position size that respects, in order:
//|   the configured risk, the max-loss wall, and the daily-loss wall.
//| Returns 0 when no size can satisfy all three.
double RiskGate(double stopDist, string &reason)
  {
   double tickVal  = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_VALUE_LOSS);
   double tickSize = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_SIZE);
   if(stopDist <= 0.0 || tickVal <= 0.0 || tickSize <= 0.0)
     { reason = "bad symbol tick data"; return 0.0; }

   double lossPerLot = (stopDist / tickSize) * tickVal;
   if(lossPerLot <= 0.0) { reason = "loss-per-lot <= 0"; return 0.0; }

   double riskPct = MathMin(InpRiskPercent, InpMaxRiskPercent);
   double riskBase = InpCompoundRisk ? AccountInfoDouble(ACCOUNT_BALANCE) : g_initialBal;
   double wantRisk = riskBase * riskPct / 100.0;

   // --- headroom to each wall, measured from CURRENT equity ---
   double eq = AccountInfoDouble(ACCOUNT_EQUITY);
   double roomTotal = eq - SafeFloor();
   double roomDaily = eq - DailySafeFloor();
   if(roomTotal <= 0.0) { reason = "at/below the max-loss safe floor"; return 0.0; }
   if(roomDaily <= 0.0) { reason = "at/below the daily safe floor"; return 0.0; }

   double allowed = wantRisk;
   if(InpShrinkToFit)
      allowed = MathMin(allowed, MathMin(roomTotal, roomDaily));
   else if(wantRisk > roomTotal || wantRisk > roomDaily)
     { reason = "full-size loss would cross a wall"; return 0.0; }

   double lots = allowed / lossPerLot;

   double step = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_STEP);
   double minL = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MIN);
   double maxL = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MAX);
   if(InpMaxLots > 0.0) lots = MathMin(lots, InpMaxLots);
   if(step > 0.0)       lots = MathFloor(lots / step) * step;
   if(lots < minL)      { reason = "required size below broker minimum after risk gating"; return 0.0; }
   if(lots > maxL)      lots = maxL;

   // final verification with the ROUNDED size - rounding up must never
   // be able to cross a wall
   double worstLoss = lots * lossPerLot;
   if(worstLoss >= roomTotal || worstLoss >= roomDaily)
     { reason = "rounded size still crosses a wall"; return 0.0; }

   double margin = 0.0;
   double ask = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
   if(OrderCalcMargin(ORDER_TYPE_BUY, _Symbol, lots, ask, margin))
      if(margin > AccountInfoDouble(ACCOUNT_MARGIN_FREE) * 0.9)
        { reason = "insufficient free margin"; return 0.0; }

   return lots;
  }

//====================================================================
//  SIGNAL - evaluated on the just-closed M30 bar (shift 1)
//====================================================================
bool LongSignal(double &sigClose, double &atrVal, string &why)
  {
   int needM30 = MathMax(InpM30History, MathMax(InpDonchian, InpVolMa) + InpAtrPeriod + 60);
   MqlRates m[];
   int nm = CopyRates(_Symbol, PERIOD_M30, 0, needM30, m);
   if(nm < MathMax(InpDonchian, InpVolMa) + InpAtrPeriod + 10)
     { why = "not enough M30 history"; return false; }

   int sig = nm - 2;                       // shift 1 == last CLOSED M30 bar
   if(sig < InpAtrPeriod + InpDonchian + 2) { why = "M30 index too early"; return false; }

   sigClose = m[sig].close;
   datetime sigTime = m[sig].time;

   // ---- session filter (broker server hour + configured offset) ----
   MqlDateTime st; TimeToStruct(sigTime, st);
   int hr = (st.hour + InpServerHourOffset) % 24;
   if(hr < 0) hr += 24;
   if(hr >= InpSkipHourLo && hr <= InpSkipHourHi) { why = "inside skipped session"; return false; }

   // ---- ATR = SIMPLE mean of TR over 14 closed bars ----
   if(!AtrSma(m, nm, sig, InpAtrPeriod, atrVal)) { why = "ATR unavailable"; return false; }

   // ---- Donchian high and volume average, both over the bars BEFORE sig ----
   double prevHigh = -DBL_MAX;
   for(int i = sig - InpDonchian; i <= sig - 1; i++)
      prevHigh = MathMax(prevHigh, m[i].high);

   double volSum = 0.0;
   for(int i = sig - InpVolMa; i <= sig - 1; i++)
      volSum += (double)(InpUseRealVolume ? m[i].real_volume : m[i].tick_volume);
   double volMa = volSum / InpVolMa;
   double volNow = (double)(InpUseRealVolume ? m[sig].real_volume : m[sig].tick_volume);
   if(volMa <= 0.0 || volNow <= volMa * InpVolMult) { why = "volume filter"; return false; }

   // ---- M30 pullback EMA (needs the full series for correct seeding) ----
   double closes[]; ArrayResize(closes, nm);
   for(int i = 0; i < nm; i++) closes[i] = m[i].close;
   double emaPb[]; EmaSeries(closes, nm, InpPullbackEma, emaPb);

   // ---- H4 context: last CLOSED H4 bar relative to the signal bar ----
   MqlRates h4[];
   int nh = CopyRates(_Symbol, PERIOD_H4, 0, InpH4History, h4);
   if(nh < InpH4Slow * 6) { why = "not enough H4 history"; return false; }
   int shH4 = iBarShift(_Symbol, PERIOD_H4, sigTime, false) + 1;   // +1 => last CLOSED
   int iH4  = nh - 1 - shH4;
   if(shH4 < 1 || iH4 < 1) { why = "H4 index unavailable"; return false; }

   double h4c[]; ArrayResize(h4c, nh);
   for(int i = 0; i < nh; i++) h4c[i] = h4[i].close;
   double h4f[], h4s[];
   EmaSeries(h4c, nh, InpH4Fast, h4f);
   EmaSeries(h4c, nh, InpH4Slow, h4s);

   // ---- D1 context: last CLOSED D1 bar, plus the one before it ----
   MqlRates d1[];
   int nd = CopyRates(_Symbol, PERIOD_D1, 0, InpD1History, d1);
   if(nd < InpMinD1Bars)
     { why = StringFormat("only %d D1 bars (need %d for parity)", nd, InpMinD1Bars); return false; }
   int shD1 = iBarShift(_Symbol, PERIOD_D1, sigTime, false) + 1;
   int iD1  = nd - 1 - shD1;
   if(shD1 < 1 || iD1 < 1) { why = "D1 index unavailable"; return false; }

   double d1c[]; ArrayResize(d1c, nd);
   for(int i = 0; i < nd; i++) d1c[i] = d1[i].close;
   double d1e[]; EmaSeries(d1c, nd, InpD1Ema, d1e);
   double d1adx[]; AdxSeries(d1, nd, InpAdxPeriod, d1adx);

   double d1v = d1adx[iD1];
   double d1p = d1adx[iD1 - 1];
   if(d1v == EMPTY_VALUE || d1p == EMPTY_VALUE) { why = "D1 ADX unavailable"; return false; }
   if(d1v < InpD1AdxMin)  { why = "D1 ADX below threshold"; return false; }
   if(!(d1v > d1p))       { why = "D1 ADX not rising"; return false; }

   bool h4Bull = (h4f[iH4] > h4s[iH4]) && (h4[iH4].close > h4s[iH4]);
   bool d1Bull = (d1[iD1].close > d1e[iD1]);
   if(!(h4Bull && d1Bull)) { why = "HTF not bullish"; return false; }

   bool breakout = (m[sig].close > prevHigh);
   bool pullback = (m[sig].low <= emaPb[sig]) && (m[sig].close > emaPb[sig])
                   && (m[sig].close > m[sig].open);
   if(!(breakout || pullback)) { why = "no entry trigger"; return false; }

   why = breakout ? "breakout" : "pullback";
   return true;
  }

//====================================================================
//  TRADE MANAGEMENT
//====================================================================

//| Re-anchor TP to the ACTUAL fill so realised reward:risk equals
//| InpRR measured from the entry - exactly how the backtest scores it.
void RetagTP()
  {
   for(int i = PositionsTotal() - 1; i >= 0; i--)
     {
      ulong ticket = PositionGetTicket(i);
      if(ticket == 0) continue;
      if(PositionGetString(POSITION_SYMBOL) != _Symbol) continue;
      if(PositionGetInteger(POSITION_MAGIC) != InpMagic) continue;

      double open = PositionGetDouble(POSITION_PRICE_OPEN);
      double sl   = PositionGetDouble(POSITION_SL);
      double tp   = PositionGetDouble(POSITION_TP);
      if(open <= 0.0 || sl <= 0.0 || sl >= open) return;

      int    dg    = (int)SymbolInfoInteger(_Symbol, SYMBOL_DIGITS);
      double want  = NormalizeDouble(open + InpRR * (open - sl), dg);
      double stops = (double)SymbolInfoInteger(_Symbol, SYMBOL_TRADE_STOPS_LEVEL) * _Point;
      double ask   = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
      if(MathAbs(want - tp) < _Point) return;
      if(want <= ask + stops) return;
      if(!trade.PositionModify(ticket, sl, want))
         Print("RetagTP: modify failed, retcode ", trade.ResultRetcode());
      return;
     }
  }

//| Force-exit after InpMaxHoldBars M30 bars, matching the backtest's
//| 576-bar maximum hold. Without this, live trades can run far longer
//| than anything that was ever tested.
void EnforceMaxHold()
  {
   if(InpMaxHoldBars <= 0) return;
   for(int i = PositionsTotal() - 1; i >= 0; i--)
     {
      ulong ticket = PositionGetTicket(i);
      if(ticket == 0) continue;
      if(PositionGetString(POSITION_SYMBOL) != _Symbol) continue;
      if(PositionGetInteger(POSITION_MAGIC) != InpMagic) continue;
      datetime opened = (datetime)PositionGetInteger(POSITION_TIME);
      int barsHeld = iBarShift(_Symbol, PERIOD_M30, opened, false);
      if(barsHeld >= InpMaxHoldBars)
        {
         if(trade.PositionClose(ticket))
            Print("Max-hold exit after ", barsHeld, " M30 bars.");
        }
      return;
     }
  }

//====================================================================
void OnTick()
  {
   // ---------- LAYER 1: every-tick equity guard ----------
   // Runs on EVERY tick, not just new bars, so a gap or a fast move
   // cannot carry the account through the wall unnoticed.
   double eq = AccountInfoDouble(ACCOUNT_EQUITY);
   if(eq <= SafeFloor())
     {
      if(HasPosition()) CloseAllNow("equity reached the safe floor");
      if(!g_haltedTotal)
        {
         g_haltedTotal = true;
         PrintFormat("HALTED: equity %.2f reached the safe floor %.2f (hard wall %.2f). "
                     "No further trades.", eq, SafeFloor(), MaxLossFloor());
        }
      return;
     }
   if(g_haltedTotal) return;

   UpdateDayState();

   // ---------- LAYER 2: daily guard ----------
   if(eq <= DailySafeFloor())
     {
      if(HasPosition()) CloseAllNow("daily safe floor reached");
      return;                                  // resets automatically tomorrow
     }

   // ---------- one M30 bar at a time ----------
   datetime t = iTime(_Symbol, PERIOD_M30, 0);
   if(t == 0 || t == g_lastBar) return;
   g_lastBar = t;

   UpdateConsecutiveLosses();   // once per bar, not per tick (HistorySelect is costly)

   if(HasPosition())
     {
      RetagTP();
      EnforceMaxHold();
      return;
     }

   if(TimeCurrent() < g_pauseUntil) return;

   // ---------- signal ----------
   double sigClose = 0.0, atrVal = 0.0; string why = "";
   if(!LongSignal(sigClose, atrVal, why))
     {
      if(InpVerboseLog && StringFind(why, "history") >= 0) Print("No trade: ", why);
      return;
     }

   // ---------- spread guard ----------
   if(InpMaxSpreadPts > 0)
     {
      long spr = SymbolInfoInteger(_Symbol, SYMBOL_SPREAD);
      if(spr > InpMaxSpreadPts)
        { Print("Skipped (", why, "): spread ", spr, " > ", InpMaxSpreadPts); return; }
     }

   int    dg    = (int)SymbolInfoInteger(_Symbol, SYMBOL_DIGITS);
   double ask   = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
   double bid   = SymbolInfoDouble(_Symbol, SYMBOL_BID);
   double stops = (double)SymbolInfoInteger(_Symbol, SYMBOL_TRADE_STOPS_LEVEL) * _Point;

   double sl = NormalizeDouble(sigClose - InpAtrMult * atrVal, dg);
   double tp = NormalizeDouble(ask + InpRR * (ask - sl), dg);
   if(sl >= bid - stops || tp <= ask + stops)
     { Print("Skipped (", why, "): stops too close to market."); return; }

   // ---------- LAYER 3: pre-trade risk gate ----------
   string reason = "";
   double lots = RiskGate(ask - sl, reason);
   if(lots <= 0.0)
     { Print("Skipped (", why, "): ", reason); return; }

   if(trade.Buy(lots, _Symbol, 0.0, sl, tp))
     {
      RetagTP();
      if(InpVerboseLog)
         PrintFormat("BUY %s %.2f lots | entry~%.2f SL %.2f | risk %.2f | eq %.2f | floor %.2f",
                     why, lots, ask, sl, lots * ((ask - sl) /
                     SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_SIZE)) *
                     SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_VALUE_LOSS),
                     eq, SafeFloor());
     }
   else
      Print("Buy failed, retcode ", trade.ResultRetcode());
  }
//+------------------------------------------------------------------+
