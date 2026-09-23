//+------------------------------------------------------------------+
//|                                         Liquidity_Inspector.mq5  |
//|                 Visual Inspector for Liquidity Pools & Sweeps    |
//|                                  LLMTradingV2 Institutional V2   |
//+------------------------------------------------------------------+
#property copyright "LLMTradingV2"
#property link      "https://github.com/arbuuuud/LLMTradingV2"
#property version   "1.00"
#property description "Visualizes Buy-Side/Sell-Side Liquidity Pools (EQH/EQL) and Liquidity Sweeps"

//--- Inputs
input group "=== Liquidity Settings ==="
input int      InpSwingWindow       = 3;                 // Fractal Window
input int      InpMaxBars           = 300;               // Max Bars to Analyze
input double   InpEqualTolerancePts = 25.0;              // Equal High/Low Tolerance in Points
input color    InpColorBSL          = C'239,68,68';      // Buy-Side Liquidity (Red)
input color    InpColorSSL          = C'16,185,129';     // Sell-Side Liquidity (Green)
input color    InpColorSweep        = clrYellow;         // Sweep Marker Color

#define OBJ_PREFIX "LIQ_INSP_"

datetime g_last_bar_time = 0;

int OnInit()
{
   CleanObjects();
   RedrawLiquidity();
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
      RedrawLiquidity();
   }
}

