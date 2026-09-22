//+------------------------------------------------------------------+
//|                                       Structure_Inspector.mq5    |
//|  Unified Market Structure: Swings, HH/HL/LH/LL, BOS, CHoCH & Fibo|
//|                    Dual Fibo: Active Leg & Previous Completed Leg|
//|                                  LLMTradingV2 Institutional V2   |
//+------------------------------------------------------------------+
#property copyright "LLMTradingV2"
#property link      "https://github.com/arbuuuud/LLMTradingV2"
#property version   "2.20"
#property description "Unified Market Structure & Dual Fibo: Swings, HH/HL/LH/LL, BOS, CHoCH, and DUAL FIBO (Active Leg + Previous Completed Leg TP Targets)"

//--- Inputs
input group "=== Fractal Swing Settings ==="
input int      InpSwingWindow          = 3;           // Fractal Window (Bars Left & Right)
input int      InpMaxBars              = 300;         // Max Bars to Analyze
input bool     InpShowZigZagLines      = true;        // Draw Structure Wave Lines (High-Low)
input color    InpColorZigZag          = C'71,85,105';// Structure Wave Line Color (Slate)

input group "=== Swing Labels & Colors ==="
input bool     InpShowHH_LL_Labels     = true;        // Classify HH, HL, LH, LL
input color    InpColorHigherHigh      = C'34,197,94'; // Higher High (Green)
input color    InpColorLowerHigh       = C'239,68,68'; // Lower High (Red)
input color    InpColorHigherLow       = C'16,185,129';// Higher Low (Emerald)
input color    InpColorLowerLow        = C'244,63,94'; // Lower Low (Rose)
input int      InpLabelFontSize        = 8;           // Font Size for Labels

input group "=== Fibonacci on Swings ==="
input bool     InpShowFiboRetrace      = true;        // Show Retracement % on Swings (HL/LH)
input bool     InpShowFiboExtension    = true;        // Show Extension % on Swings (HH/LL)

input group "=== 1. Active Leg Live Fibo (In-Progress) ==="
input bool     InpShowActiveFibo       = true;        // Show Active In-Progress Leg Zones
input color    InpColorActiveShallow   = C'30,58,138';// Active 38.2% - 50.0% Zone (Dark Blue Fill)
input color    InpColorActiveOTE       = C'6,78,59';  // Active 61.8% - 78.6% Golden OTE Zone (Dark Emerald Fill)
input color    InpColorActiveEQ        = clrYellow;   // Active 50.0% Equilibrium Line
input color    InpColorActiveExt       = C'168,85,247';// Active Extension Target Lines (Purple)

input group "=== 2. Previous Completed Leg Fibo (TP Tracker) ==="
input bool     InpShowPrevFibo         = true;        // Show Previous Completed Leg Fibo Targets
input color    InpColorPrevExt1272     = clrGold;     // Previous Leg TP1 (1.272 Ext) Line
input color    InpColorPrevExt1618     = C'249,115,22';// Previous Leg TP2 (1.618 Golden Ext) Line
input color    InpColorPrevOTE         = C'100,116,139';// Previous Leg OTE Boundary (Slate)

input group "=== BOS & CHoCH Settings ==="
input bool     InpShowBOS              = true;        // Show Break of Structure (BOS)
input color    InpColorBOS             = C'59,130,246';// BOS Line Color (Blue)
input bool     InpShowCHoCH            = true;        // Show Change of Character (CHoCH)
input color    InpColorCHoCH           = C'217,70,239';// CHoCH Line Color (Fuchsia)
input bool     InpShowStrongWeak       = true;        // Mark Strong Low / Strong High

#define OBJ_PREFIX "STR_INSP_"

enum ENUM_TREND
{
   TREND_RANGING = 0,
   TREND_BULLISH = 1,
   TREND_BEARISH = -1
};

struct SwingNode
{
   bool     is_high;
   double   price;
   datetime time;
   int      bar_idx;
   string   label;       // "SH", "HH", "LH", "EQH", "SL", "HL", "LL", "EQL"
   string   fibo_tag;    // e.g. "[61.8% OTE]" or "[1.272 Ext]"
   color    clr;
};

datetime g_last_bar_time = 0;

int OnInit()
{
   CleanObjects();
   RedrawStructure();
   return(INIT_SUCCEEDED);
}

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
      RedrawStructure();
   }
}

