//+------------------------------------------------------------------+
//|                                       OrderBlock_Inspector.mq5   |
//|                 Master OrderBlock & S&D Visual Inspector         |
//|                                  LLMTradingV2 Institutional V2   |
//+------------------------------------------------------------------+
#property copyright "LLMTradingV2"
#property link      "https://github.com/arbuuuud/LLMTradingV2"
#property version   "3.00"
#property description "Master Institutional Inspector: M1 Precomputed POI Databank Integration (Strategy Tester & Live), Reversal OB, Continuation S&D, and Smart Confluence"

//--- Inputs
input group "=== Architecture V2 Data Lake Integration (Solusi A & Databank) ==="
input bool     InpUsePoiDatabank       = true;              // Load from M1 POI Databank (Ultra-Fast & Accurate for Backtest & Live)
input string   InpDatabankFile         = "xauusd_m1_poi_databank.bin"; // Binary POI Databank File Name
input bool     InpUseEngineSnapshot    = true;              // Load from Live Snapshot JSON (Live mode only)
input string   InpSnapshotFile         = "live_snapshot_xauusd.json";  // Live Snapshot File Name

input group "=== Category Display Switches ==="
input bool     InpShowReversalOB       = true;              // Show Reversal OB (+OB DBR / -OB RBD)
input bool     InpShowContinuationSD   = true;              // Show Continuation S&D (+Demand RBR / -Supply DBD)
input bool     InpShowBreakers         = false;             // Show Breaker Blocks (Optional - Default OFF)

input group "=== Proximity & Display Settings ==="
input int      InpMaxZonesAbove        = 2;                 // Max Nearest Zones Above Price (Roofs)
input int      InpMaxZonesBelow        = 2;                 // Max Nearest Zones Below Price (Floors)
input bool     InpShowMeanThreshold    = true;              // Draw 50% Mean Threshold (MT) Line
input int      InpFallbackMaxBars      = 3000;              // Fallback Local MT5 Scan Lookback Bars

input group "=== Distinct Color Palette ==="
input color    InpColorBullOB          = C'30,144,255';     // [REVERSAL] +OB (DBR) - Royal DodgerBlue
input color    InpColorBearOB          = C'220,20,60';      // [REVERSAL] -OB (RBD) - Crimson Red
input color    InpColorContDemand      = C'46,139,87';      // [CONTINUATION] +Demand (RBR) - SeaGreen Teal
input color    InpColorContSupply      = C'218,165,32';     // [CONTINUATION] -Supply (DBD) - Goldenrod Amber
input color    InpColorConfDemand      = C'0,206,209';      // [CONFLUENCE] Demand Cluster - DarkTurquoise
input color    InpColorConfSupply      = C'218,112,214';    // [CONFLUENCE] Supply Cluster - Orchid Magenta
input color    InpColorBreakerBull     = C'0,235,235';      // [BREAKER FLIP] Bullish Support - Bright Cyan
input color    InpColorBreakerBear     = C'255,99,71';      // [BREAKER FLIP] Bearish Resistance - Tomato Orange
input color    InpColorInside          = C'255,255,255';    // [CURRENT INSIDE ZONE] Active Highlight - White

#define OBJ_PREFIX "OB_INSP_"

enum ENUM_ZONE_KIND
{
   ZONE_REVERSAL_DBR,      // Drop-Base-Rally (+OB Reversal)
   ZONE_REVERSAL_RBD,      // Rally-Base-Drop (-OB Reversal)
   ZONE_CONTINUATION_RBR,  // Rally-Base-Rally (+Demand Continuation)
   ZONE_CONTINUATION_DBD,  // Drop-Base-Drop (-Supply Continuation)
   ZONE_BREAKER_BULLISH,   // Breaker Block Support (Flipped from -OB)
   ZONE_BREAKER_BEARISH    // Breaker Block Resistance (Flipped from +OB)
};

struct ZoneItem
{
   string            id;
   ENUM_ZONE_KIND    kind;
   bool              is_bullish;          // Support vs Resistance
   double            top;
   double            bottom;
   double            mean_threshold;      // 50% Level
   datetime          time;
   int               bar_index;
   int               base_count;          // Number of base candles
   double            impulse_ratio;       // Leg-Out / Base Range
   bool              has_swept_liq;
   bool              is_breaker;
   datetime          breaker_time;
   bool              is_touched;
   int               touch_count;
   double            deepest_touch_price;
   bool              is_mitigated;        // Closed inside
   bool              is_fully_used;       // Swept 100%
   bool              is_inside;
   bool              is_confluence;       // Merged from overlapping zones
   string            confluence_desc;     // e.g. "OB(DBR) + SD(RBR)"
   string            source_tag;          // e.g. "[DataBank]", "[Local]", "[DataLake]"
   double            distance;
};

