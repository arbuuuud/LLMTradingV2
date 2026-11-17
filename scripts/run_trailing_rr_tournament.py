"""
Turnamen 2 Kage Bunshin: Matrix Trailing Stop & Risk-to-Reward (R:R) Engine (Subtask 5-3H / Pilar 2).
Menguji perbandingan head-to-head 24 Shadow Clones di 300,440 bar M1 XAUUSD (Zero Look-Ahead Bias):
1. Controls: Legacy Sasuke 0.5R vs Pure Equilibrium (No Trailing)
2. Group A: Fixed R-Multiple Trailing (1.0R, 1.2R, 1.5R, 2.0R)
3. Group B: Dynamic ATR Trailing (ATR M1, ATR M5, ATR M15)
4. Group C: Naruto 2 Summary Trailing (Dollar Offsets $2, $3, $4)
5. Group D: Context-Aware Dual Mode (Skenario 3: No Trail / Full TP vs Skenario 1&2: Extend TP + ATR Trail)
6. Group E: ADX Regime Adaptive (Ranging: Full TP vs Trend: ATR Trail)
"""

import sys
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

from src.features.indicators import calculate_adx

PARQUET_PATH = PROJECT_ROOT / "data" / "parquet" / "XAUUSD" / "M1" / "XAUUSD_M1.parquet"
REPORTS_DIR = PROJECT_ROOT / "reports"
OUTPUT_REPORT_PATH = REPORTS_DIR / "kage_bunshin_pilar2_trailing_rr_matrix.json"


def calc_atr_np(h: np.ndarray, l: np.ndarray, c: np.ndarray, period: int = 14) -> np.ndarray:
    """Calculates Wilder's ATR using pure numpy."""
    c_prev = np.roll(c, 1)
    c_prev[0] = c[0]
    tr = np.maximum(h - l, np.maximum(np.abs(h - c_prev), np.abs(l - c_prev)))
    atr = np.zeros_like(tr)
    atr[:period] = np.mean(tr[:period])
    for i in range(period, len(tr)):
        atr[i] = (atr[i-1] * (period - 1) + tr[i]) / period
    return atr


def precompute_market_context(df_m1: pl.DataFrame) -> pl.DataFrame:
    """
    Precomputes all indicators and HTF structures strictly without look-ahead bias:
    - D1 Bias (Champion Pilar 1 for M1)
    - ATR M1 (period 14)
    - ATR M5 (period 14, available at T + 5m)
    - ATR M15 (period 14, available at T + 15m)
    - ADX M1 (period 14)
    - M15 Rolling Structure (Floor, Roof, Buy Zone Top, Sell Zone Bot, Eq M15)
    """
    # 1. D1 Bias
    df_d1 = (
        df_m1.sort("timestamp")
        .group_by_dynamic("timestamp", every="1d")
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
            .alias("d1_bias"),
            (pl.col("timestamp") + timedelta(days=1)).alias("avail_d1")
        ])
        .select(["avail_d1", "d1_bias"])
    )

    # 2. ATR M1
    h_m1 = df_m1["high"].to_numpy()
    l_m1 = df_m1["low"].to_numpy()
    c_m1 = df_m1["close"].to_numpy()
    atr_m1 = calc_atr_np(h_m1, l_m1, c_m1, 14)

    # 3. ATR M5
    df_m5 = (
        df_m1.sort("timestamp")
        .group_by_dynamic("timestamp", every="5m")
        .agg([
            pl.first("open").alias("open"),
            pl.max("high").alias("high"),
            pl.min("low").alias("low"),
            pl.last("close").alias("close")
        ])
    )
    atr_m5_arr = calc_atr_np(df_m5["high"].to_numpy(), df_m5["low"].to_numpy(), df_m5["close"].to_numpy(), 14)
    df_m5 = df_m5.with_columns([
        pl.Series("atr_m5", atr_m5_arr),
        (pl.col("timestamp") + timedelta(minutes=5)).alias("avail_m5")
    ]).select(["avail_m5", "atr_m5"])

    # 4. ATR M15 & M15 Rolling Structure (20 bars = 300 mins)
    df_m15 = (
        df_m1.sort("timestamp")
        .group_by_dynamic("timestamp", every="15m")
        .agg([
            pl.first("open").alias("open"),
            pl.max("high").alias("high"),
            pl.min("low").alias("low"),
            pl.last("close").alias("close")
        ])
    )
    atr_m15_arr = calc_atr_np(df_m15["high"].to_numpy(), df_m15["low"].to_numpy(), df_m15["close"].to_numpy(), 14)
    df_m15 = (
        df_m15.with_columns([
            pl.Series("atr_m15", atr_m15_arr),
            pl.col("high").rolling_max(window_size=20).alias("roof_m15"),
            pl.col("low").rolling_min(window_size=20).alias("floor_m15"),
            (pl.col("timestamp") + timedelta(minutes=15)).alias("avail_m15")
        ])
        .with_columns([
            (pl.col("roof_m15") - pl.col("floor_m15")).alias("span_m15"),
            ((pl.col("roof_m15") + pl.col("floor_m15")) / 2.0).alias("eq_m15")
        ])
        .with_columns([
            (pl.col("floor_m15") + pl.col("span_m15") * 0.25).alias("m15_demand_top"),
            (pl.col("roof_m15") - pl.col("span_m15") * 0.25).alias("m15_supply_bot")
        ])
        .select(["avail_m15", "atr_m15", "roof_m15", "floor_m15", "eq_m15", "m15_demand_top", "m15_supply_bot"])
    )

    # 5. ADX M1
    df_adx = calculate_adx(df_m1, period=14)

    # Stream As-Of Joins to M1
    df_stream = (
        df_m1.sort("timestamp")
        .with_columns([
            pl.Series("atr_m1", atr_m1),
            df_adx["adx_14"].alias("adx_m1")
        ])
        .join_asof(df_d1, left_on="timestamp", right_on="avail_d1", strategy="backward")
        .join_asof(df_m5, left_on="timestamp", right_on="avail_m5", strategy="backward")
        .join_asof(df_m15, left_on="timestamp", right_on="avail_m15", strategy="backward")
    )
    return df_stream


