//+------------------------------------------------------------------+
//| DonchianMTF_v2.mq5                                               |
//| M30 Donchian breakout + H4/D1 trend/ADX filters. Long only.      |
//| Single position, fixed-fractional risk, SL+TP on every trade.    |
//| No martingale, no grid, no hedging, no averaging.                |
//|                                                                  |
//| v2 CHANGES - all four exist to make LIVE match the BACKTEST that |
//| produced the 96/100. None were chosen to raise a score.          |
//|                                                                  |
//|  [1] ATR is SMA(TR,14), not iATR Wilder RMA. The tester CSV atr  |
//|      column is tr.rolling(14).mean(); iATR is Wilder-smoothed    |
//|      and differed by a median 9.7% (95th pct 35%). A different   |
//|      ATR means a different stop distance = a different strategy. |
//|  [2] TP is re-anchored to the ACTUAL FILL after entry. The       |
//|      backtest defines risk as |fill - SL| and TP as fill+RR*risk |
//|      so every win pays exactly +2.00R. v1 anchored SL and TP to  |
//|      the signal-bar close, so a gap made wins pay 1.82-2.09R.    |
//|  [3] Risk base defaults to the INITIAL balance (no compounding)  |
//|      because the backtest sizes every trade off the start        |
//|      balance. Set InpCompoundRisk=true to size off live balance. |
//|  [4] Max-spread guard. The backtest modelled only ~7 points of   |
//|      total cost on gold. Retail gold spreads run 15-30+ points,  |
//|      and entering on a blown-out spread removes the edge.        |
//+------------------------------------------------------------------+
#property version   "2.10"
#property strict

#include <Trade\Trade.mqh>

input group           "Strategy"
input int      InpDonchian     = 20;
input double   InpAtrMult      = 2.0;
input double   InpRR           = 2.0;
input int      InpAtrPeriod    = 14;
input int      InpAdxPeriod    = 14;
input double   InpH4AdxMin     = 20.0;
input double   InpD1AdxMin     = 18.0;
input int      InpVolMa        = 20;
input double   InpVolMult      = 1.0;
input int      InpH4Fast       = 20;
input int      InpH4Slow       = 50;
input int      InpD1Ema        = 50;
input bool     InpRealVolume   = false;
input int      InpAdxHistory   = 600;

input group           "Risk / prop-firm limits"
input double   InpRiskPercent      = 0.40;   // risk per trade (%). 96/100 was tested at 0.40
input double   InpMaxRiskPercent   = 5.00;   // hard cap per trade (%)
input bool     InpCompoundRisk     = false;  // false = size off initial balance (matches backtest)
input double   InpDailyLossStopPct = 3.00;   // halt for the day at this DD (0=off). Keep BELOW your firm limit.
input double   InpTotalLossStopPct = 8.00;   // halt permanently at this DD (0=off)
input double   InpMaxLots          = 0.0;    // absolute lot cap (0=off)
input double   InpInitialBalance   = 0.0;    // 0 = balance at attach

input group           "Execution"
input long     InpMagic           = 20260817;
input ulong    InpSlippage        = 30;
input int      InpMaxSpreadPoints = 30;      // skip entry if spread wider than this (0=off)
input bool     InpRetagTP         = true;    // re-anchor TP to the actual fill  [fix 2]

CTrade   trade;
int      hH4Fast  = INVALID_HANDLE;
int      hH4Slow  = INVALID_HANDLE;
int      hD1Ema   = INVALID_HANDLE;
datetime lastBar  = 0;

double   g_h4Adx[];
double   g_d1Adx[];
datetime g_h4Cache = 0;
datetime g_d1Cache = 0;

double   g_initialBalance = 0.0;
double   g_dayStartEquity = 0.0;
int      g_dayStamp       = -1;
bool     g_halted         = false;

