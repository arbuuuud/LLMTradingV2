"""
Turnamen Kage Bunshin: Uji Empiris Top 1 vs Top 2 (OR / Consensus) HTF Bias Matrix.
Menguji tandingkan:
1. Single Top 1 HTF Bias
2. Single Top 2 HTF Bias
3. Top 2 Permissive OR (Block BUY only if BOTH are Bearish)
4. Top 2 Strict Consensus (Block BUY if EITHER is Bearish)
5. Top 2 Bullish Alignment (Allow BUY if EITHER is Bullish)
pada dataset 300,440 bar M1 XAUUSD (Zero Look-Ahead Bias).
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
OUTPUT_REPORT_PATH = REPORTS_DIR / "kage_bunshin_htf_top2_or_tournament.json"


def precompute_htf_bias(df_m1: pl.DataFrame, htf_code: str) -> pl.DataFrame:
    tf_map = {
        "M15": ("15m", timedelta(minutes=15)),
        "M30": ("30m", timedelta(minutes=30)),
        "H1":  ("1h",  timedelta(hours=1)),
        "H4":  ("4h",  timedelta(hours=4)),
        "D1":  ("1d",  timedelta(days=1)),
    }
    every_str, duration = tf_map[htf_code]

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
            .alias(f"{htf_code}_bias"),
            (pl.col("timestamp") + duration).alias("available_at")
        ])
        .select(["available_at", f"{htf_code}_bias"])
    )
    return df_htf


def resample_execution_bars(df_m1: pl.DataFrame, exec_tf: str) -> pl.DataFrame:
    if exec_tf == "M1":
        return df_m1.sort("timestamp")
    
    tf_map = {
        "M3": "3m",
        "M5": "5m",
        "M15": "15m"
    }
    every_str = tf_map[exec_tf]
    df_res = (
        df_m1.sort("timestamp")
        .group_by_dynamic("timestamp", every=every_str)
        .agg([
            pl.first("open").alias("open"),
            pl.max("high").alias("high"),
            pl.min("low").alias("low"),
            pl.last("close").alias("close")
        ])
    )
    return df_res


def run_single_simulation(df_exec: pl.DataFrame, bias1_col: str = None, bias2_col: str = None, mode: str = "SINGLE"):
    """
    Modes:
    - NONE: No bias filter
    - SINGLE: uses bias1_col only
    - PERMISSIVE_OR: allow_buy unless BOTH bias1 & bias2 are bearish
    - STRICT_OR: block_buy if EITHER bias1 or bias2 is bearish
    - ALIGNED_OR: allow_buy only if EITHER bias1 or bias2 is bullish
    """
    timestamps = df_exec["timestamp"].dt.epoch("s").to_numpy()
    hours = df_exec["timestamp"].dt.hour().to_numpy()
    minutes = df_exec["timestamp"].dt.minute().to_numpy()
    highs = df_exec["high"].to_numpy()
    lows = df_exec["low"].to_numpy()
    closes = df_exec["close"].to_numpy()

    b1_arr = df_exec[bias1_col].to_numpy() if bias1_col and bias1_col in df_exec.columns else None
    b2_arr = df_exec[bias2_col].to_numpy() if bias2_col and bias2_col in df_exec.columns else None

    n_bars = len(df_exec)
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

    grid_weights = [0.25, 0.35, 0.40]
    risk_money = 50.0
    spread = 0.35
    slippage = 0.05

    for i in range(25, n_bars):
        t_sec = timestamps[i]
        hr = hours[i]
        mn = minutes[i]
        h = highs[i]
        l = lows[i]
        c = closes[i]

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

            allow_buy = True
            allow_sell = True

            b1 = b1_arr[i] if b1_arr is not None else "NEUTRAL"
            b2 = b2_arr[i] if b2_arr is not None else "NEUTRAL"

            b1_bear = b1 in ("STRONG_BEARISH", "WEAK_BEARISH")
            b1_bull = b1 in ("STRONG_BULLISH", "WEAK_BULLISH")
            b2_bear = b2 in ("STRONG_BEARISH", "WEAK_BEARISH")
            b2_bull = b2 in ("STRONG_BULLISH", "WEAK_BULLISH")

            if mode == "SINGLE":
                if b1_bear: allow_buy = False
                elif b1_bull: allow_sell = False
            elif mode == "PERMISSIVE_OR":
                # Permissive: Block BUY ONLY IF BOTH are Bearish
                if b1_bear and b2_bear: allow_buy = False
                if b1_bull and b2_bull: allow_sell = False
            elif mode == "STRICT_OR":
                # Strict: Block BUY if EITHER is Bearish
                if b1_bear or b2_bear: allow_buy = False
                if b1_bull or b2_bull: allow_sell = False
            elif mode == "ALIGNED_OR":
                # Aligned: Allow BUY if at least one is Bullish
                if not (b1_bull or b2_bull): allow_buy = False
                if not (b1_bear or b2_bear): allow_sell = False

            sl_buffer = max(0.50, span * 0.0375)

            if in_discount and allow_buy and (t_sec >= buy_cooldown_until):
                sl = round(sw_low - 2.50 - sl_buffer, 2)
                tp = round(eq, 2)
                l1 = round(min(mid - 0.25, sw_low + span * 0.25), 2)
                l2 = round(min(mid - 0.50, sw_low + span * 0.125), 2)
                l3 = round(min(mid - 0.75, sw_low), 2)
                levels = [l1, l2, l3]
                for lay_idx, limit_p in enumerate(levels):
                    if l <= limit_p:
                        open_trades.append({
                            "dir": "BUY",
                            "in": limit_p,
                            "sl": sl,
                            "tp": tp,
                            "risk": risk_money * grid_weights[lay_idx]
                        })
                last_order_time_sec = t_sec

            elif in_premium and allow_sell and (t_sec >= sell_cooldown_until):
                sl = round(sw_high + 2.50 + sl_buffer, 2)
                tp = round(eq, 2)
                l1 = round(max(mid + 0.25, sw_low + span * 0.75), 2)
                l2 = round(max(mid + 0.50, sw_low + span * 0.875), 2)
                l3 = round(max(mid + 0.75, sw_high), 2)
                levels = [l1, l2, l3]
                for lay_idx, limit_p in enumerate(levels):
                    if h >= limit_p:
                        open_trades.append({
                            "dir": "SELL",
                            "in": limit_p,
                            "sl": sl,
                            "tp": tp,
                            "risk": risk_money * grid_weights[lay_idx]
                        })
                last_order_time_sec = t_sec

    wins = [t for t in closed_trades if t["pnl"] > 0]
    losses = [t for t in closed_trades if t["pnl"] < 0]
    gross_win = sum(t["pnl"] for t in wins)
    gross_loss = abs(sum(t["pnl"] for t in losses))
    pf = round(gross_win / gross_loss, 2) if gross_loss > 0 else 999.0
    net_pnl = round(balance - 10000.0, 2)
    wr = round(len(wins) / len(closed_trades) * 100.0, 1) if closed_trades else 0.0

    return {
        "trades": len(closed_trades),
        "win_rate": wr,
        "profit_factor": pf,
        "max_drawdown_pct": round(max_dd, 2),
        "net_pnl": net_pnl,
        "final_balance": round(balance, 2)
    }


def main():
    print("⏳ Loading M1 parquet dataset...")
    df_m1 = pl.read_parquet(PARQUET_PATH)
    print(f"✅ Loaded {len(df_m1):,} bars.")

    # Precompute all HTF biases
    print("⏳ Precomputing HTF Biases: M15, H1, H4, D1 (Zero Look-Ahead)...")
    df_bias_m15 = precompute_htf_bias(df_m1, "M15")
    df_bias_h1 = precompute_htf_bias(df_m1, "H1")
    df_bias_h4 = precompute_htf_bias(df_m1, "H4")
    df_bias_d1 = precompute_htf_bias(df_m1, "D1")

    # Resample execution timeframes and join biases
    resampled_dfs = {}
    for etf in ["M1", "M3", "M5", "M15"]:
        print(f"⏳ Precomputing bars & joining biases for {etf}...")
        df_e = resample_execution_bars(df_m1, etf)
        
        # As-of joins (ensure unique timestamps or drop prior joined timestamp)
        df_e = df_e.join_asof(df_bias_m15, left_on="timestamp", right_on="available_at", strategy="backward")
        if "available_at" in df_e.columns: df_e = df_e.drop("available_at")
        df_e = df_e.join_asof(df_bias_h1, left_on="timestamp", right_on="available_at", strategy="backward")
        if "available_at" in df_e.columns: df_e = df_e.drop("available_at")
        df_e = df_e.join_asof(df_bias_h4, left_on="timestamp", right_on="available_at", strategy="backward")
        if "available_at" in df_e.columns: df_e = df_e.drop("available_at")
        df_e = df_e.join_asof(df_bias_d1, left_on="timestamp", right_on="available_at", strategy="backward")
        if "available_at" in df_e.columns: df_e = df_e.drop("available_at")
        resampled_dfs[etf] = df_e

    # Define test combinations
    configs = [
        # === M1 EXPERIMENTS ===
        {"id": "M1_D1_ONLY", "tf": "M1", "b1": "D1_bias", "b2": None, "mode": "SINGLE", "desc": "Top 1 D1"},
        {"id": "M1_H4_ONLY", "tf": "M1", "b1": "H4_bias", "b2": None, "mode": "SINGLE", "desc": "Top 2 H4"},
        {"id": "M1_D1_OR_H4_PERMISSIVE", "tf": "M1", "b1": "D1_bias", "b2": "H4_bias", "mode": "PERMISSIVE_OR", "desc": "Block if BOTH Bearish"},
        {"id": "M1_D1_OR_H4_STRICT", "tf": "M1", "b1": "D1_bias", "b2": "H4_bias", "mode": "STRICT_OR", "desc": "Block if EITHER Bearish"},

        # === M3 EXPERIMENTS ===
        {"id": "M3_D1_ONLY", "tf": "M3", "b1": "D1_bias", "b2": None, "mode": "SINGLE", "desc": "Top 1 D1"},
        {"id": "M3_H4_ONLY", "tf": "M3", "b1": "H4_bias", "b2": None, "mode": "SINGLE", "desc": "Top 2 H4"},
        {"id": "M3_D1_OR_H4_PERMISSIVE", "tf": "M3", "b1": "D1_bias", "b2": "H4_bias", "mode": "PERMISSIVE_OR", "desc": "Block if BOTH Bearish"},
        {"id": "M3_D1_OR_H4_STRICT", "tf": "M3", "b1": "D1_bias", "b2": "H4_bias", "mode": "STRICT_OR", "desc": "Block if EITHER Bearish"},

        # === M5 EXPERIMENTS ===
        {"id": "M5_D1_ONLY", "tf": "M5", "b1": "D1_bias", "b2": None, "mode": "SINGLE", "desc": "Top 1 PnL D1"},
        {"id": "M5_H4_ONLY", "tf": "M5", "b1": "H4_bias", "b2": None, "mode": "SINGLE", "desc": "Top 2 PnL H4"},
        {"id": "M5_M15_ONLY", "tf": "M5", "b1": "M15_bias", "b2": None, "mode": "SINGLE", "desc": "Top 1 Min-DD M15"},
        {"id": "M5_D1_OR_H4_PERMISSIVE", "tf": "M5", "b1": "D1_bias", "b2": "H4_bias", "mode": "PERMISSIVE_OR", "desc": "D1+H4 Block if BOTH Bearish"},
        {"id": "M5_D1_OR_H4_STRICT", "tf": "M5", "b1": "D1_bias", "b2": "H4_bias", "mode": "STRICT_OR", "desc": "D1+H4 Block if EITHER Bearish"},
        {"id": "M5_D1_OR_M15_PERMISSIVE", "tf": "M5", "b1": "D1_bias", "b2": "M15_bias", "mode": "PERMISSIVE_OR", "desc": "D1+M15 Block if BOTH Bearish"},
        {"id": "M5_D1_OR_M15_STRICT", "tf": "M5", "b1": "D1_bias", "b2": "M15_bias", "mode": "STRICT_OR", "desc": "D1+M15 Block if EITHER Bearish"},

        # === M15 EXPERIMENTS ===
        {"id": "M15_H1_ONLY", "tf": "M15", "b1": "H1_bias", "b2": None, "mode": "SINGLE", "desc": "Top 1 H1"},
        {"id": "M15_H4_ONLY", "tf": "M15", "b1": "H4_bias", "b2": None, "mode": "SINGLE", "desc": "Top 2 H4"},
        {"id": "M15_H1_OR_H4_PERMISSIVE", "tf": "M15", "b1": "H1_bias", "b2": "H4_bias", "mode": "PERMISSIVE_OR", "desc": "Block if BOTH Bearish"},
        {"id": "M15_H1_OR_H4_STRICT", "tf": "M15", "b1": "H1_bias", "b2": "H4_bias", "mode": "STRICT_OR", "desc": "Block if EITHER Bearish"},
        {"id": "M15_H1_OR_H4_ALIGNED", "tf": "M15", "b1": "H1_bias", "b2": "H4_bias", "mode": "ALIGNED_OR", "desc": "Allow if EITHER Bullish"}
    ]

    print("\n⚔️ RUNNING KAGE BUNSHIN TOURNAMENT: TOP 1 VS TOP 2 COMBINATIONS ⚔️\n")
    results = []
    t0 = time.time()
    for cfg in configs:
        df_e = resampled_dfs[cfg["tf"]]
        res = run_single_simulation(df_e, cfg["b1"], cfg["b2"], cfg["mode"])
        res["id"] = cfg["id"]
        res["tf"] = cfg["tf"]
        res["desc"] = cfg["desc"]
        results.append(res)

    el = time.time() - t0
    print(f"🏁 Finished all {len(configs)} simulations in {el:.2f} seconds!\n")

    # Group by TF and print leaderboards
    for tf in ["M1", "M3", "M5", "M15"]:
        print(f"==================== HASIL KAGE BUNSHIN: ENTRY {tf} ====================")
        tf_res = [r for r in results if r["tf"] == tf]
        tf_res.sort(key=lambda x: (x["profit_factor"], x["net_pnl"]), reverse=True)
        print(f"{'Experiment ID':25s} | {'Mode / Desc':25s} | {'PF':5s} | {'DD %':6s} | {'Net PnL ($)':12s} | {'WR %':5s} | Trades")
        print("-" * 95)
        for r in tf_res:
            print(f"{r['id']:25s} | {r['desc']:25s} | {r['profit_factor']:5.2f} | {r['max_drawdown_pct']:5.2f}% | ${r['net_pnl']:11.2f} | {r['win_rate']:4.1f}% | {r['trades']}")
        print()

    OUTPUT_REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_REPORT_PATH, "w") as f:
        json.dump(results, f, indent=2)
    print(f"📁 Report saved to {OUTPUT_REPORT_PATH}")


if __name__ == "__main__":
    main()