// Compact Databank Memory Record
struct DatabankOB
{
   long     time;
   int      is_bull;
   double   top;
   double   bottom;
   long     break_time;
};

DatabankOB g_databank[];
int        g_databank_total = 0;
bool       g_databank_loaded = false;

datetime g_last_bar_time = 0;
datetime g_last_file_mtime = 0;
string   g_active_object_names[];
int      g_active_object_count = 0;

void RegisterActiveObjectName(const string &name)
{
   ArrayResize(g_active_object_names, g_active_object_count + 1);
   g_active_object_names[g_active_object_count] = name;
   g_active_object_count++;
}

void PurgeOrphanedObjects()
{
   int total = ObjectsTotal(0, 0, -1);
   for(int i = total - 1; i >= 0; i--)
   {
      string name = ObjectName(0, i, 0, -1);
      if(StringFind(name, OBJ_PREFIX) == 0)
      {
         bool is_active = false;
         for(int j = 0; j < g_active_object_count; j++)
         {
            if(g_active_object_names[j] == name) { is_active = true; break; }
         }
         if(!is_active)
         {
            ObjectDelete(0, name);
         }
      }
   }
}

// Anti-Flicker Object Updaters (In-Place Coordinate & Property Updates)
void UpdateOrCreateRect(string name, datetime t1, double p1, datetime t2, double p2, color clr, int style, int width)
{
   if(ObjectFind(0, name) < 0)
   {
      ObjectCreate(0, name, OBJ_RECTANGLE, 0, t1, p1, t2, p2);
   }
   else
   {
      ObjectSetInteger(0, name, OBJPROP_TIME, 0, t1);
      ObjectSetDouble(0, name, OBJPROP_PRICE, 0, p1);
      ObjectSetInteger(0, name, OBJPROP_TIME, 1, t2);
      ObjectSetDouble(0, name, OBJPROP_PRICE, 1, p2);
   }
   ObjectSetInteger(0, name, OBJPROP_COLOR, clr);
   ObjectSetInteger(0, name, OBJPROP_STYLE, style);
   ObjectSetInteger(0, name, OBJPROP_WIDTH, width);
   ObjectSetInteger(0, name, OBJPROP_BACK, true);
   ObjectSetInteger(0, name, OBJPROP_FILL, true);
}

void UpdateOrCreateLine(string name, datetime t1, double p, datetime t2, color clr, int style, int width)
{
   if(ObjectFind(0, name) < 0)
   {
      ObjectCreate(0, name, OBJ_TREND, 0, t1, p, t2, p);
   }
   else
   {
      ObjectSetInteger(0, name, OBJPROP_TIME, 0, t1);
      ObjectSetDouble(0, name, OBJPROP_PRICE, 0, p);
      ObjectSetInteger(0, name, OBJPROP_TIME, 1, t2);
      ObjectSetDouble(0, name, OBJPROP_PRICE, 1, p);
   }
   ObjectSetInteger(0, name, OBJPROP_COLOR, clr);
   ObjectSetInteger(0, name, OBJPROP_STYLE, style);
   ObjectSetInteger(0, name, OBJPROP_WIDTH, width);
   ObjectSetInteger(0, name, OBJPROP_RAY_RIGHT, false);
   ObjectSetInteger(0, name, OBJPROP_BACK, false);
}

void UpdateOrCreateText(string name, datetime t, double p, string text, color clr, int font_size, int anchor)
{
   if(ObjectFind(0, name) < 0)
   {
      ObjectCreate(0, name, OBJ_TEXT, 0, t, p);
   }
   else
   {
      ObjectSetInteger(0, name, OBJPROP_TIME, 0, t);
      ObjectSetDouble(0, name, OBJPROP_PRICE, 0, p);
   }
   ObjectSetString(0, name, OBJPROP_TEXT, text);
   ObjectSetInteger(0, name, OBJPROP_COLOR, clr);
   ObjectSetInteger(0, name, OBJPROP_FONTSIZE, font_size);
   ObjectSetInteger(0, name, OBJPROP_ANCHOR, anchor);
}

