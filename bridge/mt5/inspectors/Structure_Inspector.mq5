//+------------------------------------------------------------------+
//|                                       Structure_Inspector.mq5    |
//|                 Visual Inspector for Swing Points, BOS & CHoCH   |
//|                                  LLMTradingV2 Institutional V2   |
//+------------------------------------------------------------------+
#property copyright "LLMTradingV2"
#property link      "https://github.com/arbuuuud/LLMTradingV2"
#property version   "1.00"
#property description "Visualizes Fractal Swing Highs/Lows, Break of Structure (BOS), and Change of Character (CHoCH)"

//--- Inputs
input group "=== Structure Settings ==="
input int      InpSwingWindow       = 3;           // Fractal Window (Bars Left & Right)
input int      InpMaxBars           = 300;         // Max Bars to Analyze
input color    InpColorSwingHigh    = clrCyan;     // Swing High Color
input color    InpColorSwingLow     = clrOrange;   // Swing Low Color
input color    InpColorBOS          = clrLimeGreen;// BOS Line Color
input color    InpColorCHoCH        = clrMagenta;  // CHoCH Line Color

//--- Prefix for chart objects
#define OBJ_PREFIX "STR_INSP_"

enum ENUM_TREND
{
   TREND_RANGING = 0,
   TREND_BULLISH = 1,
   TREND_BEARISH = -1
};

datetime g_last_bar_time = 0;

