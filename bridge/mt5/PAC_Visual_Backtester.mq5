//+------------------------------------------------------------------+
//|                                     PAC_Visual_Backtester.mq5    |
//|                 PAC Scalper Institutional Strategy Tester EA     |
//|                       LLMTradingV2 Autonomous Architecture       |
//+------------------------------------------------------------------+
#property copyright "LLMTradingV2"
#property link      "https://github.com/arbuuuud/LLMTradingV2"
#property version   "2.30"
#property description "PAC Scalper Strategy Tester & Visual Inspector: Real PAC Channels, RBR/DBD Base Prioritization, 3-Layer Grid, Naruto 2 Summary Trailing, and Full Visual Chart HUD"

#include <Trade\Trade.mqh>
#include <Trade\PositionInfo.mqh>
#include <Trade\AccountInfo.mqh>
#include <Trade\OrderInfo.mqh>

//--- ENUM RISK PROFILE
enum ENUM_PAC_RISK_PROFILE
{
   PROFILE_PROP_FIRM,   // 🛡️ Prop Firm (0.25% Risk)
   PROFILE_SWEET_SPOT,  // 💎 Sweet Spot (0.50% Risk - Recommended)
   PROFILE_AGGRESSIVE,  // ⚡ Aggressive (1.00% Risk)
   PROFILE_YOLO,        // 🚀 YOLO (2.00% Risk)
   PROFILE_CUSTOM       // ⚙️ Custom Risk
};

//--- INPUT PARAMETERS
input group "=== Risk Profile & Capital Management ==="
input ENUM_PAC_RISK_PROFILE InpRiskProfile       = PROFILE_SWEET_SPOT; // Active Risk Profile Preset
input double                InpCustomRiskPct     = 0.50;               // Custom Risk Per Trade (%)
input ulong                 InpMagicNumber       = 1001;               // Expert Magic Number
input ulong                 InpDeviationPoints   = 20;                 // Max Slippage Deviation (points)

input group "=== PAC Engine Geometry & Lookback ==="
input int                   InpPACLookbackBars   = 20;                 // PAC Rolling Swings Lookback (Bars)
input double                InpDiscountThreshold = 0.25;               // Discount Buy Zone Ceiling (0-25%)
input double                InpPremiumThreshold  = 0.75;               // Premium Sell Zone Floor (75-100%)
input double                InpDynamicSLBuffer   = 0.25;               // Dynamic ATR/Range SL Buffer Multiplier (DEC-029)
input bool                  InpEnableRBRDBD      = true;               // Prioritize RBR/DBD Bases over Swings (DEC-032)
input int                   InpRBRDBDSearchBars  = 30;                 // RBR/DBD Base Scan Depth (Bars)

input group "=== 3-Layer Grid & Naruto 2 Trailing (DEC-033) ==="
input bool                  InpEnable3LayerGrid  = true;               // Simultaneous 3-Layer Grid
input double                InpWeightL1          = 0.25;               // Layer 1 Allocation (25% Bibir)
input double                InpWeightL2          = 0.35;               // Layer 2 Allocation (35% Tengah)
input double                InpWeightL3          = 0.40;               // Layer 3 Allocation (40% Dasar)
input bool                  InpEnableNaruto2     = true;               // Enable Naruto 2 Summary BEP + Trailing
input double                InpNaruto2TriggerPts = 2.00;               // Naruto 2 Trigger Distance above Summary BEP ($)
input double                InpNaruto2TrailDist  = 2.00;               // Naruto 2 Trailing Step Distance ($)

input group "=== Safeguard Protections ==="
input bool                  InpEnableAntiKnife   = true;               // Anti-Falling-Knife Directional Cooldown (DEC-031)
input int                   InpCooldownMinutes   = 15;                 // Cooldown Duration after Stop Loss (Minutes)

