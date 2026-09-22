//+------------------------------------------------------------------+
//|                                       OrderBlock_Inspector.mq5   |
//|                 Master OrderBlock & S&D Visual Inspector         |
//|                                  LLMTradingV2 Institutional V2   |
//+------------------------------------------------------------------+
#property copyright "LLMTradingV2"
#property link      "https://github.com/arbuuuud/LLMTradingV2"
#property version   "2.10"
#property description "Master Institutional Inspector: Reversal OB (DBR/RBD), Continuation S&D (RBR/DBD with Leg-In/Base/Leg-Out rules), and Breaker Blocks"

//--- Inputs
input group "=== Category Display Switches ==="
input bool     InpShowReversalOB       = true;              // Show Reversal OB (+OB DBR / -OB RBD)
input bool     InpShowContinuationSD   = true;              // Show Continuation S&D (+Demand RBR / -Supply DBD)
input bool     InpShowBreakers         = false;             // Show Breaker Blocks (Optional - Default OFF)

input group "=== Continuation S&D Quality Filters ==="
input int      InpMaxBaseCandles       = 3;                 // Max Base Candles (Strict: 1 to 3)
input double   InpMinImpulseRatio      = 1.5;               // Min Impulse Ratio (Leg-Out / Base Range >= 1.5x)

input group "=== Proximity & Display Settings ==="
input int      InpMaxBars              = 1000;              // Max Bars to Analyze (Default 1000 for deep roof/floor search)
input int      InpMaxZonesAbove        = 2;                 // Max Nearest Zones Above Price (Roofs)
input int      InpMaxZonesBelow        = 2;                 // Max Nearest Zones Below Price (Floors)
input bool     InpShowMeanThreshold    = true;              // Draw 50% Mean Threshold (MT) Line

input group "=== Distinct Color Palette ==="
input color    InpColorBullOB          = C'30,144,255';     // [REVERSAL] +OB (DBR) - Royal DodgerBlue
input color    InpColorBearOB          = C'220,20,60';      // [REVERSAL] -OB (RBD) - Crimson Red
input color    InpColorContDemand      = C'46,139,87';      // [CONTINUATION] +Demand (RBR) - SeaGreen Teal
input color    InpColorContSupply      = C'218,165,32';     // [CONTINUATION] -Supply (DBD) - Goldenrod Amber
input color    InpColorBreakerBull     = C'0,235,235';      // [BREAKER FLIP] Bullish Support - Bright Cyan
input color    InpColorBreakerBear     = C'255,99,71';      // [BREAKER FLIP] Bearish Resistance - Tomato Orange
input color    InpColorInside          = C'255,255,255';    // [CURRENT INSIDE ZONE] Active Highlight - White

#define OBJ_PREFIX "OB_INSP_"

enum ENUM_ZONE_KIND
{
   ZONE_REVERSAL_DBR,      // Drop-Base-Rally (+OB Reversal)
   ZONE_REVERSAL_RBD,      // Rally-Base-Drop (-OB Reversal)
   ZONE_CONTINUATION_RBR,  // Rally-Base-Rally (+Demand Continuation)
   ZONE_CONTINUATION_DBD,  // Drop-Base-Drop (-Supply Continuation)
   ZONE_BREAKER_BULLISH,   // Breaker Block Support (Flipped from -OB)
   ZONE_BREAKER_BEARISH    // Breaker Block Resistance (Flipped from +OB)
};

struct ZoneItem
{
   string            id;
   ENUM_ZONE_KIND    kind;
   bool              is_bullish;          // Support vs Resistance
   double            top;
   double            bottom;
   double            mean_threshold;      // 50% Level
   datetime          time;
   int               bar_index;
   int               base_count;          // Number of base candles
   double            impulse_ratio;       // Leg-Out / Base Range
   bool              has_swept_liq;
   bool              is_breaker;
   datetime          breaker_time;
   bool              is_touched;
   int               touch_count;
   double            deepest_touch_price;
   bool              is_mitigated;        // Closed inside
   bool              is_fully_used;       // Swept 100%
   bool              is_inside;
   double            distance;
};

