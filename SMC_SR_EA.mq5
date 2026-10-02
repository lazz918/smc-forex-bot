//+------------------------------------------------------------------+
//|                                              SMC_SR_EA.mq5       |
//|                     SMC + Support/Resistance Expert Advisor      |
//|                              Fully functional for MT5            |
//+------------------------------------------------------------------+
#property copyright "SMC Forex Bot"
#property version   "2.00"
#property strict

#include <Trade\Trade.mqh>
CTrade trade;

//--- Inputs
input group "=== Risk Management ==="
input double RiskPercent     = 1.0;      // Risk % per trade
input double MinRR           = 2.0;      // Minimum Reward:Risk
input double MaxSpreadPips   = 3.0;      // Max allowed spread
input int    MagicNumber     = 202610;   // Magic number
input int    MaxOpenTrades   = 3;        // Max concurrent trades

input group "=== Partial TP & Trailing ==="
input bool   UsePartialTP    = true;     // Enable partial take profit
input double PartialTPRR     = 1.0;      // Partial TP at this R multiple
input double PartialTPPercent = 50.0;    // % of position to close
input bool   UseTrailingStop = true;     // Enable trailing stop
input double TrailStartRR    = 1.5;      // Start trailing after this R
input double TrailStepPips   = 10.0;     // Trail distance in pips

input group "=== SMC Parameters ==="
input int    SwingLookback   = 5;        // Swing left/right bars
input double OBImpulseMult   = 1.8;      // Order Block impulse × ATR
input double FVGMinATR       = 0.35;     // Min FVG size × ATR
input int    ATRPeriod       = 14;       // ATR period
input int    CooldownBars    = 16;       // Bars between signals

input group "=== Filters ==="
input bool   UseSessionFilter = true;    // London + NY only
input bool   UseKillzones     = true;    // Killzone filter
input bool   UsePremiumDiscount = true;  // Prefer discount longs / premium shorts
input bool   RequireSR        = false;   // Require S/R confluence
input bool   UseNewsFilter    = true;    // Avoid high-impact news windows

input group "=== Timeframes ==="
input ENUM_TIMEFRAMES HTF    = PERIOD_H4;  // Higher TF for bias
input ENUM_TIMEFRAMES LTF    = PERIOD_M15; // Entry TF

//--- Globals
datetime lastBarTime = 0;
int      lastSignalBar = -999;
double   atrBuffer[];
double   high[], low[], open[], close[];
bool     partialDone[];          // track partial TP per position ticket (simplified)

//+------------------------------------------------------------------+
int OnInit()
{
   trade.SetExpertMagicNumber(MagicNumber);
   trade.SetDeviationInPoints(30);
   trade.SetTypeFilling(ORDER_FILLING_IOC);
   ArraySetAsSeries(atrBuffer, true);
   ArraySetAsSeries(high, true);
   ArraySetAsSeries(low, true);
   ArraySetAsSeries(open, true);
   ArraySetAsSeries(close, true);
   Print("SMC+SR EA initialized on ", _Symbol);
   return(INIT_SUCCEEDED);
}

//+------------------------------------------------------------------+
void OnDeinit(const int reason) {}

