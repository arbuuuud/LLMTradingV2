//+------------------------------------------------------------------+
//|                                       OrderBlock_Inspector.mq5   |
//|                 Master OrderBlock & S&D Visual Inspector         |
//|                                  LLMTradingV2 Institutional V2   |
//+------------------------------------------------------------------+
#property copyright "LLMTradingV2"
#property link      "https://github.com/arbuuuud/LLMTradingV2"
#property version   "2.20"
#property description "Master Institutional Inspector: Reversal OB (DBR/RBD), Continuation S&D (RBR/DBD), Smart Confluence Clustering, and Two-Tier Data Lake Integration"

//--- Inputs
input group "=== Architecture V2 Data Lake Integration (Solusi A) ==="
input bool     InpUseEngineSnapshot    = true;              // Solusi A: Load from Python Two-Tier Data Lake Snapshot
input string   InpSnapshotFile         = "live_snapshot_xauusd.json"; // Shared Snapshot File Name

input group "=== Category Display Switches ==="
input bool     InpShowReversalOB       = true;              // Show Reversal OB (+OB DBR / -OB RBD)
input bool     InpShowContinuationSD   = true;              // Show Continuation S&D (+Demand RBR / -Supply DBD)
input bool     InpShowBreakers         = false;             // Show Breaker Blocks (Optional - Default OFF)

input group "=== Continuation S&D Quality Filters (Local MT5 Mode) ==="
input int      InpMaxBaseCandles       = 3;                 // Max Base Candles (Strict: 1 to 3)
input double   InpMinImpulseRatio      = 1.5;               // Min Impulse Ratio (Leg-Out / Base Range >= 1.5x)

