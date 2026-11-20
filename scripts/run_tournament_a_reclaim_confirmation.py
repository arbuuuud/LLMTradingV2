"""
Tournament A: The Reclaim Confirmation Study (Ubah Paradigma Entry: Pasif Limit vs Reclaim Reversal).
Kage Bunshin Wick-Hunt Defense Study.
Dataset: 300,440 M1 XAUUSD bars (Zero Look-Ahead Bias).

Objectives:
1. Meneliti fenomena "Air Terjun" (True Breakdown) vs "Jarum Asli" (Liquidity Grab & Reclaim).
2. Membandingkan:
   - Baseline Pasif Limit Order (menangkap pisau jatuh di dasar jurang).
   - Reclaim Market Execution (tunggu tembus, mental balik, baru hajar buy/sell).
   - Reclaim Retest Limit (tunggu reclaim, pasang limit order di level swing untuk retest).
3. Menguji multi-TF bar close konfirmasi: M1, M2, M3, M5.
4. Menghitung trade yang diselamatkan dari "Air Terjun" (True Breakdowns yang berhasil dihindari).
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
OUTPUT_JSON_PATH = PROJECT_ROOT / "reports" / "tournament_a_reclaim_confirmation_report.json"
OUTPUT_MD_PATH = PROJECT_ROOT / "reports" / "tournament_a_reclaim_confirmation_report.md"


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
    Simulates a single Reclaim Confirmation Clone across 300,440 M1 bars.
    """
    global _SHARED
    c_name = clone_cfg["name"]
    is_baseline = clone_cfg.get("is_baseline", False)
    
    # Reclaim Parameters
    exec_mode = clone_cfg.get("exec_mode", "BASELINE_PASSIVE") # BASELINE_PASSIVE, RECLAIM_MARKET, RECLAIM_RETEST_LIMIT
    reclaim_tf = clone_cfg.get("reclaim_tf", 1) # M1, M2, M3, M5
    min_sweep_pts = clone_cfg.get("min_sweep_pts", 0.25) # Minimum wick penetration beyond swing
    max_sweep_mult = clone_cfg.get("max_sweep_mult", 0.50) # Max sweep depth (mult of span)
    sl_buffer = clone_cfg.get("sl_buffer", 0.25)
    tp_style = clone_cfg.get("tp_style", "EQ") # EQ (50%), RUNNER (opposite swing), 2R, 3R
    retest_ttl_bars = clone_cfg.get("retest_ttl_bars", 5)

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
    pending_retest_limits = []

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

    air_terjun_avoided_count = 0
    reclaim_triggered_count = 0
    missed_retest_count = 0

    # State tracking for sweeping swings
    bull_sweep_active = False
    bull_sweep_lowest = 999999.0
    bull_sweep_start_idx = -1
    bull_sweep_span = 0.0
    bull_sweep_sw_low = 0.0
    bull_sweep_sw_high = 0.0

    bear_sweep_active = False
    bear_sweep_highest = -999999.0
    bear_sweep_start_idx = -1
    bear_sweep_span = 0.0
    bear_sweep_sw_high = 0.0
    bear_sweep_sw_low = 0.0

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

        # 2. Process Pending Retest Limits
        rem_pending = []
        for p_ord in pending_retest_limits:
            if p_ord["expire_idx"] < i:
                missed_retest_count += 1
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
        pending_retest_limits = rem_pending

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
        b1 = d1_bias[i]
        b2 = h4_bias[i]
        both_bear = (b1 in ("STRONG_BEARISH", "WEAK_BEARISH")) and (b2 in ("STRONG_BEARISH", "WEAK_BEARISH"))
        both_bull = (b1 in ("STRONG_BULLISH", "WEAK_BULLISH")) and (b2 in ("STRONG_BULLISH", "WEAK_BULLISH"))
        daily_pnl_pct = ((balance - current_day_start_equity) / max(current_day_start_equity, 100.0)) * 100.0

        # =========================================================================
        # PARADIGMA 1: BASELINE PASSIVE LIMIT ORDER (Menangkap Pisau di Bawah Jurang)
        # =========================================================================
        if is_baseline or exec_mode == "BASELINE_PASSIVE":
            if len(open_trades) == 0 and (t_sec - last_order_time_sec >= 60.0):
                is_disc = in_disc_m1[i]
                is_prem = in_prem_m1[i]
                mid = c

                trigger_buy = False
                trigger_sell = False
                is_counter = False
                trade_risk_mult = 1.0
                tp_mode = "EQ"

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

                if trigger_buy:
                    baseline_sl_buffer = max(0.50, span * 0.0375)
                    sl = round(sw_low - 2.50 - baseline_sl_buffer, 2)
                    tp = round(sw_low + (span * 0.382), 2) if (is_counter and tp_mode == "SHALLOW") else round(eq, 2)
                    trade_risk = base_risk * (trade_risk_mult if is_counter else 1.0)

                    levels = [
                        round(min(mid - 0.25, sw_low + span * 0.25), 2),
                        round(min(mid - 0.50, sw_low + span * 0.125), 2),
                        round(min(mid - 0.75, sw_low), 2)
                    ]
                    weights = [0.25, 0.35, 0.40]
                    for lay_idx, limit_p in enumerate(levels):
                        if l <= limit_p:
                            open_trades.append({
                                "dir": "BUY",
                                "in": limit_p,
                                "sl": sl,
                                "tp": tp,
                                "risk": trade_risk * weights[lay_idx],
                                "is_counter": is_counter
                            })
                    last_order_time_sec = t_sec

                elif trigger_sell:
                    baseline_sl_buffer = max(0.50, span * 0.0375)
                    sl = round(sw_high + 2.50 + baseline_sl_buffer, 2)
                    tp = round(sw_low + (span * 0.618), 2) if (is_counter and tp_mode == "SHALLOW") else round(eq, 2)
                    trade_risk = base_risk * (trade_risk_mult if is_counter else 1.0)

                    levels = [
                        round(max(mid + 0.25, sw_low + span * 0.75), 2),
                        round(max(mid + 0.50, sw_low + span * 0.875), 2),
                        round(max(mid + 0.75, sw_high), 2)
                    ]
                    weights = [0.25, 0.35, 0.40]
                    for lay_idx, limit_p in enumerate(levels):
                        if h >= limit_p:
                            open_trades.append({
                                "dir": "SELL",
                                "in": limit_p,
                                "sl": sl,
                                "tp": tp,
                                "risk": trade_risk * weights[lay_idx],
                                "is_counter": is_counter
                            })
                    last_order_time_sec = t_sec

            continue

        # =========================================================================
        # PARADIGMA 2: RECLAIM CONFIRMATION (Tunggu Sapuan Selesai & Mental Balik)
        # =========================================================================
        is_tf_close = ((i + 1) % reclaim_tf == 0)

        # Track Bullish Sweep State (Harga menusuk di bawah Swing Low)
        if l < sw_low:
            if not bull_sweep_active:
                bull_sweep_active = True
                bull_sweep_lowest = l
                bull_sweep_start_idx = i
                bull_sweep_span = span
                bull_sweep_sw_low = sw_low
                bull_sweep_sw_high = sw_high
            else:
                if l < bull_sweep_lowest:
                    bull_sweep_lowest = l

        # Detect Bullish Reclaim (Candle close M1/M2/M3/M5 TUTUP KEMBALI DI ATAS SWING LOW)
        if bull_sweep_active and is_tf_close:
            sweep_depth = bull_sweep_sw_low - bull_sweep_lowest
            max_allowed_sweep = max_sweep_mult * bull_sweep_span

            # Did price actually close above the swing low?
            if c >= bull_sweep_sw_low:
                # RECLAIM SUCCEEDED!
                if sweep_depth >= min_sweep_pts and sweep_depth <= max_allowed_sweep:
                    # Valid Liquidity Sweep Reclaim!
                    reclaim_triggered_count += 1
                    
                    # Cek HTF and Counter-trend rules
                    is_counter = both_bear
                    allow_trade = True
                    trade_risk_mult = 1.0
                    if is_counter:
                        if daily_pnl_pct >= 1.0 or daily_pnl_pct <= -0.5:
                            allow_trade = False
                        else:
                            trade_risk_mult = 0.50

                    if allow_trade and len(open_trades) == 0 and (t_sec >= buy_cooldown_until):
                        sl_level = round(bull_sweep_lowest - sl_buffer, 2)
                        
                        # TP Style
                        if tp_style == "EQ":
                            tp_level = round((bull_sweep_sw_high + bull_sweep_sw_low) / 2.0, 2)
                        elif tp_style == "RUNNER":
                            tp_level = round(bull_sweep_sw_high, 2)
                        elif tp_style == "2R":
                            tp_level = round(c + 2.0 * abs(c - sl_level), 2)
                        elif tp_style == "3R":
                            tp_level = round(c + 3.0 * abs(c - sl_level), 2)
                        else:
                            tp_level = round((bull_sweep_sw_high + bull_sweep_sw_low) / 2.0, 2)

                        trade_risk = base_risk * trade_risk_mult

                        if exec_mode == "RECLAIM_MARKET":
                            # Instant Market Buy at Candle Close
                            open_trades.append({
                                "dir": "BUY",
                                "in": c,
                                "sl": sl_level,
                                "tp": tp_level,
                                "risk": trade_risk,
                                "is_counter": is_counter
                            })
                            last_order_time_sec = t_sec

                        elif exec_mode == "RECLAIM_RETEST_LIMIT":
                            # Wait for pullback to swing low level
                            pending_retest_limits.append({
                                "dir": "BUY",
                                "limit_price": bull_sweep_sw_low,
                                "sl": sl_level,
                                "tp": tp_level,
                                "risk": trade_risk,
                                "is_counter": is_counter,
                                "expire_idx": i + retest_ttl_bars
                            })

                bull_sweep_active = False # Reset sweep tracker

            elif sweep_depth > max_allowed_sweep:
                # "AIR TERJUN" DETECTED!
                # Price plunged too deep without reclaiming!
                # Passive limit orders would have died here!
                air_terjun_avoided_count += 1
                bull_sweep_active = False

            elif (i - bull_sweep_start_idx) > 30:
                # Timeout, no reclaim after 30 bars
                air_terjun_avoided_count += 1
                bull_sweep_active = False

        # Track Bearish Sweep State (Harga menusuk di atas Swing High)
        if h > sw_high:
            if not bear_sweep_active:
                bear_sweep_active = True
                bear_sweep_highest = h
                bear_sweep_start_idx = i
                bear_sweep_span = span
                bear_sweep_sw_high = sw_high
                bear_sweep_sw_low = sw_low
            else:
                if h > bear_sweep_highest:
                    bear_sweep_highest = h

        # Detect Bearish Reclaim (Candle close TUTUP KEMBALI DI BAWAH SWING HIGH)
        if bear_sweep_active and is_tf_close:
            sweep_depth = bear_sweep_highest - bear_sweep_sw_high
            max_allowed_sweep = max_sweep_mult * bear_sweep_span

            if c <= bear_sweep_sw_high:
                if sweep_depth >= min_sweep_pts and sweep_depth <= max_allowed_sweep:
                    reclaim_triggered_count += 1
                    is_counter = both_bull
                    allow_trade = True
                    trade_risk_mult = 1.0
                    if is_counter:
                        if daily_pnl_pct >= 1.0 or daily_pnl_pct <= -0.5:
                            allow_trade = False
                        else:
                            trade_risk_mult = 0.50

                    if allow_trade and len(open_trades) == 0 and (t_sec >= sell_cooldown_until):
                        sl_level = round(bear_sweep_highest + sl_buffer, 2)
                        
                        if tp_style == "EQ":
                            tp_level = round((bear_sweep_sw_high + bear_sweep_sw_low) / 2.0, 2)
                        elif tp_style == "RUNNER":
                            tp_level = round(bear_sweep_sw_low, 2)
                        elif tp_style == "2R":
                            tp_level = round(c - 2.0 * abs(sl_level - c), 2)
                        elif tp_style == "3R":
                            tp_level = round(c - 3.0 * abs(sl_level - c), 2)
                        else:
                            tp_level = round((bear_sweep_sw_high + bear_sweep_sw_low) / 2.0, 2)

                        trade_risk = base_risk * trade_risk_mult

                        if exec_mode == "RECLAIM_MARKET":
                            open_trades.append({
                                "dir": "SELL",
                                "in": c,
                                "sl": sl_level,
                                "tp": tp_level,
                                "risk": trade_risk,
                                "is_counter": is_counter
                            })
                            last_order_time_sec = t_sec

                        elif exec_mode == "RECLAIM_RETEST_LIMIT":
                            pending_retest_limits.append({
                                "dir": "SELL",
                                "limit_price": bear_sweep_sw_high,
                                "sl": sl_level,
                                "tp": tp_level,
                                "risk": trade_risk,
                                "is_counter": is_counter,
                                "expire_idx": i + retest_ttl_bars
                            })

                bear_sweep_active = False

            elif sweep_depth > max_allowed_sweep:
                air_terjun_avoided_count += 1
                bear_sweep_active = False

            elif (i - bear_sweep_start_idx) > 30:
                air_terjun_avoided_count += 1
                bear_sweep_active = False

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
        "exec_mode": exec_mode,
        "reclaim_tf": reclaim_tf,
        "min_sweep_pts": min_sweep_pts,
        "max_sweep_mult": max_sweep_mult,
        "sl_buffer": sl_buffer,
        "tp_style": tp_style,
        "net_pnl": net_pnl,
        "pf": pf,
        "max_dd": round(max_dd, 2),
        "win_rate": wr,
        "total_trades": len(closed_trades),
        "daily_1pct_rate": day_1pct_rate,
        "weekly_5pct_rate": week_5pct_rate,
        "air_terjun_avoided": air_terjun_avoided_count,
        "reclaim_triggered": reclaim_triggered_count,
        "missed_retest": missed_retest_count
    }


