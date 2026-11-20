"""
Mega Kage Bunshin Tournament Common Core Module.
High-Performance Vectorized Precomputation & Multiprocess Engine.
Zero Look-Ahead Bias on 300,440 M1 XAUUSD bars.
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
                .otherwise(pl.lit("WEAK_BEARISH"))
                .alias("bias")
            ])
            .with_columns([
                (pl.col("timestamp") + duration).alias("available_at")
            ])
        )
        bias_dfs[code] = df_htf.select(["available_at", "bias"])
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

    is_bearish = closes < opens
    is_bullish = closes > opens

    recent_ob_bull_low = 0.0
    recent_ob_bull_idx = -999999
    recent_ob_bear_high = 0.0
    recent_ob_bear_idx = -999999

    for i in range(2, n):
        if is_bearish[i-1] and is_bullish[i] and (closes[i] > highs[i-1]):
            recent_ob_bull_low = lows[i-1]
            recent_ob_bull_idx = i

        if is_bullish[i-1] and is_bearish[i] and (closes[i] < lows[i-1]):
            recent_ob_bear_high = highs[i-1]
            recent_ob_bear_idx = i

        if (i - recent_ob_bull_idx) <= 120 and recent_ob_bull_low > 0.0:
            if lows[i] < recent_ob_bull_low:
                recent_ob_bull_low = 0.0
            else:
                poi_bull_bottom_ob[i] = recent_ob_bull_low

        if (i - recent_ob_bear_idx) <= 120 and recent_ob_bear_high > 0.0:
            if highs[i] > recent_ob_bear_high:
                recent_ob_bear_high = 0.0
            else:
                poi_bear_top_ob[i] = recent_ob_bear_high

    return poi_bull_bottom_ob, poi_bear_top_ob


def precompute_reversal_patterns(opens, highs, lows, closes):
    n = len(closes)
    rng3 = np.maximum(highs[2:] - lows[2:], 0.01)
    body3_bear = opens[2:] - closes[2:]
    body3_bull = closes[2:] - opens[2:]

    ev_star = (
        (closes[:-2] > opens[:-2]) &
        (np.abs(closes[1:-1] - opens[1:-1]) <= (rng3 * 0.35)) &
        (closes[2:] < (opens[:-2] + closes[:-2]) / 2.0)
    )
    bear_maru = (body3_bear > 0) & ((body3_bear / rng3) >= 0.70) & (closes[2:] < lows[1:-1])

    morn_star = (
        (closes[:-2] < opens[:-2]) &
        (np.abs(closes[1:-1] - opens[1:-1]) <= (rng3 * 0.35)) &
        (closes[2:] > (opens[:-2] + closes[:-2]) / 2.0)
    )
    bull_maru = (body3_bull > 0) & ((body3_bull / rng3) >= 0.70) & (closes[2:] > highs[1:-1])

    rev_against_buy = np.zeros(n, dtype=bool)
    rev_against_sell = np.zeros(n, dtype=bool)
    rev_against_buy[2:] = ev_star | bear_maru
    rev_against_sell[2:] = morn_star | bull_maru

    return rev_against_buy, rev_against_sell


def load_market_data():
    """Loads M1 parquet, computes HTF biases, SMC features, and returns clean dictionary."""
    df_m1 = pl.read_parquet(PARQUET_PATH).sort("timestamp")
    htf_biases = precompute_htf_biases(df_m1)

    htf_aligned = {}
    for code in ["D1", "H4", "H1"]:
        b_df = htf_biases[code].rename({"bias": f"{code}_bias"})
        joined = df_m1.select(["timestamp"]).join_asof(
            b_df,
            left_on="timestamp",
            right_on="available_at",
            strategy="backward"
        )
        htf_aligned[code] = joined[f"{code}_bias"].fill_null("NEUTRAL").to_numpy()

    m1_f = precompute_tf_features(df_m1, 1)
    m2_f = precompute_tf_features(df_m1, 2)
    m3_f = precompute_tf_features(df_m1, 3)
    m5_f = precompute_tf_features(df_m1, 5)
    m15_f = precompute_tf_features(df_m1, 15)

    micro_disc = m1_f["in_discount"] | m2_f["in_discount"] | m3_f["in_discount"]
    micro_prem = m1_f["in_premium"] | m2_f["in_premium"] | m3_f["in_premium"]
    inter_disc = m5_f["in_discount"] | m15_f["in_discount"]
    inter_prem = m5_f["in_premium"] | m15_f["in_premium"]
    bos_bull_inter = m15_f["bos_bull"]
    bos_bear_inter = m15_f["bos_bear"]

    highs = df_m1["high"].to_numpy()
    lows = df_m1["low"].to_numpy()
    opens = df_m1["open"].to_numpy()
    closes = df_m1["close"].to_numpy()

    atr14 = precompute_atr(highs, lows, closes, 14)
    atr100 = precompute_atr(highs, lows, closes, 100)
    poi_bull_bot, poi_bear_top = precompute_poi_arrays(highs, lows, opens, closes, m1_f["sw_high"], m1_f["sw_low"])
    rev_against_buy, rev_against_sell = precompute_reversal_patterns(opens, highs, lows, closes)

    timestamps_sec = (df_m1["timestamp"].dt.epoch("s").to_numpy()).astype(np.float64)
    hours = df_m1["timestamp"].dt.hour().to_numpy().astype(np.int32)
    minutes = df_m1["timestamp"].dt.minute().to_numpy().astype(np.int32)
    days = df_m1["timestamp"].dt.strftime("%Y-%m-%d").to_list()
    iso_weeks = df_m1["timestamp"].dt.strftime("%G-W%V").to_list()

    return {
        "highs": highs,
        "lows": lows,
        "opens": opens,
        "closes": closes,
        "timestamps_sec": timestamps_sec,
        "hours": hours,
        "minutes": minutes,
        "days": days,
        "iso_weeks": iso_weeks,
        "d1_bias": htf_aligned["D1"],
        "h4_bias": htf_aligned["H4"],
        "m1_f": m1_f,
        "m5_f": m5_f,
        "micro_disc": micro_disc,
        "micro_prem": micro_prem,
        "inter_disc": inter_disc,
        "inter_prem": inter_prem,
        "bos_bull_inter": bos_bull_inter,
        "bos_bear_inter": bos_bear_inter,
        "atr14": atr14,
        "atr100": atr100,
        "poi_bull_bot": poi_bull_bot,
        "poi_bear_top": poi_bear_top,
        "rev_against_buy": rev_against_buy,
        "rev_against_sell": rev_against_sell,
    }


def simulate_partial_clone(clone_cfg: dict, data: dict) -> dict:
    """
    Simulates a partial close & BEP migration configuration across 300,440 M1 bars.
    """
    mode_name = clone_cfg["name"]
    trigger_type = clone_cfg.get("trigger_type", "FIBO_50") # FIBO_38, FIBO_50, FIBO_62, FIBO_79, R_0p5, R_0p75, R_1p0, R_1p5
    harvest_cut = clone_cfg.get("harvest_cut", 0.50)        # 0.20, 0.25, 0.33, 0.50, 0.67, 0.75, 1.0
    layer_mode = clone_cfg.get("layer_mode", "ALL_LAYERS")  # ALL_LAYERS, DEEP_ONLY, SHALLOW_ONLY, PYRAMIDAL, L4_ONLY
    bep_buffer = clone_cfg.get("bep_buffer", 0.00)          # 0.00, 0.15, 0.25, 0.40, 0.60, 0.85
    profit_lock_r = clone_cfg.get("profit_lock_r", 0.0)     # 0.0 (BEP+ only), 0.25, 0.50
    runner_target = clone_cfg.get("runner_target", "SWING_100") # SWING_100, FIBO_127, FIBO_161, FIBO_200, UNLIMITED, EQ
    daily_gating = clone_cfg.get("daily_gating", "UNGATED") # UNGATED, HARD_1PCT_HALT, DYN_ACCEL, DEFENSIVE_HALT
    layer_weights = clone_cfg.get("layer_weights", [0.15, 0.25, 0.30, 0.30])
    trailing_style = clone_cfg.get("trailing_style", "STATIC_BEP") # STATIC_BEP, STEPPED_R, M1_SWING
    reversal_exit = clone_cfg.get("reversal_exit", False)
    spread = clone_cfg.get("spread", 0.15)
    slippage = clone_cfg.get("slippage", 0.05)
    regime_aware = clone_cfg.get("regime_aware", True)

    highs = data["highs"]
    lows = data["lows"]
    opens = data["opens"]
    closes = data["closes"]
    timestamps_sec = data["timestamps_sec"]
    hours = data["hours"]
    minutes = data["minutes"]
    days = data["days"]
    iso_weeks = data["iso_weeks"]
    d1_bias = data["d1_bias"]
    h4_bias = data["h4_bias"]
    m1_f = data["m1_f"]
    m5_f = data["m5_f"]
    micro_disc = data["micro_disc"]
    micro_prem = data["micro_prem"]
    inter_disc = data["inter_disc"]
    inter_prem = data["inter_prem"]
    bos_bull_inter = data["bos_bull_inter"]
    bos_bear_inter = data["bos_bear_inter"]
    atr14 = data["atr14"]
    atr100 = data["atr100"]
    poi_bull_bot = data["poi_bull_bot"]
    poi_bear_top = data["poi_bear_top"]
    rev_against_buy = data["rev_against_buy"]
    rev_against_sell = data["rev_against_sell"]

    sw_h_m1 = m1_f["sw_high"]
    sw_l_m1 = m1_f["sw_low"]
    span_m1 = m1_f["span"]
    in_disc_m1 = m1_f["in_discount"]
    in_prem_m1 = m1_f["in_premium"]
    in_disc_m5 = m5_f["in_discount"]
    in_prem_m5 = m5_f["in_premium"]

    balance = 10000.0
    equity_peak = balance
    max_dd = 0.0

    current_session = ""
    session_start_balance = balance
    session_floor_pnl = -50.0
    session_halted = False
    prior_session_profit = 0.0

    current_day_str = ""
    current_day_start_equity = balance
    daily_stats = defaultdict(lambda: {"start": None, "end": None, "trades": 0})
    weekly_stats = defaultdict(lambda: {"start": None, "end": None, "trades": 0})

    buy_cooldown_until = 0.0
    sell_cooldown_until = 0.0
    last_order_time_sec = 0.0

    open_trades = []
    closed_trades = []

    wick_saved_count = 0
    freight_train_avoided_count = 0
    stand_aside_count = 0
    partial_close_count = 0
    bep_saved_count = 0
    runner_wins_count = 0
    sasuke_force_tp_count = 0

    base_risk = 50.0
    n_bars = len(closes)

    for i in range(n_bars):
        h = highs[i]
        l = lows[i]
        o = opens[i]
        c = closes[i]
        t_sec = timestamps_sec[i]
        hr = hours[i]
        mn = minutes[i]
        bar_range = h - l
        cur_atr = atr14[i]
        base_atr_val = atr100[i]

        day_str = days[i]
        week_str = iso_weeks[i]

        if day_str != current_day_str:
            current_day_str = day_str
            current_day_start_equity = balance
            daily_stats[day_str]["start"] = balance

        if weekly_stats[week_str]["start"] is None:
            weekly_stats[week_str]["start"] = balance

        day_realized_pnl = balance - current_day_start_equity
        day_pnl_pct = (day_realized_pnl / current_day_start_equity) * 100.0

        if daily_gating == "HARD_1PCT_HALT" and day_pnl_pct >= 1.0:
            daily_stats[day_str]["end"] = balance
            weekly_stats[week_str]["end"] = balance
            continue
        elif daily_gating == "DEFENSIVE_HALT" and day_pnl_pct <= -0.5:
            daily_stats[day_str]["end"] = balance
            weekly_stats[week_str]["end"] = balance
            continue

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
        setups_hitting_partial = set()

        for tr in open_trades:
            sl_dist = max(0.50, abs(tr["in"] - tr["initial_sl"]))
            is_deep = (tr["layer_idx"] in (2, 3))
            is_shallow = (tr["layer_idx"] in (0, 1))

            # Check eligibility for partial close
            eligible = False
            if layer_mode == "ALL_LAYERS": eligible = True
            elif layer_mode == "DEEP_ONLY": eligible = is_deep
            elif layer_mode == "SHALLOW_ONLY": eligible = is_shallow
            elif layer_mode == "PYRAMIDAL": eligible = (tr["layer_idx"] > 0)
            elif layer_mode == "L4_ONLY": eligible = (tr["layer_idx"] == 3)

            # A. Partial Harvest Trigger
            if not tr["partial_taken"] and eligible and harvest_cut < 1.0:
                hit_trigger = False
                trig_p = tr["partial_trigger_price"]
                if tr["dir"] == "BUY" and h >= trig_p:
                    hit_trigger = True
                elif tr["dir"] == "SELL" and (l + spread) <= trig_p:
                    hit_trigger = True

                if hit_trigger:
                    cut = harvest_cut
                    if daily_gating == "DYN_ACCEL" and day_pnl_pct >= 0.50:
                        cut = 1.0

                    gain_pts = abs(trig_p - tr["in"])
                    r_gain = gain_pts / sl_dist
                    pnl_part = (tr["risk"] * cut) * r_gain
                    balance += pnl_part
                    tr["partial_pnl"] += pnl_part
                    tr["partial_taken"] = True
                    tr["active_fraction"] -= cut
                    partial_close_count += 1
                    setups_hitting_partial.add(tr["setup_id"])

                    # SL migration
                    if tr["dir"] == "BUY":
                        new_sl = tr["in"] + bep_buffer
                        if profit_lock_r > 0.0: new_sl = max(new_sl, tr["in"] + sl_dist * profit_lock_r)
                        tr["sl"] = max(tr["sl"], round(new_sl, 2))
                    else:
                        new_sl = tr["in"] - bep_buffer
                        if profit_lock_r > 0.0: new_sl = min(new_sl, tr["in"] - sl_dist * profit_lock_r)
                        tr["sl"] = min(tr["sl"], round(new_sl, 2))

                    if tr["active_fraction"] <= 0.001:
                        tr["pnl"] = tr["partial_pnl"]
                        tr["r_multiple"] = r_gain
                        tr["exit_reason"] = "PARTIAL_FULL"
                        closed_trades.append(tr)
                        daily_stats[day_str]["trades"] += 1
                        weekly_stats[week_str]["trades"] += 1
                        continue

            # B. Trailing
            if tr["partial_taken"] and trailing_style != "STATIC_BEP":
                if trailing_style == "STEPPED_R":
                    if tr["dir"] == "BUY":
                        r_run = (h - tr["in"]) / sl_dist
                        if r_run >= 2.0: tr["sl"] = max(tr["sl"], round(tr["in"] + sl_dist * 1.0, 2))
                        elif r_run >= 1.5: tr["sl"] = max(tr["sl"], round(tr["in"] + sl_dist * 0.5, 2))
                    else:
                        r_run = (tr["in"] - l) / sl_dist
                        if r_run >= 2.0: tr["sl"] = min(tr["sl"], round(tr["in"] - sl_dist * 1.0, 2))
                        elif r_run >= 1.5: tr["sl"] = min(tr["sl"], round(tr["in"] - sl_dist * 0.5, 2))
                elif trailing_style == "M1_SWING":
                    if tr["dir"] == "BUY":
                        sw_p = sw_l_m1[i] - 0.25
                        if sw_p > tr["sl"]: tr["sl"] = round(sw_p, 2)
                    else:
                        sw_p = sw_h_m1[i] + 0.25
                        if sw_p < tr["sl"]: tr["sl"] = round(sw_p, 2)

            # C. Sasuke Reversal Cognition
            if reversal_exit and (tr["partial_taken"] or is_deep):
                closed_by_rev = False
                if tr["dir"] == "BUY":
                    cur_p = c - tr["in"]
                    cur_r = cur_p / sl_dist
                    if cur_r >= 0.50 and rev_against_buy[i]:
                        pnl = (tr["risk"] * tr["active_fraction"]) * cur_r
                        balance += pnl
                        tr["pnl"] = tr["partial_pnl"] + pnl
                        tr["r_multiple"] = cur_r
                        tr["exit_reason"] = "FORCE_TP_REVERSAL"
                        closed_trades.append(tr)
                        sasuke_force_tp_count += 1
                        daily_stats[day_str]["trades"] += 1
                        weekly_stats[week_str]["trades"] += 1
                        closed_by_rev = True
                else:
                    cur_p = tr["in"] - (c + spread)
                    cur_r = cur_p / sl_dist
                    if cur_r >= 0.50 and rev_against_sell[i]:
                        pnl = (tr["risk"] * tr["active_fraction"]) * cur_r
                        balance += pnl
                        tr["pnl"] = tr["partial_pnl"] + pnl
                        tr["r_multiple"] = cur_r
                        tr["exit_reason"] = "FORCE_TP_REVERSAL"
                        closed_trades.append(tr)
                        sasuke_force_tp_count += 1
                        daily_stats[day_str]["trades"] += 1
                        weekly_stats[week_str]["trades"] += 1
                        closed_by_rev = True
                if closed_by_rev:
                    continue

            # D. Standard TP & SL Checks
            if tr["dir"] == "BUY":
                if h >= (tr["tp"] + slippage):
                    gain_pts = tr["tp"] - tr["in"]
                    r_gain = gain_pts / sl_dist
                    rem_pnl = (tr["risk"] * tr["active_fraction"]) * r_gain
                    balance += rem_pnl
                    tr["pnl"] = tr["partial_pnl"] + rem_pnl
                    tr["r_multiple"] = r_gain
                    tr["exit_reason"] = "TP"
                    closed_trades.append(tr)
                    daily_stats[day_str]["trades"] += 1
                    weekly_stats[week_str]["trades"] += 1
                    if tr.get("baseline_sl_breached", False):
                        wick_saved_count += 1
                    if is_shallow:
                        setups_hitting_partial.add(tr["setup_id"])
                    else:
                        runner_wins_count += 1

                elif l <= (tr["sl"] - slippage):
                    loss_pts = tr["in"] - tr["sl"]
                    is_bep = (loss_pts <= (bep_buffer + 0.05))
                    r_loss = 0.0 if is_bep else -1.0
                    if is_bep and tr["sl"] > tr["in"]:
                        r_loss = (tr["sl"] - tr["in"]) / sl_dist

                    rem_pnl = (tr["risk"] * tr["active_fraction"]) * r_loss
                    balance += rem_pnl
                    tr["pnl"] = tr["partial_pnl"] + rem_pnl
                    tr["r_multiple"] = r_loss
                    tr["exit_reason"] = "BEP" if is_bep else "SL"
                    if is_bep: bep_saved_count += 1
                    closed_trades.append(tr)
                    daily_stats[day_str]["trades"] += 1
                    weekly_stats[week_str]["trades"] += 1
                    if not is_bep:
                        cd_dur = 600 if sess_name == "ASIAN" else (900 if sess_name == "LONDON" else 1500)
                        buy_cooldown_until = t_sec + cd_dur
                else:
                    if l <= (tr["baseline_sl"] - slippage):
                        tr["baseline_sl_breached"] = True
                    rem.append(tr)

            elif tr["dir"] == "SELL":
                if (l + spread) <= (tr["tp"] - slippage):
                    gain_pts = tr["in"] - tr["tp"]
                    r_gain = gain_pts / sl_dist
                    rem_pnl = (tr["risk"] * tr["active_fraction"]) * r_gain
                    balance += rem_pnl
                    tr["pnl"] = tr["partial_pnl"] + rem_pnl
                    tr["r_multiple"] = r_gain
                    tr["exit_reason"] = "TP"
                    closed_trades.append(tr)
                    daily_stats[day_str]["trades"] += 1
                    weekly_stats[week_str]["trades"] += 1
                    if tr.get("baseline_sl_breached", False):
                        wick_saved_count += 1
                    if is_shallow:
                        setups_hitting_partial.add(tr["setup_id"])
                    else:
                        runner_wins_count += 1

                elif (h + spread) >= (tr["sl"] + slippage):
                    loss_pts = tr["sl"] - tr["in"]
                    is_bep = (loss_pts <= (bep_buffer + 0.05))
                    r_loss = 0.0 if is_bep else -1.0
                    if is_bep and tr["sl"] < tr["in"]:
                        r_loss = (tr["in"] - tr["sl"]) / sl_dist

                    rem_pnl = (tr["risk"] * tr["active_fraction"]) * r_loss
                    balance += rem_pnl
                    tr["pnl"] = tr["partial_pnl"] + rem_pnl
                    tr["r_multiple"] = r_loss
                    tr["exit_reason"] = "BEP" if is_bep else "SL"
                    if is_bep: bep_saved_count += 1
                    closed_trades.append(tr)
                    daily_stats[day_str]["trades"] += 1
                    weekly_stats[week_str]["trades"] += 1
                    if not is_bep:
                        cd_dur = 600 if sess_name == "ASIAN" else (900 if sess_name == "LONDON" else 1500)
                        sell_cooldown_until = t_sec + cd_dur
                else:
                    if (h + spread) >= (tr["baseline_sl"] + slippage):
                        tr["baseline_sl_breached"] = True
                    rem.append(tr)

        # Cross-layer Auto-BEP trigger
        if setups_hitting_partial:
            for tr in rem:
                if tr["setup_id"] in setups_hitting_partial and is_deep:
                    sl_dist = max(0.50, abs(tr["in"] - tr["initial_sl"]))
                    if tr["dir"] == "BUY":
                        new_sl = tr["in"] + bep_buffer
                        if profit_lock_r > 0.0: new_sl = max(new_sl, tr["in"] + sl_dist * profit_lock_r)
                        if new_sl > tr["sl"]:
                            tr["sl"] = round(new_sl, 2)
                    else:
                        new_sl = tr["in"] - bep_buffer
                        if profit_lock_r > 0.0: new_sl = min(new_sl, tr["in"] - sl_dist * profit_lock_r)
                        if new_sl < tr["sl"]:
                            tr["sl"] = round(new_sl, 2)

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

        # 2. Setup Scanning & Limit Placement
        if len(open_trades) == 0 and (t_sec - last_order_time_sec >= 60.0):
            sw_high = sw_h_m1[i]
            sw_low = sw_l_m1[i]
            span = span_m1[i]
            if sw_high <= sw_low or span < 1.0:
                continue

            # Reflex Guards
            if bar_range > (1.80 * cur_atr):
                freight_train_avoided_count += 1
                continue
            is_volatile_spike = (cur_atr / base_atr_val) >= 1.30

            b1 = d1_bias[i]
            b2 = h4_bias[i]
            both_bear = (b1 in ("STRONG_BEARISH", "WEAK_BEARISH")) and (b2 in ("STRONG_BEARISH", "WEAK_BEARISH"))
            both_bull = (b1 in ("STRONG_BULLISH", "WEAK_BULLISH")) and (b2 in ("STRONG_BULLISH", "WEAK_BULLISH"))

            trigger_buy = False
            trigger_sell = False
            is_counter = False
            trade_risk_mult = 1.0
            tp_mode = "EQ"

            if in_disc_m1[i] and (t_sec >= buy_cooldown_until):
                if not both_bear:
                    trigger_buy = True
                else:
                    if day_pnl_pct < 1.0 and day_pnl_pct > -0.5:
                        opsi_a = in_disc_m5[i]
                        opsi_b = (micro_disc[i] and inter_disc[i]) or bos_bull_inter[i]
                        if opsi_a or opsi_b:
                            trigger_buy = True
                            is_counter = True
                            trade_risk_mult = 0.50
                            tp_mode = "EQ" if opsi_a else "SHALLOW"

            elif in_prem_m1[i] and (t_sec >= sell_cooldown_until):
                if not both_bull:
                    trigger_sell = True
                else:
                    if day_pnl_pct < 1.0 and day_pnl_pct > -0.5:
                        opsi_a = in_prem_m5[i]
                        opsi_b = (micro_prem[i] and inter_prem[i]) or bos_bear_inter[i]
                        if opsi_a or opsi_b:
                            trigger_sell = True
                            is_counter = True
                            trade_risk_mult = 0.50
                            tp_mode = "EQ" if opsi_a else "SHALLOW"

            if is_volatile_spike and is_counter:
                stand_aside_count += 1
                trigger_buy = False
                trigger_sell = False

            if not trigger_buy and not trigger_sell:
                continue

            eq = (sw_high + sw_low) / 2.0
            equilibrium = eq
            mid = c
            setup_id = f"st_{i}"

            baseline_sl_buffer = max(0.50, span * 0.0375)
            base_buy_sl = round(sw_low - 2.50 - baseline_sl_buffer, 2)
            base_sell_sl = round(sw_high + 2.50 + baseline_sl_buffer, 2)

            p_bot = poi_bull_bot[i]
            poi_valid_buy = (p_bot > 0.0) and (p_bot < sw_low) and ((sw_low - p_bot) <= (0.5 * span))
            sl_buy = round(p_bot - 0.25, 2) if poi_valid_buy else round(sw_low - (span * 0.130) - 0.25, 2)

            p_top = poi_bear_top[i]
            poi_valid_sell = (p_top > 0.0) and (p_top > sw_high) and ((p_top - sw_high) <= (0.5 * span))
            sl_sell = round(p_top + 0.25, 2) if poi_valid_sell else round(sw_high + (span * 0.130) + 0.25, 2)

            if trigger_buy:
                trade_risk = base_risk * (trade_risk_mult if is_counter else 1.0)
                tp_harvester = round(sw_low + (span * 0.382), 2) if (is_counter and tp_mode == "SHALLOW") else round(equilibrium, 2)

                if is_counter and regime_aware:
                    tp_runner = tp_harvester
                else:
                    if runner_target == "EQ": tp_runner = tp_harvester
                    elif runner_target == "SWING_100": tp_runner = round(sw_high, 2)
                    elif runner_target == "FIBO_127": tp_runner = round(sw_high + (span * 0.272), 2)
                    elif runner_target == "FIBO_161": tp_runner = round(sw_high + (span * 0.618), 2)
                    elif runner_target == "FIBO_200": tp_runner = round(sw_high + (span * 1.000), 2)
                    elif runner_target == "UNLIMITED": tp_runner = round(sw_high + (span * 2.000), 2)
                    else: tp_runner = round(sw_high, 2)

                levels = [
                    round(min(mid - 0.25, sw_low + span * 0.25), 2),
                    round(min(mid - 0.50, sw_low + span * 0.125), 2),
                    round(min(mid - 0.75, sw_low), 2),
                    round(min(mid - 1.00, sw_low - (span * 0.272)), 2)
                ]

                # Partial Trigger Calculation
                if trigger_type == "FIBO_38": part_trig = round(sw_low + (span * 0.382), 2)
                elif trigger_type == "FIBO_50": part_trig = round(equilibrium, 2)
                elif trigger_type == "FIBO_62": part_trig = round(sw_low + (span * 0.618), 2)
                elif trigger_type == "FIBO_79": part_trig = round(sw_low + (span * 0.786), 2)
                else: part_trig = None

                for lay_idx, limit_p in enumerate(levels):
                    if l <= limit_p:
                        sl_d = max(0.50, abs(limit_p - sl_buy))
                        if trigger_type.startswith("R_"):
                            r_val = float(trigger_type.split("_")[1].replace("p", "."))
                            lay_part_trig = round(limit_p + (sl_d * r_val), 2)
                        else:
                            lay_part_trig = part_trig

                        assigned_tp = tp_harvester if lay_idx in (0, 1) else tp_runner
                        open_trades.append({
                            "setup_id": setup_id,
                            "layer_idx": lay_idx,
                            "dir": "BUY",
                            "in": limit_p,
                            "sl": sl_buy,
                            "initial_sl": sl_buy,
                            "baseline_sl": base_buy_sl,
                            "tp": assigned_tp,
                            "partial_trigger_price": lay_part_trig,
                            "partial_taken": False,
                            "partial_pnl": 0.0,
                            "active_fraction": 1.0,
                            "risk": trade_risk * layer_weights[lay_idx],
                            "is_counter": is_counter,
                            "baseline_sl_breached": False
                        })
                last_order_time_sec = t_sec

            elif trigger_sell:
                trade_risk = base_risk * (trade_risk_mult if is_counter else 1.0)
                tp_harvester = round(sw_low + (span * 0.618), 2) if (is_counter and tp_mode == "SHALLOW") else round(equilibrium, 2)

                if is_counter and regime_aware:
                    tp_runner = tp_harvester
                else:
                    if runner_target == "EQ": tp_runner = tp_harvester
                    elif runner_target == "SWING_100": tp_runner = round(sw_low, 2)
                    elif runner_target == "FIBO_127": tp_runner = round(sw_low - (span * 0.272), 2)
                    elif runner_target == "FIBO_161": tp_runner = round(sw_low - (span * 0.618), 2)
                    elif runner_target == "FIBO_200": tp_runner = round(sw_low - (span * 1.000), 2)
                    elif runner_target == "UNLIMITED": tp_runner = round(sw_low - (span * 2.000), 2)
                    else: tp_runner = round(sw_low, 2)

                levels = [
                    round(max(mid + 0.25, sw_low + span * 0.75), 2),
                    round(max(mid + 0.50, sw_low + span * 0.875), 2),
                    round(max(mid + 0.75, sw_high), 2),
                    round(max(mid + 1.00, sw_high + (span * 0.272)), 2)
                ]

                if trigger_type == "FIBO_38": part_trig = round(sw_high - (span * 0.382), 2)
                elif trigger_type == "FIBO_50": part_trig = round(equilibrium, 2)
                elif trigger_type == "FIBO_62": part_trig = round(sw_high - (span * 0.618), 2)
                elif trigger_type == "FIBO_79": part_trig = round(sw_high - (span * 0.786), 2)
                else: part_trig = None

                for lay_idx, limit_p in enumerate(levels):
                    if h >= limit_p:
                        sl_d = max(0.50, abs(sl_sell - limit_p))
                        if trigger_type.startswith("R_"):
                            r_val = float(trigger_type.split("_")[1].replace("p", "."))
                            lay_part_trig = round(limit_p - (sl_d * r_val), 2)
                        else:
                            lay_part_trig = part_trig

                        assigned_tp = tp_harvester if lay_idx in (0, 1) else tp_runner
                        open_trades.append({
                            "setup_id": setup_id,
                            "layer_idx": lay_idx,
                            "dir": "SELL",
                            "in": limit_p,
                            "sl": sl_sell,
                            "initial_sl": sl_sell,
                            "baseline_sl": base_sell_sl,
                            "tp": assigned_tp,
                            "partial_trigger_price": lay_part_trig,
                            "partial_taken": False,
                            "partial_pnl": 0.0,
                            "active_fraction": 1.0,
                            "risk": trade_risk * layer_weights[lay_idx],
                            "is_counter": is_counter,
                            "baseline_sl_breached": False
                        })
                last_order_time_sec = t_sec

    # Summary Statistics Calculation
    total_trades = len(closed_trades)
    wins = [t for t in closed_trades if t.get("pnl", 0.0) > 0.01]
    losses = [t for t in closed_trades if t.get("pnl", 0.0) < -0.01]
    be_trades = [t for t in closed_trades if abs(t.get("pnl", 0.0)) <= 0.01]

    win_count = len(wins)
    loss_count = len(losses)
    win_rate = (win_count / total_trades * 100.0) if total_trades > 0 else 0.0

    gross_profit = sum(t["pnl"] for t in wins)
    gross_loss = abs(sum(t["pnl"] for t in losses))
    net_pnl = balance - 10000.0
    profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else 99.9

    daily_results = []
    for d_k, d_v in daily_stats.items():
        if d_v["start"] and d_v["start"] > 0:
            d_pnl = d_v["end"] - d_v["start"]
            d_pct = (d_pnl / d_v["start"]) * 100.0
            daily_results.append(d_pct)

    days_total = len(daily_results)
    days_1pct_hit = sum(1 for p in daily_results if p >= 1.0)
    daily_1pct_rate = (days_1pct_hit / days_total * 100.0) if days_total > 0 else 0.0
    days_breach = sum(1 for p in daily_results if p <= -1.0)
    daily_breach_rate = (days_breach / days_total * 100.0) if days_total > 0 else 0.0

    weekly_results = []
    for w_k, w_v in weekly_stats.items():
        if w_v["start"] and w_v["start"] > 0:
            w_pnl = w_v["end"] - w_v["start"]
            w_pct = (w_pnl / w_v["start"]) * 100.0
            weekly_results.append(w_pct)

    weeks_total = len(weekly_results)
    weeks_5pct_hit = sum(1 for p in weekly_results if p >= 5.0)
    weekly_5pct_rate = (weeks_5pct_hit / weeks_total * 100.0) if weeks_total > 0 else 0.0

    win_r_vals = [t.get("r_multiple", 0) for t in wins]
    loss_r_vals = [abs(t.get("r_multiple", 0)) for t in losses]
    avg_win_r = float(np.mean(win_r_vals)) if win_r_vals else 0.0
    avg_loss_r = float(np.mean(loss_r_vals)) if loss_r_vals else 1.0
    realized_rr = avg_win_r / avg_loss_r if avg_loss_r > 0 else avg_win_r

    quant_score = (
        (weekly_5pct_rate * 2.0) +
        (daily_1pct_rate * 1.5) +
        ((net_pnl / 10000.0) * 10.0) -
        (max_dd * 2.0) -
        (daily_breach_rate * 3.0)
    )

    return {
        "name": mode_name,
        "config": clone_cfg,
        "net_pnl": round(net_pnl, 2),
        "return_pct": round((net_pnl / 10000.0) * 100.0, 2),
        "profit_factor": round(profit_factor, 2),
        "max_drawdown_pct": round(max_dd, 2),
        "win_rate_pct": round(win_rate, 2),
        "total_trades": total_trades,
        "daily_1pct_target_hit_rate": round(daily_1pct_rate, 2),
        "weekly_5pct_target_hit_rate": round(weekly_5pct_rate, 2),
        "daily_loss_breach_rate": round(daily_breach_rate, 2),
        "realized_rr": f"1:{realized_rr:.2f}",
        "realized_rr_val": round(realized_rr, 2),
        "partial_close_count": partial_close_count,
        "bep_saved_count": bep_saved_count,
        "runner_wins_count": runner_wins_count,
        "wick_saved_count": wick_saved_count,
        "freight_train_avoided_count": freight_train_avoided_count,
        "stand_aside_count": stand_aside_count,
        "quant_score": round(quant_score, 2)
    }
