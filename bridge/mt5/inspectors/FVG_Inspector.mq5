//+------------------------------------------------------------------+
//|                                            FVG_Inspector.mq5     |
//|    Nearest 2 Above, 2 Below + 1 Current Inside Zone Proximity    |
//|                                  LLMTradingV2 Institutional V2   |
//+------------------------------------------------------------------+
#property copyright "LLMTradingV2"
#property link      "https://github.com/arbuuuud/LLMTradingV2"
#property version   "2.20"
#property description "Displays ONLY 2 Nearest Zones Above, 2 Nearest Zones Below, plus 1 Current Inside Zone if price is within a gap"

//--- Inputs
input group "=== Proximity Display Settings ==="
input int      InpMaxZonesAbove        = 2;                 // Max Nearest Zones Above Price (Overhead)
input int      InpMaxZonesBelow        = 2;                 // Max Nearest Zones Below Price (Underlying)
input int      InpMaxBars              = 300;               // Max Bars to Analyze
input double   InpMinGapPoints         = 10.0;              // Minimum Gap Size (Points)
input bool     InpExtendToCurrent      = true;              // Extend Zones to Current Candle

input group "=== Regular FVG Colors ==="
input color    InpColorBullFVG         = C'16,185,129';     // Bullish FVG Box Color (Emerald)
input color    InpColorBearFVG         = C'239,68,68';      // Bearish FVG Box Color (Rose)
input bool     InpShowCE50             = true;              // Show 50% Consequent Encroachment (CE) Line
input color    InpColorCE              = C'250,204,21';     // CE 50% Line Color (Yellow)

input group "=== Inversion FVG (iFVG) Colors ==="
input color    InpColorInversionClean  = clrGold;           // Standard iFVG Box Color (Gold)
input color    InpColorInversionPower  = C'249,115,22';     // Powerful iFVG Breached WITH Counter-FVG (Orange)

input group "=== Combined FVG + iFVG Confluence Colors ==="
input color    InpColorCombined        = C'6,182,212';      // Combined Confluence Highlight (Cyan/Neon)
input color    InpColorInsideZone      = clrWhite;          // Highlight Border for Current Inside Zone

#define OBJ_PREFIX "FVG_INSP_"

enum ENUM_ZONE_TYPE
{
   ZONE_REGULAR_FVG,
   ZONE_INVERSION_FVG,
   ZONE_COMBINED_CONFLUENCE
};

struct FVGNode
{
   string   id;
   bool     is_bullish;
   double   top;
   double   bottom;
   double   ce_price;
   datetime time;
   int      bar_idx;
   bool     is_mitigated;
   bool     is_inverted;
   datetime invert_time;
   bool     inverted_with_counter_fvg;
   string   counter_fvg_id;
};

struct CandidateZone
{
   ENUM_ZONE_TYPE type;
   string   id;
   string   display_label;
   color    box_color;
   bool     is_bullish;
   double   top;
   double   bottom;
   double   ce_price;
   datetime start_time;
   bool     is_mitigated;
   bool     has_counter_fvg;
   double   distance_to_price;
};

datetime g_last_bar_time = 0;

int OnInit()
{
   CleanObjects();
   RedrawFVGSystem();
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
      RedrawFVGSystem();
   }
}