//+------------------------------------------------------------------+
//| Load Precomputed M1 POI Databank (Ultra-Fast 2.7 MB Binary)      |
//+------------------------------------------------------------------+
bool LoadPoiDatabankFromDisk()
{
   if(g_databank_loaded && g_databank_total > 0) return true;

   int handle = FileOpen(InpDatabankFile, FILE_READ | FILE_BIN | FILE_COMMON);
   if(handle == INVALID_HANDLE)
   {
      handle = FileOpen(InpDatabankFile, FILE_READ | FILE_BIN);
   }
   if(handle == INVALID_HANDLE)
   {
      Print("[OrderBlock_Inspector] Could not open POI databank: ", InpDatabankFile, ", error: ", GetLastError());
      return false;
   }

   // Read 4-byte header 'POIB'
   char magic[4];
   FileReadArray(handle, magic, 0, 4);
   string magic_str = CharArrayToString(magic, 0, 4);
   if(magic_str != "POIB")
   {
      Print("[OrderBlock_Inspector] Invalid POI databank magic header: ", magic_str);
      FileClose(handle);
      return false;
   }

   uint count = FileReadInteger(handle, INT_VALUE);
   if(count <= 0 || count > 500000)
   {
      Print("[OrderBlock_Inspector] Unexpected record count in databank: ", count);
      FileClose(handle);
      return false;
   }

   ArrayResize(g_databank, count);
   g_databank_total = (int)count;

   for(uint i = 0; i < count; i++)
   {
      g_databank[i].time = FileReadLong(handle);
      g_databank[i].is_bull = FileReadInteger(handle, INT_VALUE);
      g_databank[i].top = FileReadDouble(handle);
      g_databank[i].bottom = FileReadDouble(handle);
      g_databank[i].break_time = FileReadLong(handle);
   }

   FileClose(handle);
   g_databank_loaded = true;
   PrintFormat("[OrderBlock_Inspector] ✅ Successfully loaded %d M1 POI records from Databank!", g_databank_total);
   return true;
}

//+------------------------------------------------------------------+
//| Expert initialization function                                   |
//+------------------------------------------------------------------+
int OnInit()
{
   CleanObjects();
   if(InpUsePoiDatabank)
   {
      LoadPoiDatabankFromDisk();
   }
   RedrawZones();
   EventSetTimer(1); // 1-second check (zero flicker)
   return(INIT_SUCCEEDED);
}

//+------------------------------------------------------------------+
//| Expert deinitialization function                                 |
//+------------------------------------------------------------------+
void OnDeinit(const int reason)
{
   EventKillTimer();
   CleanObjects();
   ChartRedraw();
}

void CleanObjects()
{
   ObjectsDeleteAll(0, OBJ_PREFIX);
   g_active_object_count = 0;
   ArrayResize(g_active_object_names, 0);
}

void OnTimer()
{
   if(MQLInfoInteger(MQL_TESTER)) return; // Strategy Tester runs on OnTick
   if(!InpUseEngineSnapshot) return;

   datetime file_mtime = (datetime)FileGetInteger(InpSnapshotFile, FILE_MODIFY_DATE, false);
   if(file_mtime == 0)
      file_mtime = (datetime)FileGetInteger(InpSnapshotFile, FILE_MODIFY_DATE, true);

   if(file_mtime != 0 && file_mtime == g_last_file_mtime)
   {
      return; // Snapshot hasn't changed, zero redraw
   }

   g_last_file_mtime = file_mtime;
   RedrawZones();
}

void OnTick()
{
   datetime current_time = iTime(_Symbol, _Period, 0);
   if(current_time != g_last_bar_time)
   {
      g_last_bar_time = current_time;
      RedrawZones();
   }
}