input group "=== Visual Chart Graphics (Strategy Tester Visual Mode) ==="
input bool                  InpDrawZones         = true;               // Draw Buy & Sell Institutional Zones
input bool                  InpDrawPACLines      = true;               // Draw Upper, Midpoint, Lower Channel Lines
input bool                  InpDrawGridLevels    = true;               // Draw L1, L2, L3 Pending Target Lines
input bool                  InpShowOnChartHUD    = true;               // Show Real-time HUD Status Board
input color                 InpColorBuyZone      = C'34,197,94';       // Buy Zone Color (Emerald Green)
input color                 InpColorSellZone     = C'239,68,68';       // Sell Zone Color (Rose Red)
input color                 InpColorEquilibrium  = C'251,191,36';      // Equilibrium 50% TP Color (Gold Amber)
input color                 InpColorHardSL       = C'220,38,38';       // Hard SL Color (Crimson)

#define PREFIX_PAC "PAC_VIS_"

//--- GLOBAL STRUCTURES
struct RBR_DBD_Base
{
   double   top;
   double   bottom;
   bool     is_dbd;
   datetime time;
   bool     used;
};

//--- GLOBAL VARIABLES
CTrade         m_trade;
CPositionInfo  m_position;
COrderInfo     m_order;
CAccountInfo   m_account;

datetime       m_last_bar_time      = 0;
datetime       m_buy_cooldown_until = 0;
datetime       m_sell_cooldown_until= 0;
string         m_last_direction     = "NEUTRAL";
datetime       m_last_order_time    = 0;

// Naruto 2 Trailing State
bool           m_n2_trailing_active = false;
double         m_n2_trail_sl        = 0.0;
double         m_n2_summary_bep     = 0.0;

//+------------------------------------------------------------------+
//| Expert initialization function                                   |
//+------------------------------------------------------------------+
int OnInit()
{
   m_trade.SetExpertMagicNumber(InpMagicNumber);
   m_trade.SetDeviationInPoints(InpDeviationPoints);

   // Configure broker filling mode
   uint filling = (uint)SymbolInfoInteger(_Symbol, SYMBOL_FILLING_MODE);
   if((filling & SYMBOL_FILLING_FOK) != 0)
      m_trade.SetTypeFilling(ORDER_FILLING_FOK);
   else if((filling & SYMBOL_FILLING_IOC) != 0)
      m_trade.SetTypeFilling(ORDER_FILLING_IOC);
   else
      m_trade.SetTypeFilling(ORDER_FILLING_RETURN);

   // Clear previous visual objects
   ObjectsDeleteAll(0, PREFIX_PAC);

   PrintFormat("[PAC Visual Tester] Initialized on %s. Risk Profile: %s. RBR/DBD: %s. Naruto 2: %s",
               _Symbol, EnumToString(InpRiskProfile), InpEnableRBRDBD ? "ON" : "OFF", InpEnableNaruto2 ? "ON" : "OFF");

   return(INIT_SUCCEEDED);
}

//+------------------------------------------------------------------+
//| Expert deinitialization function                                 |
//+------------------------------------------------------------------+
void OnDeinit(const int reason)
{
   ObjectsDeleteAll(0, PREFIX_PAC);
   Comment("");
}

//+------------------------------------------------------------------+
//| Calculate Lot Size based on Risk Profile                         |
//+------------------------------------------------------------------+
double GetActiveRiskPct()
{
   switch(InpRiskProfile)
   {
      case PROFILE_PROP_FIRM:  return 0.25;
      case PROFILE_SWEET_SPOT: return 0.50;
      case PROFILE_AGGRESSIVE: return 1.00;
      case PROFILE_YOLO:       return 2.00;
      default:                 return InpCustomRiskPct;
   }
}