void RedrawStructure()
{
   CleanObjects();

   int total_bars = iBars(_Symbol, _Period);
   int bars_to_check = MathMin(InpMaxBars, total_bars - InpSwingWindow - 1);
   if(bars_to_check < InpSwingWindow * 2 + 1) return;

   MqlRates rates[];
   ArraySetAsSeries(rates, true);
   if(CopyRates(_Symbol, _Period, 0, bars_to_check, rates) < bars_to_check) return;

   // 1. Detect Fractal Swings chronologically
   SwingNode swings[];
   ArrayResize(swings, 0);

   for(int i = bars_to_check - InpSwingWindow - 1; i >= InpSwingWindow; i--)
   {
      // Check Swing High
      bool is_sh = true;
      double h = rates[i].high;
      for(int w = 1; w <= InpSwingWindow; w++)
      {
         if(rates[i - w].high >= h || rates[i + w].high >= h) { is_sh = false; break; }
      }

      // Check Swing Low
      bool is_sl = true;
      double l = rates[i].low;
      for(int w = 1; w <= InpSwingWindow; w++)
      {
         if(rates[i - w].low <= l || rates[i + w].low <= l) { is_sl = false; break; }
      }

      if(is_sh)
      {
         int sz = ArraySize(swings);
         ArrayResize(swings, sz + 1);
         swings[sz].is_high   = true;
         swings[sz].price     = h;
         swings[sz].time      = rates[i].time;
         swings[sz].bar_idx   = i;
         swings[sz].label     = "SH";
         swings[sz].fibo_tag  = "";
         swings[sz].clr       = InpColorHigherHigh;
      }

      if(is_sl)
      {
         int sz = ArraySize(swings);
         ArrayResize(swings, sz + 1);
         swings[sz].is_high   = false;
         swings[sz].price     = l;
         swings[sz].time      = rates[i].time;
         swings[sz].bar_idx   = i;
         swings[sz].label     = "SL";
         swings[sz].fibo_tag  = "";
         swings[sz].clr       = InpColorHigherLow;
      }
   }

   int total_swings = ArraySize(swings);
   if(total_swings == 0) return;

   // 2. Classify HH/HL/LH/LL and Calculate Fibo Retracement & Extension
   double prev_sh_p = 0;
   double prev_sl_p = 0;

   for(int s = 0; s < total_swings; s++)
   {
      if(swings[s].is_high)
      {
         double cur_h = swings[s].price;
         if(prev_sh_p <= 0)
         {
            swings[s].label = "SH";
            swings[s].clr   = InpColorHigherHigh;
         }
         else if(cur_h > prev_sh_p)
         {
            swings[s].label = "HH";
            swings[s].clr   = InpColorHigherHigh;

            if(InpShowFiboExtension)
            {
               int prev_l_idx = FindPrevSwing(swings, s, false);
               if(prev_l_idx >= 0 && prev_sh_p > swings[prev_l_idx].price)
               {
                  double base_range = prev_sh_p - swings[prev_l_idx].price;
                  if(base_range > 0)
                  {
                     double ext_ratio = (cur_h - swings[prev_l_idx].price) / base_range;
                     swings[s].fibo_tag = StringFormat(" [%.3f Ext]", ext_ratio);
                  }
               }
            }
         }
         else if(cur_h < prev_sh_p)
         {
            swings[s].label = "LH";
            swings[s].clr   = InpColorLowerHigh;

            if(InpShowFiboRetrace)
            {
               int prev_l_idx = FindPrevSwing(swings, s, false);
               if(prev_l_idx >= 0 && prev_sh_p > swings[prev_l_idx].price)
               {
                  double base_range = prev_sh_p - swings[prev_l_idx].price;
                  if(base_range > 0)
                  {
                     double ret_ratio = (cur_h - swings[prev_l_idx].price) / base_range;
                     swings[s].fibo_tag = FormatRetraceTag(ret_ratio);
                  }
               }
            }
         }
         else
         {
            swings[s].label = "EQH";
            swings[s].clr   = clrYellow;
         }
         prev_sh_p = cur_h;
      }
      else // is_low
      {
         double cur_l = swings[s].price;
         if(prev_sl_p <= 0)
         {
            swings[s].label = "SL";
            swings[s].clr   = InpColorHigherLow;
         }
         else if(cur_l > prev_sl_p)
         {
            swings[s].label = "HL";
            swings[s].clr   = InpColorHigherLow;

            if(InpShowFiboRetrace)
            {
               int prev_h_idx = FindPrevSwing(swings, s, true);
               if(prev_h_idx >= 0 && swings[prev_h_idx].price > prev_sl_p)
               {
                  double base_range = swings[prev_h_idx].price - prev_sl_p;
                  if(base_range > 0)
                  {
                     double ret_ratio = (swings[prev_h_idx].price - cur_l) / base_range;
                     swings[s].fibo_tag = FormatRetraceTag(ret_ratio);
                  }
               }
            }
         }
         else if(cur_l < prev_sl_p)
         {
            swings[s].label = "LL";
            swings[s].clr   = InpColorLowerLow;

            if(InpShowFiboExtension)
            {
               int prev_h_idx = FindPrevSwing(swings, s, true);
               if(prev_h_idx >= 0 && swings[prev_h_idx].price > prev_sl_p)
               {
                  double base_range = swings[prev_h_idx].price - prev_sl_p;
                  if(base_range > 0)
                  {
                     double ext_ratio = (swings[prev_h_idx].price - cur_l) / base_range;
                     swings[s].fibo_tag = StringFormat(" [%.3f Ext]", ext_ratio);
                  }
               }
            }
         }
         else
         {
            swings[s].label = "EQL";
            swings[s].clr   = clrYellow;
         }
         prev_sl_p = cur_l;
      }
   }

   // 3. Draw ZigZag Wave Lines
   if(InpShowZigZagLines && total_swings > 1)
   {
      for(int s = 0; s < total_swings - 1; s++)
      {
         string zz_name = OBJ_PREFIX + "ZZ_" + IntegerToString(swings[s].time);
         ObjectCreate(0, zz_name, OBJ_TREND, 0, swings[s].time, swings[s].price, swings[s + 1].time, swings[s + 1].price);
         ObjectSetInteger(0, zz_name, OBJPROP_COLOR, InpColorZigZag);
         ObjectSetInteger(0, zz_name, OBJPROP_STYLE, STYLE_DOT);
         ObjectSetInteger(0, zz_name, OBJPROP_WIDTH, 1);
         ObjectSetInteger(0, zz_name, OBJPROP_RAY_RIGHT, false);
      }
   }

   // 4. Draw Swing Labels with Fibo Info
   for(int s = 0; s < total_swings; s++)
   {
      string lbl_name = OBJ_PREFIX + "LBL_" + IntegerToString(swings[s].time);
      double anchor_price = swings[s].is_high ? (swings[s].price + 8 * _Point) : (swings[s].price - 8 * _Point);
      int anchor_pos      = swings[s].is_high ? ANCHOR_LOWER : ANCHOR_UPPER;

      string display_text = InpShowHH_LL_Labels ? swings[s].label : (swings[s].is_high ? "SH" : "SL");
      if(StringLen(swings[s].fibo_tag) > 0)
      {
         display_text += swings[s].fibo_tag;
      }
      display_text += " (" + DoubleToString(swings[s].price, _Digits) + ")";

      ObjectCreate(0, lbl_name, OBJ_TEXT, 0, swings[s].time, anchor_price);
      ObjectSetString(0, lbl_name, OBJPROP_TEXT, display_text);
      ObjectSetInteger(0, lbl_name, OBJPROP_COLOR, swings[s].clr);
      ObjectSetInteger(0, lbl_name, OBJPROP_FONTSIZE, InpLabelFontSize);
      ObjectSetInteger(0, lbl_name, OBJPROP_ANCHOR, anchor_pos);
   }

   // 5. Evaluate BOS & CHoCH Breakouts
   ENUM_TREND current_trend = TREND_RANGING;
   double active_sh_price = 0;
   datetime active_sh_time = 0;
   double active_sl_price = 0;
   datetime active_sl_time = 0;
   int next_swing_idx = 0;

   for(int i = bars_to_check - InpSwingWindow - 1; i >= 0; i--)
   {
      datetime bar_t = rates[i].time;
      double close_p = rates[i].close;

      while(next_swing_idx < total_swings && swings[next_swing_idx].bar_idx >= i)
      {
         if(swings[next_swing_idx].is_high)
         {
            active_sh_price = swings[next_swing_idx].price;
            active_sh_time  = swings[next_swing_idx].time;
         }
         else
         {
            active_sl_price = swings[next_swing_idx].price;
            active_sl_time  = swings[next_swing_idx].time;
         }
         next_swing_idx++;
      }

      // Check Bullish Breakout
      if(active_sh_price > 0 && close_p > active_sh_price)
      {
         bool is_bos = (current_trend == TREND_BULLISH);
         string tag  = is_bos ? "BOS" : "CHoCH";
         color line_c= is_bos ? InpColorBOS : InpColorCHoCH;

         if((is_bos && InpShowBOS) || (!is_bos && InpShowCHoCH))
         {
            string line_id = OBJ_PREFIX + tag + "_UP_" + IntegerToString(bar_t);
            ObjectCreate(0, line_id, OBJ_TREND, 0, active_sh_time, active_sh_price, bar_t, active_sh_price);
            ObjectSetInteger(0, line_id, OBJPROP_COLOR, line_c);
            ObjectSetInteger(0, line_id, OBJPROP_STYLE, is_bos ? STYLE_DASH : STYLE_SOLID);
            ObjectSetInteger(0, line_id, OBJPROP_WIDTH, is_bos ? 1 : 2);
            ObjectSetInteger(0, line_id, OBJPROP_RAY_RIGHT, false);

            string txt_id = OBJ_PREFIX + "TXT_" + line_id;
            ObjectCreate(0, txt_id, OBJ_TEXT, 0, bar_t, active_sh_price);
            ObjectSetString(0, txt_id, OBJPROP_TEXT, " " + tag + " Bullish");
            ObjectSetInteger(0, txt_id, OBJPROP_COLOR, line_c);
            ObjectSetInteger(0, txt_id, OBJPROP_FONTSIZE, 8);
            ObjectSetInteger(0, txt_id, OBJPROP_ANCHOR, ANCHOR_LEFT);

            if(InpShowStrongWeak && active_sl_time > 0)
            {
               string str_id = OBJ_PREFIX + "STRONG_LOW_" + IntegerToString(active_sl_time);
               ObjectCreate(0, str_id, OBJ_TEXT, 0, active_sl_time, active_sl_price - 20 * _Point);
               ObjectSetString(0, str_id, OBJPROP_TEXT, "[Strong Low]");
               ObjectSetInteger(0, str_id, OBJPROP_COLOR, InpColorHigherLow);
               ObjectSetInteger(0, str_id, OBJPROP_FONTSIZE, 8);
               ObjectSetInteger(0, str_id, OBJPROP_ANCHOR, ANCHOR_UPPER);
            }
         }
         current_trend = TREND_BULLISH;
         active_sh_price = 0;
      }
      // Check Bearish Breakout
      else if(active_sl_price > 0 && close_p < active_sl_price)
      {
         bool is_bos = (current_trend == TREND_BEARISH);
         string tag  = is_bos ? "BOS" : "CHoCH";
         color line_c= is_bos ? InpColorBOS : InpColorCHoCH;

         if((is_bos && InpShowBOS) || (!is_bos && InpShowCHoCH))
         {
            string line_id = OBJ_PREFIX + tag + "_DN_" + IntegerToString(bar_t);
            ObjectCreate(0, line_id, OBJ_TREND, 0, active_sl_time, active_sl_price, bar_t, active_sl_price);
            ObjectSetInteger(0, line_id, OBJPROP_COLOR, line_c);
            ObjectSetInteger(0, line_id, OBJPROP_STYLE, is_bos ? STYLE_DASH : STYLE_SOLID);
            ObjectSetInteger(0, line_id, OBJPROP_WIDTH, is_bos ? 1 : 2);
            ObjectSetInteger(0, line_id, OBJPROP_RAY_RIGHT, false);

            string txt_id = OBJ_PREFIX + "TXT_" + line_id;
            ObjectCreate(0, txt_id, OBJ_TEXT, 0, bar_t, active_sl_price);
            ObjectSetString(0, txt_id, OBJPROP_TEXT, " " + tag + " Bearish");
            ObjectSetInteger(0, txt_id, OBJPROP_COLOR, line_c);
            ObjectSetInteger(0, txt_id, OBJPROP_FONTSIZE, 8);
            ObjectSetInteger(0, txt_id, OBJPROP_ANCHOR, ANCHOR_LEFT);

            if(InpShowStrongWeak && active_sh_time > 0)
            {
               string str_id = OBJ_PREFIX + "STRONG_HIGH_" + IntegerToString(active_sh_time);
               ObjectCreate(0, str_id, OBJ_TEXT, 0, active_sh_time, active_sh_price + 20 * _Point);
               ObjectSetString(0, str_id, OBJPROP_TEXT, "[Strong High]");
               ObjectSetInteger(0, str_id, OBJPROP_COLOR, InpColorLowerHigh);
               ObjectSetInteger(0, str_id, OBJPROP_FONTSIZE, 8);
               ObjectSetInteger(0, str_id, OBJPROP_ANCHOR, ANCHOR_LOWER);
            }
         }
         current_trend = TREND_BEARISH;
         active_sl_price = 0;
      }
   }

   // 6. Draw Dual Fibo: Active In-Progress Leg + Previous Completed Leg
   if(total_swings >= 2)
   {
      // A. Previous Completed Leg (TP Targets Tracker)
      if(InpShowPrevFibo)
      {
         DrawPreviousLegFibo(swings, rates, rates[0].time);
      }

      // B. Active In-Progress Leg
      if(InpShowActiveFibo)
      {
         DrawActiveFiboZones(swings, rates[0].time);
      }
   }

   ChartRedraw();
}

