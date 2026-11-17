"""
Turnamen 1 Kage Bunshin: Matrix Higher Timeframe (HTF) Trend Bias Gate (Subtask 5-3H / Pilar 1).
Menguji tandingkan matriks Execution Timeframe (M1, M3, M5, M15) vs HTF Bias (M15, M30, H1, H4, D1)
pada dataset 300,440 bar M1 XAUUSD dengan ZERO look-ahead bias untuk menemukan kombinasi paling profitable.
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
OUTPUT_REPORT_PATH = REPORTS_DIR / "kage_bunshin_pilar1_htf_bias_matrix.json"


def precompute_htf_bias(df_m1: pl.DataFrame, htf_code: str) -> pl.DataFrame:
    """
    Menghitung HTF Bias dengan ZERO look-ahead bias.
    Bar HTF yang dimulai pada T baru selesai pada T + duration.
    Status bias (BULLISH/BEARISH/NEUTRAL) baru boleh dibaca oleh bar eksekusi setelah bar HTF tertutup sempurna.
    """
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
    """Resample M1 bars into target execution timeframe (M1, M3, M5, M15)."""
    if exec_tf == "M1":
        return df_m1.sort("timestamp")

    mins = int(exec_tf[1:])
    return (
        df_m1.sort("timestamp")
        .group_by_dynamic("timestamp", every=f"{mins}m")
        .agg([
            pl.first("open").alias("open"),
            pl.max("high").alias("high"),
            pl.min("low").alias("low"),
            pl.last("close").alias("close"),
            pl.sum("tick_volume").alias("tick_volume") if "tick_volume" in df_m1.columns else pl.lit(100).alias("tick_volume")
        ])
    )


def simulate_pac_with_htf_bias(
    df_exec: pl.DataFrame,
    htf_bias_col: str = None,
    risk_money: float = 50.0,
    spread: float = 0.25,
    slippage: float = 0.05
) -> dict:
    """
    Simulasi PAC Scalper event-driven murni (Zero Look-Ahead Bias)
    dengan penyaring HTF Bias Gatekeeper.
    """
    n = len(df_exec)
    if n < 100:
        return {"trades": 0, "win_rate": 0.0, "pnl": 0.0, "pf": 0.0, "dd": 0.0}

    highs = df_exec["high"].to_numpy()
    lows = df_exec["low"].to_numpy()
    closes = df_exec["close"].to_numpy()
    timestamps = df_exec["timestamp"].to_list()
    hours = np.array([t.hour for t in timestamps])
    minutes = np.array([t.minute for t in timestamps])

    biases = df_exec[htf_bias_col].to_numpy() if htf_bias_col and htf_bias_col in df_exec.columns else None

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
    session_floor_pnl = -50.0
    
    buy_cooldown_until = 0.0
    sell_cooldown_until = 0.0
    last_order_time_sec = 0.0

    # Grid weights L1 50%, L2 25%, L3 25% (Inverted Pyramid)
    grid_weights = [0.50, 0.25, 0.25]

    for i in range(25, n):
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
            alloc_loss = 50.0
            if prior_session_profit > 50.0:
                alloc_loss += (prior_session_profit * 0.25)
            session_floor_pnl = -alloc_loss

        # 1. Manage Open Trades
        rem = []
        for tr in open_trades:
            # BUY exit evaluation
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
            # SELL exit evaluation
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

        # 2. Check PAC Entry Condition (Rolling 20-bar window - Zero Look-Ahead Bias)
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

            current_bias = biases[i] if biases is not None else "NEUTRAL"

            # =============================================================
            # PILAR 1: HTF BIAS GATEKEEPER
            # Jika HTF Strong Bearish -> DILARANG BUY (Hanya boleh SELL)
            # Jika HTF Strong Bullish -> DILARANG SELL (Hanya boleh BUY)
            # =============================================================
            allow_buy = True
            allow_sell = True

            if current_bias in ("STRONG_BEARISH", "WEAK_BEARISH"):
                allow_buy = False  # Pasang gembok BUY saat HTF downtrend!
            elif current_bias in ("STRONG_BULLISH", "WEAK_BULLISH"):
                allow_sell = False # Pasang gembok SELL saat HTF uptrend!

            sl_buffer = max(0.50, span * 0.0375)

            # BUY GRID DISPATCH
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

            # SELL GRID DISPATCH
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

    # Summarize results
    total_trades = len(closed_trades)
    wins = [t for t in closed_trades if t.get("pnl", 0) > 0]
    losses = [t for t in closed_trades if t.get("pnl", 0) < 0]
    gp = sum(t.get("pnl", 0) for t in wins)
    gl = abs(sum(t.get("pnl", 0) for t in losses))
    pf = (gp / gl) if gl > 0 else 999.0
    net_pnl = balance - 10000.0
    wr = (len(wins) / total_trades * 100.0) if total_trades > 0 else 0.0

    return {
        "trades": total_trades,
        "win_rate": round(wr, 1),
        "profit_factor": round(pf, 2),
        "net_pnl": round(net_pnl, 2),
        "max_drawdown_pct": round(max_dd, 2),
        "final_balance": round(balance, 2)
    }


def main():
    print("=" * 100)
    print("🥋 TURNAMEN 1 KAGE BUNSHIN: HIGHER TIMEFRAME (HTF) TREND BIAS MATRIX")
    print("Matriks Kombinasi: Execution TF (M1, M3, M5, M15) vs Bias HTF (None, M15, M30, H1, H4, D1)")
    print("Metodologi: 100% Real-Time Event-Driven (Zero Look-Ahead Bias) | Data: 300,440 Bar M1")
    print("=" * 100)

    t0_start = time.time()
    df_m1_full = pl.read_parquet(PARQUET_PATH)
    print(f"Dataset Ground Truth : {len(df_m1_full):,} bar M1 ({df_m1_full['timestamp'].min()} s/d {df_m1_full['timestamp'].max()})")

    # Precompute HTF biases
    print("\n⏳ Precomputing HTF Biases (Zero Look-Ahead with available_at boundary)...")
    t_pre0 = time.time()
    htf_biases = {
        "M15": precompute_htf_bias(df_m1_full, "M15"),
        "M30": precompute_htf_bias(df_m1_full, "M30"),
        "H1":  precompute_htf_bias(df_m1_full, "H1"),
        "H4":  precompute_htf_bias(df_m1_full, "H4"),
        "D1":  precompute_htf_bias(df_m1_full, "D1"),
    }
    print(f"✅ HTF Biases precomputed in {time.time() - t_pre0:.2f}s")

    exec_timeframes = ["M1", "M3", "M5", "M15"]
    htf_candidates = ["NONE", "M15", "M30", "H1", "H4", "D1"]

    tournament_matrix = []
    clone_idx = 1

    for etf in exec_timeframes:
        for htf in htf_candidates:
            # Aturan hirarki: Bias TF harus lebih besar dari Execution TF
            if htf != "NONE":
                etf_mins = int(etf[1:])
                htf_mins = 15 if htf == "M15" else (30 if htf == "M30" else (60 if htf == "H1" else (240 if htf == "H4" else 1440)))
                if htf_mins <= etf_mins:
                    continue  # Lewati jika bias tidak lebih tinggi dari execution TF

            clone_id = f"CLONE-{clone_idx:02d}_{etf}+{'NO_BIAS' if htf == 'NONE' else htf}"
            tournament_matrix.append({
                "clone_id": clone_id,
                "exec_tf": etf,
                "htf_bias": htf
            })
            clone_idx += 1

    print(f"\n🚀 Total Clones Siap Bertanding: {len(tournament_matrix)} Shadow Clones")
    print(f"{'Clone ID':<22} | {'Exec':<5} | {'HTF Bias':<8} | {'Trades':<7} | {'WinRate':<7} | {'PF':<6} | {'MaxDD':<7} | {'Net PnL ($)':<12}")
    print("-" * 95)

    leaderboard = []

    # Cache execution dataframes to avoid re-aggregating repeatedly
    cached_exec_dfs = {}
    for etf in exec_timeframes:
        print(f"Aggregating Execution DF {etf}...", end="\r")
        cached_exec_dfs[etf] = resample_execution_bars(df_m1_full, etf)
    print(" " * 50, end="\r")

    for item in tournament_matrix:
        cid = item["clone_id"]
        etf = item["exec_tf"]
        htf = item["htf_bias"]

        df_exec = cached_exec_dfs[etf]

        if htf == "NONE":
            sim_df = df_exec
            bias_col = None
        else:
            df_htf = htf_biases[htf]
            sim_df = df_exec.join_asof(
                df_htf,
                left_on="timestamp",
                right_on="available_at",
                strategy="backward"
            )
            bias_col = f"{htf}_bias"

        res = simulate_pac_with_htf_bias(sim_df, bias_col)
        entry = {
            "clone_id": cid,
            "exec_tf": etf,
            "htf_bias": htf,
            "trades": res["trades"],
            "win_rate": res["win_rate"],
            "profit_factor": res["profit_factor"],
            "max_drawdown_pct": res["max_drawdown_pct"],
            "net_pnl": res["net_pnl"],
            "final_balance": res["final_balance"]
        }
        leaderboard.append(entry)

        row_str = f"{cid:<22} | {etf:<5} | {htf:<8} | {res['trades']:<7} | {res['win_rate']:<6.1f}% | {res['profit_factor']:<6.2f} | {res['max_drawdown_pct']:<6.2f}% | ${res['net_pnl']:<11,.2f}"
        print(row_str)

    # Sort leaderboard by Net PnL and Profit Factor
    leaderboard.sort(key=lambda x: (x["profit_factor"], x["net_pnl"]), reverse=True)

    print("\n" + "=" * 100)
    print("🏆 HASIL LEADERBOARD TURNAMEN 1 (PILAR 1: HTF BIAS MATRIX)")
    print("=" * 100)
    for rank, lb in enumerate(leaderboard[:10], start=1):
        medal = "🥇" if rank == 1 else ("🥈" if rank == 2 else ("🥉" if rank == 3 else f"#{rank}"))
        print(f"{medal} {lb['clone_id']:<24} (Exec: {lb['exec_tf']} | Bias: {lb['htf_bias']}) -> PnL: ${lb['net_pnl']:+12,.2f} | PF: {lb['profit_factor']:<5.2f} | WR: {lb['win_rate']:<5.1f}% | DD: {lb['max_drawdown_pct']}% | Trades: {lb['trades']}")

    # Save to reports
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    report_data = {
        "tournament_id": "KB-PILAR-1-HTF-BIAS-MATRIX",
        "title": "Turnamen 1 Kage Bunshin: Matrix HTF Trend Bias Gate",
        "timestamp": datetime.now().isoformat(),
        "total_bars": len(df_m1_full),
        "total_clones": len(tournament_matrix),
        "execution_time_sec": round(time.time() - t0_start, 2),
        "leaderboard": leaderboard
    }
    with open(OUTPUT_REPORT_PATH, "w", encoding="utf-8") as f:
        json.dump(report_data, f, indent=2)

    print(f"\n💾 Laporan resmi Kage Bunshin disimpan di: {OUTPUT_REPORT_PATH}")


if __name__ == "__main__":
    main()