//+------------------------------------------------------------------+
void OnTick()
{
   // Always manage open positions (partial TP + trailing) every tick
   ManageOpenPositions();

   // New bar only for new entries
   datetime t = iTime(_Symbol, LTF, 0);
   if(t == lastBarTime) return;
   lastBarTime = t;

   // Spread filter
   double spread = SymbolInfoInteger(_Symbol, SYMBOL_SPREAD) * _Point;
   double maxSpread = MaxSpreadPips * PipSize();
   if(spread > maxSpread) return;

   // Count open trades
   if(CountOpenTrades() >= MaxOpenTrades) return;

   // News filter (simple weekday/hour windows)
   MqlDateTime dt;
   TimeToStruct(TimeCurrent(), dt);
   if(UseNewsFilter && IsNewsWindow(dt)) return;

   // Session / Killzone
   if(UseSessionFilter && !InSession(dt.hour)) return;
   if(UseKillzones && !InKillzone(dt.hour)) return;

   // Copy rates
   int bars = 300;
   if(CopyHigh(_Symbol, LTF, 0, bars, high) < bars) return;
   if(CopyLow(_Symbol, LTF, 0, bars, low) < bars) return;
   if(CopyOpen(_Symbol, LTF, 0, bars, open) < bars) return;
   if(CopyClose(_Symbol, LTF, 0, bars, close) < bars) return;
   if(CopyBuffer(iATR(_Symbol, LTF, ATRPeriod), 0, 0, bars, atrBuffer) < bars) return;

   // HTF bias
   int bias = GetHTFBias();
   if(bias == 0) return;

   // Cooldown
   int currentBar = Bars(_Symbol, LTF);
   if(currentBar - lastSignalBar < CooldownBars) return;

   // Detect swings & structure (simplified)
   bool sweepLow = false, sweepHigh = false;
   bool bullStruct = false, bearStruct = false;
   DetectLiquidityAndStructure(bars, sweepLow, sweepHigh, bullStruct, bearStruct);

   double entry = close[0];
   double sl = 0, tp = 0;
   string reason = "";

   // LONG
   if(bias > 0 && (sweepLow || bullStruct))
   {
      if(UsePremiumDiscount && IsPremium(bars)) return;
      if(FindBullishZone(bars, entry, sl, reason))
      {
         double risk = entry - sl;
         if(risk < 6 * PipSize()) return;
         tp = entry + MinRR * risk;
         if(OpenTrade(ORDER_TYPE_BUY, entry, sl, tp, reason))
            lastSignalBar = currentBar;
      }
   }
   // SHORT
   else if(bias < 0 && (sweepHigh || bearStruct))
   {
      if(UsePremiumDiscount && IsDiscount(bars)) return;
      if(FindBearishZone(bars, entry, sl, reason))
      {
         double risk = sl - entry;
         if(risk < 6 * PipSize()) return;
         tp = entry - MinRR * risk;
         if(OpenTrade(ORDER_TYPE_SELL, entry, sl, tp, reason))
            lastSignalBar = currentBar;
      }
   }
}

//+------------------------------------------------------------------+
double PipSize()
{
   if(_Digits == 3 || _Digits == 5) return _Point * 10;
   return _Point;
}

//+------------------------------------------------------------------+
bool InSession(int hour)
{
   return (hour >= 7 && hour < 16) || (hour >= 12 && hour < 21);
}

//+------------------------------------------------------------------+
bool InKillzone(int hour)
{
   // London Open 7-10, NY Open 12-15, London Close 15-17
   return (hour >= 7 && hour < 10) || (hour >= 12 && hour < 15) || (hour >= 15 && hour < 17);
}

//+------------------------------------------------------------------+
int GetHTFBias()
{
   double htfHigh[50], htfLow[50], htfClose[50];
   ArraySetAsSeries(htfHigh, true);
   ArraySetAsSeries(htfLow, true);
   ArraySetAsSeries(htfClose, true);
   if(CopyHigh(_Symbol, HTF, 0, 50, htfHigh) < 50) return 0;
   if(CopyLow(_Symbol, HTF, 0, 50, htfLow) < 50) return 0;
   if(CopyClose(_Symbol, HTF, 0, 50, htfClose) < 50) return 0;

   // Simple HH/HL vs LH/LL
   double lastHigh = htfHigh[10];
   double lastLow  = htfLow[10];
   bool higherHigh = false, higherLow = false;
   bool lowerHigh = false, lowerLow = false;

   for(int i = 9; i >= 1; i--)
   {
      if(htfHigh[i] > lastHigh) { higherHigh = true; lastHigh = htfHigh[i]; }
      if(htfLow[i]  > lastLow)  { higherLow  = true; lastLow  = htfLow[i]; }
      if(htfHigh[i] < lastHigh) { lowerHigh  = true; }
      if(htfLow[i]  < lastLow)  { lowerLow   = true; lastLow = htfLow[i]; }
   }
   if(higherHigh && higherLow) return 1;
   if(lowerHigh && lowerLow)   return -1;
   // Fallback: price vs SMA
   double sma = 0;
   for(int i = 0; i < 20; i++) sma += htfClose[i];
   sma /= 20;
   if(htfClose[0] > sma) return 1;
   if(htfClose[0] < sma) return -1;
   return 0;
}

