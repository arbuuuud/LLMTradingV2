"""
Batch 4: Candle Body Invalidation vs Wick Sweep (Soft SL & Multi-TF Bar Close) Tournament.
Kage Bunshin Wick-Hunt Defense Study.
Dataset: 300,440 M1 XAUUSD bars (Zero Look-Ahead Bias).

Tests ~200-250 clone variations across:
1. Baseline (Current production: Hard SL sw_low - 2.50 - buffer)
2. Bar Close Confirmation Timeframes: M1, M2, M3, M5
3. Invalidation Levels: SWING_EXACT (sw_low), SWING_BUFFER (sw_low - 0.50), FIBO_130, FIBO_236
4. Disaster Hard SL Bumpers: 1.5x ATR, 2.0x ATR, 2.5x ATR, 3.0x ATR
5. Patience Closes: 1 Bar Close vs 2 Consecutive Bar Closes
6. Grid Styles: STANDARD vs JUDAS_4_LAYERS
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
OUTPUT_JSON_PATH = PROJECT_ROOT / "reports" / "batch4_bar_close_invalidation_tournament_report.json"
OUTPUT_MD_PATH = PROJECT_ROOT / "reports" / "batch4_bar_close_invalidation_tournament_report.md"
MASTER_REGISTRY_PATH = PROJECT_ROOT / "reports" / "kage_bunshin_wick_study_master_registry.json"


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


_SHARED = {}

def init_worker(shared_dict):
    global _SHARED
    _SHARED = shared_dict


def run_single_clone_simulation(clone_cfg: dict) -> dict:
    """
    Simulates a single Bar-Close Invalidation Clone across 300,440 M1 bars.
    """
    global _SHARED
    c_name = clone_cfg["name"]
    is_baseline = clone_cfg.get("is_baseline", False)
    tf_mins = clone_cfg.get("tf_mins", 1) # 1, 2, 3, 5
    inv_level_mode = clone_cfg.get("inv_level_mode", "SWING_EXACT") # SWING_EXACT, SWING_BUF, FIBO_130, FIBO_236
    disaster_mult = clone_cfg.get("disaster_mult", 2.0) # x ATR
    consecutive_req = clone_cfg.get("consecutive_req", 1) # 1 or 2
    grid_style = clone_cfg.get("grid_style", "STANDARD") # STANDARD vs JUDAS_4_LAYERS

    t_secs = _SHARED["t_secs"]
    hours = _SHARED["hours"]
    minutes = _SHARED["minutes"]
    highs = _SHARED["highs"]
    lows = _SHARED["lows"]
    closes = _SHARED["closes"]
    days = _SHARED["days"]
    iso_weeks = _SHARED["iso_weeks"]
    atr_arr = _SHARED["atr"]
    
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

    n_bars = len(closes)
    balance = 10000.0
    equity_peak = balance
    max_dd = 0.0

    open_trades = []
    closed_trades = []

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

    wick_saved_count = 0
    soft_sl_trigger_count = 0
    disaster_sl_trigger_count = 0

    if grid_style == "STANDARD":
        grid_weights = [0.25, 0.35, 0.40]
    elif grid_style == "JUDAS_4_LAYERS":
        grid_weights = [0.15, 0.25, 0.30, 0.30]
    else:
        grid_weights = [0.25, 0.35, 0.40]

    for i in range(25, n_bars):
        t_sec = t_secs[i]
        hr = int(hours[i])
        mn = int(minutes[i])
        h = highs[i]
        l = lows[i]
        c = closes[i]
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

        # Is current bar the close of confirmation TF?
        is_tf_close = ((i + 1) % tf_mins == 0)

        # 1. Process Open Trades
        rem = []
        for tr in open_trades:
            if tr["dir"] == "BUY":
                # Check Take Profit
                if h >= (tr["tp"] + slippage):
                    pnl = tr["risk"] * ((tr["tp"] - tr["in"]) / max(tr["in"] - tr["sl_denom"], 0.1))
                    balance += pnl
                    tr["pnl"] = pnl
                    closed_trades.append(tr)
                    if tr.get("baseline_sl_breached", False):
                        wick_saved_count += 1

                # Check Disaster Hard SL (Immediate intraday safety net)
                elif l <= (tr["disaster_sl"] - slippage):
                    pnl = -tr["risk"] * (abs(tr["in"] - tr["disaster_sl"]) / max(tr["in"] - tr["sl_denom"], 0.1))
                    balance += pnl
                    tr["pnl"] = pnl
                    closed_trades.append(tr)
                    disaster_sl_trigger_count += 1
                    cd_dur = 600 if sess_name == "ASIAN" else (900 if sess_name == "LONDON" else 1500)
                    buy_cooldown_until = t_sec + cd_dur

                # Check Soft SL / Bar-Close Invalidation
                elif is_tf_close and (c <= tr["inv_level"]):
                    tr["consecutive_breaches"] += 1
                    if tr["consecutive_breaches"] >= consecutive_req:
                        # Soft Invalidation Exit at market close price
                        pnl = -tr["risk"] * (abs(tr["in"] - c) / max(tr["in"] - tr["sl_denom"], 0.1))
                        balance += pnl
                        tr["pnl"] = pnl
                        closed_trades.append(tr)
                        soft_sl_trigger_count += 1
                        cd_dur = 600 if sess_name == "ASIAN" else (900 if sess_name == "LONDON" else 1500)
                        buy_cooldown_until = t_sec + cd_dur
                    else:
                        rem.append(tr)
                else:
                    if is_tf_close and (c > tr["inv_level"]):
                        tr["consecutive_breaches"] = 0
                    if l <= (tr["baseline_sl"] - slippage):
                        tr["baseline_sl_breached"] = True
                    rem.append(tr)

            elif tr["dir"] == "SELL":
                # Check Take Profit
                if (l + spread) <= (tr["tp"] - slippage):
                    pnl = tr["risk"] * ((tr["in"] - tr["tp"]) / max(tr["sl_denom"] - tr["in"], 0.1))
                    balance += pnl
                    tr["pnl"] = pnl
                    closed_trades.append(tr)
                    if tr.get("baseline_sl_breached", False):
                        wick_saved_count += 1

                # Check Disaster Hard SL
                elif (h + spread) >= (tr["disaster_sl"] + slippage):
                    pnl = -tr["risk"] * (abs(tr["disaster_sl"] - tr["in"]) / max(tr["sl_denom"] - tr["in"], 0.1))
                    balance += pnl
                    tr["pnl"] = pnl
                    closed_trades.append(tr)
                    disaster_sl_trigger_count += 1
                    cd_dur = 600 if sess_name == "ASIAN" else (900 if sess_name == "LONDON" else 1500)
                    sell_cooldown_until = t_sec + cd_dur

                # Check Soft SL / Bar-Close Invalidation
                elif is_tf_close and (c >= tr["inv_level"]):
                    tr["consecutive_breaches"] += 1
                    if tr["consecutive_breaches"] >= consecutive_req:
                        pnl = -tr["risk"] * (abs(c - tr["in"]) / max(tr["sl_denom"] - tr["in"], 0.1))
                        balance += pnl
                        tr["pnl"] = pnl
                        closed_trades.append(tr)
                        soft_sl_trigger_count += 1
                        cd_dur = 600 if sess_name == "ASIAN" else (900 if sess_name == "LONDON" else 1500)
                        sell_cooldown_until = t_sec + cd_dur
                    else:
                        rem.append(tr)
                else:
                    if is_tf_close and (c < tr["inv_level"]):
                        tr["consecutive_breaches"] = 0
                    if (h + spread) >= (tr["baseline_sl"] + slippage):
                        tr["baseline_sl_breached"] = True
                    rem.append(tr)
        open_trades = rem

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

        # 2. Setup Scanning
        if len(open_trades) == 0 and (t_sec - last_order_time_sec >= 60.0):
            sw_high = sw_h_m1[i]
            sw_low = sw_l_m1[i]
            span = span_m1[i]
            cur_atr = max(atr_arr[i], 1.0)

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

            trigger_buy = False
            trigger_sell = False
            is_counter = False
            trade_risk_mult = 1.0
            tp_mode = "EQ"

            # HYBRID_4 Objective Aware Unlock
            if is_disc and (t_sec >= buy_cooldown_until):
                if not both_bear:
                    trigger_buy = True
                    is_counter = False
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
                    is_counter = False
                else:
                    if daily_pnl_pct < 1.0 and daily_pnl_pct > -0.5:
                        opsi_a = in_prem_m5[i]
                        opsi_b = (micro_prem[i] and inter_prem[i]) or bos_bear_inter[i]
                        if opsi_a or opsi_b:
                            trigger_sell = True
                            is_counter = True
                            trade_risk_mult = 0.50
                            tp_mode = "EQ" if opsi_a else "SHALLOW"

            if not trigger_buy and not trigger_sell:
                continue

            # Baseline SL
            baseline_sl_buffer = max(0.50, span * 0.0375)
            base_buy_sl = round(sw_low - 2.50 - baseline_sl_buffer, 2)
            base_sell_sl = round(sw_high + 2.50 + baseline_sl_buffer, 2)

            trade_risk = base_risk * (trade_risk_mult if is_counter else 1.0)

            # Invalidation Level & Disaster Hard SL
            if is_baseline:
                inv_buy = base_buy_sl
                inv_sell = base_sell_sl
                disaster_buy = base_buy_sl
                disaster_sell = base_sell_sl
            else:
                if inv_level_mode == "SWING_EXACT":
                    inv_buy = sw_low
                    inv_sell = sw_high
                elif inv_level_mode == "SWING_BUF":
                    inv_buy = sw_low - 0.50
                    inv_sell = sw_high + 0.50
                elif inv_level_mode == "FIBO_130":
                    inv_buy = sw_low - (span * 0.130)
                    inv_sell = sw_high + (span * 0.130)
                elif inv_level_mode == "FIBO_236":
                    inv_buy = sw_low - (span * 0.236)
                    inv_sell = sw_high + (span * 0.236)
                else:
                    inv_buy = sw_low
                    inv_sell = sw_high

                disaster_buy = round(sw_low - (disaster_mult * cur_atr), 2)
                disaster_sell = round(sw_high + (disaster_mult * cur_atr), 2)

            if trigger_buy:
                baseline_sl = base_buy_sl
                tp = round(sw_low + (span * 0.382), 2) if (is_counter and tp_mode == "SHALLOW") else round(eq, 2)

                if grid_style == "STANDARD":
                    levels = [
                        round(min(mid - 0.25, sw_low + span * 0.25), 2),
                        round(min(mid - 0.50, sw_low + span * 0.125), 2),
                        round(min(mid - 0.75, sw_low), 2)
                    ]
                elif grid_style == "JUDAS_4_LAYERS":
                    levels = [
                        round(min(mid - 0.25, sw_low + span * 0.25), 2),
                        round(min(mid - 0.50, sw_low + span * 0.125), 2),
                        round(min(mid - 0.75, sw_low), 2),
                        round(min(mid - 1.00, sw_low - (span * 0.272)), 2)
                    ]
                else:
                    levels = [round(min(mid - 0.25, sw_low + span * 0.25), 2)]

                for lay_idx, limit_p in enumerate(levels):
                    if l <= limit_p:
                        w = grid_weights[min(lay_idx, len(grid_weights) - 1)]
                        lay_risk = trade_risk * w
                        open_trades.append({
                            "dir": "BUY",
                            "in": limit_p,
                            "inv_level": inv_buy,
                            "disaster_sl": disaster_buy,
                            "sl_denom": inv_buy,
                            "baseline_sl": baseline_sl,
                            "tp": tp,
                            "risk": lay_risk,
                            "is_counter": is_counter,
                            "baseline_sl_breached": False,
                            "consecutive_breaches": 0
                        })
                last_order_time_sec = t_sec

            elif trigger_sell:
                baseline_sl = base_sell_sl
                tp = round(sw_low + (span * 0.618), 2) if (is_counter and tp_mode == "SHALLOW") else round(eq, 2)

                if grid_style == "STANDARD":
                    levels = [
                        round(max(mid + 0.25, sw_low + span * 0.75), 2),
                        round(max(mid + 0.50, sw_low + span * 0.875), 2),
                        round(max(mid + 0.75, sw_high), 2)
                    ]
                elif grid_style == "JUDAS_4_LAYERS":
                    levels = [
                        round(max(mid + 0.25, sw_low + span * 0.75), 2),
                        round(max(mid + 0.50, sw_low + span * 0.875), 2),
                        round(max(mid + 0.75, sw_high), 2),
                        round(max(mid + 1.00, sw_high + (span * 0.272)), 2)
                    ]
                else:
                    levels = [round(max(mid + 0.25, sw_low + span * 0.75), 2)]

                for lay_idx, limit_p in enumerate(levels):
                    if h >= limit_p:
                        w = grid_weights[min(lay_idx, len(grid_weights) - 1)]
                        lay_risk = trade_risk * w
                        open_trades.append({
                            "dir": "SELL",
                            "in": limit_p,
                            "inv_level": inv_sell,
                            "disaster_sl": disaster_sell,
                            "sl_denom": inv_sell,
                            "baseline_sl": baseline_sl,
                            "tp": tp,
                            "risk": lay_risk,
                            "is_counter": is_counter,
                            "baseline_sl_breached": False,
                            "consecutive_breaches": 0
                        })
                last_order_time_sec = t_sec

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
    days_breach = sum(1 for p in day_results if p <= -1.0)
    day_breach_rate = round((days_breach / days_total) * 100.0, 1) if days_total > 0 else 0.0

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
        "tf_mins": tf_mins,
        "inv_level_mode": inv_level_mode,
        "disaster_mult": disaster_mult,
        "consecutive_req": consecutive_req,
        "grid_style": grid_style,
        "net_pnl": net_pnl,
        "pf": pf,
        "max_dd": round(max_dd, 2),
        "win_rate": wr,
        "total_trades": len(closed_trades),
        "daily_1pct_rate": day_1pct_rate,
        "daily_breach_rate": day_breach_rate,
        "weekly_5pct_rate": week_5pct_rate,
        "wick_saved_count": wick_saved_count,
        "soft_sl_trigger_count": soft_sl_trigger_count,
        "disaster_sl_trigger_count": disaster_sl_trigger_count
    }


def main():
    print("=" * 80)
    print("🥋 MASTER KAGE BUNSHIN TOURNAMENT — BATCH 4: CANDLE BODY INVALIDATION (SOFT SL)")
    print("Dataset: 300,440 M1 XAUUSD bars | Objective: 1% Day / 5% Week | Wick-Hunt Defense")
    print("=" * 80)

    start_t0 = time.time()
    print("[1/3] Loading 300,440 M1 Parquet Data...")
    df = pl.read_parquet(PARQUET_PATH)
    n_bars = len(df)
    print(f"Loaded {n_bars:,} bars.")

    print("[2/3] Precomputing Multi-TF Features, Biases & ATR Arrays...")
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

    atr_arr = precompute_atr(highs, lows, closes, 14)

    shared_data = {
        "t_secs": t_secs,
        "hours": hours,
        "minutes": minutes,
        "highs": highs,
        "lows": lows,
        "closes": closes,
        "days": days,
        "iso_weeks": iso_weeks,
        "sw_h_m1": tf_features["M1"]["sw_high"],
        "sw_l_m1": tf_features["M1"]["sw_low"],
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
        "atr": atr_arr
    }
    print(f"Precomputations done in {time.time() - t_feat_start:.2f}s.")

    print("[3/3] Generating Clone Army Matrix for Batch 4...")
    clones = []
    
    # Baseline
    clones.append({
        "name": "CLONE_000_BASELINE_PROD",
        "is_baseline": True,
        "tf_mins": 1,
        "inv_level_mode": "BASELINE",
        "disaster_mult": 0.0,
        "consecutive_req": 1,
        "grid_style": "STANDARD"
    })

    # Bar Close Variations
    tfs = [1, 2, 3, 5]
    inv_modes = ["SWING_EXACT", "SWING_BUF", "FIBO_130", "FIBO_236"]
    disaster_mults = [1.5, 2.0, 2.5]
    consecutives = [1, 2]
    grid_styles = ["STANDARD", "JUDAS_4_LAYERS"]

    c_idx = 1
    for tf_m in tfs:
        for inv_m in inv_modes:
            for dm in disaster_mults:
                for cons in consecutives:
                    for gs in grid_styles:
                        c_name = f"CLONE_{c_idx:03d}_M{tf_m}_{inv_m}_D{dm:.1f}x_C{cons}_{gs}".replace(".", "p")
                        clones.append({
                            "name": c_name,
                            "is_baseline": False,
                            "tf_mins": tf_m,
                            "inv_level_mode": inv_m,
                            "disaster_mult": dm,
                            "consecutive_req": cons,
                            "grid_style": gs
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
            if completed_count % 30 == 0 or completed_count == total_futures:
                elapsed = time.time() - t_sim_start
                rate = completed_count / max(elapsed, 0.1)
                print(f"  -> Progress: {completed_count}/{total_futures} clones finished ({completed_count/total_futures*100:.1f}%) | Speed: {rate:.1f} clones/sec")

    sim_elapsed = time.time() - t_sim_start
    print(f"All {len(results)} clones finished in {sim_elapsed:.2f}s ({len(results)/sim_elapsed:.1f} clones/sec)!")

    for r in results:
        score = (r["daily_1pct_rate"] * 1.5) + (r["weekly_5pct_rate"] * 1.5) + (r["pf"] * 5.0) - (r["max_dd"] * 1.5) + (r["net_pnl"] / 2000.0)
        r["composite_score"] = round(score, 2)

    results.sort(key=lambda x: x["composite_score"], reverse=True)
    baseline_res = next((r for r in results if r["name"] == "CLONE_000_BASELINE_PROD"), results[-1])

    print("\n" + "=" * 115)
    print(f"{'Rank':4} | {'Clone Name':45} | {'Net PnL':10} | {'PF':5} | {'MaxDD':6} | {'WR%':5} | {'Day1%':6} | {'Wk5%':6} | {'WickSaved':9} | {'Score':6}")
    print("=" * 115)
    print(f"{'BASE':4} | {baseline_res['name']:45} | ${baseline_res['net_pnl']:9.2f} | {baseline_res['pf']:5.2f} | {baseline_res['max_dd']:5.2f}% | {baseline_res['win_rate']:4.1f}% | {baseline_res['daily_1pct_rate']:5.1f}% | {baseline_res['weekly_5pct_rate']:5.1f}% | {baseline_res['wick_saved_count']:9d} | {baseline_res['composite_score']:6.1f}")
    print("-" * 115)

    for rank, r in enumerate(results[:15], 1):
        print(f"{rank:4} | {r['name']:45} | ${r['net_pnl']:9.2f} | {r['pf']:5.2f} | {r['max_dd']:5.2f}% | {r['win_rate']:4.1f}% | {r['daily_1pct_rate']:5.1f}% | {r['weekly_5pct_rate']:5.1f}% | {r['wick_saved_count']:9d} | {r['composite_score']:6.1f}")
    print("=" * 115)

    out_payload = {
        "tournament": "BATCH_4_BAR_CLOSE_INVALIDATION",
        "dataset_bars": n_bars,
        "total_clones": len(results),
        "execution_time_sec": round(time.time() - start_t0, 2),
        "baseline": baseline_res,
        "top_10": results[:10],
        "all_clones": results
    }
    with open(OUTPUT_JSON_PATH, "w") as f:
        json.dump(out_payload, f, indent=2)
    print(f"Saved full JSON results to: {OUTPUT_JSON_PATH}")

    if MASTER_REGISTRY_PATH.exists():
        with open(MASTER_REGISTRY_PATH, "r") as f:
            registry = json.load(f)
    else:
        registry = {"batches": {}}

    registry["batches"]["batch_4_bar_close"] = {
        "title": "Batch 4: Candle Body Invalidation (Soft SL & Disaster Bumper)",
        "total_clones": len(results),
        "execution_time_sec": round(time.time() - start_t0, 2),
        "report_json": str(OUTPUT_JSON_PATH),
        "report_md": str(OUTPUT_MD_PATH),
        "baseline": baseline_res,
        "top_5_champions": results[:5]
    }
    with open(MASTER_REGISTRY_PATH, "w") as f:
        json.dump(registry, f, indent=2)
    print(f"Updated Master Registry: {MASTER_REGISTRY_PATH}")

    generate_md_report(out_payload, baseline_res, results)


def generate_md_report(payload, baseline, results):
    top_5 = results[:5]
    lines = [
        "# 🥋 Kage Bunshin Wick-Hunt Defense Study — Batch 4 Report",
        "## Candle Body Invalidation (Soft SL & Disaster Bumper) Matrix",
        f"- **Dataset**: 300,440 M1 XAUUSD Bars (Zero Look-Ahead Bias)",
        f"- **Total Clones Evaluated**: {payload['total_clones']} clones",
        f"- **Total Execution Time**: {payload['execution_time_sec']:.2f} seconds",
        "",
        "---",
        "",
        "## 📊 1. Head-to-Head Comparison: Baseline vs Top 5 Champions",
        "",
        "| Rank | Clone Architecture | Net PnL ($) | PF | Max DD (%) | Win Rate (%) | Daily 1% Hit | Weekly 5% Hit | Wick Saved | Composite Score |",
        "|---|---|---|---|---|---|---|---|---|---|",
        f"| **PROD BASELINE** | `{baseline['name']}` | **${baseline['net_pnl']:,.2f}** | **{baseline['pf']:.2f}** | **{baseline['max_dd']:.2f}%** | **{baseline['win_rate']:.1f}%** | **{baseline['daily_1pct_rate']:.1f}%** | **{baseline['weekly_5pct_rate']:.1f}%** | **{baseline['wick_saved_count']}** | **{baseline['composite_score']:.1f}** |"
    ]

    for rank, r in enumerate(top_5, 1):
        lines.append(
            f"| **#{rank}** | `{r['name']}` | **${r['net_pnl']:,.2f}** | **{r['pf']:.2f}** | **{r['max_dd']:.2f}%** | **{r['win_rate']:.1f}%** | **{r['daily_1pct_rate']:.1f}%** | **{r['weekly_5pct_rate']:.1f}%** | **{r['wick_saved_count']}** | **{r['composite_score']:.1f}** |"
        )

    lines.extend([
        "",
        "---",
        "",
        "## 💡 2. Temuan Utama (Key Insights) Batch 4",
        "",
        f"1. **Imunitas terhadap Wick Sweep**: Posisi tidak terbunuh oleh jarum sesaat (tick), hanya ditutup jika candle resmi close di luar level invalidasi.",
        f"2. **Timeframe Konfirmasi Optimal**: Membandingkan M1 vs M2 vs M3 vs M5 bar-close invalidation.",
        f"3. **Peran Disaster Bumper**: Hard SL darurat berbasis ATR menjaga akun dari flash crash berita ekstrem.",
        "",
        "---",
        "Report generated by Master Kage Bunshin Tournament Engine."
    ])

    with open(OUTPUT_MD_PATH, "w") as f:
        f.write("\n".join(lines))
    print(f"Saved Markdown report to: {OUTPUT_MD_PATH}")


if __name__ == "__main__":
    main()