//+------------------------------------------------------------------+
//| Expert initialization function                                   |
//+------------------------------------------------------------------+
int OnInit()
{
   CleanObjects();
   RedrawStructure();
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
//| Remove all objects drawn by this inspector                       |
//+------------------------------------------------------------------+
void CleanObjects()
{
   ObjectsDeleteAll(0, OBJ_PREFIX);
}

//+------------------------------------------------------------------+
//| OnTick function                                                  |
//+------------------------------------------------------------------+
void OnTick()
{
   datetime current_time = iTime(_Symbol, _Period, 0);
   if(current_time != g_last_bar_time)
   {
      g_last_bar_time = current_time;
      RedrawStructure();
   }
}

//+------------------------------------------------------------------+
//| Core Structure Analysis & Drawing                                |
//+------------------------------------------------------------------+
void RedrawStructure()
{
   CleanObjects();

   int total_bars = iBars(_Symbol, _Period);
   int bars_to_check = MathMin(InpMaxBars, total_bars - InpSwingWindow - 1);
   if(bars_to_check < InpSwingWindow * 2 + 1) return;

   MqlRates rates[];
   ArraySetAsSeries(rates, true);
   if(CopyRates(_Symbol, _Period, 0, bars_to_check, rates) < bars_to_check) return;

   double last_sh_price = 0;
   datetime last_sh_time = 0;
   double last_sl_price = 0;
   datetime last_sl_time = 0;
   ENUM_TREND current_trend = TREND_RANGING;

   // Process from oldest to newest bar
   for(int i = bars_to_check - InpSwingWindow - 1; i >= InpSwingWindow; i--)
   {
      // 1. Check Swing High
      bool is_sh = true;
      double h = rates[i].high;
      for(int w = 1; w <= InpSwingWindow; w++)
      {
         if(rates[i - w].high >= h || rates[i + w].high >= h)
         {
            is_sh = false;
            break;
         }
      }

      // 2. Check Swing Low
      bool is_sl = true;
      double l = rates[i].low;
      for(int w = 1; w <= InpSwingWindow; w++)
      {
         if(rates[i - w].low <= l || rates[i + w].low <= l)
         {
            is_sl = false;
            break;
         }
      }

      if(is_sh)
      {
         last_sh_price = h;
         last_sh_time = rates[i].time;
         string obj_name = OBJ_PREFIX + "SH_" + IntegerToString(rates[i].time);
         ObjectCreate(0, obj_name, OBJ_TEXT, 0, rates[i].time, h + 10 * _Point);
         ObjectSetString(0, obj_name, OBJPROP_TEXT, "SH (" + DoubleToString(h, _Digits) + ")");
         ObjectSetInteger(0, obj_name, OBJPROP_COLOR, InpColorSwingHigh);
         ObjectSetInteger(0, obj_name, OBJPROP_FONTSIZE, 9);
         ObjectSetInteger(0, obj_name, OBJPROP_ANCHOR, ANCHOR_LOWER);
      }

      if(is_sl)
      {
         last_sl_price = l;
         last_sl_time = rates[i].time;
         string obj_name = OBJ_PREFIX + "SL_" + IntegerToString(rates[i].time);
         ObjectCreate(0, obj_name, OBJ_TEXT, 0, rates[i].time, l - 10 * _Point);
         ObjectSetString(0, obj_name, OBJPROP_TEXT, "SL (" + DoubleToString(l, _Digits) + ")");
         ObjectSetInteger(0, obj_name, OBJPROP_COLOR, InpColorSwingLow);
         ObjectSetInteger(0, obj_name, OBJPROP_FONTSIZE, 9);
         ObjectSetInteger(0, obj_name, OBJPROP_ANCHOR, ANCHOR_UPPER);
      }

      // 3. Evaluate BOS / CHoCH on candle close
      double close_price = rates[i].close;
      datetime bar_time = rates[i].time;

      if(last_sh_price > 0 && close_price > last_sh_price)
      {
         string event_type = (current_trend == TREND_BULLISH) ? "BOS" : "CHoCH";
         color line_color = (current_trend == TREND_BULLISH) ? InpColorBOS : InpColorCHoCH;

         string line_name = OBJ_PREFIX + event_type + "_BULL_" + IntegerToString(bar_time);
         ObjectCreate(0, line_name, OBJ_TREND, 0, last_sh_time, last_sh_price, bar_time, last_sh_price);
         ObjectSetInteger(0, line_name, OBJPROP_COLOR, line_color);
         ObjectSetInteger(0, line_name, OBJPROP_STYLE, (event_type == "BOS") ? STYLE_DASH : STYLE_SOLID);
         ObjectSetInteger(0, line_name, OBJPROP_WIDTH, (event_type == "CHoCH") ? 2 : 1);
         ObjectSetInteger(0, line_name, OBJPROP_RAY_RIGHT, false);

         string text_name = OBJ_PREFIX + "TXT_" + line_name;
         ObjectCreate(0, text_name, OBJ_TEXT, 0, bar_time, last_sh_price);
         ObjectSetString(0, text_name, OBJPROP_TEXT, " " + event_type + " Bullish");
         ObjectSetInteger(0, text_name, OBJPROP_COLOR, line_color);
         ObjectSetInteger(0, text_name, OBJPROP_FONTSIZE, 8);
         ObjectSetInteger(0, text_name, OBJPROP_ANCHOR, ANCHOR_LEFT);

         current_trend = TREND_BULLISH;
         last_sh_price = 0; // consumed
      }
      else if(last_sl_price > 0 && close_price < last_sl_price)
      {
         string event_type = (current_trend == TREND_BEARISH) ? "BOS" : "CHoCH";
         color line_color = (current_trend == TREND_BEARISH) ? InpColorBOS : InpColorCHoCH;

         string line_name = OBJ_PREFIX + event_type + "_BEAR_" + IntegerToString(bar_time);
         ObjectCreate(0, line_name, OBJ_TREND, 0, last_sl_time, last_sl_price, bar_time, last_sl_price);
         ObjectSetInteger(0, line_name, OBJPROP_COLOR, line_color);
         ObjectSetInteger(0, line_name, OBJPROP_STYLE, (event_type == "BOS") ? STYLE_DASH : STYLE_SOLID);
         ObjectSetInteger(0, line_name, OBJPROP_WIDTH, (event_type == "CHoCH") ? 2 : 1);
         ObjectSetInteger(0, line_name, OBJPROP_RAY_RIGHT, false);

         string text_name = OBJ_PREFIX + "TXT_" + line_name;
         ObjectCreate(0, text_name, OBJ_TEXT, 0, bar_time, last_sl_price);
         ObjectSetString(0, text_name, OBJPROP_TEXT, " " + event_type + " Bearish");
         ObjectSetInteger(0, text_name, OBJPROP_COLOR, line_color);
         ObjectSetInteger(0, text_name, OBJPROP_FONTSIZE, 8);
         ObjectSetInteger(0, text_name, OBJPROP_ANCHOR, ANCHOR_LEFT);

         current_trend = TREND_BEARISH;
         last_sl_price = 0; // consumed
      }
   }

   ChartRedraw();
}
