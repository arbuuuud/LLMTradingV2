//+------------------------------------------------------------------+
//|                                       OrderBlock_Inspector.mq5   |
//|                 Master OrderBlock & S&D Visual Inspector         |
//|                                  LLMTradingV2 Institutional V2   |
//+------------------------------------------------------------------+
#property copyright "LLMTradingV2"
#property link      "https://github.com/arbuuuud/LLMTradingV2"
#property version   "2.00"
#property description "Master Institutional Inspector for Order Blocks (OB), S&D Reversal (DBR/RBD), Continuation (RBR/DBD), and Breaker Blocks with Proximity Filtering"

//--- Inputs
input group "=== Proximity & Display Settings ==="
input int      InpMaxBars           = 300;               // Max Bars to Analyze
input int      InpMaxZonesAbove     = 2;                 // Max Nearest Zones Above Price
input int      InpMaxZonesBelow     = 2;                 // Max Nearest Zones Below Price
input bool     InpShowBreakers      = true;              // Display Breaker Blocks (Flipped OBs)
input bool     InpShowMeanThreshold = true;              // Draw 50% Mean Threshold (MT) Line

input group "=== Color Palette ==="
input color    InpColorBullOB       = C'30,144,255';     // Bullish OB (+OB / Demand) - DodgerBlue
input color    InpColorBearOB       = C'186,85,211';     // Bearish OB (-OB / Supply) - MediumOrchid
input color    InpColorBreakerBull  = C'0,220,220';      // Bullish Breaker Support - Cyan
input color    InpColorBreakerBear  = C'255,99,71';      // Bearish Breaker Resistance - Tomato / OrangeRed
input color    InpColorInside       = C'255,255,255';    // Active Inside Zone Highlight (White)

#define OBJ_PREFIX "OB_INSP_"

enum ENUM_OB_TYPE
{
   OB_REVERSAL_DBR,        // Drop-Base-Rally (+OB Reversal)
   OB_REVERSAL_RBD,        // Rally-Base-Drop (-OB Reversal)
   OB_CONTINUATION_RBR,    // Rally-Base-Rally (+OB Continuation)
   OB_CONTINUATION_DBD,    // Drop-Base-Drop (-OB Continuation)
   OB_BREAKER_BULLISH,     // Breaker Block Support (Flipped from -OB)
   OB_BREAKER_BEARISH      // Breaker Block Resistance (Flipped from +OB)
};

struct OrderBlockItem
{
   string            id;
   bool              is_bullish;          // Current effective trading role (True = Support/Buy, False = Resistance/Sell)
   ENUM_OB_TYPE      ob_type;
   double            top;
   double            bottom;
   double            mean_threshold;      // 50% Level
   datetime          time;
   int               bar_index;
   bool              has_swept_liq;
   bool              is_breaker;
   datetime          breaker_time;
   bool              is_touched;
   int               touch_count;
   double            deepest_touch_price;
   bool              is_mitigated;        // Candle body closed inside
   bool              is_fully_used;       // Wick/body penetrated 100% through opposite boundary
   bool              is_inside;           // Current live price is inside
   double            distance;
};

datetime g_last_bar_time = 0;

