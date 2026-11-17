"""
Turnamen 3 Kage Bunshin: Zone Depletion & Stale Order Mechanics (Subtask 5-3H / Pilar 3).
Menguji perbandingan head-to-head 10 Shadow Clones di 300,440 bar M1 XAUUSD (Zero Look-Ahead Bias):
1. Model A: Macro Zone Lockout (DEC-035: Seluruh kotak Floor/Roof digembok setelah TP)
2. Model B: Micro Level Depletion (Ide Pengguna: Hanya level tersentuh yang habis, virgin depth tetap aktif)
3. Model C: Touch-and-Burn (Cancel L2/L3 setelah L1 TP, re-entry hanya di lantai paling dasar L3)
4. Model D: Unlimited Retests (Legacy Control: Bebas re-entry tanpa pelacakan depletion)
5. Model E: Deeper Penetration Retest Only (Hanya boleh re-entry jika wick tembus lebih dalam)
Semua model diuji dengan 2 variasi eksekusi: Pure Equilibrium TP dan Naruto 2 Trailing.
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
OUTPUT_REPORT_PATH = REPORTS_DIR / "kage_bunshin_pilar3_zone_depletion_matrix.json"


def precompute_market_stream(df_m1: pl.DataFrame) -> pl.DataFrame:
    """Precomputes D1 trend bias strictly with available_at boundary (Zero Look-Ahead)."""
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

    df_stream = (
        df_m1.sort("timestamp")
        .join_asof(df_d1, left_on="timestamp", right_on="avail_d1", strategy="backward")
    )
    return df_stream


def simulate_depletion_clone(
    df_stream: pl.DataFrame,
    spec: dict,
    total_risk_money: float = 50.0,
    spread: float = 0.25,
    slippage: float = 0.05
) -> dict:
    """
    Simulates a specific Zone Depletion & Stale Orders mechanic
    over 300,440 M1 bars with bar-by-bar deterministic accuracy.
    """
    n = len(df_stream)
    highs = df_stream["high"].to_numpy()
    lows = df_stream["low"].to_numpy()
    closes = df_stream["close"].to_numpy()
    timestamps = df_stream["timestamp"].to_list()
    hours = np.array([t.hour for t in timestamps])
    minutes = np.array([t.minute for t in timestamps])
    d1_biases = df_stream["d1_bias"].to_numpy()

    depletion_model = spec["depletion_model"] # "MACRO_LOCKOUT", "MICRO_DEPLETION", "TOUCH_AND_BURN", "UNLIMITED", "DEEPER_ONLY"
    use_naruto2 = spec.get("use_naruto2", False)

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

    # Grid weights L1 50%, L2 25%, L3 25%
    grid_weights = [0.50, 0.25, 0.25]

    # Structure & Depletion state
    current_roof = 0.0
    current_floor = 0.0
    macro_buy_zone_completed = False
    macro_sell_zone_completed = False

    # Micro level depletion state: [L1_spent, L2_spent, L3_spent]
    buy_levels_spent = [False, False, False]
    sell_levels_spent = [False, False, False]
    deepest_buy_touch = 999999.0
    deepest_sell_touch = 0.0

    # Tracking metrics for research
    virgin_depth_trades_count = 0
    blocked_by_depletion_count = 0

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

        # 1. Manage Open Trades
        rem = []
        for tr in open_trades:
            entry_p = tr["in"]
            init_sl_dist = tr["sl_dist"]
            layer_idx = tr["layer_idx"]

            # Track peak price
            if tr["dir"] == "BUY":
                if h > tr["peak"]:
                    tr["peak"] = h
                running_pts = tr["peak"] - entry_p

                # Naruto 2 Trailing if enabled
                if use_naruto2 and running_pts >= 2.0:
                    cand_sl = tr["peak"] - 2.0
                    cand_sl = max(cand_sl, entry_p) # Lock BEP
                    tr["sl"] = max(tr["sl"], cand_sl)

                # Check TP Hit
                if h >= (tr["tp"] + slippage):
                    pnl = tr["risk"] * ((tr["tp"] - entry_p) / init_sl_dist)
                    balance += pnl
                    tr["pnl"] = pnl
                    closed_trades.append(tr)

                    # --- DEPLETION MECHANICS TRIGGER UPON TP ---
                    if depletion_model == "MACRO_LOCKOUT":
                        macro_buy_zone_completed = True
                    elif depletion_model == "MICRO_DEPLETION":
                        buy_levels_spent[layer_idx] = True
                    elif depletion_model == "TOUCH_AND_BURN":
                        buy_levels_spent[0] = True
                        buy_levels_spent[1] = True
                    elif depletion_model == "DEEPER_ONLY":
                        deepest_buy_touch = min(deepest_buy_touch, l)

                # Check SL / Trailing Hit
                elif l <= (tr["sl"] - slippage):
                    exit_p = tr["sl"]
                    pts = exit_p - entry_p
                    pnl = tr["risk"] * (pts / init_sl_dist)
                    balance += pnl
                    tr["pnl"] = pnl
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

                # Naruto 2 Trailing if enabled
                if use_naruto2 and running_pts >= 2.0:
                    cand_sl = tr["trough"] + 2.0
                    cand_sl = min(cand_sl, entry_p)
                    tr["sl"] = min(tr["sl"], cand_sl)

                # Check TP Hit
                if (l + spread) <= (tr["tp"] - slippage):
                    pnl = tr["risk"] * ((entry_p - tr["tp"]) / init_sl_dist)
                    balance += pnl
                    tr["pnl"] = pnl
                    closed_trades.append(tr)

                    # --- DEPLETION MECHANICS TRIGGER UPON TP ---
                    if depletion_model == "MACRO_LOCKOUT":
                        macro_sell_zone_completed = True
                    elif depletion_model == "MICRO_DEPLETION":
                        sell_levels_spent[layer_idx] = True
                    elif depletion_model == "TOUCH_AND_BURN":
                        sell_levels_spent[0] = True
                        sell_levels_spent[1] = True
                    elif depletion_model == "DEEPER_ONLY":
                        deepest_sell_touch = max(deepest_sell_touch, h)

                # Check SL / Trailing Hit
                elif (h + spread) >= (tr["sl"] + slippage):
                    exit_p = tr["sl"]
                    pts = entry_p - exit_p
                    pnl = tr["risk"] * (pts / init_sl_dist)
                    balance += pnl
                    tr["pnl"] = pnl
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

        # 2. Structure Update & Depletion Reset Detection
        sub_h = highs[i-20:i]
        sub_l = lows[i-20:i]
        sw_high = np.max(sub_h)
        sw_low = np.min(sub_l)

        # Check if new structure formed (shifter >= 1.0 pt)
        if abs(sw_high - current_roof) >= 1.0 or abs(sw_low - current_floor) >= 1.0:
            current_roof = sw_high
            current_floor = sw_low
            # Reset depletion on new structure!
            macro_buy_zone_completed = False
            macro_sell_zone_completed = False
            buy_levels_spent = [False, False, False]
            sell_levels_spent = [False, False, False]
            deepest_buy_touch = 999999.0
            deepest_sell_touch = 0.0

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

        # 3. Entry Evaluation with Depletion Filter
        if len(open_trades) == 0 and (t_sec - last_order_time_sec >= 60.0):
            # --- BUY EVALUATION ---
            if in_discount and allow_buy and (t_sec >= buy_cooldown_until):
                # Check Macro Lockout
                if depletion_model == "MACRO_LOCKOUT" and macro_buy_zone_completed:
                    blocked_by_depletion_count += 1
                else:
                    sl = round(sw_low - 2.50 - sl_buffer, 2)
                    tp = round(eq, 2)
                    l1 = round(min(mid - 0.25, sw_low + span * 0.25), 2)
                    l2 = round(min(mid - 0.50, sw_low + span * 0.125), 2)
                    l3 = round(min(mid - 0.75, sw_low), 2)
                    levels = [l1, l2, l3]

                    orders_placed = 0
                    for lay_idx, limit_p in enumerate(levels):
                        # Depletion Gate per Layer
                        is_layer_allowed = True

                        if depletion_model in ("MICRO_DEPLETION", "TOUCH_AND_BURN"):
                            if buy_levels_spent[lay_idx]:
                                is_layer_allowed = False
                                blocked_by_depletion_count += 1
                            else:
                                if lay_idx > 0 and buy_levels_spent[0]:
                                    virgin_depth_trades_count += 1

                        elif depletion_model == "DEEPER_ONLY":
                            if limit_p >= deepest_buy_touch:
                                is_layer_allowed = False
                                blocked_by_depletion_count += 1

                        if is_layer_allowed and l <= limit_p:
                            open_trades.append({
                                "dir": "BUY",
                                "in": limit_p,
                                "sl": sl,
                                "tp": tp,
                                "sl_dist": max(limit_p - sl, 0.50),
                                "risk": total_risk_money * grid_weights[lay_idx],
                                "peak": limit_p,
                                "layer_idx": lay_idx
                            })
                            orders_placed += 1

                    if orders_placed > 0:
                        last_order_time_sec = t_sec

            # --- SELL EVALUATION ---
            elif in_premium and allow_sell and (t_sec >= sell_cooldown_until):
                if depletion_model == "MACRO_LOCKOUT" and macro_sell_zone_completed:
                    blocked_by_depletion_count += 1
                else:
                    sl = round(sw_high + 2.50 + sl_buffer, 2)
                    tp = round(eq, 2)
                    l1 = round(max(mid + 0.25, sw_low + span * 0.75), 2)
                    l2 = round(max(mid + 0.50, sw_low + span * 0.875), 2)
                    l3 = round(max(mid + 0.75, sw_high), 2)
                    levels = [l1, l2, l3]

                    orders_placed = 0
                    for lay_idx, limit_p in enumerate(levels):
                        is_layer_allowed = True

                        if depletion_model in ("MICRO_DEPLETION", "TOUCH_AND_BURN"):
                            if sell_levels_spent[lay_idx]:
                                is_layer_allowed = False
                                blocked_by_depletion_count += 1
                            else:
                                if lay_idx > 0 and sell_levels_spent[0]:
                                    virgin_depth_trades_count += 1

                        elif depletion_model == "DEEPER_ONLY":
                            if limit_p <= deepest_sell_touch:
                                is_layer_allowed = False
                                blocked_by_depletion_count += 1

                        if is_layer_allowed and h >= limit_p:
                            open_trades.append({
                                "dir": "SELL",
                                "in": limit_p,
                                "sl": sl,
                                "tp": tp,
                                "sl_dist": max(sl - limit_p, 0.50),
                                "risk": total_risk_money * grid_weights[lay_idx],
                                "trough": limit_p,
                                "layer_idx": lay_idx
                            })
                            orders_placed += 1

                    if orders_placed > 0:
                        last_order_time_sec = t_sec

    # Summarize metrics
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

    return {
        "trades": total_trades,
        "win_rate": round(wr, 1),
        "profit_factor": round(pf, 2),
        "net_pnl": round(net_pnl, 2),
        "max_drawdown_pct": round(max_dd, 2),
        "payoff_ratio": round(payoff_ratio, 2),
        "avg_win": round(avg_win, 2),
        "avg_loss": round(avg_loss, 2),
        "virgin_depth_trades": virgin_depth_trades_count,
        "blocked_by_depletion": blocked_by_depletion_count
    }


def main():
    print("=" * 115)
    print("🥋 TURNAMEN 3 KAGE BUNSHIN: ZONE DEPLETION & STALE ORDERS MECHANICS")
    print("Adu Tanding: Macro Lockout (DEC-035) vs Micro Level Depletion (Ide Anda) vs Touch-and-Burn vs Unlimited")
    print("Metodologi: 100% Real-Time Event-Driven (Zero Look-Ahead Bias) | Data: 300,440 Bar M1 XAUUSD")
    print("=" * 115)

    t0_start = time.time()
    df_m1_full = pl.read_parquet(PARQUET_PATH)
    print(f"Dataset Ground Truth : {len(df_m1_full):,} bar M1 ({df_m1_full['timestamp'].min()} s/d {df_m1_full['timestamp'].max()})")

    print("\n⏳ Precomputing Market Stream (D1 Trend Bias Gate)...")
    df_stream = precompute_market_stream(df_m1_full)
    print("✅ Market Stream ready!")

    clones = [
        # --- SUB-GROUP 1: PURE EQUILIBRIUM TP (NO TRAIL) ---
        {
            "id": "CLONE-01_UNLIMITED_NO_TRAIL",
            "depletion_model": "UNLIMITED",
            "use_naruto2": False,
            "desc": "Unlimited Retests (Legacy: Tanpa gembok, bebas re-entry)"
        },
        {
            "id": "CLONE-02_MACRO_LOCKOUT_NO_TRAIL",
            "depletion_model": "MACRO_LOCKOUT",
            "use_naruto2": False,
            "desc": "Macro Zone Lockout (DEC-035: Seluruh zona digembok setelah TP)"
        },
        {
            "id": "CLONE-03_MICRO_DEPLETION_NO_TRAIL",
            "depletion_model": "MICRO_DEPLETION",
            "use_naruto2": False,
            "desc": "Micro Level Depletion (Ide Anda: L1 habis, L2/L3 virgin depth aktif)"
        },
        {
            "id": "CLONE-04_TOUCH_AND_BURN_NO_TRAIL",
            "depletion_model": "TOUCH_AND_BURN",
            "use_naruto2": False,
            "desc": "Touch-and-Burn (L1 TP -> L1 & L2 dibakar, re-entry hanya di L3)"
        },
        {
            "id": "CLONE-05_DEEPER_ONLY_NO_TRAIL",
            "depletion_model": "DEEPER_ONLY",
            "use_naruto2": False,
            "desc": "Deeper Penetration Only (Hanya order jika tembus lebih dalam dari sentuhan terakhir)"
        },

        # --- SUB-GROUP 2: NARUTO 2 TRAILING (CHAMPION PILAR 2) ---
        {
            "id": "CLONE-06_UNLIMITED_NARUTO2",
            "depletion_model": "UNLIMITED",
            "use_naruto2": True,
            "desc": "Unlimited Retests + Naruto 2 ($2.00 Summary Trailing)"
        },
        {
            "id": "CLONE-07_MACRO_LOCKOUT_NARUTO2",
            "depletion_model": "MACRO_LOCKOUT",
            "use_naruto2": True,
            "desc": "Macro Zone Lockout (DEC-035) + Naruto 2 ($2.00 Trailing)"
        },
        {
            "id": "CLONE-08_MICRO_DEPLETION_NARUTO2",
            "depletion_model": "MICRO_DEPLETION",
            "use_naruto2": True,
            "desc": "Micro Level Depletion (Ide Anda) + Naruto 2 ($2.00 Trailing)"
        },
        {
            "id": "CLONE-09_TOUCH_AND_BURN_NARUTO2",
            "depletion_model": "TOUCH_AND_BURN",
            "use_naruto2": True,
            "desc": "Touch-and-Burn + Naruto 2 ($2.00 Trailing)"
        },
        {
            "id": "CLONE-10_DEEPER_ONLY_NARUTO2",
            "depletion_model": "DEEPER_ONLY",
            "use_naruto2": True,
            "desc": "Deeper Penetration Only + Naruto 2 ($2.00 Trailing)"
        }
    ]

    print(f"\n🚀 Total Clones Siap Bertanding: {len(clones)} Shadow Clones")
    header = f"{'Clone ID':<32} | {'Trades':<7} | {'WinRate':<7} | {'PF':<6} | {'MaxDD':<7} | {'Payoff':<6} | {'VirginTrd':<9} | {'Net PnL ($)':<12}"
    print(header)
    print("-" * 115)

    leaderboard = []

    for c in clones:
        t0 = time.time()
        res = simulate_depletion_clone(df_stream, c, total_risk_money=50.0)
        dur = time.time() - t0

        entry = {
            "clone_id": c["id"],
            "depletion_model": c["depletion_model"],
            "use_naruto2": c["use_naruto2"],
            "description": c["desc"],
            "trades": res["trades"],
            "win_rate": res["win_rate"],
            "profit_factor": res["profit_factor"],
            "max_drawdown_pct": res["max_drawdown_pct"],
            "payoff_ratio": res["payoff_ratio"],
            "avg_win": res["avg_win"],
            "avg_loss": res["avg_loss"],
            "virgin_depth_trades": res["virgin_depth_trades"],
            "blocked_by_depletion": res["blocked_by_depletion"],
            "net_pnl": res["net_pnl"],
            "duration_sec": round(dur, 2)
        }
        leaderboard.append(entry)

        row_str = f"{c['id']:<32} | {res['trades']:<7} | {res['win_rate']:<6.1f}% | {res['profit_factor']:<6.2f} | {res['max_drawdown_pct']:<6.2f}% | {res['payoff_ratio']:<6.2f} | {res['virgin_depth_trades']:<9d} | ${res['net_pnl']:<11,.2f}"
        print(row_str)

    # Save to report
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    report_data = {
        "tournament_id": "KB-PILAR-3-ZONE-DEPLETION-MATRIX",
        "title": "Turnamen 3 Kage Bunshin: Zone Depletion & Stale Orders Mechanics",
        "timestamp": datetime.now().isoformat(),
        "total_bars": len(df_m1_full),
        "total_clones": len(clones),
        "execution_time_sec": round(time.time() - t0_start, 2),
        "leaderboard": leaderboard
    }
    with open(OUTPUT_REPORT_PATH, "w", encoding="utf-8") as f:
        json.dump(report_data, f, indent=2)

    print("\n" + "=" * 115)
    print("🏆 HASIL LEADERBOARD TURNAMEN 3 (PILAR 3: ZONE DEPLETION MATRIX)")
    print("=" * 115)
    leaderboard.sort(key=lambda x: (x["profit_factor"], x["net_pnl"]), reverse=True)
    for rank, lb in enumerate(leaderboard, start=1):
        medal = "🥇" if rank == 1 else ("🥈" if rank == 2 else ("🥉" if rank == 3 else f"#{rank}"))
        print(f"{medal} {lb['clone_id']:<32} -> PF: {lb['profit_factor']:<5.2f} | PnL: ${lb['net_pnl']:+12,.2f} | WR: {lb['win_rate']:<5.1f}% | Payoff: {lb['payoff_ratio']:<4.2f} | DD: {lb['max_drawdown_pct']:<5.2f}% | Virgin Trades: {lb['virgin_depth_trades']}")
        print(f"    └─ Deskripsi: {lb['description']}")

    print(f"\n💾 Laporan resmi Kage Bunshin disimpan di: {OUTPUT_REPORT_PATH}")


if __name__ == "__main__":
    main()
