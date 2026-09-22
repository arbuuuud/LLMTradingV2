//+------------------------------------------------------------------+
//|                                       Structure_Inspector.mq5    |
//|    Comprehensive Market Structure: Swings, HH/HL/LH/LL, BOS & CHoCH|
//|                                  LLMTradingV2 Institutional V2   |
//+------------------------------------------------------------------+
#property copyright "LLMTradingV2"
#property link      "https://github.com/arbuuuud/LLMTradingV2"
#property version   "2.00"
#property description "Unified Market Structure Inspector: Swing Points, HH/HL/LH/LL Classification, BOS, CHoCH, and Strong/Weak Structure"

//--- Inputs
input group "=== Fractal Swing Settings ==="
input int      InpSwingWindow       = 3;           // Fractal Window (Bars Left & Right)
input int      InpMaxBars           = 300;         // Max Bars to Analyze
input bool     InpShowZigZagLines   = true;        // Draw Structure Wave Lines (High-Low)
input color    InpColorZigZag       = C'71,85,105';// Structure Wave Line Color (Slate)

input group "=== Swing Labels & Colors ==="
input bool     InpShowHH_LL_Labels  = true;        // Classify HH, HL, LH, LL
input color    InpColorHigherHigh   = C'34,197,94'; // Higher High (Green)
input color    InpColorLowerHigh    = C'239,68,68'; // Lower High (Red/Orange)
input color    InpColorHigherLow    = C'16,185,129';// Higher Low (Emerald)
input color    InpColorLowerLow     = C'244,63,94'; // Lower Low (Rose)
input int      InpLabelFontSize     = 8;           // Font Size for Labels

input group "=== BOS & CHoCH Settings ==="
input bool     InpShowBOS           = true;        // Show Break of Structure (BOS)
input color    InpColorBOS          = C'59,130,246';// BOS Line Color (Blue)
input bool     InpShowCHoCH         = true;        // Show Change of Character (CHoCH)
input color    InpColorCHoCH        = C'217,70,239';// CHoCH Line Color (Fuchsia)
input bool     InpShowStrongWeak    = true;        // Mark Strong Low / Strong High

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
   string   label;
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

   // 1. Detect All Fractal Swings chronologically (from oldest to newest)
   SwingNode swings[];
   ArrayResize(swings, 0);

   double prev_sh_price = 0;
   double prev_sl_price = 0;

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
         swings[sz].is_high = true;
         swings[sz].price   = h;
         swings[sz].time    = rates[i].time;
         swings[sz].bar_idx = i;

         if(prev_sh_price <= 0)
         {
            swings[sz].label = "SH";
            swings[sz].clr   = InpColorHigherHigh;
         }
         else if(h > prev_sh_price)
         {
            swings[sz].label = "HH";
            swings[sz].clr   = InpColorHigherHigh;
         }
         else if(h < prev_sh_price)
         {
            swings[sz].label = "LH";
            swings[sz].clr   = InpColorLowerHigh;
         }
         else
         {
            swings[sz].label = "EQH";
            swings[sz].clr   = clrYellow;
         }
         prev_sh_price = h;
      }

      if(is_sl)
      {
         int sz = ArraySize(swings);
         ArrayResize(swings, sz + 1);
         swings[sz].is_high = false;
         swings[sz].price   = l;
         swings[sz].time    = rates[i].time;
         swings[sz].bar_idx = i;

         if(prev_sl_price <= 0)
         {
            swings[sz].label = "SL";
            swings[sz].clr   = InpColorHigherLow;
         }
         else if(l > prev_sl_price)
         {
            swings[sz].label = "HL";
            swings[sz].clr   = InpColorHigherLow;
         }
         else if(l < prev_sl_price)
         {
            swings[sz].label = "LL";
            swings[sz].clr   = InpColorLowerLow;
         }
         else
         {
            swings[sz].label = "EQL";
            swings[sz].clr   = clrYellow;
         }
         prev_sl_price = l;
      }
   }

   int total_swings = ArraySize(swings);
   if(total_swings == 0) return;

   // 2. Draw ZigZag Structure Lines connecting Highs & Lows
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

   // 3. Draw Swing Labels (HH, HL, LH, LL)
   for(int s = 0; s < total_swings; s++)
   {
      string lbl_name = OBJ_PREFIX + "LBL_" + IntegerToString(swings[s].time);
      double anchor_price = swings[s].is_high ? (swings[s].price + 8 * _Point) : (swings[s].price - 8 * _Point);
      int anchor_pos      = swings[s].is_high ? ANCHOR_LOWER : ANCHOR_UPPER;

      string display_text = InpShowHH_LL_Labels ? swings[s].label : (swings[s].is_high ? "SH" : "SL");
      display_text += " (" + DoubleToString(swings[s].price, _Digits) + ")";

      ObjectCreate(0, lbl_name, OBJ_TEXT, 0, swings[s].time, anchor_price);
      ObjectSetString(0, lbl_name, OBJPROP_TEXT, display_text);
      ObjectSetInteger(0, lbl_name, OBJPROP_COLOR, swings[s].clr);
      ObjectSetInteger(0, lbl_name, OBJPROP_FONTSIZE, InpLabelFontSize);
      ObjectSetInteger(0, lbl_name, OBJPROP_ANCHOR, anchor_pos);
   }

   // 4. Evaluate BOS & CHoCH Breakouts chronologically
   ENUM_TREND current_trend = TREND_RANGING;
   double active_sh_price = 0;
   datetime active_sh_time = 0;
   double active_sl_price = 0;
   datetime active_sl_time = 0;

   // Walk through historical candles and track when a swing is broken by candle close
   int next_swing_idx = 0;

   for(int i = bars_to_check - InpSwingWindow - 1; i >= 0; i--)
   {
      datetime bar_t = rates[i].time;
      double close_p = rates[i].close;

      // Register swings that formed up to this bar
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

      // Check Bullish Breakout (close above active SH)
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

            // Strong Low Marker: The low that pushed this high
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
         active_sh_price = 0; // consumed
      }

      // Check Bearish Breakout (close below active SL)
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

            // Strong High Marker: The high that pushed this low
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
         active_sl_price = 0; // consumed
      }
   }

   ChartRedraw();
}
