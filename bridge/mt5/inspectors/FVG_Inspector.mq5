//+------------------------------------------------------------------+
//|                                            FVG_Inspector.mq5     |
//|      Institutional FVG, Inversion FVG (iFVG), and Confluence     |
//|                                  LLMTradingV2 Institutional V2   |
//+------------------------------------------------------------------+
#property copyright "LLMTradingV2"
#property link      "https://github.com/arbuuuud/LLMTradingV2"
#property version   "2.00"
#property description "Visualizes Distinct FVGs, Inversion FVGs (iFVG with Counter-FVG Breach Detection), and FVG+iFVG Confluence Zones"

//--- Inputs
input group "=== 1. Regular FVG Settings ==="
input int      InpMaxBars              = 300;               // Max Bars to Analyze
input double   InpMinGapPoints         = 10.0;              // Minimum Gap Size (Points)
input bool     InpShowRegularFVG       = true;              // Draw Regular FVGs
input color    InpColorBullFVG         = C'16,185,129';     // Bullish FVG Box Color (Emerald)
input color    InpColorBearFVG         = C'239,68,68';      // Bearish FVG Box Color (Rose)
input bool     InpShowCE50             = true;              // Show 50% Consequent Encroachment (CE) Line
input color    InpColorCE              = C'250,204,21';     // CE 50% Line Color (Yellow)
input bool     InpShowMitigated        = false;             // Show Fully Filled Gaps

input group "=== 2. Inversion FVG (iFVG) Settings ==="
input bool     InpShowInversionFVG     = true;              // Draw Inversion FVGs (iFVG) as Distinct Objects
input color    InpColorInversionClean  = clrGold;           // Standard iFVG Box Color (Gold)
input color    InpColorInversionPower  = C'249,115,22';     // Powerful iFVG Breached WITH Counter-FVG (Orange)
input bool     InpExtendToCurrent      = true;              // Extend Active Zones to Current Candle

input group "=== 3. FVG + iFVG Confluence Zone (High Probability) ==="
input bool     InpShowConfluenceZones  = true;              // Highlight Overlapping / Same-Swing FVG + iFVG
input color    InpColorConfluence      = C'6,182,212';      // Confluence Zone Highlight (Cyan / Neon)
input int      InpSwingWindow          = 3;                 // Swing Window for Same-Swing Verification

