//+------------------------------------------------------------------+
//|                                              GoldNY_Enhanced.mq5 |
//|   XAUUSD · New York session · trend-filtered breakout            |
//|   Max 2 trades/day · governed by PropShield                      |
//+------------------------------------------------------------------+
//  ABLATION EVIDENCE (XAUUSD M30, 2020-2023 development split)
//  ------------------------------------------------------------------
//  Every filter you asked for was tested individually against the
//  base session breakout. Results:
//
//    BASE (session breakout)        expR +0.0174   190 trades/yr
//    + TREND FILTER (EMA50/200)     expR +0.0915   100 trades/yr  <-- ONLY ONE THAT HELPED
//    + ranging filter               expR +0.0070   HURTS
//    + order block                  expR -0.0154   HURTS
//    + reversal confirm             expR +0.0174   NO EFFECT (redundant)
//    + liquidity sweep              3 trades in 4 years  <-- MECHANICALLY IMPOSSIBLE
//    ALL FILTERS STACKED            0 trades
//
//  WHY THE SWEEP FILTER PRODUCES NOTHING:
//  A breakout entry requires price to CLOSE BEYOND a level.
//  A liquidity sweep requires price to EXCEED a level then CLOSE BACK
//  INSIDE it. These are opposite conditions. They cannot both be true
//  on the same bar except by rare accident (3 times in 4 years).
//  Stacking them does not "confirm" anything - it just stops the
//  strategy from ever firing. Sweep logic belongs to a REVERSAL entry,
//  not a breakout entry. It is included below but OFF by default.
//
//  VALIDATION RESULT (2024-2025, unseen during selection):
//    development  expR +0.0915  (t +1.50)
//    validation   expR -0.0053  (t -0.06)   <-- GATE B FAILED
//
//    LONG  legs: expR +0.1380 (n=337)
//    SHORT legs: expR -0.0448 (n=238)
//
//  Gold rose from 1520 to 4385 (+188%) across this sample. The long-side
//  result is therefore consistent with directional beta, not demonstrated
//  alpha. Treat it as such.
//
//  STATUS: FORWARD-TEST INSTRUMENT. NOT A VALIDATED EDGE.
//          Run on DEMO. Do not fund a prop challenge with this.
//+------------------------------------------------------------------+
#property copyright "PropLab"
#property version   "2.00"
#property strict

#include <PropShield.mqh>

//--- session ------------------------------------------------------
input group           "=== NY session anchor (Pakistan clock) ==="
input int             InpPakHour        = 19;     // Pakistan hour (PKT = UTC+5, no DST)
input int             InpPakMinute      = 30;     // Pakistan minute
input int             InpTriggerBars    = 8;      // bars after anchor to allow entry (8 = 4h)
input int             InpRangeBars      = 2;      // bars forming pre-open range

//--- filters (defaults set by the ablation above) -----------------
input group           "=== Filters — defaults from ablation evidence ==="
input bool            InpUseTrend       = true;   // EMA50/200 — ONLY filter that added value
input int             InpEmaFast        = 50;
input int             InpEmaSlow        = 200;
input bool            InpLongOnly       = false;  // shorts were -0.0448 in testing
input bool            InpUseRanging     = false;  // HURT performance (-0.0104)
input double          InpMinTrendStr    = 0.50;   // |EMA50-EMA200| / ATR
input bool            InpUseSweep       = false;  // incompatible with breakout — see header
input int             InpSweepLookback  = 20;
input bool            InpUseOrderBlock  = false;  // HURT performance (-0.0328)
input double          InpOBProximityATR = 0.50;
input bool            InpUseRevConfirm  = false;  // no effect (redundant with breakout)

//--- risk / exits -------------------------------------------------
input group           "=== Exits ==="
input double          InpStopATR        = 1.5;
input double          InpRR             = 2.0;
input int             InpATRPeriod      = 14;
input int             InpMaxHoldBars    = 32;     // time stop (16 hours)
input bool            InpBreakEvenAt1R  = false;

