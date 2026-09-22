//+------------------------------------------------------------------+
//|                                       OrderBlock_Inspector.mq5   |
//|                 Visual Inspector for SMC Order Blocks (OB)       |
//|                                  LLMTradingV2 Institutional V2   |
//+------------------------------------------------------------------+
#property copyright "LLMTradingV2"
#property link      "https://github.com/arbuuuud/LLMTradingV2"
#property version   "1.00"
#property description "Visualizes Institutional Order Blocks (OB) and their Mitigation Lifecycle"

//--- Inputs
input group "=== Order Block Settings ==="
input int      InpMaxBars           = 300;               // Max Bars to Analyze
input color    InpColorBullOB       = C'30,144,255';     // Bullish OB Color (DodgerBlue)
input color    InpColorBearOB       = C'186,85,211';     // Bearish OB Color (MediumOrchid)
input bool     InpShowMitigated     = true;              // Show Mitigated OBs
input bool     InpExtendToCurrent   = true;              // Extend Active OBs to Current Candle

#define OBJ_PREFIX "OB_INSP_"

datetime g_last_bar_time = 0;

int OnInit()
{
   CleanObjects();
   RedrawOrderBlocks();
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
      RedrawOrderBlocks();
   }
}

void RedrawOrderBlocks()
{
   CleanObjects();

   int total_bars = iBars(_Symbol, _Period);
   int bars_to_check = MathMin(InpMaxBars, total_bars - 4);
   if(bars_to_check < 4) return;

   MqlRates rates[];
   ArraySetAsSeries(rates, true);
   if(CopyRates(_Symbol, _Period, 0, bars_to_check, rates) < bars_to_check) return;

   datetime current_candle_time = rates[0].time;

   // Scan for displacement that formed an FVG, then identify the origin candle
   for(int i = bars_to_check - 3; i >= 1; i--)
   {
      // Check if bar i created an FVG:
      // Bullish FVG: rates[i].low > rates[i+2].high
      bool is_bull_fvg = (rates[i].low > rates[i + 2].high);
      bool is_bear_fvg = (rates[i].high < rates[i + 2].low);

      if(!is_bull_fvg && !is_bear_fvg) continue;

      // Origin candle is i+2 or i+1
      int ob_idx = i + 2;
      bool is_down_candle = rates[ob_idx].close < rates[ob_idx].open;
      bool is_up_candle   = rates[ob_idx].close > rates[ob_idx].open;

      bool valid_bull_ob = is_bull_fvg && is_down_candle;
      bool valid_bear_ob = is_bear_fvg && is_up_candle;

      if(!valid_bull_ob && !valid_bear_ob) continue;

      double top = rates[ob_idx].high;
      double bottom = rates[ob_idx].low;
      datetime ob_time = rates[ob_idx].time;

      // Track mitigation
      bool is_mitigated = false;
      datetime end_time = current_candle_time;

      for(int k = ob_idx - 1; k >= 0; k--)
      {
         if(valid_bull_ob && rates[k].low <= top)
         {
            is_mitigated = true;
            if(!InpExtendToCurrent) { end_time = rates[k].time; break; }
         }
         else if(valid_bear_ob && rates[k].high >= bottom)
         {
            is_mitigated = true;
            if(!InpExtendToCurrent) { end_time = rates[k].time; break; }
         }
      }

      if(is_mitigated && !InpShowMitigated) continue;

      string id_str = IntegerToString(ob_time);
      string rect_name = OBJ_PREFIX + "BOX_" + id_str;
      color box_color = valid_bull_ob ? InpColorBullOB : InpColorBearOB;

      ObjectCreate(0, rect_name, OBJ_RECTANGLE, 0, ob_time, top, end_time, bottom);
      ObjectSetInteger(0, rect_name, OBJPROP_COLOR, box_color);
      ObjectSetInteger(0, rect_name, OBJPROP_STYLE, is_mitigated ? STYLE_DASH : STYLE_SOLID);
      ObjectSetInteger(0, rect_name, OBJPROP_WIDTH, 1);
      ObjectSetInteger(0, rect_name, OBJPROP_BACK, true);
      ObjectSetInteger(0, rect_name, OBJPROP_FILL, true);

      // Label
      string text_name = OBJ_PREFIX + "LBL_" + id_str;
      string label_text = valid_bull_ob ? "+OB (Bullish)" : "-OB (Bearish)";
      if(is_mitigated) label_text += " [Mitigated]";

      ObjectCreate(0, text_name, OBJ_TEXT, 0, ob_time, (top + bottom) / 2.0);
      ObjectSetString(0, text_name, OBJPROP_TEXT, label_text);
      ObjectSetInteger(0, text_name, OBJPROP_COLOR, box_color);
      ObjectSetInteger(0, text_name, OBJPROP_FONTSIZE, 8);
      ObjectSetInteger(0, text_name, OBJPROP_ANCHOR, ANCHOR_LEFT);
   }

   ChartRedraw();
}