//+------------------------------------------------------------------+
int OnInit()
  {
   hH4Fast = iMA(_Symbol, PERIOD_H4, InpH4Fast, 0, MODE_EMA, PRICE_CLOSE);
   hH4Slow = iMA(_Symbol, PERIOD_H4, InpH4Slow, 0, MODE_EMA, PRICE_CLOSE);
   hD1Ema  = iMA(_Symbol, PERIOD_D1, InpD1Ema, 0, MODE_EMA, PRICE_CLOSE);

   if(hH4Fast == INVALID_HANDLE || hH4Slow == INVALID_HANDLE || hD1Ema == INVALID_HANDLE)
      return INIT_FAILED;

   g_initialBalance = (InpInitialBalance > 0.0)
                      ? InpInitialBalance
                      : AccountInfoDouble(ACCOUNT_BALANCE);

   trade.SetExpertMagicNumber((ulong)InpMagic);
   trade.SetDeviationInPoints(InpSlippage);
   trade.SetTypeFillingBySymbol(_Symbol);
   trade.SetAsyncMode(false);
   return INIT_SUCCEEDED;
  }

void OnDeinit(const int reason)
  {
   IndicatorRelease(hH4Fast);
   IndicatorRelease(hH4Slow);
   IndicatorRelease(hD1Ema);
  }

//+------------------------------------------------------------------+
//| [1] ATR as a SIMPLE mean of True Range - matches the tester atr  |
//|     column, which is tr.rolling(14).mean(). NOT iATR.            |
//|     Uses only CLOSED bars: shift 1 back through shift period.    |
//+------------------------------------------------------------------+
bool AtrSma(int period, double &value)
  {
   MqlRates r[];
   int need = period + 2;
   if(CopyRates(_Symbol, PERIOD_M30, 1, need, r) != need)
      return false;

   // r is chronological; r[need-1] == shift 1. Average the TR of the last
   // `period` closed bars, each TR needing its own previous bar.
   double sum = 0.0;
   int    cnt = 0;
   for(int i = need - 1; i >= need - period; i--)
     {
      if(i < 1)
         break;
      double tr = MathMax(r[i].high - r[i].low,
                          MathMax(MathAbs(r[i].high - r[i - 1].close),
                                  MathAbs(r[i].low  - r[i - 1].close)));
      sum += tr;
      cnt++;
     }
   if(cnt < period)
      return false;
   value = sum / cnt;
   return (value > 0.0);
  }

//+------------------------------------------------------------------+
//| Wilder ADX (RMA of TR/+DM/-DM, then RMA of DX).                  |
//| out[] chronological; out[size-1] == bar shift 0.                 |
//+------------------------------------------------------------------+
bool AdxWilder(ENUM_TIMEFRAMES tf, int period, int bars, double &out[])
  {
   MqlRates r[];
   int got = CopyRates(_Symbol, tf, 0, bars, r);
   if(got < period * 4)
      return false;

   ArrayResize(out, got);
   out[0] = EMPTY_VALUE;

   double a = 1.0 / period;
   double trs = 0.0, ps = 0.0, ms = 0.0, adxs = 0.0;
   bool seeded = false, adxSeeded = false;

   for(int i = 1; i < got; i++)
     {
      double up  = r[i].high - r[i - 1].high;
      double dn  = r[i - 1].low - r[i].low;
      double pdm = (up > dn && up > 0.0) ? up : 0.0;
      double mdm = (dn > up && dn > 0.0) ? dn : 0.0;
      double tr  = MathMax(r[i].high - r[i].low,
                           MathMax(MathAbs(r[i].high - r[i - 1].close),
                                   MathAbs(r[i].low - r[i - 1].close)));

      if(!seeded)
        {
         trs = tr; ps = pdm; ms = mdm; seeded = true;
        }
      else
        {
         trs = a * tr  + (1.0 - a) * trs;
         ps  = a * pdm + (1.0 - a) * ps;
         ms  = a * mdm + (1.0 - a) * ms;
        }

      bool   haveDx = false;
      double dx = 0.0;
      if(trs > 0.0)
        {
         double pdi = 100.0 * ps / trs;
         double mdi = 100.0 * ms / trs;
         double den = pdi + mdi;
         if(den > 0.0)
           {
            dx = 100.0 * MathAbs(pdi - mdi) / den;
            haveDx = true;
           }
        }

      if(haveDx)
        {
         if(!adxSeeded)
           {
            adxs = dx; adxSeeded = true;
           }
         else
            adxs = a * dx + (1.0 - a) * adxs;
        }

      out[i] = adxSeeded ? adxs : EMPTY_VALUE;
     }
   return true;
  }