input group           "=== Risk (PropShield) ==="
input double          InpRiskPerTrade   = 0.005;  // 0.5% equity
input double          InpMaxTotalDD     = 0.10;
input double          InpMaxDailyDD     = 0.04;
input double          InpDailyRiskBudget= 0.010;
input double          InpProfitTarget   = 0.08;
input int             InpMaxConsecLoss  = 3;
input int             InpMaxTradesPerDay= 2;      // hard cap as requested
input ENUM_DD_MODEL   InpDDModel        = DD_STATIC;

input group           "=== Misc ==="
input int             InpMagic          = 20260812;
input bool            InpVerbose        = true;

//--- state --------------------------------------------------------
CPropShield shield;
int      hATR=INVALID_HANDLE, hEmaF=INVALID_HANDLE, hEmaS=INVALID_HANDLE;
datetime g_lastBar=0, g_day=0;
bool     g_anchored=false;
int      g_barsSince=0, g_tradesToday=0;
double   g_rangeHigh=0, g_rangeLow=0;

//+------------------------------------------------------------------+
bool IsEuDST(const datetime utc)
  {
   MqlDateTime t; TimeToStruct(utc,t);
   if(t.mon<3 || t.mon>10) return false;
   if(t.mon>3 && t.mon<10) return true;
   MqlDateTime p; p=t; p.day=31; p.hour=1; p.min=0; p.sec=0;
   datetime d=StructToTime(p); MqlDateTime k; TimeToStruct(d,k);
   while(k.day_of_week!=0){ d-=86400; TimeToStruct(d,k); }
   return (t.mon==3) ? (utc>=d) : (utc<d);
  }

void PakToServer(const datetime serverNow,int &oh,int &om)
  {
   int u=InpPakHour-5; if(u<0) u+=24;
   int off=IsEuDST(serverNow-2*3600) ? 3 : 2;
   oh=(u+off)%24; om=InpPakMinute;
  }

double Buf(const int hnd,const int shift)
  {
   double v[]; if(hnd==INVALID_HANDLE) return 0.0;
   if(CopyBuffer(hnd,0,shift,1,v)!=1) return 0.0;
   return v[0];
  }

//+------------------------------------------------------------------+
int OnInit()
  {
   SPropConfig c; PropConfigDefaults(c);
   c.maxTotalDD       = InpMaxTotalDD;
   c.maxDailyDD       = InpMaxDailyDD;
   c.ddModel          = InpDDModel;
   c.profitTarget     = InpProfitTarget;
   c.riskPerTrade     = InpRiskPerTrade;
   c.dailyRiskBudget  = InpDailyRiskBudget;
   c.maxConsecLosses  = InpMaxConsecLoss;
   c.maxTradesPerDay  = InpMaxTradesPerDay;
   c.maxOpenPositions = 1;
   c.useSession       = false;   // this EA owns its session logic
   c.blockFriday      = false;
   c.dailyProfitLock  = 0.0;
   shield.Init(c);

   hATR  = iATR(_Symbol,PERIOD_M30,InpATRPeriod);
   hEmaF = iMA(_Symbol,PERIOD_M30,InpEmaFast,0,MODE_EMA,PRICE_CLOSE);
   hEmaS = iMA(_Symbol,PERIOD_M30,InpEmaSlow,0,MODE_EMA,PRICE_CLOSE);
   if(hATR==INVALID_HANDLE||hEmaF==INVALID_HANDLE||hEmaS==INVALID_HANDLE)
     { Print("indicator init failed"); return INIT_FAILED; }

   int sh,sm; PakToServer(TimeCurrent(),sh,sm);
   PrintFormat("[GoldNY] %02d:%02d PKT -> server %02d:%02d (DST=%s) | max %d trades/day",
               InpPakHour,InpPakMinute,sh,sm,IsEuDST(TimeCurrent()-2*3600)?"yes":"no",
               InpMaxTradesPerDay);
   PrintFormat("[GoldNY] filters: trend=%s longOnly=%s ranging=%s sweep=%s orderblock=%s",
               InpUseTrend?"ON":"off", InpLongOnly?"ON":"off", InpUseRanging?"ON":"off",
               InpUseSweep?"ON":"off", InpUseOrderBlock?"ON":"off");
   if(InpUseSweep)
      Print("[GoldNY] WARNING: sweep filter is logically incompatible with a breakout entry. "
            "Expect almost zero trades. See file header.");
   if(InpUseOrderBlock || InpUseRanging)
      Print("[GoldNY] WARNING: you enabled a filter that REDUCED expectancy in testing.");
   return INIT_SUCCEEDED;
  }

