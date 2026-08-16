//+------------------------------------------------------------------+
//|                                                  NYSession_EA.mq5 |
//|    New York session range-breakout, anchored to Pakistan clock    |
//|    XAUUSD + EURUSD  |  governed by PropShield                     |
//+------------------------------------------------------------------+
//  VALIDATION STATUS — READ BEFORE USING
//  ------------------------------------------------------------------
//  Tested on 2020-01-02..2023-12-31 (development split), 12 pre-
//  registered variants, modelled costs (spread + 2x slippage):
//
//     XAUUSD : positive in  6/12 variants, best expR +0.0278R
//     EURUSD : positive in  0/12 variants, best expR -0.0552R
//     Combined: 0/12 variants positive.  Best t-stat -0.55.
//
//  No variant reached statistical significance (t > 3.0 required
//  after 93 project trials). EURUSD is therefore DISABLED BY DEFAULT
//  because every tested configuration lost money on it.
//
//  This EA is a FORWARD-TEST INSTRUMENT, not a validated edge.
//  Run it on DEMO. Its purpose is to collect out-of-sample evidence.
//+------------------------------------------------------------------+
#property copyright "PropLab"
#property version   "1.00"
#property strict

#include <PropShield.mqh>

//--- session anchor ------------------------------------------------
input group           "=== Session anchor (Pakistan clock) ==="
input int             InpPakHour        = 19;    // Pakistan hour (PKT = UTC+5, no DST)
input int             InpPakMinute      = 30;    // Pakistan minute
input int             InpTriggerBars    = 8;     // bars after anchor to allow a break (8 = 4h)

//--- range / entry -------------------------------------------------
input group           "=== Range & entry ==="
input int             InpRangeBars      = 2;     // bars forming the pre-open range
input double          InpStopATR        = 1.5;   // stop = N x ATR
input double          InpRR             = 2.0;   // target = N x risk
input int             InpATRPeriod      = 14;
input int             InpMaxHoldBars    = 32;    // time stop

//--- symbols -------------------------------------------------------
input group           "=== Symbols ==="
input bool            InpTradeGold      = true;  // XAUUSD  (6/12 variants positive)
input bool            InpTradeEURUSD    = false; // EURUSD  (0/12 variants positive - OFF)
input string          InpGoldSymbol     = "XAUUSD";
input string          InpEurSymbol      = "EURUSD";

//--- risk ----------------------------------------------------------
input group           "=== Risk (PropShield) ==="
input double          InpRiskPerTrade   = 0.005; // 0.5% of equity
input double          InpMaxTotalDD     = 0.10;
input double          InpMaxDailyDD     = 0.04;
input double          InpDailyRiskBudget= 0.015;
input double          InpProfitTarget   = 0.08;
input int             InpMaxConsecLoss  = 3;
input ENUM_DD_MODEL   InpDDModel        = DD_STATIC;

input group           "=== Misc ==="
input int             InpMagic          = 20260812;
input bool            InpVerbose        = true;

//--- state ---------------------------------------------------------
CPropShield  shield;
int          g_atrGold = INVALID_HANDLE, g_atrEur = INVALID_HANDLE;
datetime     g_lastBar = 0;

struct SDayState
  {
   datetime day;
   bool     anchored;
   bool     traded;
   double   rangeHigh;
   double   rangeLow;
   int      barsSinceAnchor;
  };
SDayState g_gold, g_eur;

//+------------------------------------------------------------------+
//| EU DST: last Sunday March 01:00 UTC .. last Sunday October        |
//+------------------------------------------------------------------+
bool IsEuDST(const datetime utc)
  {
   MqlDateTime t; TimeToStruct(utc, t);
   if(t.mon < 3 || t.mon > 10) return false;
   if(t.mon > 3 && t.mon < 10) return true;

   // find last Sunday of the month
   int lastDay = (t.mon == 3) ? 31 : 31;
   MqlDateTime probe; probe = t; probe.day = lastDay; probe.hour = 1;
   probe.min = 0; probe.sec = 0;
   datetime d = StructToTime(probe);
   MqlDateTime chk; TimeToStruct(d, chk);
   while(chk.day_of_week != 0) { d -= 86400; TimeToStruct(d, chk); }

   if(t.mon == 3)  return (utc >= d);
   else            return (utc <  d);
  }

//+------------------------------------------------------------------+
//| Server hour/minute that corresponds to the configured PKT time    |
//| PKT = UTC+5 (no DST). Server = UTC+2 winter / UTC+3 summer.       |
//+------------------------------------------------------------------+
void PakToServer(const datetime serverNow, int &outHour, int &outMin)
  {
   int utcHour = InpPakHour - 5;
   if(utcHour < 0) utcHour += 24;
   // approximate UTC now for the DST test (offset differs by 1h at most,
   // which cannot flip the DST decision except within one hour of the
   // changeover; acceptable and logged)
   datetime utcApprox = serverNow - 2*3600;
   int off = IsEuDST(utcApprox) ? 3 : 2;
   outHour = (utcHour + off) % 24;
   outMin  = InpPakMinute;
  }

