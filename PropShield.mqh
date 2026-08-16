//+------------------------------------------------------------------+
//|                                                   PropShield.mqh |
//|          Strategy-agnostic risk governor for prop-firm accounts   |
//|                                                                   |
//|  The strategy proposes. The governor disposes.                    |
//|  No order reaches the market without clearing every gate here.    |
//|                                                                   |
//|  STATUS: infrastructure only. Contains NO strategy logic and NO   |
//|  edge assumption. Safe to use with any validated strategy; using  |
//|  it does not make an unvalidated strategy safe to trade.          |
//|                                                                   |
//|  Usage:                                                           |
//|    #include <PropShield.mqh>                                      |
//|    CPropShield shield;                                            |
//|    OnInit(): SPropConfig c; PropConfigDefaults(c); shield.Init(c);|
//|    OnTick(): shield.Update();                                     |
//|              string why;                                          |
//|              if(shield.CanTrade(dir,why)) {                       |
//|                 double lots = shield.CalcLots(slDistance);         |
//|                 if(shield.ValidateOrder(px,sl,tp,dir,why)) ...     |
//|              }                                                     |
//+------------------------------------------------------------------+
#property copyright "PropLab"
#property strict

//--- how the firm measures the max-loss floor ----------------------
enum ENUM_DD_MODEL
  {
   DD_STATIC    = 0,   // from initial balance (FTMO-style)
   DD_TRAILING  = 1,   // trails equity high-water mark intraday
   DD_EOD_TRAIL = 2    // trails, updated end-of-day only (Topstep-style)
  };

//+------------------------------------------------------------------+
//| Configuration. Every field must be set from the FIRM'S OWN RULES. |
//| Defaults below are deliberately conservative placeholders, not    |
//| any firm's actual terms. Verify before use.                       |
//+------------------------------------------------------------------+
struct SPropConfig
  {
   //--- firm envelope (fractions: 0.10 == 10%) ---
   double        maxTotalDD;
   double        maxDailyDD;
   ENUM_DD_MODEL ddModel;
   double        profitTarget;              // 0 = disabled
   int           minTradingDays;            // 0 = disabled
   double        consistencyCap;            // best day / total profit, 0 = disabled

   //--- our own limits, deliberately tighter than the firm's ---
   double        riskPerTrade;
   double        dailyRiskBudget;
   int           maxConsecLosses;
   int           maxOpenPositions;
   int           maxTradesPerDay;
   double        maxSymbolExposureLots;
   double        maxAggregateExposureLots;

   //--- execution guards ---
   double        maxSpreadPoints;
   int           maxSlippagePoints;

   //--- session ---
   bool          useSession;
   int           sessionStartHour;
   int           sessionEndHour;
   bool          blockFriday;
   int           fridayCutoffHour;

   //--- profit protection ---
   double        dailyProfitLock;           // 0 = disabled
   bool          lockOnTargetHit;

   //--- reserve kept between us and any hard limit ---
   double        safetyBuffer;              // 0.20 == keep 20% in reserve
  };

//+------------------------------------------------------------------+
void PropConfigDefaults(SPropConfig &c)
  {
   c.maxTotalDD               = 0.10;
   c.maxDailyDD               = 0.04;
   c.ddModel                  = DD_STATIC;
   c.profitTarget             = 0.08;
   c.minTradingDays           = 0;
   c.consistencyCap           = 0.0;
   c.riskPerTrade             = 0.005;
   c.dailyRiskBudget          = 0.015;
   c.maxConsecLosses          = 3;
   c.maxOpenPositions         = 2;
   c.maxTradesPerDay          = 5;
   c.maxSymbolExposureLots    = 1.0;
   c.maxAggregateExposureLots = 2.0;
   c.maxSpreadPoints          = 30;
   c.maxSlippagePoints        = 20;
   c.useSession               = true;
   c.sessionStartHour         = 7;
   c.sessionEndHour           = 20;
   c.blockFriday              = true;
   c.fridayCutoffHour         = 18;
   c.dailyProfitLock          = 0.02;
   c.lockOnTargetHit          = true;
   c.safetyBuffer             = 0.20;
  }