//+------------------------------------------------------------------+
//| Query Active Unbroken Zones from Databank at current bar time    |
//+------------------------------------------------------------------+
void QueryZonesFromDatabank(datetime current_time, double current_price, ZoneItem &out_zones[], int &out_count)
{
   long cur_epoch = (long)current_time;
   out_count = 0;
   ArrayResize(out_zones, 0);

   // Binary search / search backwards from the newest eligible zone <= cur_epoch
   int right = g_databank_total - 1;
   while(right >= 0 && g_databank[right].time > cur_epoch)
   {
      right--;
   }

   int floors_found = 0;
   int roofs_found = 0;

   // Scan backwards from current time
   for(int i = right; i >= 0; i--)
   {
      // Check if zone was broken before current time
      if(g_databank[i].break_time > 0 && g_databank[i].break_time <= cur_epoch)
      {
         continue; // Zone was broken in the past, inactive
      }

      bool is_bull = (g_databank[i].is_bull == 1);
      double top = g_databank[i].top;
      double btm = g_databank[i].bottom;

      // Filter by category switches
      if(is_bull && !InpShowReversalOB && !InpShowContinuationSD) continue;
      if(!is_bull && !InpShowReversalOB && !InpShowContinuationSD) continue;

      ZoneItem z;
      z.id = "DB_" + IntegerToString((long)g_databank[i].time);
      z.is_bullish = is_bull;
      z.kind = is_bull ? ZONE_REVERSAL_DBR : ZONE_REVERSAL_RBD;
      z.top = top;
      z.bottom = btm;
      z.mean_threshold = (top + btm) / 2.0;
      z.time = (datetime)g_databank[i].time;
      z.bar_index = 0;
      z.base_count = 1;
      z.impulse_ratio = 2.0;
      z.has_swept_liq = false;
      z.is_breaker = false;
      z.breaker_time = 0;
      z.is_touched = false;
      z.touch_count = 0;
      z.deepest_touch_price = 0.0;
      z.is_mitigated = false;
      z.is_fully_used = false;
      z.is_inside = false;
      z.is_confluence = false;
      z.confluence_desc = "";
      z.source_tag = "[DataBank]";
      z.distance = 0.0;

      // Check if candidate is floor (below price) or roof (above price)
      if(is_bull && top < current_price)
      {
         ArrayResize(out_zones, out_count + 1);
         out_zones[out_count] = z;
         out_count++;
         floors_found++;
      }
      else if(!is_bull && btm > current_price)
      {
         ArrayResize(out_zones, out_count + 1);
         out_zones[out_count] = z;
         out_count++;
         roofs_found++;
      }

      // Collect enough deep candidates for sorting (max 50 floors and 50 roofs)
      if(floors_found >= 50 && roofs_found >= 50) break;
   }
}

//+------------------------------------------------------------------+
//| Core Detection Engine                                            |
//+------------------------------------------------------------------+
void RedrawZones()
{
   datetime current_candle_time = iTime(_Symbol, _Period, 0);
   double current_price = SymbolInfoDouble(_Symbol, SYMBOL_BID);
   if(current_price <= 0.0) current_price = iClose(_Symbol, _Period, 0);

   ZoneItem candidates[];
   int cand_count = 0;

   // 1. CARA 1: Query directly from Precomputed M1 POI Databank (Ultra-Fast & Guaranteed Floor)
   if(InpUsePoiDatabank && g_databank_loaded && g_databank_total > 0)
   {
      QueryZonesFromDatabank(current_candle_time, current_price, candidates, cand_count);
      if(cand_count > 0)
      {
         // Perform Smart Confluence Clustering on databank zones
         ClusterAndRenderZones(candidates, cand_count, current_price, current_candle_time, "[DataBank]");
         ChartRedraw();
         return;
      }
   }

   // 2. FALLBACK: Local Chart Scanning Mode
   int total_bars = iBars(_Symbol, _Period);
   int bars_to_check = MathMin(InpFallbackMaxBars, total_bars - 5);
   if(bars_to_check < 6) return;

   MqlRates rates[];
   ArraySetAsSeries(rates, true);
   int copied = CopyRates(_Symbol, _Period, 0, bars_to_check, rates);
   if(copied < 6) return;
   bars_to_check = copied;

   current_candle_time = rates[0].time;
   current_price = rates[0].close;

   for(int i = bars_to_check - 5; i >= 1; i--)
   {
      bool is_bull_fvg = (rates[i].low > rates[i + 2].high);
      bool is_bear_fvg = (rates[i].high < rates[i + 2].low);
      if(!is_bull_fvg && !is_bear_fvg) continue;

      int origin_idx = i + 2;
      double top = rates[origin_idx].high;
      double btm = rates[origin_idx].low;

      bool fully_used = false;
      for(int k = origin_idx - 1; k >= 0; k--)
      {
         if(is_bull_fvg && rates[k].close < btm) { fully_used = true; break; }
         else if(!is_bull_fvg && rates[k].close > top) { fully_used = true; break; }
      }
      if(fully_used) continue;

      ZoneItem z;
      z.id = "LOC_" + IntegerToString(origin_idx);
      z.is_bullish = is_bull_fvg;
      z.kind = is_bull_fvg ? ZONE_REVERSAL_DBR : ZONE_REVERSAL_RBD;
      z.top = top;
      z.bottom = btm;
      z.mean_threshold = (top + btm) / 2.0;
      z.time = rates[origin_idx].time;
      z.bar_index = origin_idx;
      z.base_count = 1;
      z.impulse_ratio = 1.5;
      z.has_swept_liq = false;
      z.is_breaker = false;
      z.breaker_time = 0;
      z.is_touched = false;
      z.touch_count = 0;
      z.deepest_touch_price = 0.0;
      z.is_mitigated = false;
      z.is_fully_used = false;
      z.is_inside = false;
      z.is_confluence = false;
      z.confluence_desc = "";
      z.source_tag = "[Local]";
      z.distance = 0.0;

      ArrayResize(candidates, cand_count + 1);
      candidates[cand_count] = z;
      cand_count++;
   }

   ClusterAndRenderZones(candidates, cand_count, current_price, current_candle_time, "[Local]");
   ChartRedraw();
}