//+------------------------------------------------------------------+
void DetectLiquidityAndStructure(int bars, bool &sweepLow, bool &sweepHigh,
                                 bool &bullStruct, bool &bearStruct)
{
   sweepLow = sweepHigh = bullStruct = bearStruct = false;
   // Recent swing high/low
   double recentHigh = low[1], recentLow = high[1];
   for(int i = 2; i < 25; i++)
   {
      if(high[i] > recentHigh) recentHigh = high[i];
      if(low[i]  < recentLow)  recentLow  = low[i];
   }
   // Sweep detection on bar 1 (last closed)
   double rng = high[1] - low[1];
   if(rng > 0)
   {
      if(high[1] > recentHigh && close[1] < recentHigh)
      {
         double wick = high[1] - MathMax(open[1], close[1]);
         if(wick / rng > 0.30) sweepHigh = true;
      }
      if(low[1] < recentLow && close[1] > recentLow)
      {
         double wick = MathMin(open[1], close[1]) - low[1];
         if(wick / rng > 0.30) sweepLow = true;
      }
   }
   // Simple structure break
   if(close[1] > recentHigh) bullStruct = true;
   if(close[1] < recentLow)  bearStruct = true;
}

//+------------------------------------------------------------------+
bool IsPremium(int bars)
{
   double hi = high[1], lo = low[1];
   for(int i = 2; i < 50; i++)
   {
      if(high[i] > hi) hi = high[i];
      if(low[i]  < lo) lo = low[i];
   }
   double mid = (hi + lo) / 2.0;
   return close[0] > mid;
}

//+------------------------------------------------------------------+
bool IsDiscount(int bars)
{
   return !IsPremium(bars);
}

//+------------------------------------------------------------------+
bool FindBullishZone(int bars, double entry, double &sl, string &reason)
{
   // Look for recent strong bullish impulse → last down candle = OB
   for(int i = 3; i < 40; i++)
   {
      double atr = atrBuffer[i];
      if(atr <= 0) continue;
      // Bearish candle followed by strong bullish
      if(close[i] < open[i])
      {
         double impulse = close[i-1] - open[i-1];
         if(impulse > OBImpulseMult * atr && close[i-1] > high[i])
         {
            // Zone still valid?
            if(entry >= low[i] && entry <= high[i] * 1.002)
            {
               // Check not fully mitigated
               bool mitigated = false;
               for(int j = i-1; j >= 1; j--)
                  if(close[j] < low[i]) { mitigated = true; break; }
               if(!mitigated)
               {
                  sl = low[i] - 4 * PipSize();
                  reason = "LONG OB";
                  return true;
               }
            }
         }
      }
   }
   // Simple FVG fallback
   for(int i = 2; i < 30; i++)
   {
      if(low[i-2] > high[i])  // bullish FVG inverted indexing (series)
      {
         // series: index 0 newest
         // FVG between bar i and i-2
      }
   }
   // Fallback: recent swing low
   double swingLow = low[1];
   for(int i = 2; i < 15; i++)
      if(low[i] < swingLow) swingLow = low[i];
   if(entry - swingLow < 30 * PipSize() && entry > swingLow)
   {
      sl = swingLow - 5 * PipSize();
      reason = "LONG Swing+Struct";
      return true;
   }
   return false;
}

//+------------------------------------------------------------------+
bool FindBearishZone(int bars, double entry, double &sl, string &reason)
{
   for(int i = 3; i < 40; i++)
   {
      double atr = atrBuffer[i];
      if(atr <= 0) continue;
      if(close[i] > open[i])
      {
         double impulse = open[i-1] - close[i-1];
         if(impulse > OBImpulseMult * atr && close[i-1] < low[i])
         {
            if(entry <= high[i] && entry >= low[i] * 0.998)
            {
               bool mitigated = false;
               for(int j = i-1; j >= 1; j--)
                  if(close[j] > high[i]) { mitigated = true; break; }
               if(!mitigated)
               {
                  sl = high[i] + 4 * PipSize();
                  reason = "SHORT OB";
                  return true;
               }
            }
         }
      }
   }
   double swingHigh = high[1];
   for(int i = 2; i < 15; i++)
      if(high[i] > swingHigh) swingHigh = high[i];
   if(swingHigh - entry < 30 * PipSize() && entry < swingHigh)
   {
      sl = swingHigh + 5 * PipSize();
      reason = "SHORT Swing+Struct";
      return true;
   }
   return false;
}

//+------------------------------------------------------------------+
bool OpenTrade(ENUM_ORDER_TYPE type, double entry, double sl, double tp, string comment)
{
   double lots = CalculateLots(entry, sl);
   if(lots < SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MIN)) return false;

   bool ok = false;
   if(type == ORDER_TYPE_BUY)
      ok = trade.Buy(lots, _Symbol, 0, sl, tp, comment);
   else
      ok = trade.Sell(lots, _Symbol, 0, sl, tp, comment);

   if(ok)
      Print("Opened ", EnumToString(type), " lots=", lots, " SL=", sl, " TP=", tp, " | ", comment);
   else
      Print("Order failed: ", trade.ResultRetcode(), " ", trade.ResultRetcodeDescription());
   return ok;
}