double CalculateLot(double layer_weight, double sl_distance_points)
{
   double equity = AccountInfoDouble(ACCOUNT_EQUITY);
   if(equity <= 0 || sl_distance_points <= 0) return SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MIN);

   double total_risk_pct = GetActiveRiskPct();
   double layer_risk_pct = total_risk_pct * layer_weight;
   double risk_money = equity * (layer_risk_pct / 100.0);

   double tick_val = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_VALUE);
   double tick_sz  = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_SIZE);
   double pt       = SymbolInfoDouble(_Symbol, SYMBOL_POINT);

   double point_value = (tick_sz > 0) ? (tick_val * (pt / tick_sz)) : 1.0;
   double cost_per_lot = sl_distance_points * point_value;

   if(cost_per_lot <= 0) return SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MIN);

   double raw_lot = risk_money / cost_per_lot;

   // Normalize lot according to symbol specs
   double min_lot  = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MIN);
   double max_lot  = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MAX);
   double lot_step = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_STEP);

   double lot = MathMax(min_lot, MathMin(raw_lot, max_lot));
   lot = MathFloor(lot / lot_step) * lot_step;

   return NormalizeDouble(lot, 2);
}

//+------------------------------------------------------------------+
//| Scan for Fresh RBR and DBD Bases                                 |
//+------------------------------------------------------------------+
void ScanRBRDBDBases(MqlRates &rates[], int total_rates, RBR_DBD_Base &best_dbd, RBR_DBD_Base &best_rbr)
{
   best_dbd.used = true;
   best_rbr.used = true;

   int lookback = MathMin(InpRBRDBDSearchBars, total_rates - 3);

   for(int k = total_rates - 2; k >= total_rates - lookback; k--)
   {
      double leg_in_range = rates[k-1].high - rates[k-1].low;
      double leg_in_bear  = rates[k-1].open - rates[k-1].close;
      double leg_in_bull  = rates[k-1].close - rates[k-1].open;

      double base_range   = rates[k].high - rates[k].low;
      double base_body    = MathAbs(rates[k].close - rates[k].open);

      double leg_out_bear = rates[k+1].open - rates[k+1].close;
      double leg_out_bull = rates[k+1].close - rates[k+1].open;

      // 1. Detect DBD (Drop-Base-Drop)
      if(leg_in_bear > 0 && (leg_in_bear / MathMax(leg_in_range, 0.1) >= 0.40))
      {
         if(base_range > 0 && (base_body / base_range <= 0.50))
         {
            if(rates[k+1].close < rates[k].low && leg_out_bear > 0)
            {
               // Imbalance / FVG confirmation: High[k+1] < Low[k-1]
               if(rates[k+1].high < rates[k-1].low)
               {
                  best_dbd.top = rates[k].high;
                  best_dbd.bottom = rates[k].low;
                  best_dbd.is_dbd = true;
                  best_dbd.time = rates[k].time;
                  best_dbd.used = false;
                  break;
               }
            }
         }
      }

      // 2. Detect RBR (Rally-Base-Rally)
      if(leg_in_bull > 0 && (leg_in_bull / MathMax(leg_in_range, 0.1) >= 0.40))
      {
         if(base_range > 0 && (base_body / base_range <= 0.50))
         {
            if(rates[k+1].close > rates[k].high && leg_out_bull > 0)
            {
               // Imbalance / FVG confirmation: Low[k+1] > High[k-1]
               if(rates[k+1].low > rates[k-1].high)
               {
                  best_rbr.top = rates[k].high;
                  best_rbr.bottom = rates[k].low;
                  best_rbr.is_dbd = false;
                  best_rbr.time = rates[k].time;
                  best_rbr.used = false;
                  break;
               }
            }
         }
      }
   }
}

