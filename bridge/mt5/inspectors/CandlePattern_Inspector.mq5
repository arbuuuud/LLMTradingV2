//+------------------------------------------------------------------+
//|                                  CandlePattern_Inspector.mq5    |
//|                 Master Candlestick Confirmation Pattern Visual   |
//|                                  LLMTradingV2 Institutional V2   |
//+------------------------------------------------------------------+
#property copyright "LLMTradingV2"
#property link      "https://github.com/arbuuuud/LLMTradingV2"
#property version   "2.00"
#property description "Master Candlestick Inspector: Engulfing, Pin Bar, Star, and Marubozu with Auto Internal POI Detection for Strategy Tester & Live Chart"

//--- Inputs
input group "=== POI Confluence Filter Settings ==="
input bool     InpFilterOnlyAtPOI      = true;              // Only show candle patterns that touch an active POI (OB/Floor/Roof)
input int      InpMaxBars              = 500;               // Lookback bars to analyze
input int      InpMaxPatternsToShow    = 25;                // Max recent pattern badges to draw (anti-clutter)
input bool     InpShowPOIBoxes         = true;              // Draw background POI zones so you can see why the pattern triggered!

input group "=== Pattern Category Toggles ==="
input bool     InpShowEngulfing        = true;              // Show Bullish & Bearish Engulfing
input bool     InpShowPinBar           = true;              // Show Rejection Pin Bars (Hammer / Shooting Star)
input bool     InpShowStars            = true;              // Show Morning Star & Evening Star
input bool     InpShowMarubozu         = true;              // Show Momentum Marubozu (Displacement)

input group "=== Color Palette ==="
input color    InpColorBullishPat      = C'0,255,127';      // Bullish Confirmation (SpringGreen)
input color    InpColorBearishPat      = C'255,69,0';       // Bearish Confirmation (OrangeRed)
input color    InpColorMarubozuBull    = C'30,144,255';     // Bullish Marubozu (DodgerBlue)
input color    InpColorMarubozuBear    = C'220,20,60';      // Bearish Marubozu (Crimson)
input color    InpColorPOIBox          = C'40,40,40';       // Internal POI Box Color (Subtle Dark Grey)

#define OBJ_PREFIX "PAT_INSP_"

enum ENUM_CANDLE_PATTERN
{
   PAT_BULLISH_ENGULFING,
   PAT_BEARISH_ENGULFING,
   PAT_BULLISH_PIN_BAR,
   PAT_BEARISH_PIN_BAR,
   PAT_MORNING_STAR,
   PAT_EVENING_STAR,
   PAT_MARUBOZU_BULL,
   PAT_MARUBOZU_BEAR
};

struct DetectedPattern
{
   ENUM_CANDLE_PATTERN pat_type;
   bool                is_bullish;
   datetime            time;
   double              price_level;
   string              label;
   color               clr;
   int                 arrow_code;
};

struct InternalPOI
{
   double   top;
   double   bottom;
   datetime time;
   bool     is_bullish;
   bool     is_broken;
};

datetime g_last_bar_time = 0;

//+------------------------------------------------------------------+
//| Expert initialization function                                   |
//+------------------------------------------------------------------+
int OnInit()
{
   CleanObjects();
   RedrawPatterns();
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
      RedrawPatterns();
   }
}

//+------------------------------------------------------------------+
//| Scan Active POIs directly from rates array                       |
//+------------------------------------------------------------------+
int ScanInternalPOIs(const MqlRates &rates[], int total_bars, InternalPOI &pois[])
{
   int poi_count = 0;
   ArrayResize(pois, 0);

   for(int i = total_bars - 5; i >= 1; i--)
   {
      bool is_bull = (rates[i].low > rates[i + 2].high);
      bool is_bear = (rates[i].high < rates[i + 2].low);
      if(!is_bull && !is_bear) continue;

      int origin = i + 2;
      double top = rates[origin].high;
      double btm = rates[origin].low;

      // Lifecycle check down to bar 0
      bool broken = false;
      for(int k = origin - 1; k >= 0; k--)
      {
         if(is_bull && rates[k].close < btm) { broken = true; break; }
         else if(!is_bull && rates[k].close > top) { broken = true; break; }
      }
      if(broken) continue;

      InternalPOI p;
      p.top = top;
      p.bottom = btm;
      p.time = rates[origin].time;
      p.is_bullish = is_bull;
      p.is_broken = false;

      ArrayResize(pois, poi_count + 1);
      pois[poi_count] = p;
      poi_count++;
   }

   return poi_count;
}

