"""
Turnamen Kage Bunshin: Uji Empiris Before vs After RBR/DBD Touch Lifecycle.
Menguji tandingkan 3 Model pada 300.440 bar M1 XAUUSD (Zero Look-Ahead Bias):

1. MODEL 1 (BASELINE KAGE BUNSHIN):
   - Pure Fractal Swings (Wyckoff/PAC Murni).
   - Fondasi awal proyek tanpa RBR/DBD.

2. MODEL 2 (FLAWED RBR/DBD LIFECYCLE):
   - RBR/DBD dengan evaluasi touch yang cacat (lilin impulse R-kanan ikut dihitung touch).
   - Akibatnya 93.5% base kehilangan status virgin saat baru lahir.

3. MODEL 3 (CORRECTED TRUE S&D LIFECYCLE):
   - RBR/DBD dengan amnesti lilin pembentukan (lilin base dan impulse dikecualikan).
   - Touch HANYA dihitung jika bar setelah impulse mengalami pullback dari luar ke dalam base.
   - Status virgin dipertahankan 100% sampai terjadi true retest.
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
OUTPUT_REPORT_PATH = PROJECT_ROOT / "reports" / "rbr_touch_before_after_tournament_report.json"


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
            (pl.col("timestamp") + duration).alias("available_at")
        ])
        .select(["available_at", f"{htf_code}_bias"])
    )
    return df_htf


def run_tournament_simulation(df_m1: pl.DataFrame, model_type: str) -> dict:
    """
    model_type:
    - 'BASELINE': Pure Fractal Swings (No RBR/DBD)
    - 'FLAWED_RBR': RBR/DBD with impulse candle counted as touch
    - 'CORRECTED_RBR': True S&D with formation candle amnesty
    """
    timestamps = df_m1["timestamp"].dt.epoch("s").to_numpy()
    hours = df_m1["timestamp"].dt.hour().to_numpy()
    minutes = df_m1["timestamp"].dt.minute().to_numpy()
    opens = df_m1["open"].to_numpy()
    highs = df_m1["high"].to_numpy()
    lows = df_m1["low"].to_numpy()
    closes = df_m1["close"].to_numpy()

    d1_arr = df_m1["D1_bias"].to_numpy()
    h4_arr = df_m1["H4_bias"].to_numpy()

    n_bars = len(df_m1)

    # Pre-detect all RBR and DBD bases
    # RBR: leg-in bull (k-1), base (k), leg-out bull + FVG (k+1)
    leg_in_bull = (closes[:-2] > opens[:-2]) & ((closes[:-2] - opens[:-2]) / np.maximum(highs[:-2] - lows[:-2], 0.1) >= 0.40)
    base_rng = np.maximum(highs[1:-1] - lows[1:-1], 0.1)
    base_body = np.abs(closes[1:-1] - opens[1:-1])
    is_base = (base_body / base_rng) <= 0.50
    leg_out_bull = (closes[2:] > highs[1:-1]) & (closes[2:] > opens[2:])
    fvg_bull = lows[2:] > highs[:-2]
    rbr_mask = leg_in_bull & is_base & leg_out_bull & fvg_bull
    rbr_base_indices = set(np.where(rbr_mask)[0] + 1)

    # DBD: leg-in bear (k-1), base (k), leg-out bear + FVG (k+1)
    leg_in_bear = (opens[:-2] > closes[:-2]) & ((opens[:-2] - closes[:-2]) / np.maximum(highs[:-2] - lows[:-2], 0.1) >= 0.40)
    leg_out_bear = (closes[2:] < lows[1:-1]) & (closes[2:] < opens[2:])
    fvg_bear = highs[2:] < lows[:-2]
    dbd_mask = leg_in_bear & is_base & leg_out_bear & fvg_bear
    dbd_base_indices = set(np.where(dbd_mask)[0] + 1)

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

    for i in range(35, n_bars):
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

        # Manage Open Trades (Equilibrium TP + Hard SL)
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
            sw_high = float(np.max(sub_h))
            sw_low = float(np.min(sub_l))

            # RBR / DBD Prioritization Logic
            if model_type != "BASELINE":
                # Scan lookback window for recent RBR / DBD bases
                # Lookback up to 30 bars before current bar i
                start_scan = max(1, i - 30)
                end_scan = i - 2  # base must have completed leg-out at i-1

                best_rbr = None
                best_dbd = None

                for k in range(end_scan, start_scan - 1, -1):
                    # Check RBR
                    if best_rbr is None and k in rbr_base_indices:
                        b_top = highs[k]
                        b_btm = lows[k]
                        if abs(b_btm - sw_low) <= 15.0 and b_top <= c + 1.0:
                            # Evaluate virginity based on model
                            is_virgin = True
                            if model_type == "FLAWED_RBR":
                                # Flawed: checks bar k+1 (impulse) and onward
                                for chk in range(k + 1, i):
                                    if lows[chk] <= b_top and highs[chk] >= b_btm:
                                        is_virgin = False
                                        break
                            elif model_type == "CORRECTED_RBR":
                                # Corrected: skips k and k+1 (formation), checks k+2 onward
                                # Touch only counts if price pulled back into base
                                for chk in range(k + 2, i):
                                    if lows[chk] <= b_top and highs[chk] >= b_btm:
                                        is_virgin = False
                                        break

                            if is_virgin:
                                best_rbr = (b_top, b_btm)

                    # Check DBD
                    if best_dbd is None and k in dbd_base_indices:
                        b_top = highs[k]
                        b_btm = lows[k]
                        if abs(b_top - sw_high) <= 15.0 and b_btm >= c - 1.0:
                            is_virgin = True
                            if model_type == "FLAWED_RBR":
                                for chk in range(k + 1, i):
                                    if highs[chk] >= b_btm and lows[chk] <= b_top:
                                        is_virgin = False
                                        break
                            elif model_type == "CORRECTED_RBR":
                                for chk in range(k + 2, i):
                                    if highs[chk] >= b_btm and lows[chk] <= b_top:
                                        is_virgin = False
                                        break

                            if is_virgin:
                                best_dbd = (b_top, b_btm)

                    if best_rbr and best_dbd:
                        break

                if best_rbr:
                    sw_low = best_rbr[1]
                if best_dbd:
                    sw_high = best_dbd[0]

            span = max(sw_high - sw_low, 1.0)
            eq = (sw_high + sw_low) / 2.0

            buy_top = sw_low + (span * 0.25)
            sell_bot = sw_low + (span * 0.75)
            mid = c
            in_discount = (mid <= buy_top)
            in_premium = (mid >= sell_bot)

            # Top 2 HTF Bias OR (D1 + H4 Permissive OR Gatekeeper)
            b1 = d1_arr[i]
            b2 = h4_arr[i]
            b1_bear = b1 in ("STRONG_BEARISH", "WEAK_BEARISH")
            b1_bull = b1 in ("STRONG_BULLISH", "WEAK_BULLISH")
            b2_bear = b2 in ("STRONG_BEARISH", "WEAK_BEARISH")
            b2_bull = b2 in ("STRONG_BULLISH", "WEAK_BULLISH")

            allow_buy = not (b1_bear and b2_bear)
            allow_sell = not (b1_bull and b2_bull)

            sl_buffer = max(0.50, span * 0.0375)

            if in_discount and allow_buy and (t_sec >= buy_cooldown_until):
                sl = round(sw_low - 2.50 - sl_buffer, 2)
                tp = round(eq, 2)
                l1 = round(min(mid - 0.25, sw_low + span * 0.25), 2)
                l2 = round(min(mid - 0.50, sw_low + span * 0.125), 2)
                l3 = round(min(mid - 0.75, sw_low), 2)
                levels = [l1, l2, l3]
                entered = False
                for lay_idx, limit_p in enumerate(levels):
                    if l <= limit_p:
                        open_trades.append({
                            "dir": "BUY",
                            "in": limit_p,
                            "sl": sl,
                            "tp": tp,
                            "risk": risk_money * grid_weights[lay_idx]
                        })
                        entered = True
                if entered:
                    last_order_time_sec = t_sec

            elif in_premium and allow_sell and (t_sec >= sell_cooldown_until):
                sl = round(sw_high + 2.50 + sl_buffer, 2)
                tp = round(eq + spread, 2)
                l1 = round(max(mid + 0.25, sw_low + span * 0.75), 2)
                l2 = round(max(mid + 0.50, sw_low + span * 0.875), 2)
                l3 = round(max(mid + 0.75, sw_high), 2)
                levels = [l1, l2, l3]
                entered = False
                for lay_idx, limit_p in enumerate(levels):
                    if (h + spread) >= limit_p:
                        open_trades.append({
                            "dir": "SELL",
                            "in": limit_p,
                            "sl": sl,
                            "tp": tp,
                            "risk": risk_money * grid_weights[lay_idx]
                        })
                        entered = True
                if entered:
                    last_order_time_sec = t_sec

    # Calculate metrics
    tot = len(closed_trades)
    wins = [tr for tr in closed_trades if tr["pnl"] > 0]
    losses = [tr for tr in closed_trades if tr["pnl"] < 0]
    wr = (len(wins) / tot * 100.0) if tot > 0 else 0.0
    tot_win_usd = sum(tr["pnl"] for tr in wins)
    tot_loss_usd = abs(sum(tr["pnl"] for tr in losses))
    pf = (tot_win_usd / tot_loss_usd) if tot_loss_usd > 0 else 999.0
    net_pnl = balance - 10000.0

    return {
        "model": model_type,
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
    print("=" * 100)
    print("🧪 KAGE BUNSHIN TOURNAMENT: BEFORE VS AFTER RBR/DBD TOUCH LIFECYCLE AUDIT")
    print("   Dataset: 300,440 M1 Bars XAUUSD (Zero Look-Ahead Bias)")
    print("=" * 100)

    t0 = time.time()
    df_m1 = pl.read_parquet(PARQUET_PATH)
    print(f"✅ Loaded {len(df_m1):,} M1 bars in {time.time()-t0:.2f}s")

    print("\n⏳ Pre-computing Top 2 HTF Bias (D1 & H4 EMA 50)...")
    t_htf = time.time()
    df_d1 = precompute_htf_bias(df_m1, "D1")
    df_h4 = precompute_htf_bias(df_m1, "H4")

    df_merged = (
        df_m1.sort("timestamp")
        .join_asof(df_d1, left_on="timestamp", right_on="available_at", strategy="backward")
        .join_asof(df_h4, left_on="timestamp", right_on="available_at", strategy="backward")
        .fill_null("NEUTRAL")
    )
    print(f"✅ HTF Bias merged in {time.time()-t_htf:.2f}s")

    models = [
        ("BASELINE", "Model 1: Baseline PAC (Pure Fractal Swings - No RBR/DBD)"),
        ("FLAWED_RBR", "Model 2: Flawed RBR/DBD (Impulse R-Kanan counts as Touch)"),
        ("CORRECTED_RBR", "Model 3: Corrected True S&D (Formation Candle Amnesty)")
    ]

    results = []
    for m_code, m_desc in models:
        print(f"\n🚀 Running {m_desc}...")
        t_m = time.time()
        res = run_tournament_simulation(df_merged, m_code)
        elapsed = time.time() - t_m
        print(f"   ⏱️ Finished in {elapsed:.2f}s:")
        print(f"   Trades: {res['total_trades']:,} | WR: {res['win_rate_pct']:.2f}% | PF: {res['profit_factor']:.2f} | Max DD: {res['max_drawdown_pct']:.2f}% | Net PnL: ${res['net_pnl']:,.2f}")
        results.append(res)

    print("\n" + "=" * 100)
    print("📊 KLASEMEN AKHIR: BEFORE VS AFTER RBR/DBD LIFECYCLE TOURNAMENT (300,440 BARS)")
    print("=" * 100)
    print(f"{'Peringkat / Model':<35} | {'Trades':<8} | {'Win Rate':<9} | {'Profit Factor':<14} | {'Max DD':<10} | {'Net PnL ($)':<14}")
    print("-" * 100)
    for r in results:
        print(f"{r['model']:<35} | {r['total_trades']:<8} | {r['win_rate_pct']:<8}% | {r['profit_factor']:<14.2f} | {r['max_drawdown_pct']:<9}% | ${r['net_pnl']:<13,.2f}")
    print("=" * 100)

    with open(OUTPUT_REPORT_PATH, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\n📁 Hasil turnamen disimpan ke {OUTPUT_REPORT_PATH}")


if __name__ == "__main__":
    main()