//+------------------------------------------------------------------+
//| Expert tick function                                             |
//+------------------------------------------------------------------+
void OnTick()
{
   double bid = SymbolInfoDouble(_Symbol, SYMBOL_BID);
   double ask = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
   double mid = (bid + ask) / 2.0;

   // 1. Active Naruto 2 Summary Trailing (DEC-033) & Position Guardian
   ManagePositions(mid);

   // 2. Check Bar Update for Strategy Logic
   datetime current_bar_time = iTime(_Symbol, PERIOD_M1, 0);
   bool is_new_bar = (current_bar_time != m_last_bar_time);

   if(!is_new_bar)
      return;

   m_last_bar_time = current_bar_time;

   // Copy rates for lookback
   MqlRates rates[];
   ArraySetAsSeries(rates, false);
   int copied = CopyRates(_Symbol, PERIOD_M1, 1, InpPACLookbackBars + InpRBRDBDSearchBars + 5, rates);
   if(copied < InpPACLookbackBars + 2)
      return;

   // Calculate Rolling Swings Lookback (Last N bars)
   int start_idx = copied - InpPACLookbackBars;
   double sw_high = rates[start_idx].high;
   double sw_low  = rates[start_idx].low;

   for(int i = start_idx; i < copied; i++)
   {
      if(rates[i].high > sw_high) sw_high = rates[i].high;
      if(rates[i].low < sw_low)   sw_low  = rates[i].low;
   }

   // Scan for RBR / DBD Bases (DEC-032)
   RBR_DBD_Base dbd_base = {};
   RBR_DBD_Base rbr_base = {};
   dbd_base.used = true;
   rbr_base.used = true;

   if(InpEnableRBRDBD)
   {
      ScanRBRDBDBases(rates, copied, dbd_base, rbr_base);
   }

   // Institutional PAC Quadrants
   double span = MathMax(1.0, sw_high - sw_low);
   double eq   = (sw_high + sw_low) / 2.0;

   double buy_zone_top    = sw_low + (span * InpDiscountThreshold);
   double buy_zone_bottom = sw_low;
   double sell_zone_bottom= sw_low + (span * InpPremiumThreshold);
   double sell_zone_top   = sw_high;

   string roof_desc = "Swing High Roof";
   string floor_desc = "Swing Low Floor";

   // Prioritize RBR / DBD within proximity (DEC-032)
   if(InpEnableRBRDBD)
   {
      if(!dbd_base.used && MathAbs(dbd_base.top - sw_high) <= 15.0 && dbd_base.bottom >= mid - 1.0)
      {
         sw_high = dbd_base.top;
         sell_zone_bottom = dbd_base.bottom;
         sell_zone_top = dbd_base.top;
         roof_desc = "★ Prioritized DBD Base";
      }

      if(!rbr_base.used && MathAbs(rbr_base.bottom - sw_low) <= 15.0 && rbr_base.top <= mid + 1.0)
      {
         sw_low = rbr_base.bottom;
         buy_zone_top = rbr_base.top;
         buy_zone_bottom = rbr_base.bottom;
         floor_desc = "★ Prioritized RBR Base";
      }

      span = MathMax(1.0, sw_high - sw_low);
      eq   = (sw_high + sw_low) / 2.0;
   }

   // Dynamic ATR / Range SL Buffer (DEC-029)
   double sl_buffer = MathMax(0.50, NormalizeDouble(span * (InpDynamicSLBuffer * 0.15), 2));
   double buy_sl    = NormalizeDouble(sw_low - 2.50 - sl_buffer, 2);
   double sell_sl   = NormalizeDouble(sw_high + 2.50 + sl_buffer, 2);

   // Determine Quadrant & Direction
   bool in_discount = (mid <= buy_zone_top);
   bool in_premium  = (mid >= sell_zone_bottom);

   string direction = "NEUTRAL";
   if(in_discount) direction = "BUY";
   else if(in_premium) direction = "SELL";

   // 3. Draw Chart Visuals (Zones, Lines, HUD)
   if(InpDrawZones)
      DrawVisualZones(buy_zone_bottom, buy_zone_top, sell_zone_bottom, sell_zone_top, eq, buy_sl, sell_sl);

   if(InpShowOnChartHUD)
      DrawHUD(direction, mid, sw_high, sw_low, eq, roof_desc, floor_desc);

   // 4. Execution Logic: 3-Layer Grid Limit Order Placement
   int total_positions = GetOurPositionsCount();
   int total_pending   = GetOurOrdersCount();

   if(total_positions == 0 && total_pending == 0)
   {
      datetime now_time = TimeCurrent();

      // Check Anti-Falling-Knife Cooldown (DEC-031)
      if(direction == "BUY" && InpEnableAntiKnife && now_time < m_buy_cooldown_until)
         return;
      if(direction == "SELL" && InpEnableAntiKnife && now_time < m_sell_cooldown_until)
         return;

      if(direction != "NEUTRAL")
      {
         m_last_direction = direction;
         m_last_order_time = now_time;

         // Place Simultaneous 3-Layer Grid (DEC-028 & DEC-033)
         double weights[3];
         weights[0] = InpWeightL1;
         weights[1] = InpWeightL2;
         weights[2] = InpWeightL3;

         if(direction == "BUY")
         {
            double target_levels[3];
            target_levels[0] = NormalizeDouble(MathMin(bid - 0.25, sw_low + span * 0.25), 2);  // L1 Bibir 25%
            target_levels[1] = NormalizeDouble(MathMin(bid - 0.50, sw_low + span * 0.125), 2); // L2 Mid 12.5%
            target_levels[2] = NormalizeDouble(MathMin(bid - 0.75, sw_low), 2);                // L3 Dasar 0%

            for(int k = 0; k < 3; k++)
            {
               double sl_dist_pts = MathMax(1.0, MathAbs(target_levels[k] - buy_sl)) / _Point;
               double lot = CalculateLot(weights[k], sl_dist_pts);
               m_trade.BuyLimit(lot, target_levels[k], _Symbol, buy_sl, eq, ORDER_TIME_GTC, 0, StringFormat("PAC_BUY_L%d", k+1));
            }
         }
         else if(direction == "SELL")
         {
            double target_levels[3];
            target_levels[0] = NormalizeDouble(MathMax(ask + 0.25, sw_low + span * 0.75), 2);  // L1 Bibir 75%
            target_levels[1] = NormalizeDouble(MathMax(ask + 0.50, sw_low + span * 0.875), 2); // L2 Mid 87.5%
            target_levels[2] = NormalizeDouble(MathMax(ask + 0.75, sw_high), 2);               // L3 Pucuk 100%

            for(int k = 0; k < 3; k++)
            {
               double sl_dist_pts = MathMax(1.0, MathAbs(target_levels[k] - sell_sl)) / _Point;
               double lot = CalculateLot(weights[k], sl_dist_pts);
               m_trade.SellLimit(lot, target_levels[k], _Symbol, sell_sl, eq, ORDER_TIME_GTC, 0, StringFormat("PAC_SELL_L%d", k+1));
            }
         }
      }
   }
}