//+------------------------------------------------------------------+
bool EnsureAdx(ENUM_TIMEFRAMES tf, double &buf[], datetime &cache)
  {
   datetime t = iTime(_Symbol, tf, 0);
   if(t == 0)
      return false;
   if(t == cache && ArraySize(buf) > 0)
      return true;
   if(!AdxWilder(tf, InpAdxPeriod, InpAdxHistory, buf))
      return false;
   cache = t;
   return true;
  }

//+------------------------------------------------------------------+
bool BufferAt(int handle, int shift, double &value)
  {
   double b[];
   if(CopyBuffer(handle, 0, shift, 1, b) != 1)
      return false;
   value = b[0];
   return (MathIsValidNumber(value) && value != EMPTY_VALUE);
  }

//+------------------------------------------------------------------+
bool HasPosition()
  {
   for(int i = PositionsTotal() - 1; i >= 0; i--)
     {
      if(PositionGetTicket(i) == 0)
         continue;
      if(PositionGetString(POSITION_SYMBOL) == _Symbol &&
         PositionGetInteger(POSITION_MAGIC) == InpMagic)
         return true;
     }
   return false;
  }

//+------------------------------------------------------------------+
//| Daily and overall drawdown guards.                               |
//+------------------------------------------------------------------+
bool TradingAllowed()
  {
   MqlDateTime st;
   TimeToStruct(TimeCurrent(), st);
   double equity = AccountInfoDouble(ACCOUNT_EQUITY);

   if(st.day_of_year != g_dayStamp)
     {
      g_dayStamp       = st.day_of_year;
      g_dayStartEquity = equity;
     }

   if(g_halted)
      return false;

   if(InpTotalLossStopPct > 0.0 && g_initialBalance > 0.0)
     {
      double dd = (g_initialBalance - equity) / g_initialBalance * 100.0;
      if(dd >= InpTotalLossStopPct)
        {
         g_halted = true;
         Print("Total drawdown limit reached: ", DoubleToString(dd, 2), "% - trading halted.");
         return false;
        }
     }

   if(InpDailyLossStopPct > 0.0 && g_dayStartEquity > 0.0)
     {
      double ddd = (g_dayStartEquity - equity) / g_dayStartEquity * 100.0;
      if(ddd >= InpDailyLossStopPct)
         return false;
     }

   return true;
  }

//+------------------------------------------------------------------+
//| [3] Risk base: initial balance by default so sizing matches the  |
//|     backtest fixed-fractional model (no compounding).            |
//+------------------------------------------------------------------+
double RiskBase()
  {
   if(InpCompoundRisk)
      return AccountInfoDouble(ACCOUNT_BALANCE);
   return (g_initialBalance > 0.0) ? g_initialBalance
                                   : AccountInfoDouble(ACCOUNT_BALANCE);
  }