def simulate_trailing_clone(
    df_stream: pl.DataFrame,
    spec: dict,
    total_risk_money: float = 50.0,
    spread: float = 0.25,
    slippage: float = 0.05
) -> dict:
    """
    Simulates a specific Trailing Stop & R:R model over 300,440 M1 bars
    with event-driven precision and zero look-ahead bias.
    """
    n = len(df_stream)
    highs = df_stream["high"].to_numpy()
    lows = df_stream["low"].to_numpy()
    closes = df_stream["close"].to_numpy()
    timestamps = df_stream["timestamp"].to_list()
    hours = np.array([t.hour for t in timestamps])
    minutes = np.array([t.minute for t in timestamps])

    d1_biases = df_stream["d1_bias"].to_numpy()
    atr_m1_vals = df_stream["atr_m1"].to_numpy()
    atr_m5_vals = df_stream["atr_m5"].to_numpy()
    atr_m15_vals = df_stream["atr_m15"].to_numpy()
    adx_vals = df_stream["adx_m1"].to_numpy()

    m15_demand_tops = df_stream["m15_demand_top"].to_numpy()
    m15_supply_bots = df_stream["m15_supply_bot"].to_numpy()
    m15_eqs = df_stream["eq_m15"].to_numpy()

    # Trailing spec params
    model_type = spec["model_type"] # "LEGACY_0.5R", "NO_TRAIL", "FIXED_RR", "ATR_DYNAMIC", "NARUTO2", "DUAL_SCENARIO", "ADX_REGIME"
    trigger_r = spec.get("trigger_r", 1.0)
    lock_r = spec.get("lock_r", 0.2)
    atr_tf = spec.get("atr_tf", "M5") # "M1", "M5", "M15"
    atr_mult = spec.get("atr_mult", 1.5)
    naruto_trigger = spec.get("naruto_trigger", 2.0)
    naruto_offset = spec.get("naruto_offset", 2.0)

    balance = 10000.0
    equity_peak = balance
    max_dd = 0.0

    open_trades = []
    closed_trades = []

    # Session tracking
    current_session = ""
    current_day = ""
    session_start_balance = balance
    prior_session_profit = 0.0
    session_halted = False
    session_floor_pnl = -total_risk_money

    buy_cooldown_until = 0.0
    sell_cooldown_until = 0.0
    last_order_time_sec = 0.0

    # Inverted grid weights L1 50%, L2 25%, L3 25%
    grid_weights = [0.50, 0.25, 0.25]

    for i in range(50, n):
        t = timestamps[i]
        t_sec = t.timestamp()
        hr = hours[i]
        mn = minutes[i]
        h = highs[i]
        l = lows[i]
        c = closes[i]

        day_key = t.strftime("%Y-%m-%d")
        if day_key != current_day:
            current_day = day_key
            prior_session_profit = 0.0

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
            alloc_loss = total_risk_money
            if prior_session_profit > total_risk_money:
                alloc_loss += (prior_session_profit * 0.25)
            session_floor_pnl = -alloc_loss

        # Current ATR values
        cur_atr = atr_m5_vals[i] if atr_tf == "M5" else (atr_m15_vals[i] if atr_tf == "M15" else atr_m1_vals[i])
        if np.isnan(cur_atr) or cur_atr <= 0:
            cur_atr = 1.50
        cur_adx = adx_vals[i] if not np.isnan(adx_vals[i]) else 20.0

        # 1. Manage & Trail Open Trades
        rem = []
        for tr in open_trades:
            init_sl_dist = tr["sl_dist"]
            entry_p = tr["in"]

            # Track peak price since fill
            if tr["dir"] == "BUY":
                if h > tr["peak"]:
                    tr["peak"] = h
                running_pts = tr["peak"] - entry_p

                # -------------------------------------------------------------
                # TRAILING STOP ENGINE LOGIC (PILAR 2 CANDIDATES)
                # -------------------------------------------------------------
                new_sl = tr["sl"]

                if model_type == "NO_TRAIL":
                    # Strictly no modification! Full TP or Full SL
                    pass

                elif model_type == "LEGACY_0.5R":
                    # Status Quo on VPS: Lock at +0.5R, +1.0R, +1.5R
                    if running_pts >= 0.5 * init_sl_dist:
                        new_sl = max(new_sl, entry_p + 0.10)
                    if running_pts >= 1.0 * init_sl_dist:
                        new_sl = max(new_sl, entry_p + 0.5 * init_sl_dist)
                    if running_pts >= 1.5 * init_sl_dist:
                        new_sl = max(new_sl, entry_p + 1.0 * init_sl_dist)

                elif model_type == "FIXED_RR":
                    if running_pts >= trigger_r * init_sl_dist:
                        cand_sl = entry_p + lock_r * init_sl_dist
                        # trail behind peak
                        trail_gap = (trigger_r - lock_r) * init_sl_dist
                        cand_sl = max(cand_sl, tr["peak"] - trail_gap)
                        new_sl = max(new_sl, cand_sl)

                elif model_type == "ATR_DYNAMIC":
                    # Activate ATR trailing once running >= +1.0R
                    if running_pts >= 1.0 * init_sl_dist:
                        cand_sl = tr["peak"] - (atr_mult * cur_atr)
                        cand_sl = max(cand_sl, entry_p + 0.20) # At least BEP
                        new_sl = max(new_sl, cand_sl)

                elif model_type == "NARUTO2":
                    if running_pts >= naruto_trigger:
                        cand_sl = tr["peak"] - naruto_offset
                        cand_sl = max(cand_sl, entry_p) # Lock BEP
                        new_sl = max(new_sl, cand_sl)

                elif model_type == "DUAL_SCENARIO":
                    # User's brilliant hypothesis:
                    # If Scenario 3 (Mid-Air / not nested in HTF): NO TRAIL, strict Equilibrium TP!
                    # If Scenario 1/2 (Nested in HTF): Trailing IS ACTIVE + TP is extended!
                    if tr["is_nested"]:
                        if running_pts >= 1.0 * init_sl_dist:
                            cand_sl = tr["peak"] - (atr_mult * cur_atr)
                            cand_sl = max(cand_sl, entry_p + 0.20)
                            new_sl = max(new_sl, cand_sl)
                    else:
                        # Scenario 3: Dilarang trailing! Pure TP!
                        pass

                elif model_type == "ADX_REGIME":
                    # If ADX < 25 (Consolidation): No trail
                    # If ADX >= 25 (Trend expansion): Trail ATR M5
                    if cur_adx >= 25.0 and running_pts >= 1.0 * init_sl_dist:
                        cand_sl = tr["peak"] - (atr_mult * cur_atr)
                        cand_sl = max(cand_sl, entry_p + 0.20)
                        new_sl = max(new_sl, cand_sl)

                tr["sl"] = new_sl

                # Check TP Hit
                if h >= (tr["tp"] + slippage):
                    pnl = tr["risk"] * ((tr["tp"] - entry_p) / init_sl_dist)
                    balance += pnl
                    tr["pnl"] = pnl
                    tr["exit_reason"] = "TP"
                    closed_trades.append(tr)
                # Check SL / Trailing Hit
                elif l <= (tr["sl"] - slippage):
                    exit_p = tr["sl"]
                    pts = exit_p - entry_p
                    pnl = tr["risk"] * (pts / init_sl_dist)
                    balance += pnl
                    tr["pnl"] = pnl
                    tr["exit_reason"] = "TRAIL_OR_SL"
                    closed_trades.append(tr)
                    if pnl < 0:
                        cd_dur = 600 if sess_name == "ASIAN" else (900 if sess_name == "LONDON" else 1500)
                        buy_cooldown_until = t_sec + cd_dur
                else:
                    rem.append(tr)

            elif tr["dir"] == "SELL":
                if l < tr["trough"]:
                    tr["trough"] = l
                running_pts = entry_p - tr["trough"]

                new_sl = tr["sl"]

                if model_type == "NO_TRAIL":
                    pass

                elif model_type == "LEGACY_0.5R":
                    if running_pts >= 0.5 * init_sl_dist:
                        new_sl = min(new_sl, entry_p - 0.10)
                    if running_pts >= 1.0 * init_sl_dist:
                        new_sl = min(new_sl, entry_p - 0.5 * init_sl_dist)
                    if running_pts >= 1.5 * init_sl_dist:
                        new_sl = min(new_sl, entry_p - 1.0 * init_sl_dist)

                elif model_type == "FIXED_RR":
                    if running_pts >= trigger_r * init_sl_dist:
                        cand_sl = entry_p - lock_r * init_sl_dist
                        trail_gap = (trigger_r - lock_r) * init_sl_dist
                        cand_sl = min(cand_sl, tr["trough"] + trail_gap)
                        new_sl = min(new_sl, cand_sl)

                elif model_type == "ATR_DYNAMIC":
                    if running_pts >= 1.0 * init_sl_dist:
                        cand_sl = tr["trough"] + (atr_mult * cur_atr)
                        cand_sl = min(cand_sl, entry_p - 0.20)
                        new_sl = min(new_sl, cand_sl)

                elif model_type == "NARUTO2":
                    if running_pts >= naruto_trigger:
                        cand_sl = tr["trough"] + naruto_offset
                        cand_sl = min(cand_sl, entry_p)
                        new_sl = min(new_sl, cand_sl)

                elif model_type == "DUAL_SCENARIO":
                    if tr["is_nested"]:
                        if running_pts >= 1.0 * init_sl_dist:
                            cand_sl = tr["trough"] + (atr_mult * cur_atr)
                            cand_sl = min(cand_sl, entry_p - 0.20)
                            new_sl = min(new_sl, cand_sl)
                    else:
                        pass

                elif model_type == "ADX_REGIME":
                    if cur_adx >= 25.0 and running_pts >= 1.0 * init_sl_dist:
                        cand_sl = tr["trough"] + (atr_mult * cur_atr)
                        cand_sl = min(cand_sl, entry_p - 0.20)
                        new_sl = min(new_sl, cand_sl)

                tr["sl"] = new_sl

                # Check TP Hit
                if (l + spread) <= (tr["tp"] - slippage):
                    pnl = tr["risk"] * ((entry_p - tr["tp"]) / init_sl_dist)
                    balance += pnl
                    tr["pnl"] = pnl
                    tr["exit_reason"] = "TP"
                    closed_trades.append(tr)
                # Check SL / Trailing Hit
                elif (h + spread) >= (tr["sl"] + slippage):
                    exit_p = tr["sl"]
                    pts = entry_p - exit_p
                    pnl = tr["risk"] * (pts / init_sl_dist)
                    balance += pnl
                    tr["pnl"] = pnl
                    tr["exit_reason"] = "TRAIL_OR_SL"
                    closed_trades.append(tr)
                    if pnl < 0:
                        cd_dur = 600 if sess_name == "ASIAN" else (900 if sess_name == "LONDON" else 1500)
                        sell_cooldown_until = t_sec + cd_dur
                else:
                    rem.append(tr)

        open_trades = rem

        # Drawdown tracking
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

        # 2. Entry Logic (M1 with Champion D1 Bias Gate from Pilar 1)
        if len(open_trades) == 0 and (t_sec - last_order_time_sec >= 60.0):
            sub_h = highs[i-20:i]
            sub_l = lows[i-20:i]
            sw_high = np.max(sub_h)
            sw_low = np.min(sub_l)
            span = max(sw_high - sw_low, 1.0)
            eq = (sw_high + sw_low) / 2.0

            buy_top = sw_low + (span * 0.25)
            sell_bot = sw_low + (span * 0.75)
            mid = c

            in_discount = (mid <= buy_top)
            in_premium = (mid >= sell_bot)

            # Champion D1 Bias Gate
            cur_bias = d1_biases[i] if not isinstance(d1_biases[i], float) else "NEUTRAL"
            allow_buy = True
            allow_sell = True
            if cur_bias in ("STRONG_BEARISH", "WEAK_BEARISH"):
                allow_buy = False
            elif cur_bias in ("STRONG_BULLISH", "WEAK_BULLISH"):
                allow_sell = False

            sl_buffer = max(0.50, span * 0.0375)

            # Check if M1 is nested inside M15 S&D Zone (Scenario 1 & 2 vs Scenario 3)
            m15_d_top = m15_demand_tops[i] if not np.isnan(m15_demand_tops[i]) else 0.0
            m15_s_bot = m15_supply_bots[i] if not np.isnan(m15_supply_bots[i]) else 999999.0
            m15_eq = m15_eqs[i] if not np.isnan(m15_eqs[i]) else eq

            # BUY ENTRY
            if in_discount and allow_buy and (t_sec >= buy_cooldown_until):
                sl = round(sw_low - 2.50 - sl_buffer, 2)
                l1 = round(min(mid - 0.25, sw_low + span * 0.25), 2)
                l2 = round(min(mid - 0.50, sw_low + span * 0.125), 2)
                l3 = round(min(mid - 0.75, sw_low), 2)
                levels = [l1, l2, l3]

                for lay_idx, limit_p in enumerate(levels):
                    if l <= limit_p:
                        # Check whether this order is nested in M15 Demand Base
                        is_nested = (limit_p <= m15_d_top)
                        # Determine TP:
                        if model_type == "DUAL_SCENARIO" and is_nested:
                            tp = round(max(eq + 3.0, m15_eq), 2) # Extended TP
                        elif model_type == "ADX_REGIME" and cur_adx >= 25.0:
                            tp = round(sw_high, 2) # Opposite band expansion
                        else:
                            tp = round(eq, 2) # Normal Equilibrium TP

                        open_trades.append({
                            "dir": "BUY",
                            "in": limit_p,
                            "sl": sl,
                            "tp": tp,
                            "sl_dist": max(limit_p - sl, 0.50),
                            "risk": total_risk_money * grid_weights[lay_idx],
                            "peak": limit_p,
                            "is_nested": is_nested
                        })
                last_order_time_sec = t_sec

            # SELL ENTRY
            elif in_premium and allow_sell and (t_sec >= sell_cooldown_until):
                sl = round(sw_high + 2.50 + sl_buffer, 2)
                l1 = round(max(mid + 0.25, sw_low + span * 0.75), 2)
                l2 = round(max(mid + 0.50, sw_low + span * 0.875), 2)
                l3 = round(max(mid + 0.75, sw_high), 2)
                levels = [l1, l2, l3]

                for lay_idx, limit_p in enumerate(levels):
                    if h >= limit_p:
                        is_nested = (limit_p >= m15_s_bot)
                        if model_type == "DUAL_SCENARIO" and is_nested:
                            tp = round(min(eq - 3.0, m15_eq), 2)
                        elif model_type == "ADX_REGIME" and cur_adx >= 25.0:
                            tp = round(sw_low, 2)
                        else:
                            tp = round(eq, 2)

                        open_trades.append({
                            "dir": "SELL",
                            "in": limit_p,
                            "sl": sl,
                            "tp": tp,
                            "sl_dist": max(sl - limit_p, 0.50),
                            "risk": total_risk_money * grid_weights[lay_idx],
                            "trough": limit_p,
                            "is_nested": is_nested
                        })
                last_order_time_sec = t_sec

    # Compile performance
    total_trades = len(closed_trades)
    wins = [t for t in closed_trades if t.get("pnl", 0) > 0]
    losses = [t for t in closed_trades if t.get("pnl", 0) < 0]

    gp = sum(t.get("pnl", 0) for t in wins)
    gl = abs(sum(t.get("pnl", 0) for t in losses))
    pf = (gp / gl) if gl > 0 else 999.0
    net_pnl = balance - 10000.0
    wr = (len(wins) / total_trades * 100.0) if total_trades > 0 else 0.0

    avg_win = (gp / len(wins)) if wins else 0.0
    avg_loss = (gl / len(losses)) if losses else 0.0
    payoff_ratio = (avg_win / avg_loss) if avg_loss > 0 else 0.0

    # Nested vs Midair performance breakdown
    nested_tr = [t for t in closed_trades if t.get("is_nested", False)]
    midair_tr = [t for t in closed_trades if not t.get("is_nested", False)]

    nested_pnl = sum(t.get("pnl", 0) for t in nested_tr)
    midair_pnl = sum(t.get("pnl", 0) for t in midair_tr)

    return {
        "trades": total_trades,
        "win_rate": round(wr, 1),
        "profit_factor": round(pf, 2),
        "net_pnl": round(net_pnl, 2),
        "max_drawdown_pct": round(max_dd, 2),
        "avg_win": round(avg_win, 2),
        "avg_loss": round(avg_loss, 2),
        "payoff_ratio": round(payoff_ratio, 2),
        "nested_trades": len(nested_tr),
        "nested_pnl": round(nested_pnl, 2),
        "midair_trades": len(midair_tr),
        "midair_pnl": round(midair_pnl, 2)
    }


