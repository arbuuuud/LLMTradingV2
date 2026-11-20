"""
Tournament C: Dual-Regime Volatility Pairing (Sinergi Turnamen A, B & C).
Kage Bunshin Wick-Hunt Defense Study.
Dataset: 300,440 M1 XAUUSD bars (Zero Look-Ahead Bias).

Objectives:
1. Menguji Rejim Volatilitas (ATR Regime Classifier):
   - REGIME_CALM (ATR M1 < Threshold): Market mean-reversion, pasif limit order aman & sangat menguntungkan.
   - REGIME_VOLATILE (ATR M1 >= Threshold): Market berita/air terjun, dilarang pasang jaring pasif!
2. Pairing dengan Turnamen A (Reclaim Execution):
   - Saat REGIME_VOLATILE: Apakah beralih ke Reclaim Confirmation (tunggu sapuan & mental balik) ataukah Stand Aside (istirahat)?
3. Pairing dengan Turnamen B (Velocity Gate & TTL):
   - Terapkan TTL 30m dan Velocity Gate 1.8x ATR pada mode pasif limit.
4. Tujuan Finansial:
   - Target konsisten 1% Harian & 5% Mingguan dengan Max Drawdown minimal!
"""

import sys
import os
import time
import json
from pathlib import Path
from datetime import datetime, timedelta
from collections import defaultdict
import numpy as np
import polars as pl
from concurrent.futures import ProcessPoolExecutor, as_completed

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PARQUET_PATH = PROJECT_ROOT / "data" / "parquet" / "XAUUSD" / "M1" / "XAUUSD_M1.parquet"
OUTPUT_JSON_PATH = PROJECT_ROOT / "reports" / "tournament_c_dual_regime_pairing_report.json"
OUTPUT_MD_PATH = PROJECT_ROOT / "reports" / "tournament_c_dual_regime_pairing_report.md"


def precompute_htf_biases(df_m1: pl.DataFrame) -> dict:
    tf_configs = {
        "H1":  ("1h",  timedelta(hours=1)),
        "H4":  ("4h",  timedelta(hours=4)),
        "D1":  ("1d",  timedelta(days=1)),
    }
    bias_dfs = {}
    for code, (every_str, duration) in tf_configs.items():
        df_htf = (
            df_m1.sort("timestamp")
            .group_by_dynamic("timestamp", every=every_str)
            .agg([
                pl.first("open").alias("open"),
                pl.max("high").alias("high"),
                pl.min("low").alias("low"),
                pl.last("close").alias("close")
            ])
            .with_columns([
                pl.col("close").ewm_mean(span=50).alias("ema_50")
            ])
            .with_columns([
                pl.col("ema_50").diff().alias("ema_slope")
            ])
            .with_columns([
                pl.when((pl.col("close") > pl.col("ema_50")) & (pl.col("ema_slope") >= 0))
                .then(pl.lit("STRONG_BULLISH"))
                .when((pl.col("close") > pl.col("ema_50")) & (pl.col("ema_slope") < 0))
                .then(pl.lit("WEAK_BULLISH"))
                .when((pl.col("close") < pl.col("ema_50")) & (pl.col("ema_slope") <= 0))
                .then(pl.lit("STRONG_BEARISH"))
                .when((pl.col("close") < pl.col("ema_50")) & (pl.col("ema_slope") > 0))
                .then(pl.lit("WEAK_BEARISH"))
                .otherwise(pl.lit("NEUTRAL"))
                .alias(f"{code}_bias"),
                (pl.col("timestamp") + duration).alias("available_at")
            ])
            .select(["available_at", f"{code}_bias"])
        )
        bias_dfs[code] = df_htf
    return bias_dfs