void RedrawFVGSystem()
{
   CleanObjects();

   int total_bars = iBars(_Symbol, _Period);
   int bars_to_check = MathMin(InpMaxBars, total_bars - 3);
   if(bars_to_check < 3) return;

   MqlRates rates[];
   ArraySetAsSeries(rates, true);
   if(CopyRates(_Symbol, _Period, 0, bars_to_check, rates) < bars_to_check) return;

   datetime current_t = rates[0].time;
   double cur_price = rates[0].close;

   // 1. Detect All FVGs Chronologically
   FVGNode all_fvgs[];
   ArrayResize(all_fvgs, 0);

   for(int i = bars_to_check - 3; i >= 1; i--)
   {
      double c1_high = rates[i + 2].high;
      double c1_low  = rates[i + 2].low;
      double c3_high = rates[i].high;
      double c3_low  = rates[i].low;
      datetime gap_t = rates[i + 1].time;

      bool is_bull = (c3_low - c1_high) >= (InpMinGapPoints * _Point);
      bool is_bear = (c1_low - c3_high) >= (InpMinGapPoints * _Point);

      if(!is_bull && !is_bear) continue;

      int sz = ArraySize(all_fvgs);
      ArrayResize(all_fvgs, sz + 1);
      all_fvgs[sz].id            = "FVG_" + IntegerToString(gap_t);
      all_fvgs[sz].is_bullish    = is_bull;
      all_fvgs[sz].top           = is_bull ? c3_low : c1_low;
      all_fvgs[sz].bottom        = is_bull ? c1_high : c3_high;
      all_fvgs[sz].ce_price      = (all_fvgs[sz].top + all_fvgs[sz].bottom) / 2.0;
      all_fvgs[sz].time          = gap_t;
      all_fvgs[sz].bar_idx       = i;
      all_fvgs[sz].is_mitigated  = false;
      all_fvgs[sz].is_inverted   = false;
      all_fvgs[sz].inverted_with_counter_fvg = false;
      all_fvgs[sz].counter_fvg_id = "";
   }

   int total_fvg_count = ArraySize(all_fvgs);
   if(total_fvg_count == 0) return;

   // 2. Track Mitigation and Inversion (Breach) status
   for(int f = 0; f < total_fvg_count; f++)
   {
      int start_bar = all_fvgs[f].bar_idx - 1;
      for(int k = start_bar; k >= 0; k--)
      {
         if(all_fvgs[f].is_bullish)
         {
            if(rates[k].low <= all_fvgs[f].top)
            {
               all_fvgs[f].is_mitigated = true;
            }
            if(rates[k].close < all_fvgs[f].bottom)
            {
               all_fvgs[f].is_inverted = true;
               all_fvgs[f].invert_time = rates[k].time;

               for(int cf = 0; cf < total_fvg_count; cf++)
               {
                  if(!all_fvgs[cf].is_bullish && MathAbs(all_fvgs[cf].bar_idx - k) <= 2)
                  {
                     all_fvgs[f].inverted_with_counter_fvg = true;
                     all_fvgs[f].counter_fvg_id = all_fvgs[cf].id;
                     break;
                  }
               }
               break;
            }
         }
         else // bearish fvg
         {
            if(rates[k].high >= all_fvgs[f].bottom)
            {
               all_fvgs[f].is_mitigated = true;
            }
            if(rates[k].close > all_fvgs[f].top)
            {
               all_fvgs[f].is_inverted = true;
               all_fvgs[f].invert_time = rates[k].time;

               for(int cf = 0; cf < total_fvg_count; cf++)
               {
                  if(all_fvgs[cf].is_bullish && MathAbs(all_fvgs[cf].bar_idx - k) <= 2)
                  {
                     all_fvgs[f].inverted_with_counter_fvg = true;
                     all_fvgs[f].counter_fvg_id = all_fvgs[cf].id;
                     break;
                  }
               }
               break;
            }
         }
      }
   }

   // 3. Collect Candidate Zones
   CandidateZone candidates[];
   ArrayResize(candidates, 0);

   // A. Combined Confluences (FVG + iFVG Overlap)
   bool fvg_in_confluence[];
   ArrayResize(fvg_in_confluence, total_fvg_count);
   ArrayInitialize(fvg_in_confluence, false);

   for(int f = 0; f < total_fvg_count; f++)
   {
      if(all_fvgs[f].is_inverted) continue;

      for(int k = 0; k < total_fvg_count; k++)
      {
         if(!all_fvgs[k].is_inverted) continue;

         double overlap_top = MathMin(all_fvgs[f].top, all_fvgs[k].top);
         double overlap_btm = MathMax(all_fvgs[f].bottom, all_fvgs[k].bottom);

         if(overlap_top > overlap_btm)
         {
            fvg_in_confluence[f] = true;
            fvg_in_confluence[k] = true;

            int c_sz = ArraySize(candidates);
            ArrayResize(candidates, c_sz + 1);
            candidates[c_sz].type              = ZONE_COMBINED_CONFLUENCE;
            candidates[c_sz].id                = "COMB_" + all_fvgs[f].id + "_" + all_fvgs[k].id;
            candidates[c_sz].top               = overlap_top;
            candidates[c_sz].bottom            = overlap_btm;
            candidates[c_sz].ce_price          = (overlap_top + overlap_btm) / 2.0;
            candidates[c_sz].start_time        = MathMax(all_fvgs[f].time, all_fvgs[k].invert_time);
            candidates[c_sz].box_color         = InpColorCombined;
            candidates[c_sz].is_bullish        = all_fvgs[f].is_bullish;
            candidates[c_sz].is_mitigated      = false;
            candidates[c_sz].has_counter_fvg   = all_fvgs[k].inverted_with_counter_fvg;

            double pts = (overlap_top - overlap_btm) / _Point;
            candidates[c_sz].display_label     = StringFormat(" ★ [COMBINED: FVG + iFVG] (%.0f pts)", pts);
         }
      }
   }

   // B. Inversion FVGs (iFVG)
   for(int f = 0; f < total_fvg_count; f++)
   {
      if(!all_fvgs[f].is_inverted) continue;
      if(fvg_in_confluence[f]) continue;

      int c_sz = ArraySize(candidates);
      ArrayResize(candidates, c_sz + 1);
      candidates[c_sz].type              = ZONE_INVERSION_FVG;
      candidates[c_sz].id                = "IFVG_" + all_fvgs[f].id;
      candidates[c_sz].top               = all_fvgs[f].top;
      candidates[c_sz].bottom            = all_fvgs[f].bottom;
      candidates[c_sz].ce_price          = all_fvgs[f].ce_price;
      candidates[c_sz].start_time        = all_fvgs[f].invert_time;
      candidates[c_sz].box_color         = all_fvgs[f].inverted_with_counter_fvg ? InpColorInversionPower : InpColorInversionClean;
      candidates[c_sz].is_bullish        = !all_fvgs[f].is_bullish;
      candidates[c_sz].is_mitigated      = false;
      candidates[c_sz].has_counter_fvg   = all_fvgs[f].inverted_with_counter_fvg;

      double pts = (all_fvgs[f].top - all_fvgs[f].bottom) / _Point;
      string role = candidates[c_sz].is_bullish ? "iFVG Support" : "iFVG Resistance";
      if(all_fvgs[f].inverted_with_counter_fvg) role += " [Counter-FVG!]";
      candidates[c_sz].display_label     = StringFormat(" %s (%.0f pts)", role, pts);
   }

   // C. Regular Active FVGs
   for(int f = 0; f < total_fvg_count; f++)
   {
      if(all_fvgs[f].is_inverted) continue;
      if(fvg_in_confluence[f]) continue;

      int c_sz = ArraySize(candidates);
      ArrayResize(candidates, c_sz + 1);
      candidates[c_sz].type              = ZONE_REGULAR_FVG;
      candidates[c_sz].id                = "REG_" + all_fvgs[f].id;
      candidates[c_sz].top               = all_fvgs[f].top;
      candidates[c_sz].bottom            = all_fvgs[f].bottom;
      candidates[c_sz].ce_price          = all_fvgs[f].ce_price;
      candidates[c_sz].start_time        = all_fvgs[f].time;
      candidates[c_sz].box_color         = all_fvgs[f].is_bullish ? InpColorBullFVG : InpColorBearFVG;
      candidates[c_sz].is_bullish        = all_fvgs[f].is_bullish;
      candidates[c_sz].is_mitigated      = all_fvgs[f].is_mitigated;
      candidates[c_sz].has_counter_fvg   = false;

      double pts = (all_fvgs[f].top - all_fvgs[f].bottom) / _Point;
      string m_tag = all_fvgs[f].is_mitigated ? " [Mit]" : " [Fresh]";
      candidates[c_sz].display_label     = StringFormat(" %s (%.0f pts)%s CE: %.2f",
         all_fvgs[f].is_bullish ? "Bull FVG" : "Bear FVG", pts, m_tag, all_fvgs[f].ce_price);
   }

   // 4. Classify Zones: Strictly Above, Strictly Below, and Current Inside Zone
   CandidateZone above_zones[];
   CandidateZone below_zones[];
   CandidateZone inside_zones[];
   ArrayResize(above_zones, 0);
   ArrayResize(below_zones, 0);
   ArrayResize(inside_zones, 0);

   for(int i = 0; i < ArraySize(candidates); i++)
   {
      // A. Check if price is INSIDE this zone
      if(cur_price >= candidates[i].bottom && cur_price <= candidates[i].top)
      {
         int in_sz = ArraySize(inside_zones);
         ArrayResize(inside_zones, in_sz + 1);
         candidates[i].distance_to_price = 0.0;
         inside_zones[in_sz] = candidates[i];
      }
      // B. Strictly Above (bottom > cur_price)
      else if(candidates[i].bottom > cur_price)
      {
         int a_sz = ArraySize(above_zones);
         ArrayResize(above_zones, a_sz + 1);
         candidates[i].distance_to_price = candidates[i].bottom - cur_price;
         above_zones[a_sz] = candidates[i];
      }
      // C. Strictly Below (top < cur_price)
      else if(candidates[i].top < cur_price)
      {
         int b_sz = ArraySize(below_zones);
         ArrayResize(below_zones, b_sz + 1);
         candidates[i].distance_to_price = cur_price - candidates[i].top;
         below_zones[b_sz] = candidates[i];
      }
   }

   // Sort strictly by distance to price (closest first)
   SortZonesByProximity(above_zones);
   SortZonesByProximity(below_zones);

   // 5. Render Nearest Above Zones (at most 2)
   int num_above = MathMin(InpMaxZonesAbove, ArraySize(above_zones));
   for(int i = 0; i < num_above; i++)
   {
      string rank_prefix = StringFormat("[Above #%d] ", i + 1);
      DrawZoneObject(above_zones[i], rank_prefix, current_t, false);
   }

   // 6. Render Nearest Below Zones (at most 2)
   int num_below = MathMin(InpMaxZonesBelow, ArraySize(below_zones));
   for(int i = 0; i < num_below; i++)
   {
      string rank_prefix = StringFormat("[Below #%d] ", i + 1);
      DrawZoneObject(below_zones[i], rank_prefix, current_t, false);
   }

   // 7. Render Current Inside Zone (if any)
   if(ArraySize(inside_zones) > 0)
   {
      // Pick the most recent / highest priority inside zone
      DrawZoneObject(inside_zones[0], "⚡ [CURRENT INSIDE ZONE] ", current_t, true);
   }

   ChartRedraw();
}

