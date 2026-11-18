"""
Before vs After Comparative Audit:
Baseline Status Quo vs Integrated Engine (Nested M15 Gate + Strict Real POI Filter).
Evaluates 300,440 M1 bars across 4 dataset slices:
- Full Year
- 2025 Q3 (Consolidation & Sideways Breakout)
- 2025 Q4 (Steady Bull Trending)
- 2026 Q1 (Extreme Volatility ATH & Pullbacks)
"""

import sys
import time
import json
from pathlib import Path
from datetime import datetime, timedelta
import numpy as np
import polars as pl

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

PARQUET_PATH = PROJECT_ROOT / "data" / "parquet" / "XAUUSD" / "M1" / "XAUUSD_M1.parquet"
OUTPUT_REPORT_PATH = PROJECT_ROOT / "reports" / "before_after_m15_gate_strict_poi_audit.json"


def precompute_htf_bias(df_m1: pl.DataFrame, htf_code: str) -> pl.DataFrame:
    tf_map = {
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
            (pl.col("timestamp") + duration).alias(f"{htf_code}_avail")
        ])
        .select([f"{htf_code}_avail", f"{htf_code}_bias"])
    )
    return df_htf


def simulate_model(df_slice: pl.DataFrame, nested_m15_gate: bool, strict_poi: bool) -> dict:
    timestamps = df_slice["timestamp"].dt.epoch("s").to_numpy()
    hours = df_slice["timestamp"].dt.hour().to_numpy()
    minutes = df_slice["timestamp"].dt.minute().to_numpy()
    opens = df_slice["open"].to_numpy()
    highs = df_slice["high"].to_numpy()
    lows = df_slice["low"].to_numpy()
    closes = df_slice["close"].to_numpy()

    d1_arr = df_slice["D1_bias"].to_numpy()
    h4_arr = df_slice["H4_bias"].to_numpy()

    n_bars = len(df_slice)

    # Precompute RBR and DBD bases on M1
    leg_in_bull = (closes[:-2] > opens[:-2]) & ((closes[:-2] - opens[:-2]) / np.maximum(highs[:-2] - lows[:-2], 0.1) >= 0.40)
    base_rng = np.maximum(highs[1:-1] - lows[1:-1], 0.1)
    base_body = np.abs(closes[1:-1] - opens[1:-1])
    is_base = (base_body / base_rng) <= 0.50
    leg_out_bull = (closes[2:] > highs[1:-1]) & (closes[2:] > opens[2:])
    fvg_bull = lows[2:] > highs[:-2]
    rbr_mask = leg_in_bull & is_base & leg_out_bull & fvg_bull
    rbr_indices = set(np.where(rbr_mask)[0] + 1)

    leg_in_bear = (opens[:-2] > closes[:-2]) & ((opens[:-2] - closes[:-2]) / np.maximum(highs[:-2] - lows[:-2], 0.1) >= 0.40)
    leg_out_bear = (closes[2:] < lows[1:-1]) & (closes[2:] < opens[2:])
    fvg_bear = highs[2:] < lows[:-2]
    dbd_mask = leg_in_bear & is_base & leg_out_bear & fvg_bear
    dbd_indices = set(np.where(dbd_mask)[0] + 1)

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
    last_order_sec = 0

    open_trades = []
    closed_trades = []

    grid_weights = [0.25, 0.35, 0.40]
    base_risk = 50.0
    spread = 0.35
    slippage = 0.05

    for i in range(45, n_bars):
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
        cd_dur = 600 if sess_name == "ASIAN" else (900 if sess_name == "LONDON" else 1500)
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

        if len(open_trades) == 0 and (t_sec - last_order_sec >= 60.0):
            sub_h = highs[i-20:i]
            sub_l = lows[i-20:i]
            sw_high = float(np.max(sub_h))
            sw_low = float(np.min(sub_l))
            span = max(1.0, sw_high - sw_low)
            eq = (sw_high + sw_low) / 2.0

            buy_top = sw_low + span * 0.25
            sell_bot = sw_low + span * 0.75

            in_discount = (c <= buy_top)
            in_premium = (c >= sell_bot)

            # Top 2 HTF Bias (D1 + H4 Permissive OR)
            d1_b = d1_arr[i]
            h4_b = h4_arr[i]
            d1_bear = d1_b in ("STRONG_BEARISH", "WEAK_BEARISH")
            d1_bull = d1_b in ("STRONG_BULLISH", "WEAK_BULLISH")
            h4_bear = h4_b in ("STRONG_BEARISH", "WEAK_BEARISH")
            h4_bull = h4_b in ("STRONG_BULLISH", "WEAK_BULLISH")

            allow_buy = not (d1_bear and h4_bear)
            allow_sell = not (d1_bull and h4_bull)

            # Nested M15 Gate Filter
            if nested_m15_gate:
                sub_h15 = highs[max(0, i-60):i]
                sub_l15 = lows[max(0, i-60):i]
                sw_h15 = float(np.max(sub_h15))
                sw_l15 = float(np.min(sub_l15))
                span15 = max(1.0, sw_h15 - sw_l15)
                m15_in_discount = (c <= sw_l15 + span15 * 0.25)
                m15_in_premium = (c >= sw_l15 + span15 * 0.75)
                if in_discount and not m15_in_discount:
                    in_discount = False
                if in_premium and not m15_in_premium:
                    in_premium = False

            # Strict Real POI Filter
            if strict_poi:
                has_rbr = False
                has_dbd = False
                for k in range(i-2, max(0, i-30), -1):
                    if not has_rbr and k in rbr_indices:
                        if abs(lows[k] - sw_low) <= 12.0:
                            has_rbr = True
                    if not has_dbd and k in dbd_indices:
                        if abs(highs[k] - sw_high) <= 12.0:
                            has_dbd = True
                    if has_rbr and has_dbd:
                        break
                if in_discount and not has_rbr:
                    in_discount = False
                if in_premium and not has_dbd:
                    in_premium = False

            sl_buf = max(0.50, span * 0.0375)

            if in_discount and allow_buy and (t_sec >= buy_cooldown_until):
                sl = round(sw_low - 2.50 - sl_buf, 2)
                tp = round(eq, 2)
                l1 = round(min(c - 0.25, sw_low + span * 0.25), 2)
                l2 = round(min(c - 0.50, sw_low + span * 0.125), 2)
                l3 = round(min(c - 0.75, sw_low), 2)
                entered = False
                for lay_idx, limit_p in enumerate([l1, l2, l3]):
                    if l <= limit_p:
                        open_trades.append({
                            "dir": "BUY",
                            "in": limit_p,
                            "sl": sl,
                            "tp": tp,
                            "risk": base_risk * grid_weights[lay_idx]
                        })
                        entered = True
                if entered:
                    last_order_sec = t_sec

            elif in_premium and allow_sell and (t_sec >= sell_cooldown_until):
                sl = round(sw_high + 2.50 + sl_buf, 2)
                tp = round(eq + spread, 2)
                l1 = round(max(c + 0.25, sw_low + span * 0.75), 2)
                l2 = round(max(c + 0.50, sw_low + span * 0.875), 2)
                l3 = round(max(c + 0.75, sw_high), 2)
                entered = False
                for lay_idx, limit_p in enumerate([l1, l2, l3]):
                    if (h + spread) >= limit_p:
                        open_trades.append({
                            "dir": "SELL",
                            "in": limit_p,
                            "sl": sl,
                            "tp": tp,
                            "risk": base_risk * grid_weights[lay_idx]
                        })
                        entered = True
                if entered:
                    last_order_sec = t_sec

    tot = len(closed_trades)
    wins = [tr for tr in closed_trades if tr["pnl"] > 0]
    losses = [tr for tr in closed_trades if tr["pnl"] < 0]
    wr = (len(wins) / tot * 100.0) if tot > 0 else 0.0
    tot_win_usd = sum(tr["pnl"] for tr in wins)
    tot_loss_usd = abs(sum(tr["pnl"] for tr in losses))
    pf = (tot_win_usd / tot_loss_usd) if tot_loss_usd > 0 else 999.0
    net_pnl = balance - 10000.0

    return {
        "total_trades": tot,
        "wins": len(wins),
        "losses": len(losses),
        "win_rate_pct": round(wr, 2),
        "profit_factor": round(pf, 2),
        "max_drawdown_pct": round(max_dd, 2),
        "net_pnl": round(net_pnl, 2),
        "final_balance": round(balance, 2)
    }