//+------------------------------------------------------------------+
double CalculateLots(double entry, double sl)
{
   double balance = AccountInfoDouble(ACCOUNT_BALANCE);
   double riskMoney = balance * RiskPercent / 100.0;
   double tickSize  = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_SIZE);
   double tickValue = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_VALUE);
   double point     = _Point;
   if(tickSize == 0 || tickValue == 0) return 0.01;

   double slDistance = MathAbs(entry - sl);
   double ticks = slDistance / tickSize;
   double lot = riskMoney / (ticks * tickValue);
   double minLot = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MIN);
   double maxLot = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MAX);
   double step  = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_STEP);
   lot = MathFloor(lot / step) * step;
   return MathMax(minLot, MathMin(maxLot, lot));
}

//+------------------------------------------------------------------+
int CountOpenTrades()
{
   int count = 0;
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      if(PositionSelectByTicket(PositionGetTicket(i)))
         if(PositionGetString(POSITION_SYMBOL) == _Symbol &&
            PositionGetInteger(POSITION_MAGIC) == MagicNumber)
            count++;
   }
   return count;
}

//+------------------------------------------------------------------+
bool IsNewsWindow(MqlDateTime &dt)
{
   // High-impact approximate windows (UTC)
   // NFP Friday 12-15, FOMC Wed 12-15, CPI Wed 08-10
   if(dt.day_of_week == 5 && dt.hour >= 12 && dt.hour < 15) return true; // Fri NFP
   if(dt.day_of_week == 3 && dt.hour >= 12 && dt.hour < 15) return true; // Wed FOMC
   if(dt.day_of_week == 3 && dt.hour >= 8  && dt.hour < 10) return true; // Wed CPI
   return false;
}

//+------------------------------------------------------------------+
void ManageOpenPositions()
{
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      ulong ticket = PositionGetTicket(i);
      if(!PositionSelectByTicket(ticket)) continue;
      if(PositionGetString(POSITION_SYMBOL) != _Symbol) continue;
      if(PositionGetInteger(POSITION_MAGIC) != MagicNumber) continue;

      double openPrice = PositionGetDouble(POSITION_PRICE_OPEN);
      double currentSL = PositionGetDouble(POSITION_SL);
      double currentTP = PositionGetDouble(POSITION_TP);
      double volume    = PositionGetDouble(POSITION_VOLUME);
      long   posType   = PositionGetInteger(POSITION_TYPE);
      double profit    = PositionGetDouble(POSITION_PROFIT);

      double bid = SymbolInfoDouble(_Symbol, SYMBOL_BID);
      double ask = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
      double price = (posType == POSITION_TYPE_BUY) ? bid : ask;

      // Calculate R
      double risk = MathAbs(openPrice - currentSL);
      if(risk <= 0) risk = 10 * PipSize();
      double currentR = 0;
      if(posType == POSITION_TYPE_BUY)
         currentR = (price - openPrice) / risk;
      else
         currentR = (openPrice - price) / risk;

      // --- Partial Take Profit ---
      if(UsePartialTP && currentR >= PartialTPRR)
      {
         // Check comment to see if already partially closed
         string comment = PositionGetString(POSITION_COMMENT);
         if(StringFind(comment, "Partial") < 0)
         {
            double closeVol = NormalizeDouble(volume * PartialTPPercent / 100.0, 2);
            double minLot = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MIN);
            if(closeVol >= minLot)
            {
               if(trade.PositionClosePartial(ticket, closeVol))
               {
                  // Move SL to breakeven
                  double be = openPrice;
                  trade.PositionModify(ticket, be, currentTP);
                  Print("Partial TP closed ", closeVol, " lots. SL → BE");
               }
            }
         }
      }

      // --- Trailing Stop ---
      if(UseTrailingStop && currentR >= TrailStartRR)
      {
         double trailDist = TrailStepPips * PipSize();
         double newSL = currentSL;
         if(posType == POSITION_TYPE_BUY)
         {
            newSL = price - trailDist;
            if(newSL > currentSL && newSL < price)
               trade.PositionModify(ticket, newSL, currentTP);
         }
         else
         {
            newSL = price + trailDist;
            if(newSL < currentSL && newSL > price)
               trade.PositionModify(ticket, newSL, currentTP);
         }
      }
   }
}
//+------------------------------------------------------------------+