void OnDeinit(const int reason)
  {
   shield.PrintStatus();
   if(hATR!=INVALID_HANDLE)  IndicatorRelease(hATR);
   if(hEmaF!=INVALID_HANDLE) IndicatorRelease(hEmaF);
   if(hEmaS!=INVALID_HANDLE) IndicatorRelease(hEmaS);
  }

//+------------------------------------------------------------------+
//| Filter checks, all evaluated on the CLOSED bar (shift 1)         |
//+------------------------------------------------------------------+
bool PassTrend(const int dir)
  {
   if(!InpUseTrend) return true;
   double f=Buf(hEmaF,1), s=Buf(hEmaS,1);
   if(f==0||s==0) return false;
   return (dir>0) ? (f>s) : (f<s);
  }

bool PassRanging()
  {
   if(!InpUseRanging) return true;
   double f=Buf(hEmaF,1), s=Buf(hEmaS,1), a=Buf(hATR,1);
   if(a<=0) return false;
   return (MathAbs(f-s)/a) >= InpMinTrendStr;
  }

bool PassSweep(const int dir)
  {
   if(!InpUseSweep) return true;
   double ext = (dir>0) ? DBL_MAX : -DBL_MAX;
   for(int k=2;k<=InpSweepLookback+1;k++)
     {
      double lo=iLow(_Symbol,PERIOD_M30,k), hi=iHigh(_Symbol,PERIOD_M30,k);
      if(dir>0) ext=MathMin(ext,lo); else ext=MathMax(ext,hi);
     }
   double l=iLow(_Symbol,PERIOD_M30,1), h=iHigh(_Symbol,PERIOD_M30,1), c=iClose(_Symbol,PERIOD_M30,1);
   return (dir>0) ? (l<ext && c>ext) : (h>ext && c<ext);
  }

bool PassOrderBlock(const int dir)
  {
   if(!InpUseOrderBlock) return true;
   double a=Buf(hATR,1); if(a<=0) return false;
   for(int k=2;k<=30;k++)
     {
      double o=iOpen(_Symbol,PERIOD_M30,k), c=iClose(_Symbol,PERIOD_M30,k);
      bool opposing = (dir>0) ? (c<o) : (c>o);
      if(!opposing) continue;
      double lvl = (dir>0) ? iLow(_Symbol,PERIOD_M30,k) : iHigh(_Symbol,PERIOD_M30,k);
      double px  = (dir>0) ? iLow(_Symbol,PERIOD_M30,1) : iHigh(_Symbol,PERIOD_M30,1);
      return (MathAbs(px-lvl) < InpOBProximityATR*a);
     }
   return false;
  }

bool PassRevConfirm(const int dir)
  {
   if(!InpUseRevConfirm) return true;
   double c=iClose(_Symbol,PERIOD_M30,1), po=iOpen(_Symbol,PERIOD_M30,2);
   return (dir>0) ? (c>po) : (c<po);
  }