def main():
    print("=" * 85)
    print("🥋 KAGE BUNSHIN TOURNAMENT A: THE RECLAIM CONFIRMATION STUDY")
    print("Dataset: 300,440 M1 XAUUSD bars | Passive Limit vs Reclaim Reversal")
    print("=" * 85)

    start_t0 = time.time()
    print("[1/3] Loading 300,440 M1 Parquet Data...")
    df = pl.read_parquet(PARQUET_PATH)
    n_bars = len(df)
    print(f"Loaded {n_bars:,} bars.")

    print("[2/3] Precomputing Zero-Lookahead Multi-TF Features, Biases & ATR...")
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

    print("[3/3] Generating Clone Matrix for Tournament A...")
    clones = []
    
    # Baseline: Current Production Passive Limit
    clones.append({
        "name": "CLONE_000_BASELINE_PASSIVE_LIMIT",
        "is_baseline": True,
        "exec_mode": "BASELINE_PASSIVE",
        "reclaim_tf": 1,
        "min_sweep_pts": 0.0,
        "max_sweep_mult": 0.0,
        "sl_buffer": 0.50,
        "tp_style": "EQ"
    })

    # Reclaim Variations
    exec_modes = ["RECLAIM_MARKET", "RECLAIM_RETEST_LIMIT"]
    tfs = [1, 2, 3, 5]
    min_sweeps = [0.20, 0.50]
    max_mults = [0.35, 0.50]
    buffers = [0.25, 0.50]
    tp_styles = ["EQ", "RUNNER", "2R"]

    c_idx = 1
    for em in exec_modes:
        for tf_m in tfs:
            for ms in min_sweeps:
                for mm in max_mults:
                    for b in buffers:
                        for tp_s in tp_styles:
                            c_name = f"CLONE_{c_idx:03d}_{em}_M{tf_m}_SW{ms:.2f}_MX{mm:.2f}_B{b:.2f}_{tp_s}".replace(".", "p")
                            clones.append({
                                "name": c_name,
                                "is_baseline": False,
                                "exec_mode": em,
                                "reclaim_tf": tf_m,
                                "min_sweep_pts": ms,
                                "max_sweep_mult": mm,
                                "sl_buffer": b,
                                "tp_style": tp_s,
                                "retest_ttl_bars": 5
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
    baseline_res = next((r for r in results if r["name"] == "CLONE_000_BASELINE_PASSIVE_LIMIT"), results[-1])

    print("\n" + "=" * 125)
    print(f"{'Rank':4} | {'Clone Name':48} | {'Net PnL':10} | {'PF':5} | {'MaxDD':6} | {'WR%':5} | {'Day1%':6} | {'Wk5%':6} | {'AirTerjunSaved':14} | {'Score':6}")
    print("=" * 125)
    print(f"{'BASE':4} | {baseline_res['name']:48} | ${baseline_res['net_pnl']:9.2f} | {baseline_res['pf']:5.2f} | {baseline_res['max_dd']:5.2f}% | {baseline_res['win_rate']:4.1f}% | {baseline_res['daily_1pct_rate']:5.1f}% | {baseline_res['weekly_5pct_rate']:5.1f}% | {baseline_res['air_terjun_avoided']:14d} | {baseline_res['composite_score']:6.1f}")
    print("-" * 125)

    for rank, r in enumerate(results[:15], 1):
        print(f"{rank:4} | {r['name']:48} | ${r['net_pnl']:9.2f} | {r['pf']:5.2f} | {r['max_dd']:5.2f}% | {r['win_rate']:4.1f}% | {r['daily_1pct_rate']:5.1f}% | {r['weekly_5pct_rate']:5.1f}% | {r['air_terjun_avoided']:14d} | {r['composite_score']:6.1f}")
    print("=" * 125)

    out_payload = {
        "tournament": "TOURNAMENT_A_RECLAIM_CONFIRMATION",
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
        "# 🥋 Kage Bunshin Tournament A: The Reclaim Confirmation Report",
        "## Ubah Paradigma: Pasif Limit Order vs Reclaim Reversal Confirmation",
        f"- **Dataset**: 300,440 M1 XAUUSD Bars (Zero Look-Ahead Bias)",
        f"- **Total Clones Evaluated**: {payload['total_clones']} clones",
        f"- **Total Execution Time**: {payload['execution_time_sec']:.2f} seconds",
        "",
        "---",
        "",
        "## 📊 1. Head-to-Head: Baseline Pasif Limit vs Top 5 Reclaim Champions",
        "",
        "| Rank | Clone Architecture | Net PnL ($) | PF | Max DD (%) | Win Rate (%) | Daily 1% Hit | Weekly 5% Hit | Air Terjun Avoided | Composite Score |",
        "|---|---|---|---|---|---|---|---|---|---|",
        f"| **PROD BASELINE** | `{baseline['name']}` | **${baseline['net_pnl']:,.2f}** | **{baseline['pf']:.2f}** | **{baseline['max_dd']:.2f}%** | **{baseline['win_rate']:.1f}%** | **{baseline['daily_1pct_rate']:.1f}%** | **{baseline['weekly_5pct_rate']:.1f}%** | **{baseline['air_terjun_avoided']}** | **{baseline['composite_score']:.1f}** |"
    ]

    for rank, r in enumerate(top_5, 1):
        lines.append(
            f"| **#{rank}** | `{r['name']}` | **${r['net_pnl']:,.2f}** | **{r['pf']:.2f}** | **{r['max_dd']:.2f}%** | **{r['win_rate']:.1f}%** | **{r['daily_1pct_rate']:.1f}%** | **{r['weekly_5pct_rate']:.1f}%** | **{r['air_terjun_avoided']}** | **{r['composite_score']:.1f}** |"
        )

    lines.extend([
        "",
        "---",
        "",
        "## 💡 2. Temuan Anatomi Eksperimen",
        "",
        "1. **Penyelamatan Air Terjun**: Berapa ribu tusukan breakdown murni yang berhasil dihindari berkat tidak memasang limit order pasif di bawah jurang.",
        "2. **Market Instant vs Retest Limit**: Apakah menunggu retest membuat banyak trade terlewat, ataukah eksekusi market instan saat bar-close reclaim lebih efektif.",
        "3. **Timeframe Reclaim Paling Presisi**: M1 vs M2 vs M3 vs M5.",
        "",
        "---",
        "Report generated by Master Kage Bunshin Tournament Engine."
    ])

    with open(OUTPUT_MD_PATH, "w") as f:
        f.write("\n".join(lines))
    print(f"Saved Markdown report to: {OUTPUT_MD_PATH}")


if __name__ == "__main__":
    main()
