//+------------------------------------------------------------------+
//|                                            FVG_Inspector.mq5     |
//|                Visual Inspector for FVG and Inversion FVG (iFVG) |
//|                                  LLMTradingV2 Institutional V2   |
//+------------------------------------------------------------------+
#property copyright "LLMTradingV2"
#property link      "https://github.com/arbuuuud/LLMTradingV2"
#property version   "1.00"
#property description "Visualizes Bullish/Bearish Fair Value Gaps (FVG), Inversions (iFVG), and Mitigation Status"

//--- Inputs
input group "=== FVG Settings ==="
input int      InpMaxBars           = 300;               // Max Bars to Analyze
input double   InpMinGapPoints      = 0.0;               // Minimum Gap Size (Points)
input color    InpColorBullFVG      = C'16,185,129';     // Bullish FVG Box Color (Emerald)
input color    InpColorBearFVG      = C'239,68,68';      // Bearish FVG Box Color (Rose)
input color    InpColorInversion    = clrGold;           // Inversion FVG Box Color
input bool     InpShowMitigated     = true;              // Show Mitigated Gaps
input bool     InpExtendToCurrent   = true;              // Extend Active Gaps to Current Bar

#define OBJ_PREFIX "FVG_INSP_"

datetime g_last_bar_time = 0;

int OnInit()
{
   CleanObjects();
   RedrawFVGs();
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
      RedrawFVGs();
   }
}

void RedrawFVGs()
{
   CleanObjects();

   int total_bars = iBars(_Symbol, _Period);
   int bars_to_check = MathMin(InpMaxBars, total_bars - 3);
   if(bars_to_check < 3) return;

   MqlRates rates[];
   ArraySetAsSeries(rates, true);
   if(CopyRates(_Symbol, _Period, 0, bars_to_check, rates) < bars_to_check) return;

   datetime current_candle_time = rates[0].time;

   // Scan 3-bar sequences from oldest to newest
   for(int i = bars_to_check - 3; i >= 1; i--)
   {
      // In series array:
      // i+2 is the oldest candle in the 3-bar set
      // i+1 is the middle displacement candle
      // i   is the newest candle completing the pattern
      double oldest_high = rates[i + 2].high;
      double oldest_low  = rates[i + 2].low;
      double newest_high = rates[i].high;
      double newest_low  = rates[i].low;
      datetime gap_time  = rates[i + 1].time;

      bool is_bull_fvg = (newest_low - oldest_high) > (InpMinGapPoints * _Point);
      bool is_bear_fvg = (oldest_low - newest_high) > (InpMinGapPoints * _Point);

      if(!is_bull_fvg && !is_bear_fvg) continue;

      double top = is_bull_fvg ? newest_low : oldest_low;
      double bottom = is_bull_fvg ? oldest_high : newest_high;

      // Track mitigation & inversion in subsequent bars (from i-1 down to 0)
      bool is_mitigated = false;
      bool is_inversion = false;
      datetime end_time = current_candle_time;

      for(int k = i - 1; k >= 0; k--)
      {
         if(is_bull_fvg)
         {
            if(rates[k].low <= top)
            {
               is_mitigated = true;
               if(!InpExtendToCurrent) { end_time = rates[k].time; }
            }
            if(rates[k].close < bottom)
            {
               is_inversion = true;
               break;
            }
         }
         else // bear fvg
         {
            if(rates[k].high >= bottom)
            {
               is_mitigated = true;
               if(!InpExtendToCurrent) { end_time = rates[k].time; }
            }
            if(rates[k].close > top)
            {
               is_inversion = true;
               break;
            }
         }
      }

      if(is_mitigated && !InpShowMitigated && !is_inversion) continue;

      // Draw FVG Box
      string id_str = IntegerToString(gap_time);
      string rect_name = OBJ_PREFIX + "BOX_" + id_str;
      color box_color = is_inversion ? InpColorInversion : (is_bull_fvg ? InpColorBullFVG : InpColorBearFVG);

      ObjectCreate(0, rect_name, OBJ_RECTANGLE, 0, gap_time, top, end_time, bottom);
      ObjectSetInteger(0, rect_name, OBJPROP_COLOR, box_color);
      ObjectSetInteger(0, rect_name, OBJPROP_STYLE, is_mitigated ? STYLE_DASH : STYLE_SOLID);
      ObjectSetInteger(0, rect_name, OBJPROP_WIDTH, is_inversion ? 2 : 1);
      ObjectSetInteger(0, rect_name, OBJPROP_BACK, true);
      ObjectSetInteger(0, rect_name, OBJPROP_FILL, true);

      // Add Text Label
      string text_name = OBJ_PREFIX + "LBL_" + id_str;
      string label_text = is_inversion ? "iFVG" : (is_bull_fvg ? "Bull FVG" : "Bear FVG");
      if(is_mitigated && !is_inversion) label_text += " [Mit]";

      ObjectCreate(0, text_name, OBJ_TEXT, 0, gap_time, (top + bottom) / 2.0);
      ObjectSetString(0, text_name, OBJPROP_TEXT, label_text);
      ObjectSetInteger(0, text_name, OBJPROP_COLOR, box_color);
      ObjectSetInteger(0, text_name, OBJPROP_FONTSIZE, 8);
      ObjectSetInteger(0, text_name, OBJPROP_ANCHOR, ANCHOR_LEFT);
   }

   ChartRedraw();
}