int FindPrevSwing(const SwingNode &swings[], int current_idx, bool want_high)
{
   for(int i = current_idx - 1; i >= 0; i--)
   {
      if(swings[i].is_high == want_high) return i;
   }
   return -1;
}

string FormatRetraceTag(double ratio)
{
   double pct = ratio * 100.0;
   if(ratio >= 0.382 && ratio <= 0.500)
   {
      return StringFormat(" [%.1f%% Shallow]", pct);
   }
   else if(ratio > 0.500 && ratio < 0.618)
   {
      return StringFormat(" [%.1f%% EQ]", pct);
   }
   else if(ratio >= 0.618 && ratio <= 0.786)
   {
      return StringFormat(" [%.1f%% OTE]", pct);
   }
   else if(ratio > 0.786)
   {
      return StringFormat(" [%.1f%% Deep]", pct);
   }
   return StringFormat(" [%.1f%%]", pct);
}

//+------------------------------------------------------------------+
//| 1. Active In-Progress Leg Fibo Drawer                            |
//+------------------------------------------------------------------+
void DrawActiveFiboZones(const SwingNode &swings[], datetime current_candle_t)
{
   int last_idx = ArraySize(swings) - 1;
   int prev_idx = last_idx - 1;
   if(swings[last_idx].is_high == swings[prev_idx].is_high)
   {
      prev_idx = FindPrevSwing(swings, last_idx, !swings[last_idx].is_high);
      if(prev_idx < 0) return;
   }

   double high_p = swings[last_idx].is_high ? swings[last_idx].price : swings[prev_idx].price;
   double low_p  = swings[last_idx].is_high ? swings[prev_idx].price : swings[last_idx].price;
   datetime start_t = MathMin(swings[last_idx].time, swings[prev_idx].time);
   datetime end_t   = current_candle_t;

   double range = high_p - low_p;
   if(range <= 0) return;

   bool is_bullish_leg = swings[last_idx].is_high;

   double shallow_top, shallow_btm;
   double ote_top, ote_btm;
   double eq_500;
   double ext_1272, ext_1618;

   if(is_bullish_leg)
   {
      shallow_top = high_p - 0.382 * range;
      shallow_btm = high_p - 0.500 * range;
      ote_top     = high_p - 0.618 * range;
      ote_btm     = high_p - 0.786 * range;
      eq_500      = high_p - 0.500 * range;
      ext_1272    = low_p + 1.272 * range;
      ext_1618    = low_p + 1.618 * range;
   }
   else
   {
      shallow_btm = low_p + 0.382 * range;
      shallow_top = low_p + 0.500 * range;
      ote_btm     = low_p + 0.618 * range;
      ote_top     = low_p + 0.786 * range;
      eq_500      = low_p + 0.500 * range;
      ext_1272    = high_p - 1.272 * range;
      ext_1618    = high_p - 1.618 * range;
   }

   // 1. Draw Shallow Zone (0.382 - 0.500)
   string shallow_box = OBJ_PREFIX + "ACT_ZONE_SHALLOW";
   ObjectCreate(0, shallow_box, OBJ_RECTANGLE, 0, start_t, shallow_top, end_t, shallow_btm);
   ObjectSetInteger(0, shallow_box, OBJPROP_COLOR, InpColorActiveShallow);
   ObjectSetInteger(0, shallow_box, OBJPROP_BACK, true);
   ObjectSetInteger(0, shallow_box, OBJPROP_FILL, true);

   string txt_shallow = OBJ_PREFIX + "ACT_TXT_SHALLOW";
   ObjectCreate(0, txt_shallow, OBJ_TEXT, 0, end_t, (shallow_top + shallow_btm) / 2.0);
   ObjectSetString(0, txt_shallow, OBJPROP_TEXT, " [Active] 38.2% - 50% Shallow Zone");
   ObjectSetInteger(0, txt_shallow, OBJPROP_COLOR, C'147,197,253');
   ObjectSetInteger(0, txt_shallow, OBJPROP_FONTSIZE, 8);
   ObjectSetInteger(0, txt_shallow, OBJPROP_ANCHOR, ANCHOR_LEFT);

   // 2. Draw Golden OTE Zone (0.618 - 0.786)
   string ote_box = OBJ_PREFIX + "ACT_ZONE_OTE";
   ObjectCreate(0, ote_box, OBJ_RECTANGLE, 0, start_t, ote_top, end_t, ote_btm);
   ObjectSetInteger(0, ote_box, OBJPROP_COLOR, InpColorActiveOTE);
   ObjectSetInteger(0, ote_box, OBJPROP_BACK, true);
   ObjectSetInteger(0, ote_box, OBJPROP_FILL, true);

   string txt_ote = OBJ_PREFIX + "ACT_TXT_OTE";
   ObjectCreate(0, txt_ote, OBJ_TEXT, 0, end_t, (ote_top + ote_btm) / 2.0);
   ObjectSetString(0, txt_ote, OBJPROP_TEXT, " [Active] 61.8% - 78.6% Golden OTE Zone");
   ObjectSetInteger(0, txt_ote, OBJPROP_COLOR, C'110,231,183');
   ObjectSetInteger(0, txt_ote, OBJPROP_FONTSIZE, 8);
   ObjectSetInteger(0, txt_ote, OBJPROP_ANCHOR, ANCHOR_LEFT);

   // 3. Draw 50% Equilibrium Line
   string eq_line = OBJ_PREFIX + "ACT_LINE_EQ";
   ObjectCreate(0, eq_line, OBJ_TREND, 0, start_t, eq_500, end_t, eq_500);
   ObjectSetInteger(0, eq_line, OBJPROP_COLOR, InpColorActiveEQ);
   ObjectSetInteger(0, eq_line, OBJPROP_STYLE, STYLE_DASH);
   ObjectSetInteger(0, eq_line, OBJPROP_WIDTH, 1);
   ObjectSetInteger(0, eq_line, OBJPROP_RAY_RIGHT, false);

   string txt_eq = OBJ_PREFIX + "ACT_TXT_EQ";
   ObjectCreate(0, txt_eq, OBJ_TEXT, 0, end_t, eq_500);
   ObjectSetString(0, txt_eq, OBJPROP_TEXT, " [Active] 50.0% EQ (" + DoubleToString(eq_500, _Digits) + ")");
   ObjectSetInteger(0, txt_eq, OBJPROP_COLOR, InpColorActiveEQ);
   ObjectSetInteger(0, txt_eq, OBJPROP_FONTSIZE, 8);
   ObjectSetInteger(0, txt_eq, OBJPROP_ANCHOR, ANCHOR_LEFT);

   // 4. Draw Extension Projections (Active Leg Targets)
   DrawFiboLine("ACT_EXT_1272", start_t, end_t, ext_1272, "[Active] TP1 (1.272 Ext)", InpColorActiveExt, STYLE_DOT);
   DrawFiboLine("ACT_EXT_1618", start_t, end_t, ext_1618, "[Active] TP2 (1.618 Golden Ext)", InpColorActiveExt, STYLE_DOT);
}