datetime g_last_bar_time = 0;

//+------------------------------------------------------------------+
//| Expert initialization function                                   |
//+------------------------------------------------------------------+
int OnInit()
{
   CleanObjects();
   RedrawZones();
   return(INIT_SUCCEEDED);
}

//+------------------------------------------------------------------+
//| Expert deinitialization function                                 |
//+------------------------------------------------------------------+
void OnDeinit(const int reason)
{
   CleanObjects();
   ChartRedraw();
}

void CleanObjects()
{
   ObjectsDeleteAll(0, OBJ_PREFIX);
}

void OnTick()
{
   datetime current_time = iTime(_Symbol, _Period, 0);
   if(current_time != g_last_bar_time)
   {
      g_last_bar_time = current_time;
      RedrawZones();
   }
}

//+------------------------------------------------------------------+
//| Core Detection Engine                                            |
//+------------------------------------------------------------------+
void RedrawZones()
{
   CleanObjects();

   int total_bars = iBars(_Symbol, _Period);
   int bars_to_check = MathMin(InpMaxBars, total_bars - 5);
   if(bars_to_check < 6) return;

   MqlRates rates[];
   ArraySetAsSeries(rates, true);
   if(CopyRates(_Symbol, _Period, 0, bars_to_check, rates) < bars_to_check) return;

   datetime current_candle_time = rates[0].time;
   double current_price = rates[0].close;

   ZoneItem raw_zones[];
   int raw_count = 0;

   // 1. Scan for displacement FVG (Leg-Out)
   for(int i = bars_to_check - 5; i >= 1; i--)
   {
      bool is_bull_fvg = (rates[i].low > rates[i + 2].high);
      bool is_bear_fvg = (rates[i].high < rates[i + 2].low);

      if(!is_bull_fvg && !is_bear_fvg) continue;

      int origin_idx = i + 2;
      if(is_bull_fvg)
      {
         if(rates[origin_idx].close > rates[origin_idx].open)
         {
            if(rates[origin_idx - 1].close < rates[origin_idx - 1].open) origin_idx = origin_idx - 1;
            else if(origin_idx + 1 < bars_to_check && rates[origin_idx + 1].close < rates[origin_idx + 1].open) origin_idx = origin_idx + 1;
         }
      }
      else if(is_bear_fvg)
      {
         if(rates[origin_idx].close < rates[origin_idx].open)
         {
            if(rates[origin_idx - 1].close > rates[origin_idx - 1].open) origin_idx = origin_idx - 1;
            else if(origin_idx + 1 < bars_to_check && rates[origin_idx + 1].close > rates[origin_idx + 1].open) origin_idx = origin_idx + 1;
         }
      }

      if(origin_idx >= bars_to_check - 2 || origin_idx < 1) continue;

      // Avoid duplicates
      bool dup = false;
      for(int d = 0; d < raw_count; d++)
      {
         if(raw_zones[d].bar_index == origin_idx) { dup = true; break; }
      }
      if(dup) continue;

      // 2. Base Anatomy: Count boring candles (up to InpMaxBaseCandles)
      int base_count = 1;
      double base_high = rates[origin_idx].high;
      double base_low  = rates[origin_idx].low;

      for(int b = 1; b < InpMaxBaseCandles; b++)
      {
         int check_b = origin_idx + b; // In reverse series, +b goes backward in time
         if(check_b >= bars_to_check - 1) break;

         double b_range = rates[check_b].high - rates[check_b].low;
         double b_body  = MathAbs(rates[check_b].close - rates[check_b].open);
         if(b_range > 0 && (b_body / b_range <= 0.50))
         {
            base_count++;
            base_high = MathMax(base_high, rates[check_b].high);
            base_low  = MathMin(base_low, rates[check_b].low);
         }
         else break;
      }

      // 3. Leg-Out Impulse Ratio
      int leg_out_idx = i + 1;
      double leg_out_range = rates[leg_out_idx].high - rates[leg_out_idx].low;
      double base_range = MathMax(base_high - base_low, _Point * 10);
      double imp_ratio = leg_out_range / base_range;

      // 4. Leg-In Analysis (Candle before base)
      int prior_idx = origin_idx + base_count;
      if(prior_idx >= bars_to_check) continue;

      bool is_prior_down = (rates[prior_idx].close < rates[prior_idx].open);
      bool is_prior_up   = (rates[prior_idx].close > rates[prior_idx].open);

      ZoneItem zone;
      zone.bar_index = origin_idx;
      zone.time = rates[origin_idx].time;
      zone.top = base_high;
      zone.bottom = base_low;
      zone.mean_threshold = (zone.top + zone.bottom) / 2.0;
      zone.base_count = base_count;
      zone.impulse_ratio = NormalizeDouble(imp_ratio, 1);
      zone.is_touched = false;
      zone.touch_count = 0;
      zone.deepest_touch_price = 0.0;
      zone.is_mitigated = false;
      zone.is_fully_used = false;
      zone.is_breaker = false;
      zone.breaker_time = 0;
      zone.is_inside = false;
      zone.distance = 0.0;

      if(is_bull_fvg)
      {
         zone.is_bullish = true;
         zone.has_swept_liq = (rates[origin_idx].low < rates[prior_idx].low);

         if(is_prior_down)
         {
            // Drop-Base-Rally (Reversal OB)
            zone.kind = ZONE_REVERSAL_DBR;
            zone.id = "OB_DBR_" + IntegerToString(origin_idx);
         }
         else
         {
            // Rally-Base-Rally (Continuation Demand)
            if(base_count > InpMaxBaseCandles || imp_ratio < InpMinImpulseRatio) continue; // Strict filter
            zone.kind = ZONE_CONTINUATION_RBR;
            zone.id = "SD_RBR_" + IntegerToString(origin_idx);
         }
      }
      else
      {
         zone.is_bullish = false;
         zone.has_swept_liq = (rates[origin_idx].high > rates[prior_idx].high);

         if(is_prior_up)
         {
            // Rally-Base-Drop (Reversal OB)
            zone.kind = ZONE_REVERSAL_RBD;
            zone.id = "OB_RBD_" + IntegerToString(origin_idx);
         }
         else
         {
            // Drop-Base-Drop (Continuation Supply)
            if(base_count > InpMaxBaseCandles || imp_ratio < InpMinImpulseRatio) continue; // Strict filter
            zone.kind = ZONE_CONTINUATION_DBD;
            zone.id = "SD_DBD_" + IntegerToString(origin_idx);
         }
      }

      // 5. Track Lifecycle down to bar 0
      for(int k = origin_idx - 1; k >= 0; k--)
      {
         bool is_closed_bar = (k >= 1);

         if(zone.is_bullish && !zone.is_breaker)
         {
            // Touch test
            if(rates[k].low <= zone.top && rates[k].high >= zone.bottom)
            {
               zone.is_touched = true;
               if(zone.touch_count == 0) { zone.touch_count = 1; zone.deepest_touch_price = rates[k].low; }
               else if(rates[k].low < zone.deepest_touch_price) { zone.touch_count++; zone.deepest_touch_price = rates[k].low; }
            }
            // Retested / Mitigated: candle closed inside zone (zone is tested but STILL VALID floor)
            if(is_closed_bar && rates[k].close <= zone.top && rates[k].close >= zone.bottom)
            {
               zone.is_mitigated = true;
            }
            // Invalidation: candle body closed BELOW bottom (floor broken!)
            if(is_closed_bar && rates[k].close < zone.bottom)
            {
               if(InpShowBreakers)
               {
                  zone.is_breaker = true;
                  zone.is_bullish = false; // Flipped to Bearish Resistance
                  zone.kind = ZONE_BREAKER_BEARISH;
                  zone.breaker_time = rates[k].time;
                  zone.is_mitigated = false;
                  zone.is_fully_used = false;
                  zone.touch_count = 0;
                  zone.deepest_touch_price = 0.0;
               }
               else
               {
                  zone.is_fully_used = true; // Floor officially broken / removed
               }
            }
         }
         else if(!zone.is_bullish && !zone.is_breaker)
         {
            // Bearish Touch test
            if(rates[k].high >= zone.bottom && rates[k].low <= zone.top)
            {
               zone.is_touched = true;
               if(zone.touch_count == 0) { zone.touch_count = 1; zone.deepest_touch_price = rates[k].high; }
               else if(rates[k].high > zone.deepest_touch_price) { zone.touch_count++; zone.deepest_touch_price = rates[k].high; }
            }
            // Retested / Mitigated: candle closed inside zone (zone is tested but STILL VALID roof)
            if(is_closed_bar && rates[k].close >= zone.bottom && rates[k].close <= zone.top)
            {
               zone.is_mitigated = true;
            }
            // Invalidation: candle body closed ABOVE top (roof broken!)
            if(is_closed_bar && rates[k].close > zone.top)
            {
               if(InpShowBreakers)
               {
                  zone.is_breaker = true;
                  zone.is_bullish = true; // Flipped to Bullish Support
                  zone.kind = ZONE_BREAKER_BULLISH;
                  zone.breaker_time = rates[k].time;
                  zone.is_mitigated = false;
                  zone.is_fully_used = false;
                  zone.touch_count = 0;
                  zone.deepest_touch_price = 0.0;
               }
               else
               {
                  zone.is_fully_used = true; // Roof officially broken / removed
               }
            }
         }
         else if(zone.is_breaker)
         {
            // Retest on Breaker
            if(zone.is_bullish)
            {
               if(rates[k].low <= zone.top && rates[k].high >= zone.bottom)
               {
                  zone.is_touched = true;
                  if(zone.touch_count == 0) { zone.touch_count = 1; zone.deepest_touch_price = rates[k].low; }
                  else if(rates[k].low < zone.deepest_touch_price) { zone.touch_count++; zone.deepest_touch_price = rates[k].low; }
               }
               if(is_closed_bar && rates[k].close < zone.bottom) zone.is_fully_used = true; // Breaker broken
            }
            else
            {
               if(rates[k].high >= zone.bottom && rates[k].low <= zone.top)
               {
                  zone.is_touched = true;
                  if(zone.touch_count == 0) { zone.touch_count = 1; zone.deepest_touch_price = rates[k].high; }
                  else if(rates[k].high > zone.deepest_touch_price) { zone.touch_count++; zone.deepest_touch_price = rates[k].high; }
               }
               if(is_closed_bar && rates[k].close > zone.top) zone.is_fully_used = true; // Breaker broken
            }
         }
      }

      ArrayResize(raw_zones, raw_count + 1);
      raw_zones[raw_count] = zone;
      raw_count++;
   }

   // 6. Proximity Filtering & Category Toggles
   int above_indices[];
   double above_dists[];
   int above_count = 0;

   int below_indices[];
   double below_dists[];
   int below_count = 0;

   int inside_idx = -1;

   for(int m = 0; m < raw_count; m++)
   {
      // Category Switches
      if(raw_zones[m].is_breaker)
      {
         if(!InpShowBreakers) continue;
      }
      else if(raw_zones[m].kind == ZONE_REVERSAL_DBR || raw_zones[m].kind == ZONE_REVERSAL_RBD)
      {
         if(!InpShowReversalOB) continue;
      }
      else if(raw_zones[m].kind == ZONE_CONTINUATION_RBR || raw_zones[m].kind == ZONE_CONTINUATION_DBD)
      {
         if(!InpShowContinuationSD) continue;
      }

      // Check if price is inside
      bool is_inside = (current_price >= raw_zones[m].bottom && current_price <= raw_zones[m].top);
      raw_zones[m].is_inside = is_inside;

      if(is_inside)
      {
         inside_idx = m;
         continue; // Protected
      }

      // Exclude dead zones that have been broken by body close past boundary
      if(raw_zones[m].is_fully_used) continue;

      if(raw_zones[m].bottom > current_price)
      {
         double d = raw_zones[m].bottom - current_price;
         ArrayResize(above_indices, above_count + 1);
         ArrayResize(above_dists, above_count + 1);
         above_indices[above_count] = m;
         above_dists[above_count] = d;
         above_count++;
      }
      else if(raw_zones[m].top < current_price)
      {
         double d = current_price - raw_zones[m].top;
         ArrayResize(below_indices, below_count + 1);
         ArrayResize(below_dists, below_count + 1);
         below_indices[below_count] = m;
         below_dists[below_count] = d;
         below_count++;
      }
   }

   // Sort Above
   for(int a = 0; a < above_count - 1; a++)
   {
      for(int b = a + 1; b < above_count; b++)
      {
         if(above_dists[b] < above_dists[a])
         {
            double td = above_dists[a]; above_dists[a] = above_dists[b]; above_dists[b] = td;
            int ti = above_indices[a]; above_indices[a] = above_indices[b]; above_indices[b] = ti;
         }
      }
   }

   // Sort Below
   for(int a = 0; a < below_count - 1; a++)
   {
      for(int b = a + 1; b < below_count; b++)
      {
         if(below_dists[b] < below_dists[a])
         {
            double td = below_dists[a]; below_dists[a] = below_dists[b]; below_dists[b] = td;
            int ti = below_indices[a]; below_indices[a] = below_indices[b]; below_indices[b] = ti;
         }
      }
   }

   // 7. Draw Rendered Zones
   if(inside_idx >= 0)
   {
      DrawZone(raw_zones[inside_idx], current_candle_time, "⚡ [CURRENT INSIDE ZONE]");
   }

   int render_above = MathMin(InpMaxZonesAbove, above_count);
   for(int a = 0; a < render_above; a++)
   {
      DrawZone(raw_zones[above_indices[a]], current_candle_time, "[Above #" + IntegerToString(a + 1) + "]");
   }

   int render_below = MathMin(InpMaxZonesBelow, below_count);
   for(int b = 0; b < render_below; b++)
   {
      DrawZone(raw_zones[below_indices[b]], current_candle_time, "[Below #" + IntegerToString(b + 1) + "]");
   }

   ChartRedraw();
}