//+------------------------------------------------------------------+
//| Multi-layer Position Guardian & Naruto 2 Trailing (DEC-033)      |
//+------------------------------------------------------------------+
void ManagePositions(double current_price)
{
   int pos_count = 0;
   double total_lots = 0.0;
   double weighted_entry_sum = 0.0;
   ENUM_POSITION_TYPE pos_type = POSITION_TYPE_BUY;

   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      if(m_position.SelectByIndex(i))
      {
         if(m_position.Magic() == InpMagicNumber && m_position.Symbol() == _Symbol)
         {
            pos_count++;
            pos_type = m_position.PositionType();
            double lots = m_position.Volume();
            total_lots += lots;
            weighted_entry_sum += (m_position.PriceOpen() * lots);
         }
      }
   }

   if(pos_count == 0)
   {
      m_n2_trailing_active = false;
      m_n2_trail_sl = 0.0;
      m_n2_summary_bep = 0.0;
      return;
   }

   // Naruto 2: When multiple layers are filled, calculate summary BEP
   if(InpEnableNaruto2 && pos_count >= 2 && total_lots > 0)
   {
      m_n2_summary_bep = NormalizeDouble(weighted_entry_sum / total_lots, 2);

      bool should_trail = false;
      double candidate_sl = 0.0;

      if(pos_type == POSITION_TYPE_BUY)
      {
         // Price reaches +$2.00 above summary BEP
         if(current_price >= m_n2_summary_bep + InpNaruto2TriggerPts)
         {
            should_trail = true;
            candidate_sl = MathMax(m_n2_summary_bep, NormalizeDouble(current_price - InpNaruto2TrailDist, 2));
         }
      }
      else if(pos_type == POSITION_TYPE_SELL)
      {
         // Price reaches -$2.00 below summary BEP
         if(current_price <= m_n2_summary_bep - InpNaruto2TriggerPts)
         {
            should_trail = true;
            candidate_sl = MathMin(m_n2_summary_bep, NormalizeDouble(current_price + InpNaruto2TrailDist, 2));
         }
      }

      if(should_trail)
      {
         bool update_needed = false;
         if(!m_n2_trailing_active)
         {
            m_n2_trailing_active = true;
            m_n2_trail_sl = candidate_sl;
            update_needed = true;
         }
         else
         {
            if(pos_type == POSITION_TYPE_BUY && candidate_sl > m_n2_trail_sl)
            {
               m_n2_trail_sl = candidate_sl;
               update_needed = true;
            }
            else if(pos_type == POSITION_TYPE_SELL && candidate_sl < m_n2_trail_sl)
            {
               m_n2_trail_sl = candidate_sl;
               update_needed = true;
            }
         }

         if(update_needed)
         {
            for(int i = PositionsTotal() - 1; i >= 0; i--)
            {
               if(m_position.SelectByIndex(i))
               {
                  if(m_position.Magic() == InpMagicNumber && m_position.Symbol() == _Symbol)
                  {
                     m_trade.PositionModify(m_position.Ticket(), m_n2_trail_sl, m_position.TakeProfit());
                  }
               }
            }
         }
      }
   }
}