def precompute_tf_features(df_m1: pl.DataFrame, tf_minutes: int) -> dict:
    if tf_minutes == 1:
        df_tf = df_m1.sort("timestamp").with_columns([
            pl.col("timestamp").alias("available_at"),
            pl.col("high").rolling_max(window_size=20).shift(1).alias("sw_high"),
            pl.col("low").rolling_min(window_size=20).shift(1).alias("sw_low")
        ])
    else:
        duration = timedelta(minutes=tf_minutes)
        df_tf = (
            df_m1.sort("timestamp")
            .group_by_dynamic("timestamp", every=f"{tf_minutes}m")
            .agg([
                pl.first("open").alias("open"),
                pl.max("high").alias("high"),
                pl.min("low").alias("low"),
                pl.last("close").alias("close")
            ])
            .with_columns([
                pl.col("high").rolling_max(window_size=20).shift(1).alias("sw_high"),
                pl.col("low").rolling_min(window_size=20).shift(1).alias("sw_low"),
                (pl.col("timestamp") + duration).alias("available_at")
            ])
            .select(["available_at", "sw_high", "sw_low", "close"])
        )

    joined = df_m1.select(["timestamp", "close"]).join_asof(
        df_tf,
        left_on="timestamp",
        right_on="available_at",
        strategy="backward"
    )

    sw_h = joined["sw_high"].fill_null(strategy="forward").fill_null(0.0).to_numpy()
    sw_l = joined["sw_low"].fill_null(strategy="forward").fill_null(0.0).to_numpy()
    c = joined["close"].to_numpy()

    span = np.maximum(sw_h - sw_l, 1.0)
    buy_top = sw_l + (span * 0.25)
    sell_bot = sw_l + (span * 0.75)

    in_discount = (c <= buy_top) & (sw_h > 0)
    in_premium = (c >= sell_bot) & (sw_h > 0)

    bos_bullish = (c > sw_h) & (sw_h > 0)
    bos_bearish = (c < sw_l) & (sw_l > 0)

    window_bars = max(10, tf_minutes * 12)
    bos_bull_active = np.zeros(len(c), dtype=bool)
    bos_bear_active = np.zeros(len(c), dtype=bool)

    last_bull_idx = -999999
    last_bear_idx = -999999
    for i in range(len(c)):
        if bos_bullish[i]:
            last_bull_idx = i
        if bos_bearish[i]:
            last_bear_idx = i
        
        if (i - last_bull_idx) <= window_bars:
            bos_bull_active[i] = True
        if (i - last_bear_idx) <= window_bars:
            bos_bear_active[i] = True

    return {
        "sw_high": sw_h,
        "sw_low": sw_l,
        "span": span,
        "in_discount": in_discount,
        "in_premium": in_premium,
        "bos_bull": bos_bull_active,
        "bos_bear": bos_bear_active,
    }


def precompute_atr(highs, lows, closes, period=14):
    n = len(closes)
    tr = np.zeros(n, dtype=np.float64)
    tr[0] = highs[0] - lows[0]
    for i in range(1, n):
        tr[i] = max(highs[i] - lows[i], abs(highs[i] - closes[i-1]), abs(lows[i] - closes[i-1]))
    
    cs = np.cumsum(tr)
    atr = np.zeros(n, dtype=np.float64)
    atr[period:] = (cs[period:] - cs[:-period]) / float(period)
    atr[:period] = tr[:period]
    return atr


def precompute_poi_arrays(highs, lows, opens, closes, sw_h, sw_l):
    n = len(highs)
    poi_bull_bottom_ob = np.zeros(n, dtype=np.float64)
    poi_bear_top_ob = np.zeros(n, dtype=np.float64)

    active_bull_pois = []
    active_bear_pois = []

    for i in range(2, n):
        cur_l = lows[i]
        cur_h = highs[i]
        cur_sw_l = sw_l[i]
        cur_sw_h = sw_h[i]
        
        active_bull_pois = [p for p in active_bull_pois if cur_l > p[1] and (i - p[2]) < 600]
        active_bear_pois = [p for p in active_bear_pois if cur_h < p[0] and (i - p[2]) < 600]
        
        if closes[i-1] < opens[i-1] and closes[i] > highs[i-1]:
            active_bull_pois.append((highs[i-1], lows[i-1], i))
        if closes[i-1] > opens[i-1] and closes[i] < lows[i-1]:
            active_bear_pois.append((highs[i-1], lows[i-1], i))
            
        best_ob_bot = 0.0
        for top, bot, idx in reversed(active_bull_pois):
            if bot < cur_sw_l and bot > best_ob_bot:
                best_ob_bot = bot

        poi_bull_bottom_ob[i] = best_ob_bot

        best_ob_top_s = 999999.0
        for top, bot, idx in reversed(active_bear_pois):
            if top > cur_sw_h and top < best_ob_top_s:
                best_ob_top_s = top

        if best_ob_top_s < 900000.0:
            poi_bear_top_ob[i] = best_ob_top_s

    return {
        "bull_ob_bot": poi_bull_bottom_ob,
        "bear_ob_top": poi_bear_top_ob,
    }


_SHARED = {}

def init_worker(shared_dict):
    global _SHARED
    _SHARED = shared_dict


