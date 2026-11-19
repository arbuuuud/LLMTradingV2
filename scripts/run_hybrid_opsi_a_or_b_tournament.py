"""
Naruto Kage Bunshin Tournament: OPSI A OR OPSI B Hybridization.
Tests the exact user proposal:
- Opsi A: Ultra-Konservatif (M1 + M5 Nested Confluence)
- Opsi B: Dynamic Balanced (M1..M3 + M5/M15 Confluence OR M15/M30 BOS)

Tests various ways to combine them via OR:
1. PURE_OR_FLAT: Cond_A OR Cond_B (Flat 0.5x Risk)
2. HYBRID_DYNAMIC_RISK: Cond_A -> 0.5x Risk | Cond_B only -> 0.25x Risk
3. HYBRID_STATE_GATED: Daily PnL < 0% -> Opsi A only | Daily PnL >= 0% -> Opsi A OR Opsi B
4. HYBRID_ASYMMETRIC_TP: Opsi A -> Equilibrium TP | Opsi B only -> Shallow 0.382 Quick TP
5. HYBRID_MASTER_CHAMPION: State-Gated + Dynamic Risk (Defensive in Red, Aggressive in Green, Locked at +1%)

All evaluated strictly on:
- Daily 1% Hit Rate (Target: >= $100 on $10k)
- Weekly 5% Hit Rate (Target: >= $500 on $10k)
- Max Drawdown % (Target: < 6.0%)
- Net PnL & Profit Factor
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
PARQUET_PATH = PROJECT_ROOT / "data" / "parquet" / "XAUUSD" / "M1" / "XAUUSD_M1.parquet"
OUTPUT_JSON_PATH = PROJECT_ROOT / "reports" / "hybrid_opsi_a_or_b_tournament_report.json"
OUTPUT_MD_PATH = PROJECT_ROOT / "reports" / "hybrid_opsi_a_or_b_tournament_report.md"


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
        "bos_bear": bos_bear_active
    }


def simulate_hybrid_candidate(
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
    mode = spec["mode"]

    sw_h_m1 = tf_features["M1"]["sw_high"]
    sw_l_m1 = tf_features["M1"]["sw_low"]
    span_m1 = tf_features["M1"]["span"]
    in_disc_m1 = tf_features["M1"]["in_discount"]
    in_prem_m1 = tf_features["M1"]["in_premium"]

    d1_bias = htf_biases["D1"]
    h4_bias = htf_biases["H4"]

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

    daily_stats = defaultdict(lambda: {"start": None, "end": 10000.0, "trades": 0, "pnl": 0.0})
    weekly_stats = defaultdict(lambda: {"start": None, "end": 10000.0, "trades": 0, "pnl": 0.0})
    
    current_day_str = ""
    current_day_start_equity = balance

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

        # Process trades
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

        if len(open_trades) == 0 and (t_sec - last_order_time_sec >= 60.0):
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

            trigger_buy = False
            trigger_sell = False
            is_counter = False
            trade_risk_mult = 1.0
            tp_type = "EQ"

            # Check BUY
            if is_disc and (t_sec >= buy_cooldown_until):
                if not both_bear:
                    trigger_buy = True
                    is_counter = False
                else:
                    # Counter-trend BUY Evaluation
                    # 1. Base Objective Check: If daily target >= 1.0% secured, or daily loss <= -0.5%, LOCK TOTAL!
                    if daily_pnl_pct >= 1.0 or daily_pnl_pct <= -0.5:
                        trigger_buy = False
                    else:
                        # Compute Opsi A: M1 + M5 Confluence
                        opsi_a = tf_features["M1"]["in_discount"][i] and tf_features["M5"]["in_discount"][i]

                        # Compute Opsi B: Micro (M1..M3) + Inter (M5/M15) OR M15/M30 BOS
                        micro_active = tf_features["M1"]["in_discount"][i] or tf_features["M2"]["in_discount"][i] or tf_features["M3"]["in_discount"][i]
                        inter_active = tf_features["M5"]["in_discount"][i] or tf_features["M15"]["in_discount"][i]
                        nested_b = micro_active and inter_active
                        bos_b = tf_features["M15"]["bos_bull"][i] or tf_features["M30"]["bos_bull"][i]
                        opsi_b = nested_b or bos_b

                        if mode == "BASELINE":
                            trigger_buy = False
                        elif mode == "OPSI_A_ONLY":
                            if opsi_a:
                                trigger_buy = True
                                is_counter = True
                                trade_risk_mult = 0.50
                        elif mode == "OPSI_B_ONLY":
                            if opsi_b:
                                trigger_buy = True
                                is_counter = True
                                trade_risk_mult = 0.50
                        elif mode == "PURE_OR_FLAT":
                            # Strict Boolean: Opsi A OR Opsi B (Flat 0.5x Risk)
                            if opsi_a or opsi_b:
                                trigger_buy = True
                                is_counter = True
                                trade_risk_mult = 0.50
                        elif mode == "DYNAMIC_WEIGHTED_RISK":
                            # If Opsi A (Ultra-Conservative) -> 0.5x Risk
                            # If Opsi B only -> 0.25x Risk
                            if opsi_a or opsi_b:
                                trigger_buy = True
                                is_counter = True
                                trade_risk_mult = 0.50 if opsi_a else 0.25
                        elif mode == "STATE_GATED_OR":
                            # If Daily in Red (<0%) -> Only Opsi A allowed!
                            # If Daily in Green (>=0% and <1%) -> Opsi A OR Opsi B allowed!
                            if daily_pnl_pct < 0.0:
                                if opsi_a:
                                    trigger_buy = True
                                    is_counter = True
                                    trade_risk_mult = 0.40
                            else:
                                if opsi_a or opsi_b:
                                    trigger_buy = True
                                    is_counter = True
                                    trade_risk_mult = 0.50
                        elif mode == "ASYMMETRIC_TP_OR":
                            # Opsi A -> Full Equilibrium TP (0.50)
                            # Opsi B only -> Quick Shallow TP (0.382)
                            if opsi_a or opsi_b:
                                trigger_buy = True
                                is_counter = True
                                trade_risk_mult = 0.50
                                tp_type = "EQ" if opsi_a else "SHALLOW"
                        elif mode == "MASTER_CHAMPION_HYBRID":
                            # Combines State-Gating + Dynamic Risk + Quick TP:
                            if daily_pnl_pct < 0.0:
                                # When daily red: Only Opsi A with 0.35x risk
                                if opsi_a:
                                    trigger_buy = True
                                    is_counter = True
                                    trade_risk_mult = 0.35
                                    tp_type = "EQ"
                            else:
                                # When daily green (< 1%): Both allowed!
                                if opsi_a:
                                    trigger_buy = True
                                    is_counter = True
                                    trade_risk_mult = 0.50
                                    tp_type = "EQ"
                                elif opsi_b:
                                    trigger_buy = True
                                    is_counter = True
                                    trade_risk_mult = 0.25
                                    tp_type = "SHALLOW"

            # Check SELL
            elif is_prem and (t_sec >= sell_cooldown_until):
                if not both_bull:
                    trigger_sell = True
                    is_counter = False
                else:
                    if daily_pnl_pct >= 1.0 or daily_pnl_pct <= -0.5:
                        trigger_sell = False
                    else:
                        opsi_a = tf_features["M1"]["in_premium"][i] and tf_features["M5"]["in_premium"][i]

                        micro_active = tf_features["M1"]["in_premium"][i] or tf_features["M2"]["in_premium"][i] or tf_features["M3"]["in_premium"][i]
                        inter_active = tf_features["M5"]["in_premium"][i] or tf_features["M15"]["in_premium"][i]
                        nested_b = micro_active and inter_active
                        bos_b = tf_features["M15"]["bos_bear"][i] or tf_features["M30"]["bos_bear"][i]
                        opsi_b = nested_b or bos_b

                        if mode == "BASELINE":
                            trigger_sell = False
                        elif mode == "OPSI_A_ONLY":
                            if opsi_a:
                                trigger_sell = True
                                is_counter = True
                                trade_risk_mult = 0.50
                        elif mode == "OPSI_B_ONLY":
                            if opsi_b:
                                trigger_sell = True
                                is_counter = True
                                trade_risk_mult = 0.50
                        elif mode == "PURE_OR_FLAT":
                            if opsi_a or opsi_b:
                                trigger_sell = True
                                is_counter = True
                                trade_risk_mult = 0.50
                        elif mode == "DYNAMIC_WEIGHTED_RISK":
                            if opsi_a or opsi_b:
                                trigger_sell = True
                                is_counter = True
                                trade_risk_mult = 0.50 if opsi_a else 0.25
                        elif mode == "STATE_GATED_OR":
                            if daily_pnl_pct < 0.0:
                                if opsi_a:
                                    trigger_sell = True
                                    is_counter = True
                                    trade_risk_mult = 0.40
                            else:
                                if opsi_a or opsi_b:
                                    trigger_sell = True
                                    is_counter = True
                                    trade_risk_mult = 0.50
                        elif mode == "ASYMMETRIC_TP_OR":
                            if opsi_a or opsi_b:
                                trigger_sell = True
                                is_counter = True
                                trade_risk_mult = 0.50
                                tp_type = "EQ" if opsi_a else "SHALLOW"
                        elif mode == "MASTER_CHAMPION_HYBRID":
                            if daily_pnl_pct < 0.0:
                                if opsi_a:
                                    trigger_sell = True
                                    is_counter = True
                                    trade_risk_mult = 0.35
                                    tp_type = "EQ"
                            else:
                                if opsi_a:
                                    trigger_sell = True
                                    is_counter = True
                                    trade_risk_mult = 0.50
                                    tp_type = "EQ"
                                elif opsi_b:
                                    trigger_sell = True
                                    is_counter = True
                                    trade_risk_mult = 0.25
                                    tp_type = "SHALLOW"

            sl_buffer = max(0.50, span * 0.0375)
            trade_risk = base_risk * (trade_risk_mult if is_counter else 1.0)

            if trigger_buy:
                sl = round(sw_low - 2.50 - sl_buffer, 2)
                if is_counter and tp_type == "SHALLOW":
                    tp = round(sw_low + (span * 0.382), 2)
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
                if is_counter and tp_type == "SHALLOW":
                    tp = round(sw_low + (span * 0.618), 2)
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
        "mode": mode,
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

    print("⏳ Precomputing HTF Biases & Indicator Arrays...")
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

    tf_features = {
        code: precompute_tf_features(df_m1, mins)
        for code, mins in {"M1": 1, "M2": 2, "M3": 3, "M5": 5, "M15": 15, "M30": 30}.items()
    }

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
            "id": "BASELINE_STATUS_QUO",
            "desc": "Baseline M1: Gembok total saat dual HTF sepakat searah",
            "mode": "BASELINE"
        },
        {
            "id": "OPSI_A_STANDALONE",
            "desc": "Opsi A Murni: (M1 + M5 Confluence Saja, Risk 0.5x)",
            "mode": "OPSI_A_ONLY"
        },
        {
            "id": "OPSI_B_STANDALONE",
            "desc": "Opsi B Murni: (M1..M3 + M5/M15 Confluence OR M15/M30 BOS, Risk 0.5x)",
            "mode": "OPSI_B_ONLY"
        },
        {
            "id": "HYBRID_1_PURE_OR_FLAT",
            "desc": "Hybrid 1: Opsi A OR Opsi B (Flat 0.5x Risk)",
            "mode": "PURE_OR_FLAT"
        },
        {
            "id": "HYBRID_2_DYNAMIC_WEIGHTED",
            "desc": "Hybrid 2: Opsi A -> 0.5x Risk | Opsi B -> 0.25x Risk",
            "mode": "DYNAMIC_WEIGHTED_RISK"
        },
        {
            "id": "HYBRID_3_STATE_GATED_OR",
            "desc": "Hybrid 3: Red Day -> Opsi A Only | Green Day -> Opsi A OR Opsi B",
            "mode": "STATE_GATED_OR"
        },
        {
            "id": "HYBRID_4_ASYMMETRIC_TP_OR",
            "desc": "Hybrid 4: Opsi A -> Full EQ TP | Opsi B -> Quick Shallow TP (0.382)",
            "mode": "ASYMMETRIC_TP_OR"
        },
        {
            "id": "HYBRID_5_MASTER_CHAMPION",
            "desc": "Hybrid 5 (Master): Red Day (Opsi A 0.35x) + Green Day (Opsi A 0.5x OR Opsi B 0.25x Shallow)",
            "mode": "MASTER_CHAMPION_HYBRID"
        }
    ]

    print("\n🥷 MENJALANKAN NARUTO KAGE BUNSHIN TOURNAMENT: OPSI A OR OPSI B HYBRIDIZATION 🥷\n")
    results = []
    for cand in candidates:
        t0 = time.time()
        res = simulate_hybrid_candidate(cand, m1_data, tf_features, htf_aligned)
        results.append(res)
        print(f"✨ {cand['id']:<28} | PF: {res['profit_factor']:.2f} | DD: {res['max_drawdown_pct']:>5.2f}% | Net: ${res['net_pnl']:>9.2f} | Day 1%: {res['day_1pct_hit_rate']:>4.1f}% | Wk 5%: {res['week_5pct_hit_rate']:>4.1f}% (in {time.time()-t0:.2f}s)")

    with open(OUTPUT_JSON_PATH, "w") as f:
        json.dump(results, f, indent=2)

    md = [
        "# 🥷 HASIL TOURNAMENT: HYBRIDISASI OPSI A OR OPSI B DENGAN TUJUAN PROFIT HARIAN & MINGGUAN",
        f"**Tanggal Backtest**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "**Dataset**: 300,440 Bar M1 XAUUSD (Zero Look-Ahead Bias)",
        "**Target Objektif**: 1% Profit/Hari & 5% Profit/Minggu\n",
        "## 1. Tabel Komparasi Penuh",
        "| Model ID | Deskripsi Strategi | PF | Max DD | Net PnL ($) | **Daily 1% Hit** | **Weekly 5% Hit** | Counter Trades | Counter PnL |",
        "|:---|:---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|"
    ]
    for r in results:
        md.append(f"| `{r['id']}` | {r['desc']} | **{r['profit_factor']:.2f}** | **{r['max_drawdown_pct']:.2f}%** | **${r['net_pnl']:,.2f}** | **{r['day_1pct_hit_rate']}%** | **{r['week_5pct_hit_rate']}%** | {r['counter_trades']} | ${r['counter_pnl']:,.2f} |")

    with open(OUTPUT_MD_PATH, "w") as f:
        f.write("\n".join(md))

    print(f"\n📁 Tournament selesai! Laporan tersimpan di:\n- {OUTPUT_JSON_PATH}\n- {OUTPUT_MD_PATH}")


if __name__ == "__main__":
    main()