//+------------------------------------------------------------------+
//| Draw Visual Zones on Strategy Tester Visual Chart                |
//+------------------------------------------------------------------+
void DrawVisualZones(double buy_btm, double buy_top, double sell_btm, double sell_top, double eq, double sl_buy, double sl_sell)
{
   datetime time_start = iTime(_Symbol, PERIOD_M1, InpPACLookbackBars);
   datetime time_end   = TimeCurrent() + 600; // 10 minutes forward

   // 1. Buy Zone (0% - 25% Discount)
   string obj_buy = PREFIX_PAC + "BUY_ZONE";
   if(ObjectFind(0, obj_buy) < 0)
   {
      ObjectCreate(0, obj_buy, OBJ_RECTANGLE, 0, time_start, buy_top, time_end, buy_btm);
      ObjectSetInteger(0, obj_buy, OBJPROP_COLOR, InpColorBuyZone);
      ObjectSetInteger(0, obj_buy, OBJPROP_STYLE, STYLE_SOLID);
      ObjectSetInteger(0, obj_buy, OBJPROP_WIDTH, 1);
      ObjectSetInteger(0, obj_buy, OBJPROP_BACK, true);
      ObjectSetInteger(0, obj_buy, OBJPROP_FILL, true);
   }
   else
   {
      ObjectSetDouble(0, obj_buy, OBJPROP_PRICE, 0, buy_top);
      ObjectSetDouble(0, obj_buy, OBJPROP_PRICE, 1, buy_btm);
      ObjectSetInteger(0, obj_buy, OBJPROP_TIME, 0, time_start);
      ObjectSetInteger(0, obj_buy, OBJPROP_TIME, 1, time_end);
   }

   // 2. Sell Zone (75% - 100% Premium)
   string obj_sell = PREFIX_PAC + "SELL_ZONE";
   if(ObjectFind(0, obj_sell) < 0)
   {
      ObjectCreate(0, obj_sell, OBJ_RECTANGLE, 0, time_start, sell_top, time_end, sell_btm);
      ObjectSetInteger(0, obj_sell, OBJPROP_COLOR, InpColorSellZone);
      ObjectSetInteger(0, obj_sell, OBJPROP_STYLE, STYLE_SOLID);
      ObjectSetInteger(0, obj_sell, OBJPROP_WIDTH, 1);
      ObjectSetInteger(0, obj_sell, OBJPROP_BACK, true);
      ObjectSetInteger(0, obj_sell, OBJPROP_FILL, true);
   }
   else
   {
      ObjectSetDouble(0, obj_sell, OBJPROP_PRICE, 0, sell_top);
      ObjectSetDouble(0, obj_sell, OBJPROP_PRICE, 1, sell_btm);
      ObjectSetInteger(0, obj_sell, OBJPROP_TIME, 0, time_start);
      ObjectSetInteger(0, obj_sell, OBJPROP_TIME, 1, time_end);
   }

   // 3. Equilibrium Line 50% TP
   string obj_eq = PREFIX_PAC + "EQ_LINE";
   if(ObjectFind(0, obj_eq) < 0)
   {
      ObjectCreate(0, obj_eq, OBJ_HLINE, 0, 0, eq);
      ObjectSetInteger(0, obj_eq, OBJPROP_COLOR, InpColorEquilibrium);
      ObjectSetInteger(0, obj_eq, OBJPROP_STYLE, STYLE_DOT);
      ObjectSetInteger(0, obj_eq, OBJPROP_WIDTH, 2);
   }
   else
   {
      ObjectSetDouble(0, obj_eq, OBJPROP_PRICE, 0, eq);
   }
}