void RedrawLiquidity()
{
   CleanObjects();

   int total_bars = iBars(_Symbol, _Period);
   int bars_to_check = MathMin(InpMaxBars, total_bars - InpSwingWindow - 1);
   if(bars_to_check < InpSwingWindow * 2 + 1) return;

   MqlRates rates[];
   ArraySetAsSeries(rates, true);
   if(CopyRates(_Symbol, _Period, 0, bars_to_check, rates) < bars_to_check) return;

   // 1. Collect Swing Highs & Lows
   double sh_prices[];
   datetime sh_times[];
   int sh_indices[];

   double sl_prices[];
   datetime sl_times[];
   int sl_indices[];

   for(int i = InpSwingWindow; i < bars_to_check - InpSwingWindow; i++)
   {
      bool is_sh = true;
      double h = rates[i].high;
      for(int w = 1; w <= InpSwingWindow; w++)
      {
         if(rates[i - w].high >= h || rates[i + w].high >= h) { is_sh = false; break; }
      }
      if(is_sh)
      {
         int sz = ArraySize(sh_prices);
         ArrayResize(sh_prices, sz + 1);
         ArrayResize(sh_times, sz + 1);
         ArrayResize(sh_indices, sz + 1);
         sh_prices[sz] = h;
         sh_times[sz] = rates[i].time;
         sh_indices[sz] = i;
      }

      bool is_sl = true;
      double l = rates[i].low;
      for(int w = 1; w <= InpSwingWindow; w++)
      {
         if(rates[i - w].low <= l || rates[i + w].low <= l) { is_sl = false; break; }
      }
      if(is_sl)
      {
         int sz = ArraySize(sl_prices);
         ArrayResize(sl_prices, sz + 1);
         ArrayResize(sl_times, sz + 1);
         ArrayResize(sl_indices, sz + 1);
         sl_prices[sz] = l;
         sl_times[sz] = rates[i].time;
         sl_indices[sz] = i;
      }
   }

   // 2. Check for Equal Highs (EQH / Buy-Side Liquidity Pool)
   double tol = InpEqualTolerancePts * _Point;
   for(int i = 0; i < ArraySize(sh_prices) - 1; i++)
   {
      for(int j = i + 1; j < ArraySize(sh_prices); j++)
      {
         if(MathAbs(sh_prices[i] - sh_prices[j]) <= tol)
         {
            double pool_price = MathMax(sh_prices[i], sh_prices[j]);
            string line_name = OBJ_PREFIX + "EQH_" + IntegerToString(sh_times[j]);
            ObjectCreate(0, line_name, OBJ_TREND, 0, sh_times[j], pool_price, rates[0].time, pool_price);
            ObjectSetInteger(0, line_name, OBJPROP_COLOR, InpColorBSL);
            ObjectSetInteger(0, line_name, OBJPROP_STYLE, STYLE_DOT);
            ObjectSetInteger(0, line_name, OBJPROP_WIDTH, 2);
            ObjectSetInteger(0, line_name, OBJPROP_RAY_RIGHT, false);

            string text_name = OBJ_PREFIX + "TXT_" + line_name;
            ObjectCreate(0, text_name, OBJ_TEXT, 0, rates[0].time, pool_price);
            ObjectSetString(0, text_name, OBJPROP_TEXT, " $$$ BSL (Equal Highs)");
            ObjectSetInteger(0, text_name, OBJPROP_COLOR, InpColorBSL);
            ObjectSetInteger(0, text_name, OBJPROP_FONTSIZE, 8);
            ObjectSetInteger(0, text_name, OBJPROP_ANCHOR, ANCHOR_LEFT);
            break;
         }
      }
   }

   // 3. Check for Equal Lows (EQL / Sell-Side Liquidity Pool)
   for(int i = 0; i < ArraySize(sl_prices) - 1; i++)
   {
      for(int j = i + 1; j < ArraySize(sl_prices); j++)
      {
         if(MathAbs(sl_prices[i] - sl_prices[j]) <= tol)
         {
            double pool_price = MathMin(sl_prices[i], sl_prices[j]);
            string line_name = OBJ_PREFIX + "EQL_" + IntegerToString(sl_times[j]);
            ObjectCreate(0, line_name, OBJ_TREND, 0, sl_times[j], pool_price, rates[0].time, pool_price);
            ObjectSetInteger(0, line_name, OBJPROP_COLOR, InpColorSSL);
            ObjectSetInteger(0, line_name, OBJPROP_STYLE, STYLE_DOT);
            ObjectSetInteger(0, line_name, OBJPROP_WIDTH, 2);
            ObjectSetInteger(0, line_name, OBJPROP_RAY_RIGHT, false);

            string text_name = OBJ_PREFIX + "TXT_" + line_name;
            ObjectCreate(0, text_name, OBJ_TEXT, 0, rates[0].time, pool_price);
            ObjectSetString(0, text_name, OBJPROP_TEXT, " $$$ SSL (Equal Lows)");
            ObjectSetInteger(0, text_name, OBJPROP_COLOR, InpColorSSL);
            ObjectSetInteger(0, text_name, OBJPROP_FONTSIZE, 8);
            ObjectSetInteger(0, text_name, OBJPROP_ANCHOR, ANCHOR_LEFT);
            break;
         }
      }
   }

   // 4. Detect Liquidity Sweeps
   // If any recent candle wick pierced the recent Swing High/Low, but candle body closed back inside
   if(ArraySize(sh_prices) > 0)
   {
      double recent_sh = sh_prices[0];
      for(int k = sh_indices[0] - 1; k >= 0; k--)
      {
         if(rates[k].high > recent_sh && rates[k].close <= recent_sh)
         {
            string swp_name = OBJ_PREFIX + "SWEEP_BSL_" + IntegerToString(rates[k].time);
            ObjectCreate(0, swp_name, OBJ_ARROW_DOWN, 0, rates[k].time, rates[k].high + 15 * _Point);
            ObjectSetInteger(0, swp_name, OBJPROP_COLOR, InpColorSweep);
            ObjectSetInteger(0, swp_name, OBJPROP_WIDTH, 2);

            string swp_txt = OBJ_PREFIX + "TXT_SWEEP_BSL_" + IntegerToString(rates[k].time);
            ObjectCreate(0, swp_txt, OBJ_TEXT, 0, rates[k].time, rates[k].high + 25 * _Point);
            ObjectSetString(0, swp_txt, OBJPROP_TEXT, "BSL Swept!");
            ObjectSetInteger(0, swp_txt, OBJPROP_COLOR, InpColorSweep);
            ObjectSetInteger(0, swp_txt, OBJPROP_FONTSIZE, 8);
            ObjectSetInteger(0, swp_txt, OBJPROP_ANCHOR, ANCHOR_LOWER);
            break;
         }
      }
   }

   if(ArraySize(sl_prices) > 0)
   {
      double recent_sl = sl_prices[0];
      for(int k = sl_indices[0] - 1; k >= 0; k--)
      {
         if(rates[k].low < recent_sl && rates[k].close >= recent_sl)
         {
            string swp_name = OBJ_PREFIX + "SWEEP_SSL_" + IntegerToString(rates[k].time);
            ObjectCreate(0, swp_name, OBJ_ARROW_UP, 0, rates[k].time, rates[k].low - 15 * _Point);
            ObjectSetInteger(0, swp_name, OBJPROP_COLOR, InpColorSweep);
            ObjectSetInteger(0, swp_name, OBJPROP_WIDTH, 2);

            string swp_txt = OBJ_PREFIX + "TXT_SWEEP_SSL_" + IntegerToString(rates[k].time);
            ObjectCreate(0, swp_txt, OBJ_TEXT, 0, rates[k].time, rates[k].low - 25 * _Point);
            ObjectSetString(0, swp_txt, OBJPROP_TEXT, "SSL Swept!");
            ObjectSetInteger(0, swp_txt, OBJPROP_COLOR, InpColorSweep);
            ObjectSetInteger(0, swp_txt, OBJPROP_FONTSIZE, 8);
            ObjectSetInteger(0, swp_txt, OBJPROP_ANCHOR, ANCHOR_UPPER);
            break;
         }
      }
   }

   ChartRedraw();
}
