"""
Turnamen Kage Bunshin: Multi-Timeframe Ensemble & Dynamic Handover (M1 + M3 + M5 + M15).
Menguji perbandingan head-to-head:
1. Solo Baselines (M1, M3, M5, M15)
2. Trio Ensemble (M1 + M3 + M5)
3. Kuartet Lengkap (M1 + M3 + M5 + M15)
4. Intelligent Handover (Cancel & Upgrade Pending: M1 -> M3 -> M5 -> M15)
Dataset: 300,440 bar M1 XAUUSD (Zero Look-Ahead Bias).
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

PARQUET_PATH = PROJECT_ROOT / "data" / "parquet" / "XAUUSD" / "M1" / "XAUUSD_M1.parquet"
REPORTS_DIR = PROJECT_ROOT / "reports"
OUTPUT_REPORT_PATH = REPORTS_DIR / "kage_bunshin_ensemble_m1_m3_m5_m15.json"


def precompute_htf_bias(df_m1: pl.DataFrame, htf_code: str) -> pl.DataFrame:
    """Precompute zero look-ahead HTF bias available strictly after bar close."""
    tf_map = {
        "M15": ("15m", timedelta(minutes=15)),
        "H1":  ("1h",  timedelta(hours=1)),
        "H4":  ("4h",  timedelta(hours=4)),
        "D1":  ("1d",  timedelta(days=1)),
    }
    every_str, duration = tf_map[htf_code]

    return (
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
            .alias(f"{htf_code}_bias"),
            (pl.col("timestamp") + duration).alias("available_at")
        ])
        .select(["available_at", f"{htf_code}_bias"])
    )


def resample_tf(df_m1: pl.DataFrame, tf_mins: int) -> pl.DataFrame:
    """Resample M1 into target timeframe bars."""
    if tf_mins == 1:
        return df_m1.sort("timestamp")
    return (
        df_m1.sort("timestamp")
        .group_by_dynamic("timestamp", every=f"{tf_mins}m")
        .agg([
            pl.first("open").alias("open"),
            pl.max("high").alias("high"),
            pl.min("low").alias("low"),
            pl.last("close").alias("close")
        ])
    )


def run_ensemble_simulation(
    df_m1: pl.DataFrame,
    active_tfs: list,
    mode: str = "INDEPENDENT_ENSEMBLE", # "INDEPENDENT_ENSEMBLE" or "HANDOVER_UPGRADE"
    total_risk_money: float = 50.0,
    spread: float = 0.25,
    slippage: float = 0.05
) -> dict:
    """
    Simulasi Multi-Timeframe Terintegrasi bar demi bar (Zero Look-Ahead Bias).
    Mengevaluasi M1, M3, M5, M15 secara sinkron di setiap menit waktu nyata.
    """
    n = len(df_m1)
    highs_m1 = df_m1["high"].to_numpy()
    lows_m1 = df_m1["low"].to_numpy()
    closes_m1 = df_m1["close"].to_numpy()
    timestamps_m1 = df_m1["timestamp"].to_list()
    hours_m1 = np.array([t.hour for t in timestamps_m1])
    minutes_m1 = np.array([t.minute for t in timestamps_m1])

    # Pre-build TF lookups & HTF biases
    # Mapping best HTF bias per TF:
    # M1 -> D1
    # M3 -> D1
    # M5 -> M15
    # M15 -> H1
    htf_bias_for_tf = {
        "M1": "D1",
        "M3": "D1",
        "M5": "M15",
        "M15": "H1"
    }

    # Precompute HTF biases
    bias_dfs = {
        "D1": precompute_htf_bias(df_m1, "D1"),
        "M15": precompute_htf_bias(df_m1, "M15"),
        "H1": precompute_htf_bias(df_m1, "H1")
    }

    # Attach biases to M1 stream
    df_stream = df_m1.sort("timestamp")
    for b_code, b_df in bias_dfs.items():
        b_df_renamed = b_df.rename({"available_at": f"avail_{b_code}"})
        df_stream = df_stream.join_asof(
            b_df_renamed,
            left_on="timestamp",
            right_on=f"avail_{b_code}",
            strategy="backward"
        )

    biases_d1 = df_stream["D1_bias"].to_numpy()
    biases_m15 = df_stream["M15_bias"].to_numpy()
    biases_h1 = df_stream["H1_bias"].to_numpy()

    # Pre-build rolling 20-bar buffers for M3, M5, M15
    tf_minutes = {"M1": 1, "M3": 3, "M5": 5, "M15": 15}
    risk_per_tf = total_risk_money / len(active_tfs)

    balance = 10000.0
    equity_peak = balance
    max_dd = 0.0

    open_trades = []
    closed_trades = []
    pending_orders = [] # Unfilled limits waiting

    # Tracking session
    current_session = ""
    current_day = ""
    session_start_balance = balance
    prior_session_profit = 0.0
    session_halted = False
    session_floor_pnl = -total_risk_money

    last_order_time_per_tf = {tf: 0.0 for tf in active_tfs}
    cooldown_until_per_tf = {tf: 0.0 for tf in active_tfs}

    # Precompute rolling window for each TF
    # For M1, lookback 20 M1 bars = 20 mins
    # For M3, lookback 20 M3 bars = 60 mins
    # For M5, lookback 20 M5 bars = 100 mins
    # For M15, lookback 20 M15 bars = 300 mins
    lookback_mins = {"M1": 20, "M3": 60, "M5": 100, "M15": 300}

    # Grid weights: L1 50%, L2 25%, L3 25%
    grid_weights = [0.50, 0.25, 0.25]

    for i in range(350, n):
        t = timestamps_m1[i]
        t_sec = t.timestamp()
        hr = hours_m1[i]
        mn = minutes_m1[i]
        h = highs_m1[i]
        l = lows_m1[i]
        c = closes_m1[i]

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

        # 1. Manage Pending Orders: check if price triggers pending limit order
        rem_pending = []
        for p_ord in pending_orders:
            # Check expiration / cancel
            if t_sec - p_ord["placed_time"] > (15 * 60): # 15 mins timeout
                continue
            
            # Check fill
            if p_ord["dir"] == "BUY" and l <= p_ord["limit_price"]:
                # Filled! Convert to open trade
                open_trades.append({
                    "tf": p_ord["tf"],
                    "dir": "BUY",
                    "in": p_ord["limit_price"],
                    "sl": p_ord["sl"],
                    "tp": p_ord["tp"],
                    "risk": p_ord["risk"]
                })
            elif p_ord["dir"] == "SELL" and h >= p_ord["limit_price"]:
                # Filled!
                open_trades.append({
                    "tf": p_ord["tf"],
                    "dir": "SELL",
                    "in": p_ord["limit_price"],
                    "sl": p_ord["sl"],
                    "tp": p_ord["tp"],
                    "risk": p_ord["risk"]
                })
            else:
                rem_pending.append(p_ord)
        pending_orders = rem_pending

        # 2. Manage Open Floating Positions
        rem_trades = []
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
                    cooldown_until_per_tf[tr["tf"]] = t_sec + cd_dur
                else:
                    rem_trades.append(tr)
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
                    cooldown_until_per_tf[tr["tf"]] = t_sec + cd_dur
                else:
                    rem_trades.append(tr)
        open_trades = rem_trades

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
            pending_orders = []
            continue

        # 3. Multi-TF Scanning & Evaluation
        for tf in active_tfs:
            # Check cooldown & order frequency
            if t_sec < cooldown_until_per_tf[tf]:
                continue
            if t_sec - last_order_time_per_tf[tf] < (tf_minutes[tf] * 60):
                continue

            # Does this TF already have active positions or pending orders?
            tf_has_pos = any(tr["tf"] == tf for tr in open_trades)
            tf_has_pend = any(po["tf"] == tf for po in pending_orders)

            if tf_has_pos or tf_has_pend:
                continue

            # Calculate rolling window for this TF
            lb_m = lookback_mins[tf]
            sub_h = highs_m1[i - lb_m:i]
            sub_l = lows_m1[i - lb_m:i]
            sw_high = np.max(sub_h)
            sw_low = np.min(sub_l)
            span = max(sw_high - sw_low, 1.0)
            eq = (sw_high + sw_low) / 2.0

            buy_top = sw_low + (span * 0.25)
            sell_bot = sw_low + (span * 0.75)
            mid = c

            in_discount = (mid <= buy_top)
            in_premium = (mid >= sell_bot)

            # Get appropriate HTF bias
            htf_target = htf_bias_for_tf[tf]
            if htf_target == "D1": cur_bias = biases_d1[i]
            elif htf_target == "H1": cur_bias = biases_h1[i]
            elif htf_target == "M15": cur_bias = biases_m15[i]
            else: cur_bias = "NEUTRAL"

            allow_buy = True
            allow_sell = True
            if cur_bias in ("STRONG_BEARISH", "WEAK_BEARISH"):
                allow_buy = False
            elif cur_bias in ("STRONG_BULLISH", "WEAK_BULLISH"):
                allow_sell = False

            sl_buffer = max(0.50, span * 0.0375)

            # --- HANDOVER / UPGRADE LOGIC ---
            # If a lower TF (e.g. M1) has a pending order, and this higher TF (M3, M5, or M15) triggers:
            if mode == "HANDOVER_UPGRADE":
                if in_discount and allow_buy:
                    # Cancel any lower-TF pending orders in BUY direction!
                    lower_tfs = [t_item for t_item in active_tfs if tf_minutes[t_item] < tf_minutes[tf]]
                    pending_orders = [po for po in pending_orders if not (po["tf"] in lower_tfs and po["dir"] == "BUY")]
                elif in_premium and allow_sell:
                    # Cancel any lower-TF pending orders in SELL direction!
                    lower_tfs = [t_item for t_item in active_tfs if tf_minutes[t_item] < tf_minutes[tf]]
                    pending_orders = [po for po in pending_orders if not (po["tf"] in lower_tfs and po["dir"] == "SELL")]

            # BUY GRID PLACEMENT
            if in_discount and allow_buy:
                sl = round(sw_low - 2.50 - sl_buffer, 2)
                tp = round(eq, 2)
                l1 = round(min(mid - 0.25, sw_low + span * 0.25), 2)
                l2 = round(min(mid - 0.50, sw_low + span * 0.125), 2)
                l3 = round(min(mid - 0.75, sw_low), 2)
                levels = [l1, l2, l3]

                for lay_idx, limit_p in enumerate(levels):
                    pending_orders.append({
                        "tf": tf,
                        "dir": "BUY",
                        "limit_price": limit_p,
                        "sl": sl,
                        "tp": tp,
                        "risk": risk_per_tf * grid_weights[lay_idx],
                        "placed_time": t_sec
                    })
                last_order_time_per_tf[tf] = t_sec

            # SELL GRID PLACEMENT
            elif in_premium and allow_sell:
                sl = round(sw_high + 2.50 + sl_buffer, 2)
                tp = round(eq, 2)
                l1 = round(max(mid + 0.25, sw_low + span * 0.75), 2)
                l2 = round(max(mid + 0.50, sw_low + span * 0.875), 2)
                l3 = round(max(mid + 0.75, sw_high), 2)
                levels = [l1, l2, l3]

                for lay_idx, limit_p in enumerate(levels):
                    pending_orders.append({
                        "tf": tf,
                        "dir": "SELL",
                        "limit_price": limit_p,
                        "sl": sl,
                        "tp": tp,
                        "risk": risk_per_tf * grid_weights[lay_idx],
                        "placed_time": t_sec
                    })
                last_order_time_per_tf[tf] = t_sec

    # Summarize
    total_trades = len(closed_trades)
    wins = [t for t in closed_trades if t.get("pnl", 0) > 0]
    losses = [t for t in closed_trades if t.get("pnl", 0) < 0]
    gp = sum(t.get("pnl", 0) for t in wins)
    gl = abs(sum(t.get("pnl", 0) for t in losses))
    pf = (gp / gl) if gl > 0 else 999.0
    net_pnl = balance - 10000.0
    wr = (len(wins) / total_trades * 100.0) if total_trades > 0 else 0.0

    # TF breakdown
    tf_summary = {}
    for tf in active_tfs:
        tf_tr = [t for t in closed_trades if t["tf"] == tf]
        tf_w = [t for t in tf_tr if t.get("pnl", 0) > 0]
        tf_summary[tf] = {
            "trades": len(tf_tr),
            "pnl": round(sum(t.get("pnl", 0) for t in tf_tr), 2),
            "win_rate": round(len(tf_w) / len(tf_tr) * 100.0, 1) if tf_tr else 0.0
        }

    return {
        "trades": total_trades,
        "win_rate": round(wr, 1),
        "profit_factor": round(pf, 2),
        "net_pnl": round(net_pnl, 2),
        "max_drawdown_pct": round(max_dd, 2),
        "tf_breakdown": tf_summary
    }


def main():
    print("=" * 105)
    print("🥋 TURNAMEN ENSEMBLE & HANDOVER: M1 vs M3 vs M5 vs M15")
    print("Membandingkan: Solo vs Trio (M1+M3+M5) vs Kuartet (M1+M3+M5+M15) vs Handover Upgrade")
    print("Metodologi: 100% Real-Time Synchronous M1 Bar-by-Bar Stream (Zero Look-Ahead Bias)")
    print("=" * 105)

    df_m1_full = pl.read_parquet(PARQUET_PATH)
    print(f"Dataset Ground Truth: {len(df_m1_full):,} bar M1 ({df_m1_full['timestamp'].min()} s/d {df_m1_full['timestamp'].max()})\n")

    scenarios = [
        {"id": "SOLO-M1", "tfs": ["M1"], "mode": "INDEPENDENT_ENSEMBLE", "desc": "Solo M1 (Bias D1)"},
        {"id": "SOLO-M3", "tfs": ["M3"], "mode": "INDEPENDENT_ENSEMBLE", "desc": "Solo M3 (Bias D1)"},
        {"id": "SOLO-M5", "tfs": ["M5"], "mode": "INDEPENDENT_ENSEMBLE", "desc": "Solo M5 (Bias M15)"},
        {"id": "SOLO-M15", "tfs": ["M15"], "mode": "INDEPENDENT_ENSEMBLE", "desc": "Solo M15 (Bias H1)"},
        {"id": "TRIO-M1-M3-M5", "tfs": ["M1", "M3", "M5"], "mode": "INDEPENDENT_ENSEMBLE", "desc": "Trio Ensemble (M1 + M3 + M5 Independent)"},
        {"id": "QUARTET-ALL-4-TF", "tfs": ["M1", "M3", "M5", "M15"], "mode": "INDEPENDENT_ENSEMBLE", "desc": "Kuartet Lengkap (M1 + M3 + M5 + M15 Independent)"},
        {"id": "HANDOVER-TRIO", "tfs": ["M1", "M3", "M5"], "mode": "HANDOVER_UPGRADE", "desc": "Trio + Intelligent Handover (Cancel & Upgrade Pending)"},
        {"id": "HANDOVER-QUARTET", "tfs": ["M1", "M3", "M5", "M15"], "mode": "HANDOVER_UPGRADE", "desc": "Kuartet + Intelligent Handover (M1->M3->M5->M15 Upgrade)"},
    ]

    leaderboard = []

    header = f"{'Scenario ID':<18} | {'Mode & TFs':<45} | {'Trades':<7} | {'WinRate':<7} | {'PF':<6} | {'MaxDD':<7} | {'Net PnL ($)':<12}"
    print(header)
    print("-" * 115)

    for sc in scenarios:
        t0 = time.time()
        res = run_ensemble_simulation(
            df_m1=df_m1_full,
            active_tfs=sc["tfs"],
            mode=sc["mode"],
            total_risk_money=50.0
        )
        dur = time.time() - t0

        entry = {
            "scenario_id": sc["id"],
            "description": sc["desc"],
            "tfs": sc["tfs"],
            "mode": sc["mode"],
            "trades": res["trades"],
            "win_rate": res["win_rate"],
            "profit_factor": res["profit_factor"],
            "max_drawdown_pct": res["max_drawdown_pct"],
            "net_pnl": res["net_pnl"],
            "tf_breakdown": res["tf_breakdown"],
            "duration_sec": round(dur, 2)
        }
        leaderboard.append(entry)

        row_str = f"{sc['id']:<18} | {sc['desc']:<45} | {res['trades']:<7} | {res['win_rate']:<6.1f}% | {res['profit_factor']:<6.2f} | {res['max_drawdown_pct']:<6.2f}% | ${res['net_pnl']:<11,.2f}"
        print(row_str)

    # Save report
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_REPORT_PATH, "w", encoding="utf-8") as f:
        json.dump(leaderboard, f, indent=2)

    print("\n" + "=" * 105)
    print("🏆 HASIL KOMPARASI FINAL: TRIO vs KUARTET vs HANDOVER")
    print("=" * 105)
    leaderboard.sort(key=lambda x: (x["profit_factor"], x["net_pnl"]), reverse=True)
    for rank, lb in enumerate(leaderboard, start=1):
        medal = "🥇" if rank == 1 else ("🥈" if rank == 2 else ("🥉" if rank == 3 else f"#{rank}"))
        print(f"{medal} {lb['scenario_id']:<18} | PnL: ${lb['net_pnl']:+12,.2f} | PF: {lb['profit_factor']:<5.2f} | WR: {lb['win_rate']:<5.1f}% | DD: {lb['max_drawdown_pct']:<5.2f}% | Trades: {lb['trades']}")
        # Print breakdown per TF
        bd_str = ", ".join([f"{k}: {v['trades']} trd (${v['pnl']:+,.1f}, WR {v['win_rate']}%)" for k, v in lb['tf_breakdown'].items()])
        print(f"    └─ Kontribusi TF: {bd_str}")

    print(f"\n💾 Laporan resmi disimpan di: {OUTPUT_REPORT_PATH}")


if __name__ == "__main__":
    main()