//+------------------------------------------------------------------+
//| Draw On-Chart HUD Display                                        |
//+------------------------------------------------------------------+
void DrawHUD(string dir, double price, double roof, double floor, double eq, string roof_type, string floor_type)
{
   double equity  = AccountInfoDouble(ACCOUNT_EQUITY);
   double balance = AccountInfoDouble(ACCOUNT_BALANCE);
   double profit  = equity - balance;

   int pos_cnt = GetOurPositionsCount();
   int ord_cnt = GetOurOrdersCount();

   string hud = StringFormat(
      "=== PAC SCALPER INSTITUTIONAL V2.30 ===\n" +
      "Profile     : %s (Risk %.2f%%)\n" +
      "Live Price  : $%.2f | Direction: %s\n" +
      "Roof (Supply): $%.2f [%s]\n" +
      "Floor(Demand): $%.2f [%s]\n" +
      "Equilibrium : $%.2f (Target 50%% TP)\n" +
      "---------------------------------------\n" +
      "Active Trades : %d Positions | %d Pending Orders\n" +
      "Naruto 2 Trail: %s (Summary BEP: $%.2f)\n" +
      "Balance     : $%.2f | Equity: $%.2f\n" +
      "Floating PnL: %s$%.2f\n" +
      "Anti-Knife  : %s",
      EnumToString(InpRiskProfile), GetActiveRiskPct(),
      price, dir,
      roof, roof_type,
      floor, floor_type,
      eq,
      pos_cnt, ord_cnt,
      m_n2_trailing_active ? StringFormat("ACTIVE [SL: $%.2f]", m_n2_trail_sl) : "STANDBY",
      m_n2_summary_bep,
      balance, equity,
      profit >= 0 ? "+" : "", profit,
      InpEnableAntiKnife ? "GUARD ACTIVE (15m CD)" : "OFF"
   );

   Comment(hud);
}

//+------------------------------------------------------------------+
//| Helpers                                                          |
//+------------------------------------------------------------------+
int GetOurPositionsCount()
{
   int cnt = 0;
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      if(m_position.SelectByIndex(i))
         if(m_position.Magic() == InpMagicNumber && m_position.Symbol() == _Symbol)
            cnt++;
   }
   return cnt;
}

int GetOurOrdersCount()
{
   int cnt = 0;
   for(int i = OrdersTotal() - 1; i >= 0; i--)
   {
      if(m_order.SelectByIndex(i))
         if(m_order.Magic() == InpMagicNumber && m_order.Symbol() == _Symbol)
            cnt++;
   }
   return cnt;
}
