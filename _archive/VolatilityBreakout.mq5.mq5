//+------------------------------------------------------------------+
//| VolatilityBreakout.mq5                                           |
//| Session-based volatility breakout with trend filter              |
//+------------------------------------------------------------------+
#include <PropShield.mqh>

input group "=== Breakout Parameters ==="
input int      InpATRPeriod     = 14;     // ATR for channel width
input double   InpChannelMult   = 2.0;    // Keltner channel multiplier
input int      InpADXPeriod     = 14;     // ADX for trend strength
input double   InpADXThreshold  = 25;     // Minimum ADX to trade
input int      InpEMAPeriod     = 200;    // Trend filter EMA

input group "=== Session Parameters ==="
input int      InpSessionStart  = 7;      // London open (7 AM)
input int      InpSessionEnd    = 18;     // NY close (6 PM)
input bool     InpBlockFriday   = true;   // Block Friday after 5 PM

class CVolatilityBreakout  // <-- FIXED: Removed ": public CStrategyBase"
{
private:
   int      m_atrHandle, m_adxHandle, m_emaHandle;
   double   m_atr[], m_adx[], m_ema[];
   datetime m_lastTradeTime;
   int      m_cooldownBars;
   
public:
   bool     Init()
   {
      m_atrHandle = iATR(_Symbol, PERIOD_CURRENT, InpATRPeriod);
      m_adxHandle = iADX(_Symbol, PERIOD_CURRENT, InpADXPeriod);
      m_emaHandle = iMA(_Symbol, PERIOD_CURRENT, InpEMAPeriod, 0, MODE_EMA, PRICE_CLOSE);
      m_cooldownBars = 5;
      return (m_atrHandle != INVALID_HANDLE && m_adxHandle != INVALID_HANDLE && m_emaHandle != INVALID_HANDLE);
   }
   
   bool     IsInSession()
   {
      MqlDateTime dt;
      TimeToStruct(TimeCurrent(), dt);
      if(dt.hour < InpSessionStart || dt.hour >= InpSessionEnd) return false;
      if(InpBlockFriday && dt.day_of_week == 5 && dt.hour >= 17) return false;
      return true;
   }
   
   int      Signal()
   {
      if(!IsInSession()) return 0;
      
      CopyBuffer(m_atrHandle, 0, 0, 3, m_atr);
      CopyBuffer(m_adxHandle, 0, 0, 3, m_adx);
      CopyBuffer(m_emaHandle, 0, 0, 3, m_ema);
      
      double high = iHigh(_Symbol, PERIOD_CURRENT, 1);
      double low = iLow(_Symbol, PERIOD_CURRENT, 1);
      double close = iClose(_Symbol, PERIOD_CURRENT, 1);
      double price = SymbolInfoDouble(_Symbol, SYMBOL_BID);
      
      double middle = m_ema[0];
      double upper = middle + m_atr[0] * InpChannelMult;
      double lower = middle - m_atr[0] * InpChannelMult;
      
      bool trendUp = price > m_ema[0] && m_ema[0] > m_ema[1];
      bool trendDown = price < m_ema[0] && m_ema[0] < m_ema[1];
      bool strongTrend = m_adx[0] > InpADXThreshold;
      
      bool breakoutUp = close > upper;
      bool breakoutDown = close < lower;
      
      if(TimeCurrent() - m_lastTradeTime < m_cooldownBars * PeriodSeconds(PERIOD_CURRENT)) return 0;
      
      if(breakoutUp && trendUp && strongTrend) { m_lastTradeTime = TimeCurrent(); return 1; }
      if(breakoutDown && trendDown && strongTrend) { m_lastTradeTime = TimeCurrent(); return -1; }
      return 0;
   }
};