input group "=== Proximity & Display Settings ==="
input int      InpMaxBars              = 1000;              // Max Bars to Analyze (Fallback Local Mode)
input int      InpMaxZonesAbove        = 2;                 // Max Nearest Zones Above Price (Roofs)
input int      InpMaxZonesBelow        = 2;                 // Max Nearest Zones Below Price (Floors)
input bool     InpShowMeanThreshold    = true;              // Draw 50% Mean Threshold (MT) Line

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
   double            distance;
};

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
//| Expert initialization function                                   |
//+------------------------------------------------------------------+
int OnInit()
{
   CleanObjects();
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
   if(!InpUseEngineSnapshot) return;

   datetime file_mtime = (datetime)FileGetInteger(InpSnapshotFile, FILE_MODIFY_DATE, false);
   if(file_mtime == 0)
      file_mtime = (datetime)FileGetInteger(InpSnapshotFile, FILE_MODIFY_DATE, true);

   // Only redraw if the snapshot file timestamp has actually updated!
   if(file_mtime != 0 && file_mtime == g_last_file_mtime)
   {
      return; // Snapshot hasn't changed, DO NOTHING! Zero flicker!
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
//| JSON Value Extraction Helpers                                    |
//+------------------------------------------------------------------+
double ExtractJsonDouble(const string &json_chunk, const string &key)
{
   int pos = StringFind(json_chunk, key);
   if(pos < 0) return 0.0;
   pos += StringLen(key);
   while(pos < StringLen(json_chunk))
   {
      ushort ch = StringGetCharacter(json_chunk, pos);
      if(ch == ' ' || ch == ':' || ch == '\t') pos++;
      else break;
   }
   int end_pos = pos;
   while(end_pos < StringLen(json_chunk))
   {
      ushort ch = StringGetCharacter(json_chunk, end_pos);
      if((ch >= '0' && ch <= '9') || ch == '.' || ch == '-') end_pos++;
      else break;
   }
   if(end_pos > pos)
   {
      return StringToDouble(StringSubstr(json_chunk, pos, end_pos - pos));
   }
   return 0.0;
}

string ExtractJsonString(const string &json_chunk, const string &key)
{
   int pos = StringFind(json_chunk, key);
   if(pos < 0) return "";
   int q1 = StringFind(json_chunk, "\"", pos + StringLen(key));
   if(q1 < 0) return "";
   int q2 = StringFind(json_chunk, "\"", q1 + 1);
   if(q2 < 0) return "";
   return StringSubstr(json_chunk, q1 + 1, q2 - q1 - 1);
}

//+------------------------------------------------------------------+
//| Solusi A: Load Snapshot from Two-Tier Data Lake Cache            |
//+------------------------------------------------------------------+
bool LoadSnapshotFromDisk(ZoneItem &zones[], int &zone_count)
{
   string filename = InpSnapshotFile;
   int handle = FileOpen(filename, FILE_READ | FILE_TXT | FILE_SHARE_READ);
   if(handle == INVALID_HANDLE)
   {
      handle = FileOpen(filename, FILE_READ | FILE_TXT | FILE_SHARE_READ | FILE_COMMON);
   }
   if(handle == INVALID_HANDLE) return false;

   string json = "";
   while(!FileIsEnding(handle))
   {
      json += FileReadString(handle);
   }
   FileClose(handle);

   if(StringLen(json) < 20) return false;

   int obs_start = StringFind(json, "\"active_obs\":");
   if(obs_start < 0) return false;

   int array_start = StringFind(json, "[", obs_start);
   if(array_start < 0) return false;

   int current_pos = array_start + 1;
   zone_count = 0;
   ArrayResize(zones, 0);

   while(true)
   {
      int obj_open = StringFind(json, "{", current_pos);
      if(obj_open < 0) break;
      int obj_close = StringFind(json, "}", obj_open);
      if(obj_close < 0) break;

      string obj_str = StringSubstr(json, obj_open, obj_close - obj_open + 1);
      current_pos = obj_close + 1;

      ZoneItem z;
      z.id = ExtractJsonString(obj_str, "\"id\":");
      z.is_breaker = false;
      z.is_fully_used = false;
      z.distance = 0.0;
      z.bar_index = 0;
      z.time = TimeCurrent();
      z.base_count = 1;
      z.impulse_ratio = 1.5;

      z.is_bullish = (StringFind(obj_str, "\"direction\": \"BUY\"") >= 0 || StringFind(obj_str, "\"direction\":\"BUY\"") >= 0);

      z.top = ExtractJsonDouble(obj_str, "\"top\":");
      z.bottom = ExtractJsonDouble(obj_str, "\"bottom\":");
      z.mean_threshold = ExtractJsonDouble(obj_str, "\"mean_threshold\":");
      if(z.mean_threshold == 0.0 && z.top > z.bottom) z.mean_threshold = (z.top + z.bottom) / 2.0;

      z.is_confluence = (StringFind(obj_str, "\"is_confluence\": true") >= 0 || StringFind(obj_str, "\"is_confluence\":true") >= 0);
      z.confluence_desc = ExtractJsonString(obj_str, "\"confluence_desc\":");

      string ob_type_str = ExtractJsonString(obj_str, "\"ob_type\":");
      if(ob_type_str == "REVERSAL_DBR") z.kind = ZONE_REVERSAL_DBR;
      else if(ob_type_str == "REVERSAL_RBD") z.kind = ZONE_REVERSAL_RBD;
      else if(ob_type_str == "CONTINUATION_RBR") z.kind = ZONE_CONTINUATION_RBR;
      else if(ob_type_str == "CONTINUATION_DBD") z.kind = ZONE_CONTINUATION_DBD;
      else z.kind = z.is_bullish ? ZONE_REVERSAL_DBR : ZONE_REVERSAL_RBD;

      z.touch_count = (int)ExtractJsonDouble(obj_str, "\"touch_count\":");
      z.deepest_touch_price = ExtractJsonDouble(obj_str, "\"deepest_touch_price\":");
      z.is_mitigated = (StringFind(obj_str, "\"is_mitigated\": true") >= 0 || StringFind(obj_str, "\"is_mitigated\":true") >= 0);
      z.has_swept_liq = (StringFind(obj_str, "\"has_swept_liquidity\": true") >= 0 || StringFind(obj_str, "\"has_swept_liquidity\":true") >= 0);

      if(z.top > z.bottom)
      {
         ArrayResize(zones, zone_count + 1);
         zones[zone_count] = z;
         zone_count++;
      }

      int next_bracket = StringFind(json, "]", obj_close);
      int next_brace = StringFind(json, "{", current_pos);
      if(next_bracket >= 0 && (next_brace < 0 || next_bracket < next_brace))
      {
         break;
      }
   }

   return (zone_count > 0);
}

//+------------------------------------------------------------------+
//| Core Detection Engine                                            |
//+------------------------------------------------------------------+
void RedrawZones()
{
   datetime current_candle_time = iTime(_Symbol, _Period, 0);
   double current_price = SymbolInfoDouble(_Symbol, SYMBOL_BID);
   if(current_price <= 0.0) current_price = iClose(_Symbol, _Period, 0);

   // SOLUSI A: Cek apakah snapshot dari Python Two-Tier Data Lake tersedia
   if(InpUseEngineSnapshot)
   {
      ZoneItem snapshot_zones[];
      int snap_count = 0;
      if(LoadSnapshotFromDisk(snapshot_zones, snap_count))
      {
         ProcessAndRenderCandidates(snapshot_zones, snap_count, current_price, current_candle_time, "[DataLake]");
         ChartRedraw();
         return;
      }
   }

   // FALLBACK: Local MT5 Chart Scanning Mode
   int total_bars = iBars(_Symbol, _Period);
   int bars_to_check = MathMin(InpMaxBars, total_bars - 5);
   if(bars_to_check < 6) return;

   MqlRates rates[];
   ArraySetAsSeries(rates, true);
   if(CopyRates(_Symbol, _Period, 0, bars_to_check, rates) < bars_to_check) return;

   current_candle_time = rates[0].time;
   current_price = rates[0].close;

   ZoneItem raw_zones[];
   int raw_count = 0;

   // 1. Scan for displacement FVG (Leg-Out)
   for(int i = bars_to_check - 5; i >= 1; i--)
   {
      bool is_bull_fvg = (rates[i].low > rates[i + 2].high);
      bool is_bear_fvg = (rates[i].high < rates[i + 2].low);

      if(!is_bull_fvg && !is_bear_fvg) continue;

      int origin_idx = i + 2;
      if(is_bull_fvg)
      {
         if(rates[origin_idx].close > rates[origin_idx].open)
         {
            if(rates[origin_idx - 1].close < rates[origin_idx - 1].open) origin_idx = origin_idx - 1;
            else if(origin_idx + 1 < bars_to_check && rates[origin_idx + 1].close < rates[origin_idx + 1].open) origin_idx = origin_idx + 1;
         }
      }
      else if(is_bear_fvg)
      {
         if(rates[origin_idx].close < rates[origin_idx].open)
         {
            if(rates[origin_idx - 1].close > rates[origin_idx - 1].open) origin_idx = origin_idx - 1;
            else if(origin_idx + 1 < bars_to_check && rates[origin_idx + 1].close > rates[origin_idx + 1].open) origin_idx = origin_idx + 1;
         }
      }

      if(origin_idx >= bars_to_check - 2 || origin_idx < 1) continue;

      bool dup = false;
      for(int d = 0; d < raw_count; d++)
      {
         if(raw_zones[d].bar_index == origin_idx) { dup = true; break; }
      }
      if(dup) continue;

      int base_count = 1;
      double base_high = rates[origin_idx].high;
      double base_low  = rates[origin_idx].low;

      for(int b = 1; b < InpMaxBaseCandles; b++)
      {
         int check_b = origin_idx + b;
         if(check_b >= bars_to_check - 1) break;

         double b_range = rates[check_b].high - rates[check_b].low;
         double b_body  = MathAbs(rates[check_b].close - rates[check_b].open);
         if(b_range > 0 && (b_body / b_range <= 0.50))
         {
            base_count++;
            base_high = MathMax(base_high, rates[check_b].high);
            base_low  = MathMin(base_low, rates[check_b].low);
         }
         else break;
      }

      int leg_out_idx = i + 1;
      double leg_out_range = rates[leg_out_idx].high - rates[leg_out_idx].low;
      double base_range = MathMax(base_high - base_low, _Point * 10);
      double imp_ratio = leg_out_range / base_range;

      int prior_idx = origin_idx + base_count;
      if(prior_idx >= bars_to_check) continue;

      bool is_prior_down = (rates[prior_idx].close < rates[prior_idx].open);
      bool is_prior_up   = (rates[prior_idx].close > rates[prior_idx].open);

      ZoneItem zone;
      zone.bar_index = origin_idx;
      zone.time = rates[origin_idx].time;
      zone.top = base_high;
      zone.bottom = base_low;
      zone.mean_threshold = (zone.top + zone.bottom) / 2.0;
      zone.base_count = base_count;
      zone.impulse_ratio = NormalizeDouble(imp_ratio, 1);
      zone.is_touched = false;
      zone.touch_count = 0;
      zone.deepest_touch_price = 0.0;
      zone.is_mitigated = false;
      zone.is_fully_used = false;
      zone.is_breaker = false;
      zone.breaker_time = 0;
      zone.is_inside = false;
      zone.distance = 0.0;

      if(is_bull_fvg)
      {
         zone.is_bullish = true;
         zone.has_swept_liq = (rates[origin_idx].low < rates[prior_idx].low);

         if(is_prior_down)
         {
            zone.kind = ZONE_REVERSAL_DBR;
            zone.id = "OB_DBR_" + IntegerToString(origin_idx);
         }
         else
         {
            if(base_count > InpMaxBaseCandles || imp_ratio < InpMinImpulseRatio) continue;
            zone.kind = ZONE_CONTINUATION_RBR;
            zone.id = "SD_RBR_" + IntegerToString(origin_idx);
         }
      }
      else
      {
         zone.is_bullish = false;
         zone.has_swept_liq = (rates[origin_idx].high > rates[prior_idx].high);

         if(is_prior_up)
         {
            zone.kind = ZONE_REVERSAL_RBD;
            zone.id = "OB_RBD_" + IntegerToString(origin_idx);
         }
         else
         {
            if(base_count > InpMaxBaseCandles || imp_ratio < InpMinImpulseRatio) continue;
            zone.kind = ZONE_CONTINUATION_DBD;
            zone.id = "SD_DBD_" + IntegerToString(origin_idx);
         }
      }

      for(int k = origin_idx - 1; k >= 0; k--)
      {
         bool is_closed_bar = (k >= 1);

         if(zone.is_bullish && !zone.is_breaker)
         {
            if(rates[k].low <= zone.top && rates[k].high >= zone.bottom)
            {
               zone.is_touched = true;
               if(zone.touch_count == 0) { zone.touch_count = 1; zone.deepest_touch_price = rates[k].low; }
               else if(rates[k].low < zone.deepest_touch_price) { zone.touch_count++; zone.deepest_touch_price = rates[k].low; }
            }
            if(is_closed_bar && rates[k].close <= zone.top && rates[k].close >= zone.bottom)
            {
               zone.is_mitigated = true;
            }
            if(is_closed_bar && rates[k].close < zone.bottom)
            {
               if(InpShowBreakers)
               {
                  zone.is_breaker = true;
                  zone.is_bullish = false;
                  zone.kind = ZONE_BREAKER_BEARISH;
                  zone.breaker_time = rates[k].time;
                  zone.is_mitigated = false;
                  zone.is_fully_used = false;
                  zone.touch_count = 0;
                  zone.deepest_touch_price = 0.0;
               }
               else
               {
                  zone.is_fully_used = true;
               }
            }
         }
         else if(!zone.is_bullish && !zone.is_breaker)
         {
            if(rates[k].high >= zone.bottom && rates[k].low <= zone.top)
            {
               zone.is_touched = true;
               if(zone.touch_count == 0) { zone.touch_count = 1; zone.deepest_touch_price = rates[k].high; }
               else if(rates[k].high > zone.deepest_touch_price) { zone.touch_count++; zone.deepest_touch_price = rates[k].high; }
            }
            if(is_closed_bar && rates[k].close >= zone.bottom && rates[k].close <= zone.top)
            {
               zone.is_mitigated = true;
            }
            if(is_closed_bar && rates[k].close > zone.top)
            {
               if(InpShowBreakers)
               {
                  zone.is_breaker = true;
                  zone.is_bullish = true;
                  zone.kind = ZONE_BREAKER_BULLISH;
                  zone.breaker_time = rates[k].time;
                  zone.is_mitigated = false;
                  zone.is_fully_used = false;
                  zone.touch_count = 0;
                  zone.deepest_touch_price = 0.0;
               }
               else
               {
                  zone.is_fully_used = true;
               }
            }
         }
         else if(zone.is_breaker)
         {
            if(zone.is_bullish)
            {
               if(rates[k].low <= zone.top && rates[k].high >= zone.bottom)
               {
                  zone.is_touched = true;
                  if(zone.touch_count == 0) { zone.touch_count = 1; zone.deepest_touch_price = rates[k].low; }
                  else if(rates[k].low < zone.deepest_touch_price) { zone.touch_count++; zone.deepest_touch_price = rates[k].low; }
               }
               if(is_closed_bar && rates[k].close < zone.bottom) zone.is_fully_used = true;
            }
            else
            {
               if(rates[k].high >= zone.bottom && rates[k].low <= zone.top)
               {
                  zone.is_touched = true;
                  if(zone.touch_count == 0) { zone.touch_count = 1; zone.deepest_touch_price = rates[k].high; }
                  else if(rates[k].high > zone.deepest_touch_price) { zone.touch_count++; zone.deepest_touch_price = rates[k].high; }
               }
               if(is_closed_bar && rates[k].close > zone.top) zone.is_fully_used = true;
            }
         }
      }

      ArrayResize(raw_zones, raw_count + 1);
      zone.is_confluence = false;
      zone.confluence_desc = "";
      raw_zones[raw_count] = zone;
      raw_count++;
   }

   ZoneItem candidates[];
   int cand_count = 0;

   for(int m = 0; m < raw_count; m++)
   {
      if(raw_zones[m].is_fully_used) continue;

      if(raw_zones[m].is_breaker)
      {
         if(!InpShowBreakers) continue;
      }
      else if(raw_zones[m].kind == ZONE_REVERSAL_DBR || raw_zones[m].kind == ZONE_REVERSAL_RBD)
      {
         if(!InpShowReversalOB) continue;
      }
      else if(raw_zones[m].kind == ZONE_CONTINUATION_RBR || raw_zones[m].kind == ZONE_CONTINUATION_DBD)
      {
         if(!InpShowContinuationSD) continue;
      }

      ArrayResize(candidates, cand_count + 1);
      candidates[cand_count] = raw_zones[m];
      cand_count++;
   }

   // SMART CONFLUENCE CLUSTER MERGING
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

               string descA = candidates[a].confluence_desc;
               if(descA == "")
               {
                  if(candidates[a].kind == ZONE_REVERSAL_DBR) descA = "OB(DBR)";
                  else if(candidates[a].kind == ZONE_REVERSAL_RBD) descA = "OB(RBD)";
                  else if(candidates[a].kind == ZONE_CONTINUATION_RBR) descA = "SD(RBR)";
                  else if(candidates[a].kind == ZONE_CONTINUATION_DBD) descA = "SD(DBD)";
                  else descA = "Zone";
               }

               string descB = "";
               if(candidates[b].kind == ZONE_REVERSAL_DBR) descB = "OB(DBR)";
               else if(candidates[b].kind == ZONE_REVERSAL_RBD) descB = "OB(RBD)";
               else if(candidates[b].kind == ZONE_CONTINUATION_RBR) descB = "SD(RBR)";
               else if(candidates[b].kind == ZONE_CONTINUATION_DBD) descB = "SD(DBD)";
               else descB = "Zone";

               if(StringFind(descA, descB) < 0)
                  candidates[a].confluence_desc = descA + " + " + descB;
               else
                  candidates[a].confluence_desc = descA;

               candidates[a].has_swept_liq = candidates[a].has_swept_liq || candidates[b].has_swept_liq;
               candidates[a].is_touched = candidates[a].is_touched || candidates[b].is_touched;
               candidates[a].touch_count = MathMax(candidates[a].touch_count, candidates[b].touch_count);
               if(candidates[a].is_bullish)
               {
                  double dtA = candidates[a].deepest_touch_price > 0 ? candidates[a].deepest_touch_price : candidates[a].top;
                  double dtB = candidates[b].deepest_touch_price > 0 ? candidates[b].deepest_touch_price : candidates[b].top;
                  candidates[a].deepest_touch_price = MathMin(dtA, dtB);
               }
               else
               {
                  candidates[a].deepest_touch_price = MathMax(candidates[a].deepest_touch_price, candidates[b].deepest_touch_price);
               }
               candidates[a].is_mitigated = candidates[a].is_mitigated || candidates[b].is_mitigated;

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

   ProcessAndRenderCandidates(candidates, cand_count, current_price, current_candle_time, "[Local]");
   ChartRedraw();
}

//+------------------------------------------------------------------+
//| Proximity Sorter & Zone Drawer                                   |
//+------------------------------------------------------------------+
void ProcessAndRenderCandidates(ZoneItem &candidates[], int cand_count, double current_price, datetime current_candle_time, string source_tag)
{
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
      DrawZone(candidates[above_indices[a]], current_candle_time, source_tag + " [Above #" + IntegerToString(a + 1) + "]");
   }

   int render_below = MathMin(InpMaxZonesBelow, below_count);
   for(int b = 0; b < render_below; b++)
   {
      DrawZone(candidates[below_indices[b]], current_candle_time, source_tag + " [Below #" + IntegerToString(b + 1) + "]");
   }

   PurgeOrphanedObjects();
}

//+------------------------------------------------------------------+
//| Graphic Renderer Helper                                          |
//+------------------------------------------------------------------+
void DrawZone(const ZoneItem &zone, datetime current_time, string prefix_tag)
{
   string id_str = IntegerToString(zone.time) + "_" + IntegerToString(zone.bar_index) + "_" + DoubleToString(zone.bottom, 2);
   string rect_name = OBJ_PREFIX + "BOX_" + id_str;
   string mt_line_name = OBJ_PREFIX + "MT_" + id_str;
   string text_name = OBJ_PREFIX + "LBL_" + id_str;

   color zone_color;
   string badge = "";

   if(zone.is_confluence)
   {
      zone_color = zone.is_bullish ? InpColorConfDemand : InpColorConfSupply;
      badge = "★ [CONFLUENCE: " + zone.confluence_desc + "]";
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

   datetime start_time = zone.is_breaker ? zone.breaker_time : zone.time;
   if(start_time == 0) start_time = current_time - 3600 * 4;

   // 1. In-Place Update Rectangle Box (Zero Flicker)
   RegisterActiveObjectName(rect_name);
   int rect_style = zone.is_inside ? STYLE_SOLID : (zone.is_mitigated ? STYLE_DASH : STYLE_SOLID);
   int rect_width = zone.is_inside ? 2 : 1;
   color rect_color = zone.is_inside ? InpColorInside : zone_color;
   UpdateOrCreateRect(rect_name, start_time, zone.top, current_time, zone.bottom, rect_color, rect_style, rect_width);

   // 2. In-Place Update Mean Threshold (50% MT) Line
   if(InpShowMeanThreshold)
   {
      RegisterActiveObjectName(mt_line_name);
      UpdateOrCreateLine(mt_line_name, start_time, zone.mean_threshold, current_time, zone_color, STYLE_DOT, 1);
   }

   // 3. In-Place Update Informative Tag Label
   string label = prefix_tag + " " + badge;

   if(!zone.is_confluence && (zone.kind == ZONE_CONTINUATION_RBR || zone.kind == ZONE_CONTINUATION_DBD))
   {
      label += " Base:" + IntegerToString(zone.base_count) + "c Imp:" + DoubleToString(zone.impulse_ratio, 1) + "x";
   }

   if(zone.has_swept_liq) label += " [Swept Liq]";

   if(zone.touch_count == 0)
   {
      label += " [Virgin]";
   }
   else if(zone.is_mitigated)
   {
      label += " [Tested x" + IntegerToString(zone.touch_count) + " @ " + DoubleToString(zone.deepest_touch_price, _Digits) + "]";
   }
   else
   {
      label += " [Wick Touch x" + IntegerToString(zone.touch_count) + " @ " + DoubleToString(zone.deepest_touch_price, _Digits) + "]";
   }

   label += " MT:" + DoubleToString(zone.mean_threshold, _Digits);

   RegisterActiveObjectName(text_name);
   color text_color = zone.is_inside ? InpColorInside : zone_color;
   UpdateOrCreateText(text_name, current_time, zone.mean_threshold, label, text_color, 8, ANCHOR_RIGHT_LOWER);
}
//+------------------------------------------------------------------+