//+------------------------------------------------------------------+
class CPropShield
  {
private:
   SPropConfig m_cfg;
   double      m_initialBalance;
   double      m_hwm;                 // running equity high-water mark
   double      m_eodHwm;              // end-of-day HWM (DD_EOD_TRAIL)
   double      m_dayStartEquity;
   double      m_bestDayProfit;       // for consistency tracking
   double      m_totalProfit;
   datetime    m_currentDay;
   int         m_consecLosses;
   int         m_tradesToday;
   int         m_tradingDays;
   bool        m_halted;
   bool        m_haltedToday;
   string      m_haltReason;
   ulong       m_lastDeal;

   datetime    DayOf(datetime t) const { return (t - (t % 86400)); }
   void        ScanClosedDeals();

public:
               CPropShield(void): m_initialBalance(0),m_hwm(0),m_eodHwm(0),
                                  m_dayStartEquity(0),m_bestDayProfit(0),m_totalProfit(0),
                                  m_currentDay(0),m_consecLosses(0),m_tradesToday(0),
                                  m_tradingDays(0),m_halted(false),m_haltedToday(false),
                                  m_haltReason(""),m_lastDeal(0) {}

   void        Init(const SPropConfig &cfg);
   void        Update();
   bool        CanTrade(const int dir,string &reason);
   double      CalcLots(const double slDistance,const string sym="");
   bool        ValidateOrder(const double entry,const double sl,const double tp,
                             const int dir,string &reason);
   void        ForceHalt(const string why){ m_halted=true; m_haltReason=why; }
   void        CloseAllPositions();

   double      FloorLevel() const;
   double      DailyPnLPct() const;
   double      TotalPnLPct() const;
   double      DistanceToFloorPct() const;
   double      ConsistencyRatio() const;
   bool        IsHalted() const { return m_halted; }
   string      HaltReason() const { return m_haltReason; }
   int         ConsecLosses() const { return m_consecLosses; }
   int         TradesToday() const { return m_tradesToday; }
   int         TradingDays() const { return m_tradingDays; }
   void        PrintStatus();
  };

//+------------------------------------------------------------------+
double CPropShield::FloorLevel() const
  {
   switch(m_cfg.ddModel)
     {
      case DD_TRAILING:  return m_hwm    * (1.0 - m_cfg.maxTotalDD);
      case DD_EOD_TRAIL: return m_eodHwm * (1.0 - m_cfg.maxTotalDD);
      default:           return m_initialBalance * (1.0 - m_cfg.maxTotalDD);
     }
  }

//+------------------------------------------------------------------+
void CPropShield::Init(const SPropConfig &cfg)
  {
   m_cfg             = cfg;
   m_initialBalance  = AccountInfoDouble(ACCOUNT_BALANCE);
   m_hwm             = m_initialBalance;
   m_eodHwm          = m_initialBalance;
   m_dayStartEquity  = m_initialBalance;
   m_bestDayProfit   = 0.0;
   m_totalProfit     = 0.0;
   m_currentDay      = DayOf(TimeCurrent());
   m_consecLosses    = 0;
   m_tradesToday     = 0;
   m_tradingDays     = 0;
   m_halted          = false;
   m_haltedToday     = false;
   m_haltReason      = "";
   m_lastDeal        = 0;

   PrintFormat("[SHIELD] init bal=%.2f floor=%.2f dailyDD=%.1f%% totalDD=%.1f%% risk=%.2f%% model=%d",
               m_initialBalance,FloorLevel(),100*m_cfg.maxDailyDD,100*m_cfg.maxTotalDD,
               100*m_cfg.riskPerTrade,(int)m_cfg.ddModel);
  }