void SortZonesByProximity(CandidateZone &arr[])
{
   int n = ArraySize(arr);
   for(int i = 0; i < n - 1; i++)
   {
      for(int j = 0; j < n - i - 1; j++)
      {
         if(arr[j].distance_to_price > arr[j + 1].distance_to_price)
         {
            CandidateZone temp = arr[j];
            arr[j] = arr[j + 1];
            arr[j + 1] = temp;
         }
      }
   }
}

void DrawZoneObject(const CandidateZone &zone, string rank_tag, datetime current_t, bool is_current_inside)
{
   datetime end_t = current_t;
   string box_id = OBJ_PREFIX + "BOX_" + zone.id;

   ObjectCreate(0, box_id, OBJ_RECTANGLE, 0, zone.start_time, zone.top, end_t, zone.bottom);
   ObjectSetInteger(0, box_id, OBJPROP_COLOR, is_current_inside ? InpColorInsideZone : zone.box_color);
   ObjectSetInteger(0, box_id, OBJPROP_STYLE, is_current_inside ? STYLE_SOLID : (zone.is_mitigated ? STYLE_DASH : STYLE_SOLID));
   ObjectSetInteger(0, box_id, OBJPROP_WIDTH, is_current_inside ? 2 : ((zone.type == ZONE_COMBINED_CONFLUENCE || zone.has_counter_fvg) ? 2 : 1));
   ObjectSetInteger(0, box_id, OBJPROP_BACK, true);
   ObjectSetInteger(0, box_id, OBJPROP_FILL, true);

   // CE 50% line for regular & combined
   if(InpShowCE50 && zone.type != ZONE_INVERSION_FVG)
   {
      string ce_id = OBJ_PREFIX + "CE_" + zone.id;
      ObjectCreate(0, ce_id, OBJ_TREND, 0, zone.start_time, zone.ce_price, end_t, zone.ce_price);
      ObjectSetInteger(0, ce_id, OBJPROP_COLOR, InpColorCE);
      ObjectSetInteger(0, ce_id, OBJPROP_STYLE, STYLE_DOT);
      ObjectSetInteger(0, ce_id, OBJPROP_RAY_RIGHT, false);
   }

   // Label
   string lbl_id = OBJ_PREFIX + "LBL_" + zone.id;
   string full_text = rank_tag + zone.display_label;

   ObjectCreate(0, lbl_id, OBJ_TEXT, 0, end_t, (zone.top + zone.bottom) / 2.0);
   ObjectSetString(0, lbl_id, OBJPROP_TEXT, full_text);
   ObjectSetInteger(0, lbl_id, OBJPROP_COLOR, is_current_inside ? InpColorInsideZone : zone.box_color);
   ObjectSetInteger(0, lbl_id, OBJPROP_FONTSIZE, is_current_inside ? 9 : 8);
   ObjectSetInteger(0, lbl_id, OBJPROP_ANCHOR, ANCHOR_LEFT);
}