//+------------------------------------------------------------------+
int OnInit()
  {
   SPropConfig c; PropConfigDefaults(c);
   c.maxTotalDD      = InpMaxTotalDD;
   c.maxDailyDD      = InpMaxDailyDD;
   c.ddModel         = InpDDModel;
   c.profitTarget    = InpProfitTarget;
   c.riskPerTrade    = InpRiskPerTrade;
   c.dailyRiskBudget = InpDailyRiskBudget;
   c.maxConsecLosses = InpMaxConsecLoss;
   c.maxOpenPositions= 2;
   c.maxTradesPerDay = 2;          // one per symbol
   c.useSession      = false;      // this EA owns its own session logic
   c.blockFriday     = false;
   c.dailyProfitLock = 0.0;
   shield.Init(c);

   if(InpTradeGold)
     {
      if(!SymbolSelect(InpGoldSymbol,true)) { Print("cannot select ",InpGoldSymbol); return INIT_FAILED; }
      g_atrGold = iATR(InpGoldSymbol, PERIOD_M30, InpATRPeriod);
     }
   if(InpTradeEURUSD)
     {
      if(!SymbolSelect(InpEurSymbol,true)) { Print("cannot select ",InpEurSymbol); return INIT_FAILED; }
      g_atrEur = iATR(InpEurSymbol, PERIOD_M30, InpATRPeriod);
     }

   ZeroMemory(g_gold); ZeroMemory(g_eur);

   int sh,sm; PakToServer(TimeCurrent(),sh,sm);
   PrintFormat("[NYSession] %02d:%02d PKT -> server %02d:%02d (DST=%s). Gold=%s EURUSD=%s",
               InpPakHour,InpPakMinute,sh,sm,
               IsEuDST(TimeCurrent()-2*3600)?"yes":"no",
               InpTradeGold?"ON":"off", InpTradeEURUSD?"ON":"OFF (0/12 variants positive)");
   if(InpTradeEURUSD)
      Print("[NYSession] WARNING: EURUSD lost money in all 12 tested variants. You enabled it manually.");
   return INIT_SUCCEEDED;
  }

//+------------------------------------------------------------------+
void OnDeinit(const int reason)
  {
   shield.PrintStatus();
   if(g_atrGold!=INVALID_HANDLE) IndicatorRelease(g_atrGold);
   if(g_atrEur !=INVALID_HANDLE) IndicatorRelease(g_atrEur);
  }

//+------------------------------------------------------------------+
double GetATR(const int handle)
  {
   double v[]; if(handle==INVALID_HANDLE) return 0.0;
   if(CopyBuffer(handle,0,1,1,v)!=1) return 0.0;
   return v[0];
  }

//+------------------------------------------------------------------+
bool NewM30Bar(const string sym)
  {
   datetime t = iTime(sym, PERIOD_M30, 0);
   if(t == g_lastBar) return false;
   g_lastBar = t;
   return true;
  }