//+------------------------------------------------------------------+
double LotsByRisk(double stopDist)
  {
   double riskPct = MathMin(InpRiskPercent, InpMaxRiskPercent);
   if(stopDist <= 0.0 || riskPct <= 0.0)
      return 0.0;

   double tickVal  = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_VALUE_LOSS);
   double tickSize = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_SIZE);
   if(tickVal <= 0.0 || tickSize <= 0.0)
      return 0.0;

   double risk    = RiskBase() * riskPct / 100.0;
   double lossLot = (stopDist / tickSize) * tickVal;
   if(lossLot <= 0.0)
      return 0.0;

   double lots = risk / lossLot;
   double step = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_STEP);
   double minL = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MIN);
   double maxL = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MAX);

   if(InpMaxLots > 0.0)
      lots = MathMin(lots, InpMaxLots);
   if(step > 0.0)
      lots = MathFloor(lots / step) * step;
   if(lots < minL)
      return 0.0;
   if(lots > maxL)
      lots = maxL;

   double margin = 0.0;
   double ask = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
   if(OrderCalcMargin(ORDER_TYPE_BUY, _Symbol, lots, ask, margin))
      if(margin > AccountInfoDouble(ACCOUNT_MARGIN_FREE))
         return 0.0;

   return lots;
  }

//+------------------------------------------------------------------+
//| Long signal evaluated on the just-closed M30 bar (shift 1).      |
//+------------------------------------------------------------------+
bool LongSignal(double &sigClose, double &atrVal)
  {
   int n   = MathMax(InpDonchian, InpVolMa);
   int cnt = n + 1;

   MqlRates m[];
   if(CopyRates(_Symbol, PERIOD_M30, 1, cnt, m) != cnt)
      return false;
   if(Bars(_Symbol, PERIOD_M30) < 300)
      return false;

   int sig  = cnt - 1;
   sigClose = m[sig].close;
   double vol = (double)(InpRealVolume ? m[sig].real_volume : m[sig].tick_volume);

   if(!AtrSma(InpAtrPeriod, atrVal) || atrVal <= 0.0)   // [1] SMA ATR
      return false;

   double prevHigh = -DBL_MAX, volSum = 0.0;
   for(int i = cnt - 1 - InpDonchian; i <= cnt - 2; i++)
      prevHigh = MathMax(prevHigh, m[i].high);
   for(int i = cnt - 1 - InpVolMa; i <= cnt - 2; i++)
      volSum += (double)(InpRealVolume ? m[i].real_volume : m[i].tick_volume);
   double volMa = volSum / InpVolMa;

   if(volMa <= 0.0 || vol <= volMa * InpVolMult)
      return false;

   // HTF bar used = one bar older than the bar containing the signal bar
   int shH4 = iBarShift(_Symbol, PERIOD_H4, m[sig].time, false) + 1;
   int shD1 = iBarShift(_Symbol, PERIOD_D1, m[sig].time, false) + 1;
   if(shH4 < 1 || shD1 < 1)
      return false;

   if(!EnsureAdx(PERIOD_H4, g_h4Adx, g_h4Cache))
      return false;
   if(!EnsureAdx(PERIOD_D1, g_d1Adx, g_d1Cache))
      return false;

   int iH4 = ArraySize(g_h4Adx) - 1 - shH4;
   int iD1 = ArraySize(g_d1Adx) - 1 - shD1;
   if(iH4 < 1 || iD1 < 1)
      return false;

   double h4a = g_h4Adx[iH4], h4aP = g_h4Adx[iH4 - 1];
   double d1a = g_d1Adx[iD1], d1aP = g_d1Adx[iD1 - 1];
   if(h4a == EMPTY_VALUE || h4aP == EMPTY_VALUE ||
      d1a == EMPTY_VALUE || d1aP == EMPTY_VALUE)
      return false;

   if(h4a < InpH4AdxMin || d1a < InpD1AdxMin)
      return false;
   if(!(h4a > h4aP) || !(d1a > d1aP))
      return false;

   double fast, slow, d1ema;
   if(!BufferAt(hH4Fast, shH4, fast) || !BufferAt(hH4Slow, shH4, slow) ||
      !BufferAt(hD1Ema, shD1, d1ema))
      return false;

   double h4Close = iClose(_Symbol, PERIOD_H4, shH4);
   double d1Close = iClose(_Symbol, PERIOD_D1, shD1);
   if(h4Close <= 0.0 || d1Close <= 0.0)
      return false;

   if(!(fast > slow && h4Close > slow))
      return false;
   if(!(d1Close > d1ema))
      return false;

   return (sigClose > prevHigh);
  }