//+------------------------------------------------------------------+
//| Graphic Renderer Helper                                          |
//+------------------------------------------------------------------+
void DrawZone(const ZoneItem &zone, datetime current_time, string prefix_tag)
{
   string id_str = IntegerToString(zone.time) + "_" + IntegerToString(zone.bar_index);
   string rect_name = OBJ_PREFIX + "BOX_" + id_str;
   string mt_line_name = OBJ_PREFIX + "MT_" + id_str;
   string text_name = OBJ_PREFIX + "LBL_" + id_str;

   color zone_color;
   string badge = "";

   switch(zone.kind)
   {
      case ZONE_REVERSAL_DBR:
         zone_color = InpColorBullOB;
         badge = "[REVERSAL OB] +OB (DBR)";
         break;
      case ZONE_REVERSAL_RBD:
         zone_color = InpColorBearOB;
         badge = "[REVERSAL OB] -OB (RBD)";
         break;
      case ZONE_CONTINUATION_RBR:
         zone_color = InpColorContDemand;
         badge = "[CONTINUATION] +Demand (RBR)";
         break;
      case ZONE_CONTINUATION_DBD:
         zone_color = InpColorContSupply;
         badge = "[CONTINUATION] -Supply (DBD)";
         break;
      case ZONE_BREAKER_BULLISH:
         zone_color = InpColorBreakerBull;
         badge = "⚡ [BREAKER FLIP] Support";
         break;
      case ZONE_BREAKER_BEARISH:
         zone_color = InpColorBreakerBear;
         badge = "⚡ [BREAKER FLIP] Resistance";
         break;
      default:
         zone_color = InpColorBullOB;
         badge = "[ZONE]";
         break;
   }

   datetime start_time = zone.is_breaker ? zone.breaker_time : zone.time;
   if(start_time == 0) start_time = zone.time;

   // 1. Rectangle Box
   ObjectCreate(0, rect_name, OBJ_RECTANGLE, 0, start_time, zone.top, current_time, zone.bottom);
   ObjectSetInteger(0, rect_name, OBJPROP_COLOR, zone.is_inside ? InpColorInside : zone_color);
   ObjectSetInteger(0, rect_name, OBJPROP_STYLE, zone.is_inside ? STYLE_SOLID : (zone.is_mitigated ? STYLE_DASH : STYLE_SOLID));
   ObjectSetInteger(0, rect_name, OBJPROP_WIDTH, zone.is_inside ? 2 : 1);
   ObjectSetInteger(0, rect_name, OBJPROP_BACK, true);
   ObjectSetInteger(0, rect_name, OBJPROP_FILL, true);

   // 2. Mean Threshold (50% MT) Line
   if(InpShowMeanThreshold)
   {
      ObjectCreate(0, mt_line_name, OBJ_TREND, 0, start_time, zone.mean_threshold, current_time, zone.mean_threshold);
      ObjectSetInteger(0, mt_line_name, OBJPROP_COLOR, zone_color);
      ObjectSetInteger(0, mt_line_name, OBJPROP_STYLE, STYLE_DOT);
      ObjectSetInteger(0, mt_line_name, OBJPROP_WIDTH, 1);
      ObjectSetInteger(0, mt_line_name, OBJPROP_RAY_RIGHT, false);
      ObjectSetInteger(0, mt_line_name, OBJPROP_BACK, false);
   }

   // 3. Informative Tag Label
   string label = prefix_tag + " " + badge;

   if(zone.kind == ZONE_CONTINUATION_RBR || zone.kind == ZONE_CONTINUATION_DBD)
   {
      label += " Base:" + IntegerToString(zone.base_count) + "c Imp:" + DoubleToString(zone.impulse_ratio, 1) + "x";
   }

   if(zone.has_swept_liq) label += " [Swept Liq]";

   if(zone.touch_count == 0)
   {
      label += " [Virgin]";
   }
   else if(zone.is_mitigated)
   {
      label += " [Tested x" + IntegerToString(zone.touch_count) + " @ " + DoubleToString(zone.deepest_touch_price, _Digits) + "]";
   }
   else
   {
      label += " [Wick Touch x" + IntegerToString(zone.touch_count) + " @ " + DoubleToString(zone.deepest_touch_price, _Digits) + "]";
   }

   label += " MT:" + DoubleToString(zone.mean_threshold, _Digits);

   ObjectCreate(0, text_name, OBJ_TEXT, 0, current_time, zone.mean_threshold);
   ObjectSetString(0, text_name, OBJPROP_TEXT, label);
   ObjectSetInteger(0, text_name, OBJPROP_COLOR, zone.is_inside ? InpColorInside : zone_color);
   ObjectSetInteger(0, text_name, OBJPROP_FONTSIZE, 8);
   ObjectSetInteger(0, text_name, OBJPROP_ANCHOR, ANCHOR_RIGHT_LOWER);
}
//+------------------------------------------------------------------+