//+------------------------------------------------------------------+
//| 2. Previous Completed Leg Fibo & TP Targets Drawer               |
//+------------------------------------------------------------------+
void DrawPreviousLegFibo(const SwingNode &swings[], const MqlRates &rates[], datetime current_candle_t)
{
   int total_swings = ArraySize(swings);
   if(total_swings < 3) return;

   int last_idx = total_swings - 1;
   int prev_idx = FindPrevSwing(swings, last_idx, !swings[last_idx].is_high);
   if(prev_idx < 0) return;

   int prev_prev_idx = FindPrevSwing(swings, prev_idx, !swings[prev_idx].is_high);
   if(prev_prev_idx < 0) return;

   // Previous completed leg is from prev_prev_idx to prev_idx
   double p_high = swings[prev_idx].is_high ? swings[prev_idx].price : swings[prev_prev_idx].price;
   double p_low  = swings[prev_idx].is_high ? swings[prev_prev_idx].price : swings[prev_idx].price;
   datetime start_t = MathMin(swings[prev_idx].time, swings[prev_prev_idx].time);
   datetime end_t   = current_candle_t;

   double p_range = p_high - p_low;
   if(p_range <= 0) return;

   bool was_bullish = swings[prev_idx].is_high; // Was an upward impulse leg
   double prev_tp1_ext = 0;
   double prev_tp2_ext = 0;

   if(was_bullish)
   {
      prev_tp1_ext = p_low + 1.272 * p_range;
      prev_tp2_ext = p_low + 1.618 * p_range;
   }
   else
   {
      prev_tp1_ext = p_high - 1.272 * p_range;
      prev_tp2_ext = p_high - 1.618 * p_range;
   }

   // Check if subsequent bars touched/hit TP1 or TP2
   bool tp1_hit = false;
   bool tp2_hit = false;
   int check_start_bar = swings[prev_idx].bar_idx;

   for(int k = check_start_bar; k >= 0; k--)
   {
      if(was_bullish)
      {
         if(rates[k].high >= prev_tp1_ext) tp1_hit = true;
         if(rates[k].high >= prev_tp2_ext) tp2_hit = true;
      }
      else
      {
         if(rates[k].low <= prev_tp1_ext) tp1_hit = true;
         if(rates[k].low <= prev_tp2_ext) tp2_hit = true;
      }
   }

   string tp1_label = "[Prev Leg] TP1 (1.272 Ext)" + (tp1_hit ? " [HIT]" : " [Pending]");
   string tp2_label = "[Prev Leg] TP2 (1.618 Ext)" + (tp2_hit ? " [HIT]" : " [Pending]");

   color tp1_color = tp1_hit ? C'34,197,94' : InpColorPrevExt1272;
   color tp2_color = tp2_hit ? C'34,197,94' : InpColorPrevExt1618;

   DrawFiboLine("PREV_EXT_1272", start_t, end_t, prev_tp1_ext, tp1_label, tp1_color, STYLE_SOLID);
   DrawFiboLine("PREV_EXT_1618", start_t, end_t, prev_tp2_ext, tp2_label, tp2_color, STYLE_SOLID);
}

void DrawFiboLine(string key, datetime t1, datetime t2, double price, string label, color clr, ENUM_LINE_STYLE style)
{
   string line_name = OBJ_PREFIX + "LINE_" + key;
   ObjectCreate(0, line_name, OBJ_TREND, 0, t1, price, t2, price);
   ObjectSetInteger(0, line_name, OBJPROP_COLOR, clr);
   ObjectSetInteger(0, line_name, OBJPROP_STYLE, style);
   ObjectSetInteger(0, line_name, OBJPROP_WIDTH, (style == STYLE_SOLID) ? 2 : 1);
   ObjectSetInteger(0, line_name, OBJPROP_RAY_RIGHT, false);

   string text_name = OBJ_PREFIX + "TXT_" + key;
   ObjectCreate(0, text_name, OBJ_TEXT, 0, t2, price);
   ObjectSetString(0, text_name, OBJPROP_TEXT, " " + label + " (" + DoubleToString(price, _Digits) + ")");
   ObjectSetInteger(0, text_name, OBJPROP_COLOR, clr);
   ObjectSetInteger(0, text_name, OBJPROP_FONTSIZE, 8);
   ObjectSetInteger(0, text_name, OBJPROP_ANCHOR, ANCHOR_LEFT);
}