//+------------------------------------------------------------------+
//| Expert initialization function                                   |
//+------------------------------------------------------------------+
int OnInit()
{
   CleanObjects();
   RedrawOrderBlocks();
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

//+------------------------------------------------------------------+
//| Object cleanup helper                                            |
//+------------------------------------------------------------------+
void CleanObjects()
{
   ObjectsDeleteAll(0, OBJ_PREFIX);
}

//+------------------------------------------------------------------+
//| Expert tick function                                             |
//+------------------------------------------------------------------+
void OnTick()
{
   datetime current_time = iTime(_Symbol, _Period, 0);
   if(current_time != g_last_bar_time)
   {
      g_last_bar_time = current_time;
      RedrawOrderBlocks();
   }
}

//+------------------------------------------------------------------+
//| Core Detection & Drawing Engine                                  |
//+------------------------------------------------------------------+
void RedrawOrderBlocks()
{
   CleanObjects();

   int total_bars = iBars(_Symbol, _Period);
   int bars_to_check = MathMin(InpMaxBars, total_bars - 5);
   if(bars_to_check < 5) return;

   MqlRates rates[];
   ArraySetAsSeries(rates, true);
   if(CopyRates(_Symbol, _Period, 0, bars_to_check, rates) < bars_to_check) return;

   datetime current_candle_time = rates[0].time;
   double current_price = rates[0].close;

   OrderBlockItem raw_obs[];
   int raw_count = 0;

   // 1. Scan for displacement & FVG to identify origin Order Block candle
   for(int i = bars_to_check - 4; i >= 1; i--)
   {
      bool is_bull_fvg = (rates[i].low > rates[i + 2].high);
      bool is_bear_fvg = (rates[i].high < rates[i + 2].low);

      if(!is_bull_fvg && !is_bear_fvg) continue;

      // Base candle is typically at i + 2 (the left origin candle before displacement)
      int base_idx = i + 2;
      if(is_bull_fvg)
      {
         // Find down candle
         if(rates[base_idx].close > rates[base_idx].open)
         {
            if(rates[base_idx - 1].close < rates[base_idx - 1].open) base_idx = base_idx - 1;
            else if(base_idx + 1 < bars_to_check && rates[base_idx + 1].close < rates[base_idx + 1].open) base_idx = base_idx + 1;
         }
      }
      else if(is_bear_fvg)
      {
         // Find up candle
         if(rates[base_idx].close < rates[base_idx].open)
         {
            if(rates[base_idx - 1].close > rates[base_idx - 1].open) base_idx = base_idx - 1;
            else if(base_idx + 1 < bars_to_check && rates[base_idx + 1].close > rates[base_idx + 1].open) base_idx = base_idx + 1;
         }
      }

      if(base_idx >= bars_to_check - 1 || base_idx < 1) continue;

      // Avoid duplicate registrations of the same base candle
      bool duplicate = false;
      for(int d = 0; d < raw_count; d++)
      {
         if(raw_obs[d].bar_index == base_idx) { duplicate = true; break; }
      }
      if(duplicate) continue;

      // Classify Reversal vs Continuation based on prior candle
      int prior_idx = base_idx + 1;
      bool is_prior_down = (rates[prior_idx].close < rates[prior_idx].open);
      bool is_prior_up   = (rates[prior_idx].close > rates[prior_idx].open);

      OrderBlockItem ob;
      ob.bar_index = base_idx;
      ob.time = rates[base_idx].time;
      ob.top = rates[base_idx].high;
      ob.bottom = rates[base_idx].low;
      ob.mean_threshold = (ob.top + ob.bottom) / 2.0;
      ob.is_touched = false;
      ob.touch_count = 0;
      ob.deepest_touch_price = 0.0;
      ob.is_mitigated = false;
      ob.is_fully_used = false;
      ob.is_breaker = false;
      ob.breaker_time = 0;
      ob.is_inside = false;
      ob.distance = 0.0;

      if(is_bull_fvg)
      {
         ob.is_bullish = true;
         ob.ob_type = is_prior_down ? OB_REVERSAL_DBR : OB_CONTINUATION_RBR;
         ob.has_swept_liq = (rates[base_idx].low < rates[prior_idx].low);
         ob.id = "OB_BULL_" + IntegerToString(base_idx);
      }
      else
      {
         ob.is_bullish = false;
         ob.ob_type = is_prior_up ? OB_REVERSAL_RBD : OB_CONTINUATION_DBD;
         ob.has_swept_liq = (rates[base_idx].high > rates[prior_idx].high);
         ob.id = "OB_BEAR_" + IntegerToString(base_idx);
      }

      // 2. Track Lifecycle across subsequent bars down to bar 0
      for(int k = base_idx - 1; k >= 0; k--)
      {
         bool is_closed_bar = (k >= 1);

         if(ob.is_bullish && !ob.is_breaker)
         {
            // Touch test
            if(rates[k].low <= ob.top && rates[k].high >= ob.bottom)
            {
               ob.is_touched = true;
               if(ob.touch_count == 0)
               {
                  ob.touch_count = 1;
                  ob.deepest_touch_price = rates[k].low;
               }
               else if(rates[k].low < ob.deepest_touch_price)
               {
                  ob.touch_count++;
                  ob.deepest_touch_price = rates[k].low;
               }
            }

            // Mitigated (closed inside)
            if(is_closed_bar && rates[k].close <= ob.top && rates[k].close >= ob.bottom)
            {
               ob.is_mitigated = true;
            }

            // Fully used (swept 100% through bottom)
            if(rates[k].low <= ob.bottom)
            {
               ob.is_fully_used = true;
            }

            // Breaker Flip: body closed below bottom
            if(is_closed_bar && rates[k].close < ob.bottom)
            {
               ob.is_breaker = true;
               ob.is_bullish = false; // Now acts as Bearish Breaker Resistance
               ob.ob_type = OB_BREAKER_BEARISH;
               ob.breaker_time = rates[k].time;
               ob.is_mitigated = false; // Reset mitigation for its new breaker life
               ob.is_fully_used = false;
               ob.touch_count = 0;
               ob.deepest_touch_price = 0.0;
            }
         }
         else if(!ob.is_bullish && !ob.is_breaker)
         {
            // Bearish OB Touch test
            if(rates[k].high >= ob.bottom && rates[k].low <= ob.top)
            {
               ob.is_touched = true;
               if(ob.touch_count == 0)
               {
                  ob.touch_count = 1;
                  ob.deepest_touch_price = rates[k].high;
               }
               else if(rates[k].high > ob.deepest_touch_price)
               {
                  ob.touch_count++;
                  ob.deepest_touch_price = rates[k].high;
               }
            }

            // Mitigated (closed inside)
            if(is_closed_bar && rates[k].close >= ob.bottom && rates[k].close <= ob.top)
            {
               ob.is_mitigated = true;
            }

            // Fully used (swept 100% through top)
            if(rates[k].high >= ob.top)
            {
               ob.is_fully_used = true;
            }

            // Breaker Flip: body closed above top
            if(is_closed_bar && rates[k].close > ob.top)
            {
               ob.is_breaker = true;
               ob.is_bullish = true; // Now acts as Bullish Breaker Support
               ob.ob_type = OB_BREAKER_BULLISH;
               ob.breaker_time = rates[k].time;
               ob.is_mitigated = false;
               ob.is_fully_used = false;
               ob.touch_count = 0;
               ob.deepest_touch_price = 0.0;
            }
         }
         else if(ob.is_breaker)
         {
            // Retest tracking on Breaker Block
            if(ob.is_bullish) // Bullish Breaker Support
            {
               if(rates[k].low <= ob.top && rates[k].high >= ob.bottom)
               {
                  ob.is_touched = true;
                  if(ob.touch_count == 0) { ob.touch_count = 1; ob.deepest_touch_price = rates[k].low; }
                  else if(rates[k].low < ob.deepest_touch_price) { ob.touch_count++; ob.deepest_touch_price = rates[k].low; }
               }
               if(is_closed_bar && rates[k].close < ob.bottom) ob.is_fully_used = true;
            }
            else // Bearish Breaker Resistance
            {
               if(rates[k].high >= ob.bottom && rates[k].low <= ob.top)
               {
                  ob.is_touched = true;
                  if(ob.touch_count == 0) { ob.touch_count = 1; ob.deepest_touch_price = rates[k].high; }
                  else if(rates[k].high > ob.deepest_touch_price) { ob.touch_count++; ob.deepest_touch_price = rates[k].high; }
               }
               if(is_closed_bar && rates[k].close > ob.top) ob.is_fully_used = true;
            }
         }
      }

      ArrayResize(raw_obs, raw_count + 1);
      raw_obs[raw_count] = ob;
      raw_count++;
   }

   // 3. Proximity Filtering: Max 2 Above, Max 2 Below, + Current Inside Zone
   int above_indices[];
   double above_dists[];
   int above_count = 0;

   int below_indices[];
   double below_dists[];
   int below_count = 0;

   int inside_idx = -1;

   for(int m = 0; m < raw_count; m++)
   {
      if(raw_obs[m].is_breaker && !InpShowBreakers) continue;

      // Check if price is currently inside the zone
      bool is_inside = (current_price >= raw_obs[m].bottom && current_price <= raw_obs[m].top);
      raw_obs[m].is_inside = is_inside;

      if(is_inside)
      {
         inside_idx = m;
         continue; // Protected as inside zone
      }

      // Exclude fully used or mitigated zones from outer proximity list
      if(raw_obs[m].is_fully_used || raw_obs[m].is_mitigated) continue;

      if(raw_obs[m].bottom > current_price)
      {
         // Zone is above price
         double d = raw_obs[m].bottom - current_price;
         ArrayResize(above_indices, above_count + 1);
         ArrayResize(above_dists, above_count + 1);
         above_indices[above_count] = m;
         above_dists[above_count] = d;
         above_count++;
      }
      else if(raw_obs[m].top < current_price)
      {
         // Zone is below price
         double d = current_price - raw_obs[m].top;
         ArrayResize(below_indices, below_count + 1);
         ArrayResize(below_dists, below_count + 1);
         below_indices[below_count] = m;
         below_dists[below_count] = d;
         below_count++;
      }
   }

   // Sort Above candidates by ascending distance
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

   // Sort Below candidates by ascending distance
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

   // 4. Render Protected Zones
   int drawn_count = 0;

   // Draw Inside Zone if present
   if(inside_idx >= 0)
   {
      DrawOrderBlock(raw_obs[inside_idx], current_candle_time, "⚡ [CURRENT INSIDE ZONE]");
      drawn_count++;
   }

   // Draw up to InpMaxZonesAbove
   int render_above = MathMin(InpMaxZonesAbove, above_count);
   for(int a = 0; a < render_above; a++)
   {
      string prefix_tag = "[Above #" + IntegerToString(a + 1) + "]";
      DrawOrderBlock(raw_obs[above_indices[a]], current_candle_time, prefix_tag);
      drawn_count++;
   }

   // Draw up to InpMaxZonesBelow
   int render_below = MathMin(InpMaxZonesBelow, below_count);
   for(int b = 0; b < render_below; b++)
   {
      string prefix_tag = "[Below #" + IntegerToString(b + 1) + "]";
      DrawOrderBlock(raw_obs[below_indices[b]], current_candle_time, prefix_tag);
      drawn_count++;
   }

   ChartRedraw();
}

//+------------------------------------------------------------------+
//| Order Block Graphic Renderer Helper                              |
//+------------------------------------------------------------------+
void DrawOrderBlock(const OrderBlockItem &ob, datetime current_time, string prefix_tag)
{
   string id_str = IntegerToString(ob.time) + "_" + IntegerToString(ob.bar_index);
   string rect_name = OBJ_PREFIX + "BOX_" + id_str;
   string mt_line_name = OBJ_PREFIX + "MT_" + id_str;
   string text_name = OBJ_PREFIX + "LBL_" + id_str;

   color box_color;
   if(ob.is_breaker)
   {
      box_color = ob.is_bullish ? InpColorBreakerBull : InpColorBreakerBear;
   }
   else
   {
      box_color = ob.is_bullish ? InpColorBullOB : InpColorBearOB;
   }

   datetime start_time = ob.is_breaker ? ob.breaker_time : ob.time;
   if(start_time == 0) start_time = ob.time;

   // 1. Rectangle Box
   ObjectCreate(0, rect_name, OBJ_RECTANGLE, 0, start_time, ob.top, current_time, ob.bottom);
   ObjectSetInteger(0, rect_name, OBJPROP_COLOR, ob.is_inside ? InpColorInside : box_color);
   ObjectSetInteger(0, rect_name, OBJPROP_STYLE, ob.is_inside ? STYLE_SOLID : STYLE_DASH);
   ObjectSetInteger(0, rect_name, OBJPROP_WIDTH, ob.is_inside ? 2 : 1);
   ObjectSetInteger(0, rect_name, OBJPROP_BACK, true);
   ObjectSetInteger(0, rect_name, OBJPROP_FILL, true);

   // 2. 50% Mean Threshold (MT) Line
   if(InpShowMeanThreshold)
   {
      ObjectCreate(0, mt_line_name, OBJ_TREND, 0, start_time, ob.mean_threshold, current_time, ob.mean_threshold);
      ObjectSetInteger(0, mt_line_name, OBJPROP_COLOR, box_color);
      ObjectSetInteger(0, mt_line_name, OBJPROP_STYLE, STYLE_DOT);
      ObjectSetInteger(0, mt_line_name, OBJPROP_WIDTH, 1);
      ObjectSetInteger(0, mt_line_name, OBJPROP_RAY_RIGHT, false);
      ObjectSetInteger(0, mt_line_name, OBJPROP_BACK, false);
   }

   // 3. Informative Tag Label
   string label = prefix_tag + " ";
   if(ob.is_breaker)
   {
      label += (ob.is_bullish ? "⚡ [BULLISH BREAKER SUPPORT]" : "⚡ [BEARISH BREAKER RESISTANCE]");
   }
   else
   {
      switch(ob.ob_type)
      {
         case OB_REVERSAL_DBR:     label += "+OB (DBR Reversal)"; break;
         case OB_REVERSAL_RBD:     label += "-OB (RBD Reversal)"; break;
         case OB_CONTINUATION_RBR: label += "+OB (RBR Continuation)"; break;
         case OB_CONTINUATION_DBD: label += "-OB (DBD Continuation)"; break;
         default:                  label += (ob.is_bullish ? "+OB" : "-OB"); break;
      }
   }

   if(ob.has_swept_liq) label += " [Swept Liq]";

   if(ob.touch_count == 0)
   {
      label += " [Virgin]";
   }
   else
   {
      label += " [Touched x" + IntegerToString(ob.touch_count) + " @ " + DoubleToString(ob.deepest_touch_price, _Digits) + "]";
   }

   label += " MT: " + DoubleToString(ob.mean_threshold, _Digits);

   ObjectCreate(0, text_name, OBJ_TEXT, 0, current_time, ob.mean_threshold);
   ObjectSetString(0, text_name, OBJPROP_TEXT, label);
   ObjectSetInteger(0, text_name, OBJPROP_COLOR, ob.is_inside ? InpColorInside : box_color);
   ObjectSetInteger(0, text_name, OBJPROP_FONTSIZE, 8);
   ObjectSetInteger(0, text_name, OBJPROP_ANCHOR, ANCHOR_RIGHT_LOWER);
}
//+------------------------------------------------------------------+