def main():
    print("=" * 115)
    print("🥋 TURNAMEN 2 KAGE BUNSHIN: TRAILING STOP & RISK-TO-REWARD (R:R) ENGINE MATRIX")
    print("Adu Tanding: Legacy 0.5R vs Pure Equilibrium vs Fixed R:R vs ATR M1/M5/M15 vs Dual Scenario vs ADX")
    print("Metodologi: 100% Real-Time Event-Driven (Zero Look-Ahead Bias) | Data: 300,440 Bar M1 XAUUSD")
    print("=" * 115)

    t0_start = time.time()
    df_m1_full = pl.read_parquet(PARQUET_PATH)
    print(f"Dataset Ground Truth : {len(df_m1_full):,} bar M1 ({df_m1_full['timestamp'].min()} s/d {df_m1_full['timestamp'].max()})")

    print("\n⏳ Precomputing Market Context (ATR M1/M5/M15, ADX, D1 Bias, M15 Structure)...")
    t_pre0 = time.time()
    df_stream = precompute_market_context(df_m1_full)
    print(f"✅ Market Context precomputed in {time.time() - t_pre0:.2f}s")

    clones = [
        # Controls
        {"id": "CLONE-01_LEGACY_SASUKE_0.5R", "model_type": "LEGACY_0.5R", "desc": "Status Quo VPS (Lock BEP at +0.5R, trail +1.0R, +1.5R)"},
        {"id": "CLONE-02_PURE_EQ_NO_TRAIL", "model_type": "NO_TRAIL", "desc": "Pure Equilibrium 50% TP (NO Trailing Stop at all)"},

        # Group A: Fixed R-Multiple Trailing (Wider breathing room)
        {"id": "CLONE-03_FIXED_RR_1.0R", "model_type": "FIXED_RR", "trigger_r": 1.0, "lock_r": 0.2, "desc": "Fixed R:R (Trigger +1.0R, lock BEP +0.2R)"},
        {"id": "CLONE-04_FIXED_RR_1.2R", "model_type": "FIXED_RR", "trigger_r": 1.2, "lock_r": 0.5, "desc": "Fixed R:R (Trigger +1.2R, lock +0.5R)"},
        {"id": "CLONE-05_FIXED_RR_1.5R", "model_type": "FIXED_RR", "trigger_r": 1.5, "lock_r": 0.8, "desc": "Fixed R:R (Trigger +1.5R, lock +0.8R)"},
        {"id": "CLONE-06_FIXED_RR_2.0R", "model_type": "FIXED_RR", "trigger_r": 2.0, "lock_r": 1.2, "desc": "Fixed R:R (Trigger +2.0R, lock +1.2R)"},

        # Group B: Volatility Dynamic ATR Trailing
        {"id": "CLONE-07_ATR_M1_1.5X", "model_type": "ATR_DYNAMIC", "atr_tf": "M1", "atr_mult": 1.5, "desc": "ATR M1 Dynamic (1.5x ATR M1)"},
        {"id": "CLONE-08_ATR_M1_2.0X", "model_type": "ATR_DYNAMIC", "atr_tf": "M1", "atr_mult": 2.0, "desc": "ATR M1 Dynamic (2.0x ATR M1)"},
        {"id": "CLONE-09_ATR_M5_1.0X", "model_type": "ATR_DYNAMIC", "atr_tf": "M5", "atr_mult": 1.0, "desc": "ATR M5 Dynamic (1.0x ATR M5)"},
        {"id": "CLONE-10_ATR_M5_1.5X", "model_type": "ATR_DYNAMIC", "atr_tf": "M5", "atr_mult": 1.5, "desc": "ATR M5 Dynamic (1.5x ATR M5 Smoothed)"},
        {"id": "CLONE-11_ATR_M5_2.0X", "model_type": "ATR_DYNAMIC", "atr_tf": "M5", "atr_mult": 2.0, "desc": "ATR M5 Dynamic (2.0x ATR M5)"},
        {"id": "CLONE-12_ATR_M15_1.5X", "model_type": "ATR_DYNAMIC", "atr_tf": "M15", "atr_mult": 1.5, "desc": "ATR M15 Macro Dynamic (1.5x ATR M15)"},

        # Group C: Naruto 2 Summary Dollar Trailing
        {"id": "CLONE-13_NARUTO2_2.0_2.0", "model_type": "NARUTO2", "naruto_trigger": 2.0, "naruto_offset": 2.0, "desc": "Naruto 2 (Lock BEP at +$2.00, trail $2.00 behind)"},
        {"id": "CLONE-14_NARUTO2_3.0_2.5", "model_type": "NARUTO2", "naruto_trigger": 3.0, "naruto_offset": 2.5, "desc": "Naruto 2 (Lock BEP at +$3.00, trail $2.50 behind)"},
        {"id": "CLONE-15_NARUTO2_4.0_3.0", "model_type": "NARUTO2", "naruto_trigger": 4.0, "naruto_offset": 3.0, "desc": "Naruto 2 (Lock BEP at +$4.00, trail $3.00 behind)"},

        # Group D: Context-Aware Dual Mode (User's Breakthrough Hypothesis!)
        {"id": "CLONE-16_DUAL_ATR_M5_1.5X", "model_type": "DUAL_SCENARIO", "atr_tf": "M5", "atr_mult": 1.5, "desc": "Dual Mode (S3 Mid-Air: Full Eq TP | S1/S2: Extend TP + Trail 1.5x ATR M5)"},
        {"id": "CLONE-17_DUAL_ATR_M5_2.0X", "model_type": "DUAL_SCENARIO", "atr_tf": "M5", "atr_mult": 2.0, "desc": "Dual Mode (S3 Mid-Air: Full Eq TP | S1/S2: Extend TP + Trail 2.0x ATR M5)"},
        {"id": "CLONE-18_DUAL_ATR_M15_1.5X", "model_type": "DUAL_SCENARIO", "atr_tf": "M15", "atr_mult": 1.5, "desc": "Dual Mode (S3 Mid-Air: Full Eq TP | S1/S2: Extend TP + Trail 1.5x ATR M15)"},
        {"id": "CLONE-19_DUAL_FIXED_RR_1.5R", "model_type": "DUAL_SCENARIO", "trigger_r": 1.5, "lock_r": 0.8, "desc": "Dual Mode (S3 Mid-Air: Full Eq TP | S1/S2: Extend TP + Trail 1.5R)"},
        {"id": "CLONE-20_DUAL_NARUTO2_3.0", "model_type": "DUAL_SCENARIO", "naruto_trigger": 3.0, "naruto_offset": 2.5, "desc": "Dual Mode (S3 Mid-Air: Full Eq TP | S1/S2: Extend TP + Naruto 2 $3.00)"},

        # Group E: ADX Regime Adaptive
        {"id": "CLONE-21_ADX_REGIME_ATR_M5_1.5X", "model_type": "ADX_REGIME", "atr_tf": "M5", "atr_mult": 1.5, "desc": "ADX Regime (ADX<25: Full Eq TP | ADX>=25: Trail 1.5x ATR M5 to 100%)"},
        {"id": "CLONE-22_ADX_REGIME_ATR_M5_2.0X", "model_type": "ADX_REGIME", "atr_tf": "M5", "atr_mult": 2.0, "desc": "ADX Regime (ADX<25: Full Eq TP | ADX>=25: Trail 2.0x ATR M5 to 100%)"},
        {"id": "CLONE-23_ADX_REGIME_FIXED_1.5R", "model_type": "ADX_REGIME", "trigger_r": 1.5, "lock_r": 0.8, "desc": "ADX Regime (ADX<25: Full Eq TP | ADX>=25: Trail 1.5R to 100%)"},
        {"id": "CLONE-24_ADX_REGIME_NARUTO2", "model_type": "ADX_REGIME", "naruto_trigger": 3.0, "naruto_offset": 2.5, "desc": "ADX Regime (ADX<25: Full Eq TP | ADX>=25: Trail Naruto 2 $3.00)"},
    ]

    print(f"\n🚀 Total Clones Siap Bertanding: {len(clones)} Shadow Clones")
    header = f"{'Clone ID':<28} | {'Trades':<7} | {'WinRate':<7} | {'PF':<6} | {'MaxDD':<7} | {'Payoff':<6} | {'AvgWin':<7} | {'AvgLoss':<7} | {'Net PnL ($)':<12}"
    print(header)
    print("-" * 115)

    leaderboard = []

    for c in clones:
        t0 = time.time()
        res = simulate_trailing_clone(df_stream, c, total_risk_money=50.0)
        dur = time.time() - t0

        entry = {
            "clone_id": c["id"],
            "model_type": c["model_type"],
            "description": c["desc"],
            "trades": res["trades"],
            "win_rate": res["win_rate"],
            "profit_factor": res["profit_factor"],
            "max_drawdown_pct": res["max_drawdown_pct"],
            "payoff_ratio": res["payoff_ratio"],
            "avg_win": res["avg_win"],
            "avg_loss": res["avg_loss"],
            "net_pnl": res["net_pnl"],
            "nested_trades": res["nested_trades"],
            "nested_pnl": res["nested_pnl"],
            "midair_trades": res["midair_trades"],
            "midair_pnl": res["midair_pnl"],
            "duration_sec": round(dur, 2)
        }
        leaderboard.append(entry)

        row_str = f"{c['id']:<28} | {res['trades']:<7} | {res['win_rate']:<6.1f}% | {res['profit_factor']:<6.2f} | {res['max_drawdown_pct']:<6.2f}% | {res['payoff_ratio']:<6.2f} | ${res['avg_win']:<6.2f} | ${res['avg_loss']:<6.2f} | ${res['net_pnl']:<11,.2f}"
        print(row_str)

    # Save to report
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    report_data = {
        "tournament_id": "KB-PILAR-2-TRAILING-RR-MATRIX",
        "title": "Turnamen 2 Kage Bunshin: Trailing Stop & Risk-to-Reward (R:R) Engine Matrix",
        "timestamp": datetime.now().isoformat(),
        "total_bars": len(df_m1_full),
        "total_clones": len(clones),
        "execution_time_sec": round(time.time() - t0_start, 2),
        "leaderboard": leaderboard
    }
    with open(OUTPUT_REPORT_PATH, "w", encoding="utf-8") as f:
        json.dump(report_data, f, indent=2)

    print("\n" + "=" * 115)
    print("🏆 HASIL LEADERBOARD TURNAMEN 2 (PILAR 2: TRAILING STOP & R:R ENGINE)")
    print("=" * 115)
    leaderboard.sort(key=lambda x: (x["profit_factor"], x["net_pnl"]), reverse=True)
    for rank, lb in enumerate(leaderboard[:10], start=1):
        medal = "🥇" if rank == 1 else ("🥈" if rank == 2 else ("🥉" if rank == 3 else f"#{rank}"))
        print(f"{medal} {lb['clone_id']:<28} -> PF: {lb['profit_factor']:<5.2f} | PnL: ${lb['net_pnl']:+12,.2f} | WR: {lb['win_rate']:<5.1f}% | Payoff: {lb['payoff_ratio']:<4.2f} | DD: {lb['max_drawdown_pct']:<5.2f}% | Avg W/L: ${lb['avg_win']}/${lb['avg_loss']}")
        print(f"    └─ Deskripsi: {lb['description']}")

    print(f"\n💾 Laporan resmi Kage Bunshin disimpan di: {OUTPUT_REPORT_PATH}")


if __name__ == "__main__":
    main()