#define OBJ_PREFIX "FVG_INSP_"

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

   // 1. Detect All FVGs Chronologically
   FVGNode all_fvgs[];
   ArrayResize(all_fvgs, 0);

   for(int i = bars_to_check - 3; i >= 1; i--)
   {
      // 3-bar pattern:
      // i+2 is first candle, i+1 is middle displacement, i is third candle
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
            // Touched gap
            if(rates[k].low <= all_fvgs[f].top)
            {
               all_fvgs[f].is_mitigated = true;
            }
            // Closed below gap bottom -> Inverted to Resistance!
            if(rates[k].close < all_fvgs[f].bottom)
            {
               all_fvgs[f].is_inverted = true;
               all_fvgs[f].invert_time = rates[k].time;

               // Check if the breach formed a Counter Bearish FVG around bar k!
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
            // Touched gap
            if(rates[k].high >= all_fvgs[f].bottom)
            {
               all_fvgs[f].is_mitigated = true;
            }
            // Closed above gap top -> Inverted to Support!
            if(rates[k].close > all_fvgs[f].top)
            {
               all_fvgs[f].is_inverted = true;
               all_fvgs[f].invert_time = rates[k].time;

               // Check if the breach formed a Counter Bullish FVG around bar k!
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

   // 3. Render Distinct Objects:
   // Object 1: Regular Active FVGs
   if(InpShowRegularFVG)
   {
      for(int f = 0; f < total_fvg_count; f++)
      {
         if(all_fvgs[f].is_inverted) continue; // Inversions drawn separately
         if(all_fvgs[f].is_mitigated && !InpShowMitigated) continue;

         double gap_pts = (all_fvgs[f].top - all_fvgs[f].bottom) / _Point;
         datetime end_t = InpExtendToCurrent ? current_t : rates[0].time;
         color box_c = all_fvgs[f].is_bullish ? InpColorBullFVG : InpColorBearFVG;

         string box_id = OBJ_PREFIX + "REG_" + all_fvgs[f].id;
         ObjectCreate(0, box_id, OBJ_RECTANGLE, 0, all_fvgs[f].time, all_fvgs[f].top, end_t, all_fvgs[f].bottom);
         ObjectSetInteger(0, box_id, OBJPROP_COLOR, box_c);
         ObjectSetInteger(0, box_id, OBJPROP_STYLE, all_fvgs[f].is_mitigated ? STYLE_DASH : STYLE_SOLID);
         ObjectSetInteger(0, box_id, OBJPROP_BACK, true);
         ObjectSetInteger(0, box_id, OBJPROP_FILL, true);

         // Consequent Encroachment (CE 50%)
         if(InpShowCE50)
         {
            string ce_id = OBJ_PREFIX + "CE_" + all_fvgs[f].id;
            ObjectCreate(0, ce_id, OBJ_TREND, 0, all_fvgs[f].time, all_fvgs[f].ce_price, end_t, all_fvgs[f].ce_price);
            ObjectSetInteger(0, ce_id, OBJPROP_COLOR, InpColorCE);
            ObjectSetInteger(0, ce_id, OBJPROP_STYLE, STYLE_DOT);
            ObjectSetInteger(0, ce_id, OBJPROP_RAY_RIGHT, false);
         }

         // Label
         string lbl_id = OBJ_PREFIX + "LBL_" + all_fvgs[f].id;
         string txt = StringFormat(" %s (%.0f pts) CE: %.2f",
            all_fvgs[f].is_bullish ? "Bull FVG" : "Bear FVG", gap_pts, all_fvgs[f].ce_price);
         if(all_fvgs[f].is_mitigated) txt += " [Mitigated]";

         ObjectCreate(0, lbl_id, OBJ_TEXT, 0, all_fvgs[f].time, all_fvgs[f].top);
         ObjectSetString(0, lbl_id, OBJPROP_TEXT, txt);
         ObjectSetInteger(0, lbl_id, OBJPROP_COLOR, box_c);
         ObjectSetInteger(0, lbl_id, OBJPROP_FONTSIZE, 8);
         ObjectSetInteger(0, lbl_id, OBJPROP_ANCHOR, ANCHOR_LOWER);
      }
   }

   // Object 2: Inversion FVGs (iFVG) - Distinct Object
   if(InpShowInversionFVG)
   {
      for(int f = 0; f < total_fvg_count; f++)
      {
         if(!all_fvgs[f].is_inverted) continue;

         datetime end_t = InpExtendToCurrent ? current_t : rates[0].time;
         color ifvg_c = all_fvgs[f].inverted_with_counter_fvg ? InpColorInversionPower : InpColorInversionClean;

         string ifvg_box_id = OBJ_PREFIX + "IFVG_" + all_fvgs[f].id;
         ObjectCreate(0, ifvg_box_id, OBJ_RECTANGLE, 0, all_fvgs[f].invert_time, all_fvgs[f].top, end_t, all_fvgs[f].bottom);
         ObjectSetInteger(0, ifvg_box_id, OBJPROP_COLOR, ifvg_c);
         ObjectSetInteger(0, ifvg_box_id, OBJPROP_STYLE, STYLE_SOLID);
         ObjectSetInteger(0, ifvg_box_id, OBJPROP_WIDTH, all_fvgs[f].inverted_with_counter_fvg ? 2 : 1);
         ObjectSetInteger(0, ifvg_box_id, OBJPROP_BACK, true);
         ObjectSetInteger(0, ifvg_box_id, OBJPROP_FILL, true);

         // Label for iFVG
         string ifvg_lbl_id = OBJ_PREFIX + "LBL_IFVG_" + all_fvgs[f].id;
         string role_text = all_fvgs[f].is_bullish ? "iFVG Resistance" : "iFVG Support";
         string power_tag = all_fvgs[f].inverted_with_counter_fvg ? " [Breached WITH Counter-FVG!]" : " [Breach Flip]";

         ObjectCreate(0, ifvg_lbl_id, OBJ_TEXT, 0, all_fvgs[f].invert_time, all_fvgs[f].bottom);
         ObjectSetString(0, ifvg_lbl_id, OBJPROP_TEXT, " " + role_text + power_tag);
         ObjectSetInteger(0, ifvg_lbl_id, OBJPROP_COLOR, ifvg_c);
         ObjectSetInteger(0, ifvg_lbl_id, OBJPROP_FONTSIZE, 8);
         ObjectSetInteger(0, ifvg_lbl_id, OBJPROP_ANCHOR, ANCHOR_UPPER);
      }
   }

   // Object 3: FVG + iFVG Confluence Zone (Nested / Overlapping in Same Range)
   if(InpShowConfluenceZones)
   {
      for(int f = 0; f < total_fvg_count; f++)
      {
         if(all_fvgs[f].is_inverted) continue; // Must be an active regular FVG

         for(int k = 0; k < total_fvg_count; k++)
         {
            if(!all_fvgs[k].is_inverted) continue; // Must be an active iFVG

            // Check if price ranges overlap!
            double overlap_top = MathMin(all_fvgs[f].top, all_fvgs[k].top);
            double overlap_btm = MathMax(all_fvgs[f].bottom, all_fvgs[k].bottom);

            if(overlap_top > overlap_btm) // Valid Overlap Range!
            {
               datetime conf_start = MathMax(all_fvgs[f].time, all_fvgs[k].invert_time);
               string conf_id = OBJ_PREFIX + "CONF_" + all_fvgs[f].id + "_" + all_fvgs[k].id;

               // Draw Confluence Highlight Box
               ObjectCreate(0, conf_id, OBJ_RECTANGLE, 0, conf_start, overlap_top, current_t, overlap_btm);
               ObjectSetInteger(0, conf_id, OBJPROP_COLOR, InpColorConfluence);
               ObjectSetInteger(0, conf_id, OBJPROP_STYLE, STYLE_SOLID);
               ObjectSetInteger(0, conf_id, OBJPROP_WIDTH, 2);
               ObjectSetInteger(0, conf_id, OBJPROP_BACK, false); // Front overlay
               ObjectSetInteger(0, conf_id, OBJPROP_FILL, false);

               // Prominent Star Label
               string conf_lbl = OBJ_PREFIX + "TXT_CONF_" + conf_id;
               ObjectCreate(0, conf_lbl, OBJ_TEXT, 0, current_t, (overlap_top + overlap_btm) / 2.0);
               ObjectSetString(0, conf_lbl, OBJPROP_TEXT, " ★ [CONFLUENCE: FVG + iFVG ZONE] ★");
               ObjectSetInteger(0, conf_lbl, OBJPROP_COLOR, InpColorConfluence);
               ObjectSetInteger(0, conf_lbl, OBJPROP_FONTSIZE, 9);
               ObjectSetInteger(0, conf_lbl, OBJPROP_ANCHOR, ANCHOR_LEFT);
            }
         }
      }
   }

   ChartRedraw();
}