//+------------------------------------------------------------------+
void CPropShield::Update()
  {
   double   eq = AccountInfoDouble(ACCOUNT_EQUITY);
   datetime d  = DayOf(TimeCurrent());

   if(d != m_currentDay)                                  // ---- day roll ----
     {
      double dayPnL = eq - m_dayStartEquity;
      if(m_tradesToday > 0)
        {
         m_tradingDays++;
         if(dayPnL > m_bestDayProfit) m_bestDayProfit = dayPnL;
        }
      m_currentDay     = d;
      m_dayStartEquity = eq;
      m_tradesToday    = 0;
      m_haltedToday    = false;
      m_eodHwm         = MathMax(m_eodHwm, eq);
      PrintFormat("[SHIELD] new day. eq=%.2f days=%d consecL=%d",eq,m_tradingDays,m_consecLosses);
     }

   if(eq > m_hwm) m_hwm = eq;
   m_totalProfit = eq - m_initialBalance;
   ScanClosedDeals();

   //--- hard failures: end the run ---
   if(!m_halted)
     {
      if(eq <= FloorLevel())
        {
         m_halted = true;
         m_haltReason = StringFormat("MAX DD BREACHED eq=%.2f floor=%.2f",eq,FloorLevel());
         CloseAllPositions();
        }
      else if(m_cfg.profitTarget > 0 && m_cfg.lockOnTargetHit &&
              eq >= m_initialBalance*(1.0+m_cfg.profitTarget) &&
              (m_cfg.minTradingDays == 0 || m_tradingDays >= m_cfg.minTradingDays))
        {
         m_halted = true;
         m_haltReason = StringFormat("TARGET REACHED eq=%.2f days=%d",eq,m_tradingDays);
        }
     }

   //--- daily gates: reset tomorrow ---
   if(!m_haltedToday)
     {
      double dpl = DailyPnLPct();
      if(dpl <= -m_cfg.dailyRiskBudget)
        { m_haltedToday=true; PrintFormat("[SHIELD] daily risk spent (%.2f%%). Stand down.",100*dpl); }
      else if(m_cfg.dailyProfitLock > 0 && dpl >= m_cfg.dailyProfitLock)
        { m_haltedToday=true; PrintFormat("[SHIELD] daily profit lock (+%.2f%%). Stand down.",100*dpl); }
     }
  }

//+------------------------------------------------------------------+
void CPropShield::ScanClosedDeals()
  {
   if(!HistorySelect(TimeCurrent()-7*86400,TimeCurrent()+60)) return;
   int total = HistoryDealsTotal();
   for(int i=0; i<total; i++)
     {
      ulong tk = HistoryDealGetTicket(i);
      if(tk <= m_lastDeal) continue;
      m_lastDeal = tk;
      if(HistoryDealGetInteger(tk,DEAL_ENTRY) != DEAL_ENTRY_OUT) continue;
      double p = HistoryDealGetDouble(tk,DEAL_PROFIT)
               + HistoryDealGetDouble(tk,DEAL_SWAP)
               + HistoryDealGetDouble(tk,DEAL_COMMISSION);
      if(p < 0)      m_consecLosses++;
      else if(p > 0) m_consecLosses = 0;
      m_tradesToday++;
     }
  }