//+------------------------------------------------------------------+
//| Check if candle touches an active internal POI or chart object   |
//+------------------------------------------------------------------+
bool IsCandleAtActivePOI(double candle_high, double candle_low, const InternalPOI &pois[], int poi_count)
{
   // 1. Check internal standalone POI array (works 100% in Strategy Tester!)
   for(int p = 0; p < poi_count; p++)
   {
      if(candle_low <= pois[p].top && candle_high >= pois[p].bottom)
      {
         return true;
      }
   }

   // 2. Fallback check for external chart objects if present
   int total_objs = ObjectsTotal(0, 0, OBJ_RECTANGLE);
   for(int i = 0; i < total_objs; i++)
   {
      string name = ObjectName(0, i, 0, OBJ_RECTANGLE);
      if(StringFind(name, "OB_INSP_") == 0 || StringFind(name, "FVG_INSP_") == 0)
      {
         double p1 = ObjectGetDouble(0, name, OBJPROP_PRICE, 0);
         double p2 = ObjectGetDouble(0, name, OBJPROP_PRICE, 1);
         double top = MathMax(p1, p2);
         double btm = MathMin(p1, p2);

         if(candle_low <= top && candle_high >= btm)
         {
            return true;
         }
      }
   }

   return false;
}

//+------------------------------------------------------------------+
//| Pattern Detection & Rendering Core Engine                        |
//+------------------------------------------------------------------+
void RedrawPatterns()
{
   CleanObjects();

   int total_bars = iBars(_Symbol, _Period);
   int bars_to_check = MathMin(InpMaxBars, total_bars - 4);
   if(bars_to_check < 4) return;

   MqlRates rates[];
   ArraySetAsSeries(rates, true);
   int copied = CopyRates(_Symbol, _Period, 0, bars_to_check, rates);
   if(copied < 4) return;
   bars_to_check = copied;

   datetime current_candle_time = rates[0].time;

   // 1. Scan Internal POI Zones
   InternalPOI pois[];
   int poi_count = ScanInternalPOIs(rates, bars_to_check, pois);

   // Optional: Draw subtle POI background boxes so user sees the zone
   if(InpShowPOIBoxes)
   {
      for(int p = 0; p < MathMin(poi_count, 10); p++)
      {
         string box_name = OBJ_PREFIX + "POI_" + IntegerToString(p);
         ObjectCreate(0, box_name, OBJ_RECTANGLE, 0, pois[p].time, pois[p].top, current_candle_time, pois[p].bottom);
         ObjectSetInteger(0, box_name, OBJPROP_COLOR, InpColorPOIBox);
         ObjectSetInteger(0, box_name, OBJPROP_STYLE, STYLE_DOT);
         ObjectSetInteger(0, box_name, OBJPROP_WIDTH, 1);
         ObjectSetInteger(0, box_name, OBJPROP_BACK, true);
         ObjectSetInteger(0, box_name, OBJPROP_FILL, true);
      }
   }

   DetectedPattern patterns[];
   int pat_count = 0;

   // Scan bars from oldest to newest (up to bar 1, closed candles)
   for(int i = bars_to_check - 3; i >= 1; i--)
   {
      double o = rates[i].open;
      double h = rates[i].high;
      double l = rates[i].low;
      double c = rates[i].close;
      double c_range = MathMax(h - l, _Point * 10);
      double body = MathAbs(c - o);
      double body_ratio = body / c_range;

      double o_prev = rates[i + 1].open;
      double h_prev = rates[i + 1].high;
      double l_prev = rates[i + 1].low;
      double c_prev = rates[i + 1].close;

      double upper_wick = h - MathMax(o, c);
      double lower_wick = MathMin(o, c) - l;
      double upper_wick_ratio = upper_wick / c_range;
      double lower_wick_ratio = lower_wick / c_range;

      bool found = false;
      DetectedPattern p;
      p.time = rates[i].time;

      // 1. Morning Star & Evening Star (3-bar reversal, requires i+2)
      if(InpShowStars && i + 2 < bars_to_check)
      {
         double o_p2 = rates[i + 2].open;
         double c_p2 = rates[i + 2].close;
         double body_prev = MathAbs(c_prev - o_prev);
         double range_prev = MathMax(h_prev - l_prev, _Point * 10);

         // Morning Star
         if((c_p2 < o_p2) && (body_prev / range_prev <= 0.40) && (c > o))
         {
            double mid_p2 = (o_p2 + c_p2) / 2.0;
            if(c >= mid_p2)
            {
               p.pat_type = PAT_MORNING_STAR;
               p.is_bullish = true;
               p.price_level = l;
               p.label = "★ Morning Star";
               p.clr = InpColorBullishPat;
               p.arrow_code = 233; // Arrow Up
               found = true;
            }
         }
         // Evening Star
         else if((c_p2 > o_p2) && (body_prev / range_prev <= 0.40) && (c < o))
         {
            double mid_p2 = (o_p2 + c_p2) / 2.0;
            if(c <= mid_p2)
            {
               p.pat_type = PAT_EVENING_STAR;
               p.is_bullish = false;
               p.price_level = h;
               p.label = "★ Evening Star";
               p.clr = InpColorBearishPat;
               p.arrow_code = 234; // Arrow Down
               found = true;
            }
         }
      }

      // 2. Engulfing
      if(!found && InpShowEngulfing)
      {
         if(c_prev < o_prev && c > o && c >= o_prev && o <= c_prev)
         {
            p.pat_type = PAT_BULLISH_ENGULFING;
            p.is_bullish = true;
            p.price_level = l;
            p.label = "Bullish Engulfing";
            p.clr = InpColorBullishPat;
            p.arrow_code = 233;
            found = true;
         }
         else if(c_prev > o_prev && c < o && c <= o_prev && o >= c_prev)
         {
            p.pat_type = PAT_BEARISH_ENGULFING;
            p.is_bullish = false;
            p.price_level = h;
            p.label = "Bearish Engulfing";
            p.clr = InpColorBearishPat;
            p.arrow_code = 234;
            found = true;
         }
      }

      // 3. Pin Bar / Rejection Wick
      if(!found && InpShowPinBar)
      {
         if(lower_wick_ratio >= 0.55 && body_ratio <= 0.40 && upper_wick_ratio <= 0.25)
         {
            p.pat_type = PAT_BULLISH_PIN_BAR;
            p.is_bullish = true;
            p.price_level = l;
            p.label = "Pin Bar (Hammer)";
            p.clr = InpColorBullishPat;
            p.arrow_code = 233;
            found = true;
         }
         else if(upper_wick_ratio >= 0.55 && body_ratio <= 0.40 && lower_wick_ratio <= 0.25)
         {
            p.pat_type = PAT_BEARISH_PIN_BAR;
            p.is_bullish = false;
            p.price_level = h;
            p.label = "Pin Bar (Star)";
            p.clr = InpColorBearishPat;
            p.arrow_code = 234;
            found = true;
         }
      }

      // 4. Momentum Marubozu
      if(!found && InpShowMarubozu && body_ratio >= 0.75)
      {
         if(c > o)
         {
            p.pat_type = PAT_MARUBOZU_BULL;
            p.is_bullish = true;
            p.price_level = l;
            p.label = "Marubozu Bull";
            p.clr = InpColorMarubozuBull;
            p.arrow_code = 233;
            found = true;
         }
         else
         {
            p.pat_type = PAT_MARUBOZU_BEAR;
            p.is_bullish = false;
            p.price_level = h;
            p.label = "Marubozu Bear";
            p.clr = InpColorMarubozuBear;
            p.arrow_code = 234;
            found = true;
         }
      }

      if(found)
      {
         bool at_poi = IsCandleAtActivePOI(h, l, pois, poi_count);
         if(InpFilterOnlyAtPOI && !at_poi)
         {
            continue; // Dropped by strict POI filter!
         }

         if(at_poi)
         {
            p.label += " [★ AT POI]";
         }

         ArrayResize(patterns, pat_count + 1);
         patterns[pat_count] = p;
         pat_count++;
      }
   }

   // Render only up to InpMaxPatternsToShow newest patterns
   int start_render = MathMax(0, pat_count - InpMaxPatternsToShow);
   for(int k = start_render; k < pat_count; k++)
   {
      DrawPatternMarker(patterns[k], k);
   }

   ChartRedraw();
}