//+------------------------------------------------------------------+
//| Smart Confluence Clustering & Rendering Helper                   |
//+------------------------------------------------------------------+
void ClusterAndRenderZones(ZoneItem &candidates[], int cand_count, double current_price, datetime current_candle_time, string source_tag)
{
   bool merged_any = true;
   while(merged_any && cand_count > 1)
   {
      merged_any = false;
      for(int a = 0; a < cand_count - 1; a++)
      {
         for(int b = a + 1; b < cand_count; b++)
         {
            if(candidates[a].is_bullish != candidates[b].is_bullish) continue;

            double overlap_top = MathMin(candidates[a].top, candidates[b].top);
            double overlap_btm = MathMax(candidates[a].bottom, candidates[b].bottom);

            if(overlap_top > overlap_btm)
            {
               candidates[a].top = MathMax(candidates[a].top, candidates[b].top);
               candidates[a].bottom = MathMin(candidates[a].bottom, candidates[b].bottom);
               candidates[a].mean_threshold = (candidates[a].top + candidates[a].bottom) / 2.0;
               candidates[a].time = MathMin(candidates[a].time, candidates[b].time);
               candidates[a].is_confluence = true;
               candidates[a].confluence_desc = "Cluster";

               for(int r = b; r < cand_count - 1; r++)
               {
                  candidates[r] = candidates[r + 1];
               }
               cand_count--;
               ArrayResize(candidates, cand_count);

               merged_any = true;
               break;
            }
         }
         if(merged_any) break;
      }
   }

   int above_indices[];
   double above_dists[];
   int above_count = 0;

   int below_indices[];
   double below_dists[];
   int below_count = 0;

   int inside_idx = -1;

   for(int m = 0; m < cand_count; m++)
   {
      bool is_inside = (current_price >= candidates[m].bottom && current_price <= candidates[m].top);
      candidates[m].is_inside = is_inside;

      if(is_inside)
      {
         inside_idx = m;
         continue;
      }

      if(candidates[m].bottom > current_price)
      {
         double d = candidates[m].bottom - current_price;
         ArrayResize(above_indices, above_count + 1);
         ArrayResize(above_dists, above_count + 1);
         above_indices[above_count] = m;
         above_dists[above_count] = d;
         above_count++;
      }
      else if(candidates[m].top < current_price)
      {
         double d = current_price - candidates[m].top;
         ArrayResize(below_indices, below_count + 1);
         ArrayResize(below_dists, below_count + 1);
         below_indices[below_count] = m;
         below_dists[below_count] = d;
         below_count++;
      }
   }

   for(int a = 0; a < above_count - 1; a++)
   {
      for(int b = a + 1; b < above_count; b++)
      {
         if(above_dists[b] < above_dists[a])
         {
            double td = above_dists[a]; above_dists[a] = above_dists[b]; above_dists[b] = td;
            int ti = above_indices[a]; above_indices[a] = above_indices[b]; above_indices[b] = ti;
         }
      }
   }

   for(int a = 0; a < below_count - 1; a++)
   {
      for(int b = a + 1; b < below_count; b++)
      {
         if(below_dists[b] < below_dists[a])
         {
            double td = below_dists[a]; below_dists[a] = below_dists[b]; below_dists[b] = td;
            int ti = below_indices[a]; below_indices[a] = below_indices[b]; below_indices[b] = ti;
         }
      }
   }

   g_active_object_count = 0;
   ArrayResize(g_active_object_names, 0);

   if(inside_idx >= 0)
   {
      DrawZone(candidates[inside_idx], current_candle_time, "⚡ [CURRENT INSIDE ZONE]");
   }

   int render_above = MathMin(InpMaxZonesAbove, above_count);
   for(int a = 0; a < render_above; a++)
   {
      string tag = candidates[above_indices[a]].source_tag;
      if(tag == "") tag = source_tag;
      DrawZone(candidates[above_indices[a]], current_candle_time, tag + " [Above #" + IntegerToString(a + 1) + "]");
   }

   int render_below = MathMin(InpMaxZonesBelow, below_count);
   for(int b = 0; b < render_below; b++)
   {
      string tag = candidates[below_indices[b]].source_tag;
      if(tag == "") tag = source_tag;
      DrawZone(candidates[below_indices[b]], current_candle_time, tag + " [Below #" + IntegerToString(b + 1) + "]");
   }

   PurgeOrphanedObjects();
}