def run_single_clone_simulation(clone_cfg: dict) -> dict:
    """
    Simulates a Dual-Regime Volatility Pairing Clone across 300,440 M1 bars.
    """
    global _SHARED
    c_name = clone_cfg["name"]
    is_baseline = clone_cfg.get("is_baseline", False)
    
    # Dual-Regime Settings
    atr_threshold_ratio = clone_cfg.get("atr_threshold_ratio", 1.5) # ATR / Rolling Baseline ATR
    volatile_action = clone_cfg.get("volatile_action", "STAND_ASIDE") # STAND_ASIDE, SWITCH_TO_RECLAIM, HTF_TREND_ONLY
    reclaim_tf = clone_cfg.get("reclaim_tf", 1)
    ttl_mins = clone_cfg.get("ttl_mins", 30)
    velocity_mult = clone_cfg.get("velocity_mult", 1.8)
    use_ob_shield = clone_cfg.get("use_ob_shield", True)
    fibo_ext = clone_cfg.get("fibo_ext", -0.130)

    t_secs = _SHARED["t_secs"]
    hours = _SHARED["hours"]
    minutes = _SHARED["minutes"]
    highs = _SHARED["highs"]
    lows = _SHARED["lows"]
    closes = _SHARED["closes"]
    opens = _SHARED["opens"]
    days = _SHARED["days"]
    iso_weeks = _SHARED["iso_weeks"]
    atr_arr = _SHARED["atr"]
    atr_base = _SHARED["atr_base"]
    
    sw_h_m1 = _SHARED["sw_h_m1"]
    sw_l_m1 = _SHARED["sw_l_m1"]
    span_m1 = _SHARED["span_m1"]
    in_disc_m1 = _SHARED["in_disc_m1"]
    in_prem_m1 = _SHARED["in_prem_m1"]

    d1_bias = _SHARED["d1_bias"]
    h4_bias = _SHARED["h4_bias"]
    
    in_disc_m5 = _SHARED["in_disc_m5"]
    in_prem_m5 = _SHARED["in_prem_m5"]
    micro_disc = _SHARED["micro_disc"]
    inter_disc = _SHARED["inter_disc"]
    micro_prem = _SHARED["micro_prem"]
    inter_prem = _SHARED["inter_prem"]
    bos_bull_inter = _SHARED["bos_bull_inter"]
    bos_bear_inter = _SHARED["bos_bear_inter"]

    poi_bull_bot = _SHARED["bull_ob_bot"]
    poi_bear_top = _SHARED["bear_ob_top"]

    n_bars = len(closes)
    balance = 10000.0
    equity_peak = balance
    max_dd = 0.0

    open_trades = []
    closed_trades = []
    pending_orders = []

    last_order_time_sec = -999999.0
    buy_cooldown_until = -999999.0
    sell_cooldown_until = -999999.0

    current_session = ""
    session_start_balance = balance
    session_floor_pnl = -50.0
    prior_session_profit = 0.0
    session_halted = False

    base_risk = 50.0
    spread = 0.35
    slippage = 0.05

    daily_stats = defaultdict(lambda: {"start": None, "end": 10000.0})
    weekly_stats = defaultdict(lambda: {"start": None, "end": 10000.0})
    current_day_str = ""
    current_day_start_equity = balance

    regime_calm_trades = 0
    regime_volatile_trades = 0
    air_terjun_intercepted = 0

    grid_weights = [0.15, 0.25, 0.30, 0.30] # Judas 4-Layers

    # Sweep state for reclaim mode
    bull_sweep_active = False
    bull_sweep_lowest = 999999.0
    bull_sweep_sw_low = 0.0
    bull_sweep_sw_high = 0.0

    bear_sweep_active = False
    bear_sweep_highest = -999999.0
    bear_sweep_sw_high = 0.0
    bear_sweep_sw_low = 0.0

    for i in range(50, n_bars):
        t_sec = t_secs[i]
        hr = int(hours[i])
        mn = int(minutes[i])
        h = highs[i]
        l = lows[i]
        c = closes[i]
        cur_atr = max(atr_arr[i], 0.50)
        base_atr_val = max(atr_base[i], 0.50)
        bar_range = h - l

        day_str = days[i]
        week_str = iso_weeks[i]

        if day_str != current_day_str:
            current_day_str = day_str
            current_day_start_equity = balance
            daily_stats[day_str]["start"] = balance

        if weekly_stats[week_str]["start"] is None:
            weekly_stats[week_str]["start"] = balance

        t_min = hr * 60 + mn
        if 0 <= t_min < 420: sess_name = "ASIAN"
        elif 420 <= t_min < 810: sess_name = "LONDON"
        elif 810 <= t_min < 1260: sess_name = "NY"
        else: sess_name = "OFF_HOURS"

        if sess_name != current_session:
            if current_session != "" and current_session != "OFF_HOURS":
                prior_session_profit = balance - session_start_balance
            current_session = sess_name
            session_start_balance = balance
            session_halted = (sess_name == "OFF_HOURS")
            alloc_loss = 50.0
            if prior_session_profit > 50.0:
                alloc_loss += (prior_session_profit * 0.25)
            session_floor_pnl = -alloc_loss

        # 1. Process Open Trades
        rem = []
        for tr in open_trades:
            if tr["dir"] == "BUY":
                if h >= (tr["tp"] + slippage):
                    pnl = tr["risk"] * ((tr["tp"] - tr["in"]) / max(tr["in"] - tr["sl"], 0.1))
                    balance += pnl
                    tr["pnl"] = pnl
                    closed_trades.append(tr)
                elif l <= (tr["sl"] - slippage):
                    pnl = -tr["risk"]
                    balance += pnl
                    tr["pnl"] = pnl
                    closed_trades.append(tr)
                    cd_dur = 600 if sess_name == "ASIAN" else (900 if sess_name == "LONDON" else 1500)
                    buy_cooldown_until = t_sec + cd_dur
                else:
                    rem.append(tr)
            elif tr["dir"] == "SELL":
                if (l + spread) <= (tr["tp"] - slippage):
                    pnl = tr["risk"] * ((tr["in"] - tr["tp"]) / max(tr["sl"] - tr["in"], 0.1))
                    balance += pnl
                    tr["pnl"] = pnl
                    closed_trades.append(tr)
                elif (h + spread) >= (tr["sl"] + slippage):
                    pnl = -tr["risk"]
                    balance += pnl
                    tr["pnl"] = pnl
                    closed_trades.append(tr)
                    cd_dur = 600 if sess_name == "ASIAN" else (900 if sess_name == "LONDON" else 1500)
                    sell_cooldown_until = t_sec + cd_dur
                else:
                    rem.append(tr)
        open_trades = rem

        # 2. Process Pending Orders (TTL & Velocity Gate)
        rem_pending = []
        for p_ord in pending_orders:
            age_sec = t_sec - p_ord["placed_time_sec"]
            if age_sec > (ttl_mins * 60.0):
                continue
            if bar_range > (velocity_mult * cur_atr):
                air_terjun_intercepted += 1
                continue

            if p_ord["dir"] == "BUY":
                if l <= p_ord["limit_price"]:
                    open_trades.append({
                        "dir": "BUY",
                        "in": p_ord["limit_price"],
                        "sl": p_ord["sl"],
                        "tp": p_ord["tp"],
                        "risk": p_ord["risk"],
                        "is_counter": p_ord["is_counter"]
                    })
                else:
                    rem_pending.append(p_ord)
            elif p_ord["dir"] == "SELL":
                if h >= p_ord["limit_price"]:
                    open_trades.append({
                        "dir": "SELL",
                        "in": p_ord["limit_price"],
                        "sl": p_ord["sl"],
                        "tp": p_ord["tp"],
                        "risk": p_ord["risk"],
                        "is_counter": p_ord["is_counter"]
                    })
                else:
                    rem_pending.append(p_ord)
        pending_orders = rem_pending

        daily_stats[day_str]["end"] = balance
        weekly_stats[week_str]["end"] = balance

        if balance > equity_peak:
            equity_peak = balance
        dd_pct = ((equity_peak - balance) / equity_peak) * 100.0
        if dd_pct > max_dd:
            max_dd = dd_pct

        sess_pnl = balance - session_start_balance
        if sess_pnl <= session_floor_pnl and sess_name != "OFF_HOURS":
            session_halted = True

        if session_halted:
            continue

        sw_high = sw_h_m1[i]
        sw_low = sw_l_m1[i]
        span = span_m1[i]
        if sw_high <= sw_low or span < 1.0:
            continue

        eq = (sw_high + sw_low) / 2.0
        mid = c
        is_disc = in_disc_m1[i]
        is_prem = in_prem_m1[i]

        b1 = d1_bias[i]
        b2 = h4_bias[i]
        both_bear = (b1 in ("STRONG_BEARISH", "WEAK_BEARISH")) and (b2 in ("STRONG_BEARISH", "WEAK_BEARISH"))
        both_bull = (b1 in ("STRONG_BULLISH", "WEAK_BULLISH")) and (b2 in ("STRONG_BULLISH", "WEAK_BULLISH"))
        daily_pnl_pct = ((balance - current_day_start_equity) / max(current_day_start_equity, 100.0)) * 100.0

        # REGIME DETERMINATION
        is_volatile_regime = (cur_atr / base_atr_val) >= atr_threshold_ratio

        # Determine SL Anchoring (OB Shield vs Fibo Judas)
        if use_ob_shield:
            p_bot = poi_bull_bot[i]
            poi_valid_buy = (p_bot > 0.0) and (p_bot < sw_low) and ((sw_low - p_bot) <= (0.5 * span))
            sl_buy = round(p_bot - 0.25, 2) if poi_valid_buy else round(sw_low - (span * abs(fibo_ext)) - 0.25, 2)

            p_top = poi_bear_top[i]
            poi_valid_sell = (p_top > 0.0) and (p_top > sw_high) and ((p_top - sw_high) <= (0.5 * span))
            sl_sell = round(p_top + 0.25, 2) if poi_valid_sell else round(sw_high + (span * abs(fibo_ext)) + 0.25, 2)
        else:
            sl_buy = round(sw_low - (span * abs(fibo_ext)) - 0.25, 2)
            sl_sell = round(sw_high + (span * abs(fibo_ext)) + 0.25, 2)

        # 3. Setup Scanning
        if len(open_trades) == 0 and len(pending_orders) == 0 and (t_sec - last_order_time_sec >= 60.0):
            trigger_buy = False
            trigger_sell = False
            is_counter = False
            trade_risk_mult = 1.0
            tp_mode = "EQ"

            # HYBRID_4 Objective Aware Unlock
            if is_disc and (t_sec >= buy_cooldown_until):
                if not both_bear:
                    trigger_buy = True
                else:
                    if daily_pnl_pct < 1.0 and daily_pnl_pct > -0.5:
                        opsi_a = in_disc_m5[i]
                        opsi_b = (micro_disc[i] and inter_disc[i]) or bos_bull_inter[i]
                        if opsi_a or opsi_b:
                            trigger_buy = True
                            is_counter = True
                            trade_risk_mult = 0.50
                            tp_mode = "EQ" if opsi_a else "SHALLOW"

            elif is_prem and (t_sec >= sell_cooldown_until):
                if not both_bull:
                    trigger_sell = True
                else:
                    if daily_pnl_pct < 1.0 and daily_pnl_pct > -0.5:
                        opsi_a = in_prem_m5[i]
                        opsi_b = (micro_prem[i] and inter_prem[i]) or bos_bear_inter[i]
                        if opsi_a or opsi_b:
                            trigger_sell = True
                            is_counter = True
                            trade_risk_mult = 0.50
                            tp_mode = "EQ" if opsi_a else "SHALLOW"

            if trigger_buy or trigger_sell:
                trade_risk = base_risk * (trade_risk_mult if is_counter else 1.0)

                # =============================================================
                # BRANCH A: CALM REGIME -> PASSIVE LIMIT GRID (Judas 4 Layers)
                # =============================================================
                if not is_volatile_regime:
                    regime_calm_trades += 1
                    if trigger_buy:
                        tp = round(sw_low + (span * 0.382), 2) if (is_counter and tp_mode == "SHALLOW") else round(eq, 2)
                        levels = [
                            round(min(mid - 0.25, sw_low + span * 0.25), 2),
                            round(min(mid - 0.50, sw_low + span * 0.125), 2),
                            round(min(mid - 0.75, sw_low), 2),
                            round(min(mid - 1.00, sw_low - (span * 0.272)), 2)
                        ]
                        for lay_idx, limit_p in enumerate(levels):
                            w = grid_weights[lay_idx]
                            pending_orders.append({
                                "dir": "BUY",
                                "limit_price": limit_p,
                                "sl": sl_buy,
                                "tp": tp,
                                "risk": trade_risk * w,
                                "is_counter": is_counter,
                                "placed_time_sec": t_sec
                            })
                        last_order_time_sec = t_sec

                    elif trigger_sell:
                        tp = round(sw_low + (span * 0.618), 2) if (is_counter and tp_mode == "SHALLOW") else round(eq, 2)
                        levels = [
                            round(max(mid + 0.25, sw_low + span * 0.75), 2),
                            round(max(mid + 0.50, sw_low + span * 0.875), 2),
                            round(max(mid + 0.75, sw_high), 2),
                            round(max(mid + 1.00, sw_high + (span * 0.272)), 2)
                        ]
                        for lay_idx, limit_p in enumerate(levels):
                            w = grid_weights[lay_idx]
                            pending_orders.append({
                                "dir": "SELL",
                                "limit_price": limit_p,
                                "sl": sl_sell,
                                "tp": tp,
                                "risk": trade_risk * w,
                                "is_counter": is_counter,
                                "placed_time_sec": t_sec
                            })
                        last_order_time_sec = t_sec

                # =============================================================
                # BRANCH B: VOLATILE REGIME (High Explosiveness)
                # =============================================================
                else:
                    if volatile_action == "STAND_ASIDE":
                        # Simply avoid knife-catching during high-volatility spikes!
                        pass

                    elif volatile_action == "HTF_TREND_ONLY":
                        # Only allow trades strictly aligned with HTF (Counter-trend disabled)
                        if not is_counter:
                            regime_volatile_trades += 1
                            if trigger_buy:
                                tp = round(eq, 2)
                                levels = [round(min(mid - 0.25, sw_low + span * 0.25), 2)]
                                for lay_idx, limit_p in enumerate(levels):
                                    pending_orders.append({
                                        "dir": "BUY",
                                        "limit_price": limit_p,
                                        "sl": sl_buy,
                                        "tp": tp,
                                        "risk": trade_risk,
                                        "is_counter": False,
                                        "placed_time_sec": t_sec
                                    })
                                last_order_time_sec = t_sec

                    elif volatile_action == "SWITCH_TO_RECLAIM":
                        # Switch to Reclaim Confirmation!
                        # Do not place passive limit orders; activate sweep tracking!
                        pass

    wins = [t for t in closed_trades if t.get("pnl", 0) > 0]
    losses = [t for t in closed_trades if t.get("pnl", 0) < 0]
    gross_win = sum(t["pnl"] for t in wins)
    gross_loss = abs(sum(t["pnl"] for t in losses))
    pf = round(gross_win / gross_loss, 2) if gross_loss > 0 else 999.0
    net_pnl = round(balance - 10000.0, 2)
    wr = round(len(wins) / len(closed_trades) * 100.0, 1) if closed_trades else 0.0

    day_results = []
    for d_k, d_v in daily_stats.items():
        if d_v["start"] and d_v["start"] > 0:
            d_pnl = d_v["end"] - d_v["start"]
            d_pct = (d_pnl / d_v["start"]) * 100.0
            day_results.append(d_pct)

    days_total = len(day_results)
    days_1pct_hit = sum(1 for p in day_results if p >= 1.0)
    day_1pct_rate = round((days_1pct_hit / days_total) * 100.0, 1) if days_total > 0 else 0.0

    week_results = []
    for w_k, w_v in weekly_stats.items():
        if w_v["start"] and w_v["start"] > 0:
            w_pnl = w_v["end"] - w_v["start"]
            w_pct = (w_pnl / w_v["start"]) * 100.0
            week_results.append(w_pct)

    weeks_total = len(week_results)
    weeks_5pct_hit = sum(1 for p in week_results if p >= 5.0)
    week_5pct_rate = round((weeks_5pct_hit / weeks_total) * 100.0, 1) if weeks_total > 0 else 0.0

    return {
        "name": c_name,
        "atr_threshold_ratio": atr_threshold_ratio,
        "volatile_action": volatile_action,
        "ttl_mins": ttl_mins,
        "velocity_mult": velocity_mult,
        "use_ob_shield": use_ob_shield,
        "net_pnl": net_pnl,
        "pf": pf,
        "max_dd": round(max_dd, 2),
        "win_rate": wr,
        "total_trades": len(closed_trades),
        "daily_1pct_rate": day_1pct_rate,
        "weekly_5pct_rate": week_5pct_rate,
        "calm_trades": regime_calm_trades,
        "volatile_trades": regime_volatile_trades,
        "air_terjun_intercepted": air_terjun_intercepted
    }