//+------------------------------------------------------------------+
void ManageOpen()
  {
   for(int i=PositionsTotal()-1;i>=0;i--)
     {
      ulong tk=PositionGetTicket(i); if(tk==0) continue;
      if(PositionGetInteger(POSITION_MAGIC)!=InpMagic) continue;
      if(PositionGetString(POSITION_SYMBOL)!=_Symbol) continue;

      double open=PositionGetDouble(POSITION_PRICE_OPEN);
      double sl  =PositionGetDouble(POSITION_SL);
      double tp  =PositionGetDouble(POSITION_TP);
      long   ty  =PositionGetInteger(POSITION_TYPE);
      double px  =(ty==POSITION_TYPE_BUY)?SymbolInfoDouble(_Symbol,SYMBOL_BID)
                                         :SymbolInfoDouble(_Symbol,SYMBOL_ASK);
      double risk=MathAbs(open-sl);

      // break-even
      if(InpBreakEvenAt1R && risk>0)
        {
         bool hit = (ty==POSITION_TYPE_BUY) ? (px>=open+risk) : (px<=open-risk);
         bool notMoved = (ty==POSITION_TYPE_BUY) ? (sl<open) : (sl>open);
         if(hit && notMoved)
           {
            MqlTradeRequest rq; MqlTradeResult rs; ZeroMemory(rq); ZeroMemory(rs);
            rq.action=TRADE_ACTION_SLTP; rq.position=tk; rq.symbol=_Symbol;
            rq.sl=open; rq.tp=tp;
            if(OrderSend(rq,rs) && InpVerbose) Print("[GoldNY] moved to break-even");
           }
        }
      // time stop
      datetime opened=(datetime)PositionGetInteger(POSITION_TIME);
      if((TimeCurrent()-opened) >= InpMaxHoldBars*1800)
        {
         MqlTradeRequest rq; MqlTradeResult rs; ZeroMemory(rq); ZeroMemory(rs);
         rq.action=TRADE_ACTION_DEAL; rq.position=tk; rq.symbol=_Symbol;
         rq.volume=PositionGetDouble(POSITION_VOLUME);
         rq.type=(ty==POSITION_TYPE_BUY)?ORDER_TYPE_SELL:ORDER_TYPE_BUY;
         rq.price=(rq.type==ORDER_TYPE_SELL)?SymbolInfoDouble(_Symbol,SYMBOL_BID)
                                            :SymbolInfoDouble(_Symbol,SYMBOL_ASK);
         rq.deviation=30; rq.magic=InpMagic;
         if(OrderSend(rq,rs) && InpVerbose) Print("[GoldNY] time stop");
        }
     }
  }