def main():
    print("=" * 115)
    print("📊 BEFORE VS AFTER COMPARATIVE AUDIT: NESTED M15 GATE & STRICT REAL POI")
    print("   Dataset: 300,440 M1 Bars XAUUSD (Zero Look-Ahead Bias)")
    print("=" * 115)

    t0 = time.time()
    df_m1 = pl.read_parquet(PARQUET_PATH)
    print(f"✅ Loaded {len(df_m1):,} M1 bars in {time.time()-t0:.2f}s")

    print("\n⏳ Pre-computing Top 2 HTF Biases (D1 & H4 EMA 50)...")
    t_htf = time.time()
    df_d1 = precompute_htf_bias(df_m1, "D1")
    df_h4 = precompute_htf_bias(df_m1, "H4")

    df_full = (
        df_m1.sort("timestamp")
        .join_asof(df_d1, left_on="timestamp", right_on="D1_avail", strategy="backward")
        .join_asof(df_h4, left_on="timestamp", right_on="H4_avail", strategy="backward")
        .fill_null("NEUTRAL")
    )
    print(f"✅ HTF Biases aligned in {time.time()-t_htf:.2f}s")

    slices = [
        ("FULL_YEAR", "Full Year (300,440 bars)", df_full),
        ("2025_Q3", "2025 Q3 (89,291 bars: Sideways Consolidation & Breakout)", df_full.filter((pl.col("timestamp") >= datetime(2025, 7, 1)) & (pl.col("timestamp") < datetime(2025, 10, 1)))),
        ("2025_Q4", "2025 Q4 (88,494 bars: Steady Bull Trending Rally)", df_full.filter((pl.col("timestamp") >= datetime(2025, 10, 1)) & (pl.col("timestamp") < datetime(2026, 1, 1)))),
        ("2026_Q1", "2026 Q1 (86,297 bars: Extreme Volatility ATH & Deep Pullbacks)", df_full.filter((pl.col("timestamp") >= datetime(2026, 1, 1)) & (pl.col("timestamp") < datetime(2026, 4, 1))))
    ]

    all_results = {}

    for s_code, s_desc, s_df in slices:
        print("\n" + "=" * 115)
        print(f"📍 REGIME: {s_desc}")
        print("=" * 115)
        print(f"{'Konfigurasi Engine':<40} | {'Trades':<8} | {'Win Rate':<9} | {'Profit Factor':<14} | {'Max DD':<10} | {'Net PnL ($)':<14}")
        print("-" * 115)

        # 1. BEFORE (Status Quo Baseline)
        res_before = simulate_model(s_df, nested_m15_gate=False, strict_poi=False)
        print(f"{'1. BEFORE (Status Quo Baseline)':<40} | {res_before['total_trades']:<8} | {res_before['win_rate_pct']:<8}% | {res_before['profit_factor']:<14.2f} | {res_before['max_drawdown_pct']:<9}% | ${res_before['net_pnl']:<13,.2f}")

        # 2. AFTER (Nested M15 Gate Only)
        res_gate = simulate_model(s_df, nested_m15_gate=True, strict_poi=False)
        print(f"{'2. AFTER (Nested M15 Gate Only)':<40} | {res_gate['total_trades']:<8} | {res_gate['win_rate_pct']:<8}% | {res_gate['profit_factor']:<14.2f} | {res_gate['max_drawdown_pct']:<9}% | ${res_gate['net_pnl']:<13,.2f}")

        # 3. AFTER (Strict Real POI Only)
        res_poi = simulate_model(s_df, nested_m15_gate=False, strict_poi=True)
        print(f"{'3. AFTER (Strict Real POI Only)':<40} | {res_poi['total_trades']:<8} | {res_poi['win_rate_pct']:<8}% | {res_poi['profit_factor']:<14.2f} | {res_poi['max_drawdown_pct']:<9}% | ${res_poi['net_pnl']:<13,.2f}")

        # 4. AFTER (Integrated: Gate + Strict POI)
        res_both = simulate_model(s_df, nested_m15_gate=True, strict_poi=True)
        print(f"{'4. AFTER (Integrated: M15 Gate + POI)':<40} | {res_both['total_trades']:<8} | {res_both['win_rate_pct']:<8}% | {res_both['profit_factor']:<14.2f} | {res_both['max_drawdown_pct']:<9}% | ${res_both['net_pnl']:<13,.2f}")

        all_results[s_code] = {
            "before": res_before,
            "after_m15_gate": res_gate,
            "after_strict_poi": res_poi,
            "after_integrated": res_both
        }

    with open(OUTPUT_REPORT_PATH, "w") as f:
        json.dump(all_results, f, indent=2)

    print("\n" + "=" * 115)
    print(f"📁 Laporan audit Before vs After disimpan ke: {OUTPUT_REPORT_PATH}")
    print("=" * 115)


if __name__ == "__main__":
    main()