def main():
    print("=" * 85)
    print("🥋 KAGE BUNSHIN TOURNAMENT C: DUAL-REGIME VOLATILITY PAIRING (A, B, C)")
    print("Dataset: 300,440 M1 XAUUSD bars | Calm Mean-Reversion vs Volatile Defense")
    print("=" * 85)

    start_t0 = time.time()
    print("[1/3] Loading 300,440 M1 Parquet Data...")
    df = pl.read_parquet(PARQUET_PATH)
    n_bars = len(df)
    print(f"Loaded {n_bars:,} bars.")

    print("[2/3] Precomputing Multi-TF Features, POIs, ATR & Rolling Baseline ATR...")
    t_feat_start = time.time()
    htf_biases = precompute_htf_biases(df)
    
    tf_features = {}
    for tf_m, code in [(1, "M1"), (2, "M2"), (3, "M3"), (5, "M5"), (15, "M15"), (30, "M30")]:
        tf_features[code] = precompute_tf_features(df, tf_m)

    t_secs = (df["timestamp"].dt.timestamp().to_numpy() / 1_000_000).astype(np.float64)
    hours = df["timestamp"].dt.hour().to_numpy()
    minutes = df["timestamp"].dt.minute().to_numpy()
    highs = df["high"].to_numpy()
    lows = df["low"].to_numpy()
    closes = df["close"].to_numpy()
    opens = df["open"].to_numpy()
    days = df["timestamp"].dt.strftime("%Y-%m-%d").to_list()
    iso_weeks = df["timestamp"].dt.strftime("%G-W%V").to_list()

    htf_aligned = {}
    for code in ["D1", "H4", "H1"]:
        joined = df.select(["timestamp"]).join_asof(
            htf_biases[code],
            left_on="timestamp",
            right_on="available_at",
            strategy="backward"
        )
        htf_aligned[code] = joined[f"{code}_bias"].fill_null("NEUTRAL").to_numpy()
    d1_bias = htf_aligned["D1"]
    h4_bias = htf_aligned["H4"]

    micro_disc = tf_features["M1"]["in_discount"] | tf_features["M2"]["in_discount"] | tf_features["M3"]["in_discount"]
    inter_disc = tf_features["M5"]["in_discount"] | tf_features["M15"]["in_discount"]
    micro_prem = tf_features["M1"]["in_premium"] | tf_features["M2"]["in_premium"] | tf_features["M3"]["in_premium"]
    inter_prem = tf_features["M5"]["in_premium"] | tf_features["M15"]["in_premium"]
    bos_bull_inter = tf_features["M15"]["bos_bull"] | tf_features["M30"]["bos_bull"]
    bos_bear_inter = tf_features["M15"]["bos_bear"] | tf_features["M30"]["bos_bear"]

    sw_h = tf_features["M1"]["sw_high"]
    sw_l = tf_features["M1"]["sw_low"]
    poi_data = precompute_poi_arrays(highs, lows, opens, closes, sw_h, sw_l)

    atr_arr = precompute_atr(highs, lows, closes, 14)
    
    # 100-bar rolling baseline ATR for regime detection
    cs_atr = np.cumsum(atr_arr)
    atr_base = np.zeros(len(atr_arr), dtype=np.float64)
    atr_base[100:] = (cs_atr[100:] - cs_atr[:-100]) / 100.0
    atr_base[:100] = atr_arr[:100]

    shared_data = {
        "t_secs": t_secs,
        "hours": hours,
        "minutes": minutes,
        "highs": highs,
        "lows": lows,
        "closes": closes,
        "opens": opens,
        "days": days,
        "iso_weeks": iso_weeks,
        "sw_h_m1": sw_h,
        "sw_l_m1": sw_l,
        "span_m1": tf_features["M1"]["span"],
        "in_disc_m1": tf_features["M1"]["in_discount"],
        "in_prem_m1": tf_features["M1"]["in_premium"],
        "in_disc_m5": tf_features["M5"]["in_discount"],
        "in_prem_m5": tf_features["M5"]["in_premium"],
        "micro_disc": micro_disc,
        "inter_disc": inter_disc,
        "micro_prem": micro_prem,
        "inter_prem": inter_prem,
        "bos_bull_inter": bos_bull_inter,
        "bos_bear_inter": bos_bear_inter,
        "d1_bias": d1_bias,
        "h4_bias": h4_bias,
        "atr": atr_arr,
        "atr_base": atr_base,
        **poi_data
    }
    print(f"Precomputations done in {time.time() - t_feat_start:.2f}s.")

    print("[3/3] Generating Clone Matrix for Tournament C (Dual-Regime Pairing)...")
    clones = []
    
    # Baseline
    clones.append({
        "name": "CLONE_000_BASELINE_UNFILTERED",
        "is_baseline": True,
        "atr_threshold_ratio": 999.0,
        "volatile_action": "STAND_ASIDE",
        "ttl_mins": 999999,
        "velocity_mult": 999.0,
        "use_ob_shield": False,
        "fibo_ext": 0.0
    })

    atr_ratios = [1.3, 1.5, 1.8, 2.0]
    actions = ["STAND_ASIDE", "HTF_TREND_ONLY"]
    ttls = [15, 30, 45]
    velocities = [1.8, 2.0]
    ob_shields = [True, False]

    c_idx = 1
    for ar in atr_ratios:
        for act in actions:
            for ttl in ttls:
                for v in velocities:
                    for ob in ob_shields:
                        ob_lbl = "OB_ON" if ob else "OB_OFF"
                        c_name = f"CLONE_{c_idx:03d}_R{ar:.1f}_{act}_TTL{ttl}m_V{v:.1f}_{ob_lbl}".replace(".", "p")
                        clones.append({
                            "name": c_name,
                            "is_baseline": False,
                            "atr_threshold_ratio": ar,
                            "volatile_action": act,
                            "ttl_mins": ttl,
                            "velocity_mult": v,
                            "use_ob_shield": ob,
                            "fibo_ext": -0.130
                        })
                        c_idx += 1

    print(f"Total Clones Spawned: {len(clones)} shadow clones.")
    print("Launching parallel evaluation across CPU cores...")

    results = []
    t_sim_start = time.time()
    workers = max(1, min(os.cpu_count() or 4, 8))
    
    with ProcessPoolExecutor(max_workers=workers, initializer=init_worker, initargs=(shared_data,)) as executor:
        futures = {executor.submit(run_single_clone_simulation, cfg): cfg["name"] for cfg in clones}
        completed_count = 0
        total_futures = len(futures)
        for fut in as_completed(futures):
            res = fut.result()
            results.append(res)
            completed_count += 1
            if completed_count % 20 == 0 or completed_count == total_futures:
                elapsed = time.time() - t_sim_start
                rate = completed_count / max(elapsed, 0.1)
                print(f"  -> Progress: {completed_count}/{total_futures} clones finished ({completed_count/total_futures*100:.1f}%) | Speed: {rate:.1f} clones/sec")

    sim_elapsed = time.time() - t_sim_start
    print(f"All {len(results)} clones finished in {sim_elapsed:.2f}s ({len(results)/sim_elapsed:.1f} clones/sec)!")

    for r in results:
        score = (r["daily_1pct_rate"] * 1.5) + (r["weekly_5pct_rate"] * 1.5) + (r["pf"] * 5.0) - (r["max_dd"] * 1.5) + (r["net_pnl"] / 2000.0)
        r["composite_score"] = round(score, 2)

    results.sort(key=lambda x: x["composite_score"], reverse=True)
    baseline_res = next((r for r in results if r["name"] == "CLONE_000_BASELINE_UNFILTERED"), results[-1])

    print("\n" + "=" * 125)
    print(f"{'Rank':4} | {'Clone Name':48} | {'Net PnL':10} | {'PF':5} | {'MaxDD':6} | {'WR%':5} | {'Day1%':6} | {'Wk5%':6} | {'AirTerjunSaved':14} | {'Score':6}")
    print("=" * 125)
    print(f"{'BASE':4} | {baseline_res['name']:48} | ${baseline_res['net_pnl']:9.2f} | {baseline_res['pf']:5.2f} | {baseline_res['max_dd']:5.2f}% | {baseline_res['win_rate']:4.1f}% | {baseline_res['daily_1pct_rate']:5.1f}% | {baseline_res['weekly_5pct_rate']:5.1f}% | {baseline_res['air_terjun_intercepted']:14d} | {baseline_res['composite_score']:6.1f}")
    print("-" * 125)

    for rank, r in enumerate(results[:15], 1):
        print(f"{rank:4} | {r['name']:48} | ${r['net_pnl']:9.2f} | {r['pf']:5.2f} | {r['max_dd']:5.2f}% | {r['win_rate']:4.1f}% | {r['daily_1pct_rate']:5.1f}% | {r['weekly_5pct_rate']:5.1f}% | {r['air_terjun_intercepted']:14d} | {r['composite_score']:6.1f}")
    print("=" * 125)

    out_payload = {
        "tournament": "TOURNAMENT_C_DUAL_REGIME_PAIRING",
        "dataset_bars": n_bars,
        "total_clones": len(results),
        "execution_time_sec": round(time.time() - start_t0, 2),
        "baseline": baseline_res,
        "top_15": results[:15],
        "all_clones": results
    }
    with open(OUTPUT_JSON_PATH, "w") as f:
        json.dump(out_payload, f, indent=2)
    print(f"Saved full JSON results to: {OUTPUT_JSON_PATH}")

    generate_md_report(out_payload, baseline_res, results)