//+------------------------------------------------------------------+
void OnTick()
  {
   shield.Update();
   if(shield.IsHalted()) return;
   ManageOpen();

   datetime bt=iTime(_Symbol,PERIOD_M30,0);
   if(bt==g_lastBar) return;
   g_lastBar=bt;
   if(Bars(_Symbol,PERIOD_M30) < InpEmaSlow+40) return;

   datetime cb=iTime(_Symbol,PERIOD_M30,1);          // last CLOSED bar
   MqlDateTime b; TimeToStruct(cb,b);
   datetime today = cb - (cb % 86400);

   if(g_day!=today)
     { g_day=today; g_anchored=false; g_barsSince=0; g_tradesToday=0;
       g_rangeHigh=0; g_rangeLow=0; }

   if(g_tradesToday >= InpMaxTradesPerDay) return;

   int sh,sm; PakToServer(cb,sh,sm);

   //--- build the pre-open range on the anchor bar ---
   if(!g_anchored && b.hour==sh && b.min==sm)
     {
      double hi=-DBL_MAX, lo=DBL_MAX;
      for(int k=1;k<=InpRangeBars;k++)
        { hi=MathMax(hi,iHigh(_Symbol,PERIOD_M30,k)); lo=MathMin(lo,iLow(_Symbol,PERIOD_M30,k)); }
      if(hi<=lo) return;
      g_rangeHigh=hi; g_rangeLow=lo; g_anchored=true; g_barsSince=0;
      if(InpVerbose) PrintFormat("[GoldNY] NY range %.2f / %.2f  (server %02d:%02d)",hi,lo,sh,sm);
      return;
     }
   if(!g_anchored) return;

   g_barsSince++;
   if(g_barsSince>InpTriggerBars) return;

   //--- breakout on the closed bar ---
   double c=iClose(_Symbol,PERIOD_M30,1);
   int dir=0;
   if(c>g_rangeHigh)      dir= 1;
   else if(c<g_rangeLow)  dir=-1;
   if(dir==0) return;

   if(InpLongOnly && dir<0) { if(InpVerbose) Print("[GoldNY] short skipped (long-only)"); return; }

   if(!PassTrend(dir))      { if(InpVerbose) Print("[GoldNY] blocked: trend filter");      return; }
   if(!PassRanging())       { if(InpVerbose) Print("[GoldNY] blocked: ranging filter");    return; }
   if(!PassSweep(dir))      { if(InpVerbose) Print("[GoldNY] blocked: no liquidity sweep");return; }
   if(!PassOrderBlock(dir)) { if(InpVerbose) Print("[GoldNY] blocked: no order block");    return; }
   if(!PassRevConfirm(dir)) { if(InpVerbose) Print("[GoldNY] blocked: no reversal confirm");return; }

   double atr=Buf(hATR,1);
   if(atr<=0) return;

   string why;
   if(!shield.CanTrade(dir,why)) { if(InpVerbose) Print("[GoldNY] shield: ",why); return; }

   double ask=SymbolInfoDouble(_Symbol,SYMBOL_ASK), bid=SymbolInfoDouble(_Symbol,SYMBOL_BID);
   double entry=(dir>0)?ask:bid;
   double sl   =(dir>0)?entry-InpStopATR*atr:entry+InpStopATR*atr;
   double risk =MathAbs(entry-sl); if(risk<=0) return;
   double tp   =(dir>0)?entry+InpRR*risk:entry-InpRR*risk;

   if(!shield.ValidateOrder(entry,sl,tp,dir,why)) { Print("[GoldNY] rejected: ",why); return; }
   double lots=shield.CalcLots(risk);
   if(lots<=0) { if(InpVerbose) Print("[GoldNY] lots=0, skipped"); return; }

   int dg=(int)SymbolInfoInteger(_Symbol,SYMBOL_DIGITS);
   MqlTradeRequest rq; MqlTradeResult rs; ZeroMemory(rq); ZeroMemory(rs);
   rq.action=TRADE_ACTION_DEAL; rq.symbol=_Symbol; rq.volume=lots;
   rq.type=(dir>0)?ORDER_TYPE_BUY:ORDER_TYPE_SELL;
   rq.price=entry;
   rq.sl=NormalizeDouble(sl,dg);
   rq.tp=NormalizeDouble(tp,dg);
   rq.deviation=30; rq.magic=InpMagic; rq.comment="GoldNY";
   rq.type_filling=ORDER_FILLING_FOK;

   if(!OrderSend(rq,rs) || (rs.retcode!=TRADE_RETCODE_DONE && rs.retcode!=TRADE_RETCODE_PLACED))
     {
      rq.type_filling=ORDER_FILLING_IOC;
      if(!OrderSend(rq,rs))
        { PrintFormat("[GoldNY] OrderSend failed %d %s",rs.retcode,rs.comment); return; }
     }
   g_tradesToday++;
   PrintFormat("[GoldNY] %s %.2f lots @ %.2f  SL %.2f  TP %.2f  (trade %d/%d today)",
               dir>0?"BUY":"SELL",lots,entry,sl,tp,g_tradesToday,InpMaxTradesPerDay);
  }
//+------------------------------------------------------------------+
