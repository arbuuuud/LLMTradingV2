"""
Validation Experiment: Objective-Aware Adaptive Unlock Strategy.
Compares Head-to-Head:
1. BASELINE_M1 (Status Quo Permissive OR)
2. OBJECTIVE_AWARE_ADAPTIVE_M1 (Daily 1% Hunting Phase, 0.5x Risk, Nested Confluence OR M15/M30 BOS)
3. OBJECTIVE_AWARE_ADAPTIVE_M5 (Intraday execution with Objective Gate)
4. Key sensitivity variations (Lock at 1.0%, Lock at 1.5%, Defensive cut at -0.5%)

Dataset: 300,440 M1 XAUUSD bars (Zero Look-Ahead Bias).
Evaluates strictly: Daily 1% Hit Rate, Weekly 5% Hit Rate, Profit Factor, Max Drawdown, Net PnL.
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

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

PARQUET_PATH = PROJECT_ROOT / "data" / "parquet" / "XAUUSD" / "M1" / "XAUUSD_M1.parquet"
REPORTS_DIR = PROJECT_ROOT / "reports"
OUTPUT_JSON_PATH = REPORTS_DIR / "objective_adaptive_unlock_validation_report.json"
OUTPUT_MD_PATH = REPORTS_DIR / "objective_adaptive_unlock_validation_report.md"


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


def precompute_tf_features(df_m1: pl.DataFrame, tf_minutes: int, tf_name: str) -> dict:
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
        "bos_bear": bos_bear_active
    }


def simulate_adaptive_candidate(
    spec: dict,
    m1_data: dict,
    tf_features: dict,
    htf_biases: dict
) -> dict:
    t_secs = m1_data["t_secs"]
    hours = m1_data["hours"]
    minutes = m1_data["minutes"]
    days = m1_data["days"]
    iso_weeks = m1_data["iso_weeks"]
    highs = m1_data["highs"]
    lows = m1_data["lows"]
    closes = m1_data["closes"]

    n_bars = len(closes)
    exec_tf = spec["exec_tf"]
    exec_step = spec.get("exec_step", 1)

    sw_h_exec = tf_features[exec_tf]["sw_high"]
    sw_l_exec = tf_features[exec_tf]["sw_low"]
    span_exec = tf_features[exec_tf]["span"]
    in_disc_exec = tf_features[exec_tf]["in_discount"]
    in_prem_exec = tf_features[exec_tf]["in_premium"]

    d1_bias = htf_biases["D1"]
    h4_bias = htf_biases["H4"]

    logic_mode = spec["logic_mode"]  # BASELINE, OBJECTIVE_ADAPTIVE
    daily_lock_pct = spec.get("daily_lock_pct", 1.0)
    daily_defensive_cut_pct = spec.get("daily_defensive_cut_pct", -0.5)
    counter_risk_mult = spec.get("counter_risk_mult", 0.5)
    counter_tp_mode = spec.get("counter_tp_mode", "EQ")

    balance = 10000.0
    equity_peak = balance
    max_dd = 0.0

    current_session = ""
    session_start_balance = balance
    prior_session_profit = 0.0
    session_halted = False
    session_floor_pnl = -50.0

    buy_cooldown_until = 0
    sell_cooldown_until = 0
    last_order_time_sec = 0

    open_trades = []
    closed_trades = []
    counter_trades_count = 0
    counter_trades_wins = 0
    counter_trades_pnl = 0.0

    grid_weights = [0.25, 0.35, 0.40]
    base_risk = 50.0
    spread = 0.35
    slippage = 0.05

    # Daily state tracking
    daily_stats = defaultdict(lambda: {"start": None, "end": 10000.0, "trades": 0, "pnl": 0.0})
    weekly_stats = defaultdict(lambda: {"start": None, "end": 10000.0, "trades": 0, "pnl": 0.0})
    
    current_day_str = ""
    current_day_start_equity = balance

    for i in range(25, n_bars, exec_step):
        t_sec = t_secs[i]
        hr = int(hours[i])
        mn = int(minutes[i])
        h = highs[i]
        l = lows[i]
        c = closes[i]
        day_str = days[i]
        week_str = iso_weeks[i]

        # Daily boundary update
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

        # Manage Open Trades
        rem = []
        for tr in open_trades:
            if tr["dir"] == "BUY":
                if h >= (tr["tp"] + slippage):
                    pnl = tr["risk"] * ((tr["tp"] - tr["in"]) / max(tr["in"] - tr["sl"], 0.1))
                    balance += pnl
                    tr["pnl"] = pnl
                    closed_trades.append(tr)
                    if tr["is_counter"]:
                        counter_trades_wins += 1
                        counter_trades_pnl += pnl
                elif l <= (tr["sl"] - slippage):
                    pnl = -tr["risk"]
                    balance += pnl
                    tr["pnl"] = pnl
                    closed_trades.append(tr)
                    if tr["is_counter"]:
                        counter_trades_pnl += pnl
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
                    if tr["is_counter"]:
                        counter_trades_wins += 1
                        counter_trades_pnl += pnl
                elif (h + spread) >= (tr["sl"] + slippage):
                    pnl = -tr["risk"]
                    balance += pnl
                    tr["pnl"] = pnl
                    closed_trades.append(tr)
                    if tr["is_counter"]:
                        counter_trades_pnl += pnl
                    cd_dur = 600 if sess_name == "ASIAN" else (900 if sess_name == "LONDON" else 1500)
                    sell_cooldown_until = t_sec + cd_dur
                else:
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

        # Evaluate Entry
        if len(open_trades) == 0 and (t_sec - last_order_time_sec >= 60.0):
            sw_high = sw_h_exec[i]
            sw_low = sw_l_exec[i]
            span = span_exec[i]
            if sw_high <= sw_low or span < 1.0:
                continue

            eq = (sw_high + sw_low) / 2.0
            mid = c
            is_disc = in_disc_exec[i]
            is_prem = in_prem_exec[i]

            b1 = d1_bias[i]
            b2 = h4_bias[i]
            both_bear = (b1 in ("STRONG_BEARISH", "WEAK_BEARISH")) and (b2 in ("STRONG_BEARISH", "WEAK_BEARISH"))
            both_bull = (b1 in ("STRONG_BULLISH", "WEAK_BULLISH")) and (b2 in ("STRONG_BULLISH", "WEAK_BULLISH"))

            # Calculate current daily progress %
            daily_current_pnl_pct = ((balance - current_day_start_equity) / max(current_day_start_equity, 100.0)) * 100.0

            trigger_buy = False
            trigger_sell = False
            is_counter = False

            if is_disc and (t_sec >= buy_cooldown_until):
                if not both_bear:
                    # Standard trend-aligned / neutral BUY
                    trigger_buy = True
                    is_counter = False
                else:
                    # Counter-trend BUY candidate
                    if logic_mode == "BASELINE":
                        trigger_buy = False
                    elif logic_mode == "OBJECTIVE_ADAPTIVE":
                        if daily_current_pnl_pct >= daily_lock_pct or daily_current_pnl_pct <= daily_defensive_cut_pct:
                            trigger_buy = False
                        else:
                            micro_active = tf_features["M1"]["in_discount"][i] or tf_features["M2"]["in_discount"][i] or tf_features["M3"]["in_discount"][i]
                            inter_active = tf_features["M5"]["in_discount"][i] or tf_features["M15"]["in_discount"][i]
                            has_nested = micro_active and inter_active
                            has_bos = tf_features["M15"]["bos_bull"][i] or tf_features["M30"]["bos_bull"][i]
                            if has_nested or has_bos:
                                trigger_buy = True
                                is_counter = True

                    elif logic_mode == "BOS_ONLY_ADAPTIVE":
                        if daily_current_pnl_pct >= daily_lock_pct or daily_current_pnl_pct <= daily_defensive_cut_pct:
                            trigger_buy = False
                        else:
                            has_bos = tf_features["M15"]["bos_bull"][i] or tf_features["M30"]["bos_bull"][i]
                            if has_bos:
                                trigger_buy = True
                                is_counter = True

                    elif logic_mode == "NESTED_M1_M5_ADAPTIVE":
                        if daily_current_pnl_pct >= daily_lock_pct or daily_current_pnl_pct <= daily_defensive_cut_pct:
                            trigger_buy = False
                        else:
                            has_nested = tf_features["M1"]["in_discount"][i] and tf_features["M5"]["in_discount"][i]
                            if has_nested:
                                trigger_buy = True
                                is_counter = True

            elif is_prem and (t_sec >= sell_cooldown_until):
                if not both_bull:
                    # Standard trend-aligned / neutral SELL
                    trigger_sell = True
                    is_counter = False
                else:
                    # Counter-trend SELL candidate
                    if logic_mode == "BASELINE":
                        trigger_sell = False
                    elif logic_mode == "OBJECTIVE_ADAPTIVE":
                        if daily_current_pnl_pct >= daily_lock_pct or daily_current_pnl_pct <= daily_defensive_cut_pct:
                            trigger_sell = False
                        else:
                            micro_active = tf_features["M1"]["in_premium"][i] or tf_features["M2"]["in_premium"][i] or tf_features["M3"]["in_premium"][i]
                            inter_active = tf_features["M5"]["in_premium"][i] or tf_features["M15"]["in_premium"][i]
                            has_nested = micro_active and inter_active
                            has_bos = tf_features["M15"]["bos_bear"][i] or tf_features["M30"]["bos_bear"][i]
                            if has_nested or has_bos:
                                trigger_sell = True
                                is_counter = True

                    elif logic_mode == "BOS_ONLY_ADAPTIVE":
                        if daily_current_pnl_pct >= daily_lock_pct or daily_current_pnl_pct <= daily_defensive_cut_pct:
                            trigger_sell = False
                        else:
                            has_bos = tf_features["M15"]["bos_bear"][i] or tf_features["M30"]["bos_bear"][i]
                            if has_bos:
                                trigger_sell = True
                                is_counter = True

                    elif logic_mode == "NESTED_M1_M5_ADAPTIVE":
                        if daily_current_pnl_pct >= daily_lock_pct or daily_current_pnl_pct <= daily_defensive_cut_pct:
                            trigger_sell = False
                        else:
                            has_nested = tf_features["M1"]["in_premium"][i] and tf_features["M5"]["in_premium"][i]
                            if has_nested:
                                trigger_sell = True
                                is_counter = True

            sl_buffer = max(0.50, span * 0.0375)
            trade_risk = base_risk * (counter_risk_mult if is_counter else 1.0)

            if trigger_buy:
                sl = round(sw_low - 2.50 - sl_buffer, 2)
                if is_counter and counter_tp_mode == "SHALLOW":
                    tp = round(sw_low + (span * 0.382), 2)
                elif is_counter and counter_tp_mode == "DEEP":
                    tp = round(sw_low + (span * 0.75), 2)
                else:
                    tp = round(eq, 2)

                l1 = round(min(mid - 0.25, sw_low + span * 0.25), 2)
                l2 = round(min(mid - 0.50, sw_low + span * 0.125), 2)
                l3 = round(min(mid - 0.75, sw_low), 2)
                for lay_idx, limit_p in enumerate([l1, l2, l3]):
                    if l <= limit_p:
                        open_trades.append({
                            "dir": "BUY",
                            "in": limit_p,
                            "sl": sl,
                            "tp": tp,
                            "risk": trade_risk * grid_weights[lay_idx],
                            "is_counter": is_counter
                        })
                        if is_counter:
                            counter_trades_count += 1
                last_order_time_sec = t_sec

            elif trigger_sell:
                sl = round(sw_high + 2.50 + sl_buffer, 2)
                if is_counter and counter_tp_mode == "SHALLOW":
                    tp = round(sw_low + (span * 0.618), 2)
                elif is_counter and counter_tp_mode == "DEEP":
                    tp = round(sw_low + (span * 0.25), 2)
                else:
                    tp = round(eq, 2)

                l1 = round(max(mid + 0.25, sw_low + span * 0.75), 2)
                l2 = round(max(mid + 0.50, sw_low + span * 0.875), 2)
                l3 = round(max(mid + 0.75, sw_high), 2)
                for lay_idx, limit_p in enumerate([l1, l2, l3]):
                    if h >= limit_p:
                        open_trades.append({
                            "dir": "SELL",
                            "in": limit_p,
                            "sl": sl,
                            "tp": tp,
                            "risk": trade_risk * grid_weights[lay_idx],
                            "is_counter": is_counter
                        })
                        if is_counter:
                            counter_trades_count += 1
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

    counter_wr = round((counter_trades_wins / counter_trades_count) * 100.0, 1) if counter_trades_count > 0 else 0.0

    return {
        "id": spec["id"],
        "desc": spec["desc"],
        "exec_tf": exec_tf,
        "logic_mode": logic_mode,
        "trades": len(closed_trades),
        "win_rate": wr,
        "profit_factor": pf,
        "max_drawdown_pct": round(max_dd, 2),
        "net_pnl": net_pnl,
        "final_balance": round(balance, 2),
        "counter_trades": counter_trades_count,
        "counter_wr": counter_wr,
        "counter_pnl": round(counter_trades_pnl, 2),
        "day_1pct_hit_rate": day_1pct_rate,
        "day_breach_rate": day_breach_rate,
        "week_5pct_hit_rate": week_5pct_rate
    }


def main():
    print("⏳ Loading M1 parquet dataset...")
    df_m1 = pl.read_parquet(PARQUET_PATH)
    print(f"✅ Loaded {len(df_m1):,} bars.")

    print("⏳ Precomputing Biases and Timeframe Features...")
    raw_biases = precompute_htf_biases(df_m1)
    htf_aligned = {}
    for code in ["D1", "H4", "H1"]:
        joined = df_m1.select(["timestamp"]).join_asof(
            raw_biases[code],
            left_on="timestamp",
            right_on="available_at",
            strategy="backward"
        )
        htf_aligned[code] = joined[f"{code}_bias"].fill_null("NEUTRAL").to_numpy()

    tf_minutes_map = {
        "M1": 1, "M2": 2, "M3": 3, "M5": 5, "M15": 15, "M30": 30
    }
    tf_features = {}
    for code, mins in tf_minutes_map.items():
        tf_features[code] = precompute_tf_features(df_m1, mins, code)

    t_secs = df_m1["timestamp"].dt.epoch("s").to_numpy()
    hours = df_m1["timestamp"].dt.hour().to_numpy()
    minutes = df_m1["timestamp"].dt.minute().to_numpy()
    days = df_m1["timestamp"].dt.strftime("%Y-%m-%d").to_list()
    iso_weeks = df_m1["timestamp"].dt.strftime("%G-W%V").to_list()
    highs = df_m1["high"].to_numpy()
    lows = df_m1["low"].to_numpy()
    closes = df_m1["close"].to_numpy()

    m1_data = {
        "t_secs": t_secs,
        "hours": hours,
        "minutes": minutes,
        "days": days,
        "iso_weeks": iso_weeks,
        "highs": highs,
        "lows": lows,
        "closes": closes
    }

    candidates = [
        {
            "id": "BASELINE_M1",
            "desc": "Baseline M1 (Gembok total saat dual-HTF searah)",
            "exec_tf": "M1",
            "exec_step": 1,
            "logic_mode": "BASELINE"
        },
        {
            "id": "ADAPTIVE_M1_STANDARD_1PCT",
            "desc": "Adaptive Unlock M1 (Kunci buka saat hunting < 1.0%, risk 0.5x, lock at +1.0% / -0.5%)",
            "exec_tf": "M1",
            "exec_step": 1,
            "logic_mode": "OBJECTIVE_ADAPTIVE",
            "daily_lock_pct": 1.0,
            "daily_defensive_cut_pct": -0.5,
            "counter_risk_mult": 0.5,
            "counter_tp_mode": "EQ"
        },
        {
            "id": "ADAPTIVE_M1_BOS_ONLY_GUARD",
            "desc": "Adaptive Unlock M1 (Hanya buka jika M15/M30 BOS valid, lock at +1.0%, risk 0.5x)",
            "exec_tf": "M1",
            "exec_step": 1,
            "logic_mode": "BOS_ONLY_ADAPTIVE",
            "daily_lock_pct": 1.0,
            "daily_defensive_cut_pct": -0.5,
            "counter_risk_mult": 0.5,
            "counter_tp_mode": "EQ"
        },
        {
            "id": "ADAPTIVE_M1_M1_M5_NESTED_ONLY",
            "desc": "Adaptive Unlock M1 (Hanya buka jika M1+M5 Nested Confluence, lock at +1.0%, risk 0.5x)",
            "exec_tf": "M1",
            "exec_step": 1,
            "logic_mode": "NESTED_M1_M5_ADAPTIVE",
            "daily_lock_pct": 1.0,
            "daily_defensive_cut_pct": -0.5,
            "counter_risk_mult": 0.5,
            "counter_tp_mode": "EQ"
        },
        {
            "id": "ADAPTIVE_M1_SHALLOW_TP",
            "desc": "Adaptive Unlock M1 dengan Shallow TP (0.382 Mean Reversion Quick Escape)",
            "exec_tf": "M1",
            "exec_step": 1,
            "logic_mode": "OBJECTIVE_ADAPTIVE",
            "daily_lock_pct": 1.0,
            "daily_defensive_cut_pct": -0.5,
            "counter_risk_mult": 0.5,
            "counter_tp_mode": "SHALLOW"
        },
        {
            "id": "ADAPTIVE_M1_GREED_1_5PCT",
            "desc": "Adaptive Unlock M1 (Lock target di 1.5% profit harian)",
            "exec_tf": "M1",
            "exec_step": 1,
            "logic_mode": "OBJECTIVE_ADAPTIVE",
            "daily_lock_pct": 1.5,
            "daily_defensive_cut_pct": -0.5,
            "counter_risk_mult": 0.5,
            "counter_tp_mode": "EQ"
        },
        {
            "id": "ADAPTIVE_M5_INTRADAY",
            "desc": "Adaptive Unlock M5 (M5 Execution dengan Nested/BOS, lock at +1.0%)",
            "exec_tf": "M5",
            "exec_step": 5,
            "logic_mode": "OBJECTIVE_ADAPTIVE",
            "daily_lock_pct": 1.0,
            "daily_defensive_cut_pct": -0.5,
            "counter_risk_mult": 0.5,
            "counter_tp_mode": "EQ"
        }
    ]

    print("\n⚔️ MENJALANKAN HEAD-TO-HEAD VALIDATION: BASELINE VS OBJECTIVE-AWARE ADAPTIVE UNLOCK ⚔️\n")
    results = []
    for cand in candidates:
        t0 = time.time()
        res = simulate_adaptive_candidate(cand, m1_data, tf_features, htf_aligned)
        results.append(res)
        print(f"✨ {cand['id']:<28} | PF: {res['profit_factor']:.2f} | DD: {res['max_drawdown_pct']:>5.2f}% | Net: ${res['net_pnl']:>9.2f} | Day 1%: {res['day_1pct_hit_rate']:>4.1f}% | Wk 5%: {res['week_5pct_hit_rate']:>4.1f}% (in {time.time()-t0:.2f}s)")

    # Save outputs
    with open(OUTPUT_JSON_PATH, "w") as f:
        json.dump(results, f, indent=2)
    
    # Generate MD Report
    md = [
        "# 🎯 LAPORAN VALIDASI EMPIRIS: LOGIKA OBJECTIVE-AWARE ADAPTIVE UNLOCK",
        f"**Tanggal Audit**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "**Dataset**: 300,440 Bar M1 XAUUSD (Zero Look-Ahead Bias)",
        "**Target Objektif**: 1% Profit/Hari & 5% Profit/Minggu\n",
        "## 1. Tabel Komparasi Head-to-Head",
        "| Model ID | Deskripsi Strategi | PF | Max DD | Net PnL ($) | Daily 1% Hit | Weekly 5% Hit | Counter PnL ($) | Counter WR |",
        "|:---|:---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|"
    ]
    for r in results:
        md.append(f"| `{r['id']}` | {r['desc']} | **{r['profit_factor']:.2f}** | **{r['max_drawdown_pct']:.2f}%** | **${r['net_pnl']:,.2f}** | **{r['day_1pct_hit_rate']}%** | **{r['week_5pct_hit_rate']}%** | ${r['counter_pnl']:,.2f} | {r['counter_wr']}% |")

    with open(OUTPUT_MD_PATH, "w") as f:
        f.write("\n".join(md))
    print(f"\n📁 Validasi selesai! Hasil tersimpan di {OUTPUT_JSON_PATH} dan {OUTPUT_MD_PATH}")


if __name__ == "__main__":
    main()