//+------------------------------------------------------------------+
bool CPropShield::CanTrade(const int dir,string &reason)
  {
   reason = "";
   if(m_halted)      { reason = "HALTED: "+m_haltReason; return false; }
   if(m_haltedToday) { reason = "stood down for today";  return false; }

   double eq    = AccountInfoDouble(ACCOUNT_EQUITY);
   double room  = eq - FloorLevel();
   double need  = eq * m_cfg.riskPerTrade * (1.0 + m_cfg.safetyBuffer);
   if(room <= need)
     { reason = StringFormat("too close to floor (room %.2f < need %.2f)",room,need); return false; }

   double dpl      = DailyPnLPct();
   double dailyCap = MathMin(m_cfg.dailyRiskBudget, m_cfg.maxDailyDD*(1.0-m_cfg.safetyBuffer));
   if(dpl - m_cfg.riskPerTrade <= -dailyCap)
     { reason = StringFormat("would breach daily cap (now %.2f%%, cap %.2f%%)",100*dpl,100*dailyCap); return false; }

   if(m_consecLosses >= m_cfg.maxConsecLosses)
     { reason = StringFormat("consec-loss circuit open (%d)",m_consecLosses); return false; }
   if(m_tradesToday >= m_cfg.maxTradesPerDay)
     { reason = "max trades/day"; return false; }
   if(PositionsTotal() >= m_cfg.maxOpenPositions)
     { reason = "max open positions"; return false; }

   double sp = (double)SymbolInfoInteger(_Symbol,SYMBOL_SPREAD);
   if(sp > m_cfg.maxSpreadPoints)
     { reason = StringFormat("spread %.0f > %.0f",sp,m_cfg.maxSpreadPoints); return false; }

   MqlDateTime t; TimeToStruct(TimeCurrent(),t);
   if(m_cfg.useSession && (t.hour < m_cfg.sessionStartHour || t.hour >= m_cfg.sessionEndHour))
     { reason = "outside session"; return false; }
   if(m_cfg.blockFriday && t.day_of_week==5 && t.hour>=m_cfg.fridayCutoffHour)
     { reason = "Friday cutoff"; return false; }

   double symLots=0, allLots=0;
   for(int i=PositionsTotal()-1; i>=0; i--)
     {
      ulong tk = PositionGetTicket(i); if(tk==0) continue;
      double v = PositionGetDouble(POSITION_VOLUME);
      allLots += v;
      if(PositionGetString(POSITION_SYMBOL)==_Symbol) symLots += v;
     }
   if(symLots >= m_cfg.maxSymbolExposureLots)    { reason="symbol exposure cap";    return false; }
   if(allLots >= m_cfg.maxAggregateExposureLots) { reason="aggregate exposure cap"; return false; }

   return true;
  }

//+------------------------------------------------------------------+
double CPropShield::CalcLots(const double slDistance,const string sym)
  {
   string s = (sym=="") ? _Symbol : sym;
   if(slDistance <= 0) return 0.0;

   double eq   = AccountInfoDouble(ACCOUNT_EQUITY);
   double risk = eq * m_cfg.riskPerTrade;

   double room = (eq - FloorLevel()) / (1.0 + m_cfg.safetyBuffer);
   risk = MathMin(risk, room);

   double usedToday = -MathMin(0.0, DailyPnLPct()) * m_dayStartEquity;
   double dailyLeft = m_cfg.dailyRiskBudget * m_dayStartEquity - usedToday;
   risk = MathMin(risk, MathMax(0.0, dailyLeft));
   if(risk <= 0) return 0.0;

   double tv = SymbolInfoDouble(s,SYMBOL_TRADE_TICK_VALUE);
   double ts = SymbolInfoDouble(s,SYMBOL_TRADE_TICK_SIZE);
   if(tv<=0 || ts<=0) return 0.0;

   double lossPerLot = (slDistance/ts)*tv;
   if(lossPerLot <= 0) return 0.0;

   double lots = risk / lossPerLot;
   double mn = SymbolInfoDouble(s,SYMBOL_VOLUME_MIN);
   double mx = SymbolInfoDouble(s,SYMBOL_VOLUME_MAX);
   double st = SymbolInfoDouble(s,SYMBOL_VOLUME_STEP);
   if(st > 0) lots = MathFloor(lots/st)*st;
   lots = MathMin(lots, mx);
   lots = MathMin(lots, m_cfg.maxSymbolExposureLots);
   if(lots < mn) return 0.0;                     // cannot size safely -> skip
   return NormalizeDouble(lots,2);
  }

