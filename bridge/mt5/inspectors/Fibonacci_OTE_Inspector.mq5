//+------------------------------------------------------------------+
//|                                    Fibonacci_OTE_Inspector.mq5   |
//|                 Visual Inspector for Fibonacci OTE & Equilibrium |
//|                                  LLMTradingV2 Institutional V2   |
//+------------------------------------------------------------------+
#property copyright "LLMTradingV2"
#property link      "https://github.com/arbuuuud/LLMTradingV2"
#property version   "1.00"
#property description "Dynamically draws Fibonacci Equilibrium (0.5) and Institutional OTE Zone (0.618 - 0.786)"

//--- Inputs
input group "=== Fibonacci & OTE Settings ==="
input int      InpSwingWindow       = 3;                 // Fractal Window for Swing Anchor
input int      InpMaxBars           = 300;               // Max Bars to Analyze
input color    InpColorEquilibrium  = clrYellow;         // 50% Equilibrium Line Color
input color    InpColorOTEZone      = C'16,185,129';     // OTE Golden Pocket Color (Emerald)
input color    InpColorAnchors      = clrSilver;         // 0.0 & 1.0 Anchors Color

#define OBJ_PREFIX "FIBO_INSP_"

datetime g_last_bar_time = 0;

int OnInit()
{
   CleanObjects();
   RedrawFiboOTE();
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
      RedrawFiboOTE();
   }
}

void RedrawFiboOTE()
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
   int last_sh_idx = -1;

   double last_sl_price = 0;
   datetime last_sl_time = 0;
   int last_sl_idx = -1;

   // Find the most recent confirmed Swing High and Swing Low
   for(int i = InpSwingWindow; i < bars_to_check - InpSwingWindow; i++)
   {
      // Check Swing High
      if(last_sh_idx == -1)
      {
         bool is_sh = true;
         double h = rates[i].high;
         for(int w = 1; w <= InpSwingWindow; w++)
         {
            if(rates[i - w].high >= h || rates[i + w].high >= h) { is_sh = false; break; }
         }
         if(is_sh)
         {
            last_sh_price = h;
            last_sh_time = rates[i].time;
            last_sh_idx = i;
         }
      }

      // Check Swing Low
      if(last_sl_idx == -1)
      {
         bool is_sl = true;
         double l = rates[i].low;
         for(int w = 1; w <= InpSwingWindow; w++)
         {
            if(rates[i - w].low <= l || rates[i + w].low <= l) { is_sl = false; break; }
         }
         if(is_sl)
         {
            last_sl_price = l;
            last_sl_time = rates[i].time;
            last_sl_idx = i;
         }
      }

      if(last_sh_idx != -1 && last_sl_idx != -1) break;
   }

   if(last_sh_price <= 0 || last_sl_price <= 0 || last_sh_price <= last_sl_price) return;

   double range_diff = last_sh_price - last_sl_price;
   datetime start_time = MathMin(last_sh_time, last_sl_time);
   datetime end_time = rates[0].time;

   // Check direction: if Swing Low occurred after Swing High -> Bearish Leg, else Bullish Leg
   bool is_bullish_leg = (last_sh_idx < last_sl_idx); // lower index = more recent

   double eq_500  = 0;
   double ote_618 = 0;
   double ote_705 = 0;
   double ote_786 = 0;

   if(is_bullish_leg)
   {
      // Pullback into discount
      eq_500  = last_sh_price - 0.500 * range_diff;
      ote_618 = last_sh_price - 0.618 * range_diff;
      ote_705 = last_sh_price - 0.705 * range_diff;
      ote_786 = last_sh_price - 0.786 * range_diff;
   }
   else
   {
      // Rally into premium
      eq_500  = last_sl_price + 0.500 * range_diff;
      ote_618 = last_sl_price + 0.618 * range_diff;
      ote_705 = last_sl_price + 0.705 * range_diff;
      ote_786 = last_sl_price + 0.786 * range_diff;
   }

   // 1. Draw OTE Zone Box (0.618 to 0.786)
   string ote_box = OBJ_PREFIX + "OTE_BOX";
   double top_ote = MathMax(ote_618, ote_786);
   double btm_ote = MathMin(ote_618, ote_786);

   ObjectCreate(0, ote_box, OBJ_RECTANGLE, 0, start_time, top_ote, end_time, btm_ote);
   ObjectSetInteger(0, ote_box, OBJPROP_COLOR, InpColorOTEZone);
   ObjectSetInteger(0, ote_box, OBJPROP_STYLE, STYLE_SOLID);
   ObjectSetInteger(0, ote_box, OBJPROP_BACK, true);
   ObjectSetInteger(0, ote_box, OBJPROP_FILL, true);

   // Helper line drawer
   DrawFiboLine("EQ_500", start_time, end_time, eq_500, "50.0% Equilibrium", InpColorEquilibrium, STYLE_DASH);
   DrawFiboLine("OTE_618", start_time, end_time, ote_618, "61.8% Golden Pocket", InpColorOTEZone, STYLE_SOLID);
   DrawFiboLine("OTE_705", start_time, end_time, ote_705, "70.5% Institutional Sweet Spot", InpColorOTEZone, STYLE_DASH);
   DrawFiboLine("OTE_786", start_time, end_time, ote_786, "78.6% Deep Level", InpColorOTEZone, STYLE_SOLID);

   // Anchors
   DrawFiboLine("ANC_HIGH", last_sh_time, end_time, last_sh_price, "High Anchor (100%)", InpColorAnchors, STYLE_DOT);
   DrawFiboLine("ANC_LOW", last_sl_time, end_time, last_sl_price, "Low Anchor (0%)", InpColorAnchors, STYLE_DOT);

   ChartRedraw();
}

void DrawFiboLine(string key, datetime t1, datetime t2, double price, string label, color clr, ENUM_LINE_STYLE style)
{
   string line_name = OBJ_PREFIX + "LINE_" + key;
   ObjectCreate(0, line_name, OBJ_TREND, 0, t1, price, t2, price);
   ObjectSetInteger(0, line_name, OBJPROP_COLOR, clr);
   ObjectSetInteger(0, line_name, OBJPROP_STYLE, style);
   ObjectSetInteger(0, line_name, OBJPROP_WIDTH, 1);
   ObjectSetInteger(0, line_name, OBJPROP_RAY_RIGHT, false);

   string text_name = OBJ_PREFIX + "TXT_" + key;
   ObjectCreate(0, text_name, OBJ_TEXT, 0, t2, price);
   ObjectSetString(0, text_name, OBJPROP_TEXT, " " + label + " (" + DoubleToString(price, _Digits) + ")");
   ObjectSetInteger(0, text_name, OBJPROP_COLOR, clr);
   ObjectSetInteger(0, text_name, OBJPROP_FONTSIZE, 8);
   ObjectSetInteger(0, text_name, OBJPROP_ANCHOR, ANCHOR_LEFT);
}