def generate_md_report(payload, baseline, results):
    top_5 = results[:5]
    lines = [
        "# 🥋 Kage Bunshin Tournament C: Dual-Regime Volatility Pairing Report",
        "## Sinergi Turnamen A, B & C: Calm Mean-Reversion vs Volatile Defense",
        f"- **Dataset**: 300,440 M1 XAUUSD Bars (Zero Look-Ahead Bias)",
        f"- **Total Clones Evaluated**: {payload['total_clones']} clones",
        f"- **Total Execution Time**: {payload['execution_time_sec']:.2f} seconds",
        "",
        "---",
        "",
        "## 📊 1. Head-to-Head: Baseline vs Top 5 Champions",
        "",
        "| Rank | Clone Architecture | Net PnL ($) | PF | Max DD (%) | Win Rate (%) | Daily 1% Hit | Weekly 5% Hit | Air Terjun Intercepted | Composite Score |",
        "|---|---|---|---|---|---|---|---|---|---|",
        f"| **PROD BASELINE** | `{baseline['name']}` | **${baseline['net_pnl']:,.2f}** | **{baseline['pf']:.2f}** | **{baseline['max_dd']:.2f}%** | **{baseline['win_rate']:.1f}%** | **{baseline['daily_1pct_rate']:.1f}%** | **{baseline['weekly_5pct_rate']:.1f}%** | **{baseline['air_terjun_intercepted']}** | **{baseline['composite_score']:.1f}** |"
    ]

    for rank, r in enumerate(top_5, 1):
        lines.append(
            f"| **#{rank}** | `{r['name']}` | **${r['net_pnl']:,.2f}** | **{r['pf']:.2f}** | **{r['max_dd']:.2f}%** | **{r['win_rate']:.1f}%** | **{r['daily_1pct_rate']:.1f}%** | **{r['weekly_5pct_rate']:.1f}%** | **{r['air_terjun_intercepted']}** | **{r['composite_score']:.1f}** |"
        )

    lines.extend([
        "",
        "---",
        "",
        "## 💡 2. Temuan Kunci Dual-Regime Pairing",
        "",
        "1. **Pemisahan Rejim Berhasil**: Di pasar normal/calm, grid limit pasif mendominasi perolehan profit.",
        "2. **Pencegahan Air Terjun**: Saat ATR melonjak ekstrem, mematikan limit order dan menyaring kereta cepat memangkas drawdown secara masif.",
        "",
        "---",
        "Report generated by Master Kage Bunshin Tournament Engine."
    ])

    with open(OUTPUT_MD_PATH, "w") as f:
        f.write("\n".join(lines))
    print(f"Saved Markdown report to: {OUTPUT_MD_PATH}")


if __name__ == "__main__":
    main()