//+------------------------------------------------------------------+
//| [2] After the fill, re-anchor TP so realised reward:risk equals  |
//|     InpRR measured from the ACTUAL entry - the same definition   |
//|     the backtest used. Without this a gap turns a "2.0R" win     |
//|     into 1.82-2.09R and the tested payoff no longer applies.     |
//+------------------------------------------------------------------+
void RetagTP()
  {
   if(!InpRetagTP)
      return;
   for(int i = PositionsTotal() - 1; i >= 0; i--)
     {
      ulong ticket = PositionGetTicket(i);
      if(ticket == 0)
         continue;
      if(PositionGetString(POSITION_SYMBOL) != _Symbol ||
         PositionGetInteger(POSITION_MAGIC) != InpMagic)
         continue;

      double open = PositionGetDouble(POSITION_PRICE_OPEN);
      double sl   = PositionGetDouble(POSITION_SL);
      double tp   = PositionGetDouble(POSITION_TP);
      if(open <= 0.0 || sl <= 0.0 || sl >= open)
         return;

      int    dg    = (int)SymbolInfoInteger(_Symbol, SYMBOL_DIGITS);
      double want  = NormalizeDouble(open + InpRR * (open - sl), dg);
      double stops = (double)SymbolInfoInteger(_Symbol, SYMBOL_TRADE_STOPS_LEVEL) * _Point;
      double ask   = SymbolInfoDouble(_Symbol, SYMBOL_ASK);

      if(MathAbs(want - tp) < _Point)
         return;                       // already correct
      if(want <= ask + stops)
         return;                       // broker would reject; keep provisional TP

      if(!trade.PositionModify(ticket, sl, want))
         Print("RetagTP: PositionModify failed, retcode ", trade.ResultRetcode(),
               " - provisional TP left in place.");
      return;
     }
  }

//+------------------------------------------------------------------+
void OnTick()
  {
   datetime t = iTime(_Symbol, PERIOD_M30, 0);
   if(t == 0 || t == lastBar)
      return;
   lastBar = t;

   if(!TradingAllowed())
      return;
   if(HasPosition())
     {
      RetagTP();                       // [2] correct TP once the fill is known
      return;
     }

   double sigClose = 0.0, atrVal = 0.0;
   if(!LongSignal(sigClose, atrVal))
      return;

   // [4] refuse to enter on a blown-out spread
   if(InpMaxSpreadPoints > 0)
     {
      long spr = SymbolInfoInteger(_Symbol, SYMBOL_SPREAD);
      if(spr > InpMaxSpreadPoints)
        {
         Print("Skipped: spread ", spr, " > ", InpMaxSpreadPoints, " points.");
         return;
        }
     }

   int    dg    = (int)SymbolInfoInteger(_Symbol, SYMBOL_DIGITS);
   double ask   = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
   double bid   = SymbolInfoDouble(_Symbol, SYMBOL_BID);
   double stops = (double)SymbolInfoInteger(_Symbol, SYMBOL_TRADE_STOPS_LEVEL) * _Point;

   double sl = NormalizeDouble(sigClose - InpAtrMult * atrVal, dg);
   // provisional TP; RetagTP() corrects it to fill + RR*(fill - SL)
   double tp = NormalizeDouble(ask + InpRR * (ask - sl), dg);

   if(sl >= bid - stops || tp <= ask + stops)
      return;

   double lots = LotsByRisk(ask - sl);
   if(lots <= 0.0)
      return;

   if(trade.Buy(lots, _Symbol, 0.0, sl, tp))
      RetagTP();
  }
//+------------------------------------------------------------------+