//+------------------------------------------------------------------+
bool CPropShield::ValidateOrder(const double entry,const double sl,const double tp,
                                const int dir,string &reason)
  {
   reason = "";
   if(sl <= 0)                    { reason="NO STOP LOSS - rejected";   return false; }
   if(dir>0 && sl >= entry)       { reason="long SL above entry";       return false; }
   if(dir<0 && sl <= entry)       { reason="short SL below entry";      return false; }
   if(tp>0 && dir>0 && tp<=entry) { reason="long TP below entry";       return false; }
   if(tp>0 && dir<0 && tp>=entry) { reason="short TP above entry";      return false; }

   long   stops = SymbolInfoInteger(_Symbol,SYMBOL_TRADE_STOPS_LEVEL);
   double pt    = SymbolInfoDouble(_Symbol,SYMBOL_POINT);
   if(MathAbs(entry-sl) < stops*pt) { reason="SL inside broker stop level"; return false; }
   return true;
  }

//+------------------------------------------------------------------+
void CPropShield::CloseAllPositions()
  {
   for(int i=PositionsTotal()-1; i>=0; i--)
     {
      ulong tk = PositionGetTicket(i);
      if(tk==0) continue;
      string sym = PositionGetString(POSITION_SYMBOL);
      MqlTradeRequest rq; MqlTradeResult rs;
      ZeroMemory(rq); ZeroMemory(rs);
      rq.action   = TRADE_ACTION_DEAL;
      rq.position = tk;
      rq.symbol   = sym;
      rq.volume   = PositionGetDouble(POSITION_VOLUME);
      rq.deviation= m_cfg.maxSlippagePoints;
      rq.type     = (PositionGetInteger(POSITION_TYPE)==POSITION_TYPE_BUY)
                    ? ORDER_TYPE_SELL : ORDER_TYPE_BUY;
      rq.price    = (rq.type==ORDER_TYPE_SELL) ? SymbolInfoDouble(sym,SYMBOL_BID)
                                               : SymbolInfoDouble(sym,SYMBOL_ASK);
      if(!OrderSend(rq,rs)) PrintFormat("[SHIELD] emergency close failed: %d",rs.retcode);
     }
  }

//+------------------------------------------------------------------+
double CPropShield::DailyPnLPct() const
  {
   if(m_dayStartEquity <= 0) return 0.0;
   return (AccountInfoDouble(ACCOUNT_EQUITY)-m_dayStartEquity)/m_dayStartEquity;
  }

double CPropShield::TotalPnLPct() const
  {
   if(m_initialBalance <= 0) return 0.0;
   return (AccountInfoDouble(ACCOUNT_EQUITY)-m_initialBalance)/m_initialBalance;
  }

double CPropShield::DistanceToFloorPct() const
  {
   double eq = AccountInfoDouble(ACCOUNT_EQUITY);
   if(eq <= 0) return 0.0;
   return (eq-FloorLevel())/eq;
  }

double CPropShield::ConsistencyRatio() const
  {
   if(m_totalProfit <= 0) return 0.0;
   return m_bestDayProfit / m_totalProfit;
  }

//+------------------------------------------------------------------+
void CPropShield::PrintStatus()
  {
   PrintFormat("[SHIELD] eq=%.2f day=%.2f%% tot=%.2f%% toFloor=%.2f%% consist=%.2f consecL=%d trades=%d days=%d %s",
               AccountInfoDouble(ACCOUNT_EQUITY),100*DailyPnLPct(),100*TotalPnLPct(),
               100*DistanceToFloorPct(),ConsistencyRatio(),m_consecLosses,m_tradesToday,m_tradingDays,
               m_halted ? ("HALTED: "+m_haltReason) : (m_haltedToday ? "stood down" : "active"));
  }
//+------------------------------------------------------------------+