//+------------------------------------------------------------------+
//| Graphic Renderer Helper                                          |
//+------------------------------------------------------------------+
void DrawZone(const ZoneItem &zone, datetime current_time, string prefix_tag)
{
   string id_str = IntegerToString(zone.time) + "_" + DoubleToString(zone.bottom, 2);
   string rect_name = OBJ_PREFIX + "BOX_" + id_str;
   string mt_line_name = OBJ_PREFIX + "MT_" + id_str;
   string text_name = OBJ_PREFIX + "LBL_" + id_str;

   color zone_color;
   string badge = "";

   if(zone.is_confluence)
   {
      zone_color = zone.is_bullish ? InpColorConfDemand : InpColorConfSupply;
      badge = "★ [CONFLUENCE CLUSTER]";
   }
   else
   {
      switch(zone.kind)
      {
         case ZONE_REVERSAL_DBR:
            zone_color = InpColorBullOB;
            badge = "[REVERSAL OB] +OB (DBR)";
            break;
         case ZONE_REVERSAL_RBD:
            zone_color = InpColorBearOB;
            badge = "[REVERSAL OB] -OB (RBD)";
            break;
         case ZONE_CONTINUATION_RBR:
            zone_color = InpColorContDemand;
            badge = "[CONTINUATION] +Demand (RBR)";
            break;
         case ZONE_CONTINUATION_DBD:
            zone_color = InpColorContSupply;
            badge = "[CONTINUATION] -Supply (DBD)";
            break;
         case ZONE_BREAKER_BULLISH:
            zone_color = InpColorBreakerBull;
            badge = "⚡ [BREAKER FLIP] Support";
            break;
         case ZONE_BREAKER_BEARISH:
            zone_color = InpColorBreakerBear;
            badge = "⚡ [BREAKER FLIP] Resistance";
            break;
         default:
            zone_color = InpColorBullOB;
            badge = "[ZONE]";
            break;
      }
   }

   datetime start_time = zone.time;
   if(start_time == 0) start_time = current_time - 3600 * 4;

   RegisterActiveObjectName(rect_name);
   int rect_style = zone.is_inside ? STYLE_SOLID : (zone.is_mitigated ? STYLE_DASH : STYLE_SOLID);
   int rect_width = zone.is_inside ? 2 : 1;
   color rect_color = zone.is_inside ? InpColorInside : zone_color;
   UpdateOrCreateRect(rect_name, start_time, zone.top, current_time, zone.bottom, rect_color, rect_style, rect_width);

   if(InpShowMeanThreshold)
   {
      RegisterActiveObjectName(mt_line_name);
      UpdateOrCreateLine(mt_line_name, start_time, zone.mean_threshold, current_time, zone_color, STYLE_DOT, 1);
   }

   string label = prefix_tag + " " + badge;
   label += " MT:" + DoubleToString(zone.mean_threshold, _Digits);

   RegisterActiveObjectName(text_name);
   color text_color = zone.is_inside ? InpColorInside : zone_color;
   UpdateOrCreateText(text_name, current_time, zone.mean_threshold, label, text_color, 8, ANCHOR_RIGHT_LOWER);
}
//+------------------------------------------------------------------+