//+------------------------------------------------------------------+
//| Graphic Renderer Helper                                          |
//+------------------------------------------------------------------+
void DrawPatternMarker(const DetectedPattern &p, int index)
{
   string id_str = IntegerToString(p.time) + "_" + IntegerToString(index);
   string arrow_name = OBJ_PREFIX + "ARR_" + id_str;
   string text_name = OBJ_PREFIX + "LBL_" + id_str;

   double offset = _Point * 30; // 3 pips
   double arrow_price = p.is_bullish ? (p.price_level - offset) : (p.price_level + offset);
   double text_price  = p.is_bullish ? (arrow_price - offset * 1.5) : (arrow_price + offset * 1.5);

   // 1. Directional Arrow Marker
   ObjectCreate(0, arrow_name, OBJ_ARROW, 0, p.time, arrow_price);
   ObjectSetInteger(0, arrow_name, OBJPROP_ARROWCODE, p.arrow_code);
   ObjectSetInteger(0, arrow_name, OBJPROP_COLOR, p.clr);
   ObjectSetInteger(0, arrow_name, OBJPROP_WIDTH, 2);
   ObjectSetInteger(0, arrow_name, OBJPROP_BACK, false);

   // 2. Informative Label Badge
   ObjectCreate(0, text_name, OBJ_TEXT, 0, p.time, text_price);
   ObjectSetString(0, text_name, OBJPROP_TEXT, p.label);
   ObjectSetInteger(0, text_name, OBJPROP_COLOR, p.clr);
   ObjectSetInteger(0, text_name, OBJPROP_FONTSIZE, 8);
   ObjectSetInteger(0, text_name, OBJPROP_ANCHOR, p.is_bullish ? ANCHOR_UPPER : ANCHOR_LOWER);
}
//+------------------------------------------------------------------+