//+------------------------------------------------------------------+
void ProcessSymbol(const string sym, const int atrHandle, SDayState &st)
  {
   int bars = Bars(sym, PERIOD_M30);
   if(bars < InpRangeBars + 60) return;

   datetime bt = iTime(sym, PERIOD_M30, 1);          // last CLOSED bar
   if(bt == 0) return;
   MqlDateTime b; TimeToStruct(bt, b);
   datetime today = bt - (bt % 86400);

   if(st.day != today)                               // new day -> reset
     {
      st.day = today; st.anchored = false; st.traded = false;
      st.rangeHigh = 0; st.rangeLow = 0; st.barsSinceAnchor = 0;
     }
   if(st.traded) return;

   int sh, sm; PakToServer(bt, sh, sm);

   //--- anchor bar: build the range ---
   if(!st.anchored && b.hour == sh && b.min == sm)
     {
      double hi = -DBL_MAX, lo = DBL_MAX;
      for(int k = 1; k <= InpRangeBars; k++)
        {
         hi = MathMax(hi, iHigh(sym, PERIOD_M30, k));
         lo = MathMin(lo, iLow (sym, PERIOD_M30, k));
        }
      if(hi <= lo) return;
      st.rangeHigh = hi; st.rangeLow = lo;
      st.anchored = true; st.barsSinceAnchor = 0;
      if(InpVerbose) PrintFormat("[%s] range %.5f / %.5f set at server %02d:%02d",sym,hi,lo,sh,sm);
      return;
     }
   if(!st.anchored) return;

   st.barsSinceAnchor++;
   if(st.barsSinceAnchor > InpTriggerBars) { st.traded = true; return; }   // window closed

   //--- breakout on the closed bar ---
   double c = iClose(sym, PERIOD_M30, 1);
   int dir = 0;
   if(c > st.rangeHigh)      dir =  1;
   else if(c < st.rangeLow)  dir = -1;
   if(dir == 0) return;

   double atr = GetATR(atrHandle);
   if(atr <= 0) return;

   string why;
   if(!shield.CanTrade(dir, why))
     { if(InpVerbose) PrintFormat("[%s] blocked: %s", sym, why); st.traded = true; return; }

   double ask = SymbolInfoDouble(sym, SYMBOL_ASK);
   double bid = SymbolInfoDouble(sym, SYMBOL_BID);
   double entry = (dir > 0) ? ask : bid;
   double sl    = (dir > 0) ? entry - InpStopATR*atr : entry + InpStopATR*atr;
   double risk  = MathAbs(entry - sl);
   if(risk <= 0) return;
   double tp    = (dir > 0) ? entry + InpRR*risk : entry - InpRR*risk;

   if(!shield.ValidateOrder(entry, sl, tp, dir, why))
     { PrintFormat("[%s] order rejected: %s", sym, why); st.traded = true; return; }

   double lots = shield.CalcLots(risk, sym);
   if(lots <= 0) { if(InpVerbose) Print("[",sym,"] lot size 0 - skipped"); st.traded = true; return; }

   MqlTradeRequest rq; MqlTradeResult rs;
   ZeroMemory(rq); ZeroMemory(rs);
   rq.action    = TRADE_ACTION_DEAL;
   rq.symbol    = sym;
   rq.volume    = lots;
   rq.type      = (dir > 0) ? ORDER_TYPE_BUY : ORDER_TYPE_SELL;
   rq.price     = entry;
   rq.sl        = NormalizeDouble(sl, (int)SymbolInfoInteger(sym, SYMBOL_DIGITS));
   rq.tp        = NormalizeDouble(tp, (int)SymbolInfoInteger(sym, SYMBOL_DIGITS));
   rq.deviation = 20;
   rq.magic     = InpMagic;
   rq.comment   = "NYSession";
   rq.type_filling = ORDER_FILLING_FOK;

   if(!OrderSend(rq, rs) || (rs.retcode != TRADE_RETCODE_DONE && rs.retcode != TRADE_RETCODE_PLACED))
     {
      rq.type_filling = ORDER_FILLING_IOC;
      if(!OrderSend(rq, rs))
         PrintFormat("[%s] OrderSend failed: %d %s", sym, rs.retcode, rs.comment);
     }
   if(rs.retcode == TRADE_RETCODE_DONE || rs.retcode == TRADE_RETCODE_PLACED)
      PrintFormat("[%s] %s %.2f lots @ %.5f SL %.5f TP %.5f",
                  sym, dir>0?"BUY":"SELL", lots, entry, sl, tp);
   st.traded = true;
  }

//+------------------------------------------------------------------+
void ManageTimeStops()
  {
   for(int i = PositionsTotal()-1; i >= 0; i--)
     {
      ulong tk = PositionGetTicket(i);
      if(tk == 0) continue;
      if(PositionGetInteger(POSITION_MAGIC) != InpMagic) continue;
      datetime opened = (datetime)PositionGetInteger(POSITION_TIME);
      if((TimeCurrent() - opened) < InpMaxHoldBars*1800) continue;

      string sym = PositionGetString(POSITION_SYMBOL);
      MqlTradeRequest rq; MqlTradeResult rs; ZeroMemory(rq); ZeroMemory(rs);
      rq.action    = TRADE_ACTION_DEAL;
      rq.position  = tk;
      rq.symbol    = sym;
      rq.volume    = PositionGetDouble(POSITION_VOLUME);
      rq.type      = (PositionGetInteger(POSITION_TYPE)==POSITION_TYPE_BUY)
                     ? ORDER_TYPE_SELL : ORDER_TYPE_BUY;
      rq.price     = (rq.type==ORDER_TYPE_SELL) ? SymbolInfoDouble(sym,SYMBOL_BID)
                                                : SymbolInfoDouble(sym,SYMBOL_ASK);
      rq.deviation = 20;
      rq.magic     = InpMagic;
      if(OrderSend(rq, rs)) PrintFormat("[%s] time stop closed", sym);
     }
  }

//+------------------------------------------------------------------+
void OnTick()
  {
   shield.Update();
   if(shield.IsHalted()) return;

   ManageTimeStops();

   string ref = InpTradeGold ? InpGoldSymbol : InpEurSymbol;
   if(!NewM30Bar(ref)) return;

   if(InpTradeGold)   ProcessSymbol(InpGoldSymbol, g_atrGold, g_gold);
   if(InpTradeEURUSD) ProcessSymbol(InpEurSymbol,  g_atrEur,  g_eur);
  }
//+------------------------------------------------------------------+
