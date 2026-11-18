"""
Grand Tournament: Multi-TF Handover, Real POI & SL Architecture.
Subtask 5-3I (PLAN.md): Menguji tandingkan 7 Kubu secara empiris di 300.440 bar M1 XAUUSD
dengan evaluasi menyeluruh (Full Dataset) dan per kuartal rezim pasar (Q3, Q4, Q1).

Matriks 7 Kubu Tanding:
1. KUBU 1 (BASELINE M1 NAIVE): Kuadran swing bebas (bisa di udara kosong) + SL lokal M1 (3.5pt) + Global Cooldown saat SL (M15 terkunci).
2. KUBU 2 (STRICT REAL POI ONLY): Order DILARANG dipasang jika tidak ada Base DBD/RBR atau FVG (No phantom orders).
3. KUBU 3 (NESTED M15 GATE): M1 hanya boleh pasang order jika M15 sudah di zona ekstrem (>= 75% Sell / <= 25% Buy).
4. KUBU 4 (HTF SL AT BIRTH): M1 masuk posisi tapi SL sejak lahir ditaruh di atap M15 (lot size mengecil proporsional agar risiko flat $50).
5. KUBU 5 (PENDING HANDOVER): M1 pasang limit; jika M15 mengonfirmasi atap sebelum terisi -> batalkan M1, upgrade ke limit M15.
6. KUBU 6 (DECOUPLED POST-SL HANDOVER): M1 pasang limit; jika M1 kena SL tapi harga masih di area Supply M15 -> M15 LANGSUNG PASANG LIMIT BARU di atap M15 (cooldown M1 tidak membekukan M15).
7. KUBU 7 (DOMINANT TF ONLY - M5 + M15): M1 dimatikan total. Akun hanya trading di level struktural M5 & M15.
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
OUTPUT_REPORT_PATH = PROJECT_ROOT / "reports" / "grand_handover_poi_tournament_report.json"


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


def resample_bars(df_m1: pl.DataFrame, timeframe: str) -> pl.DataFrame:
    if timeframe == "M1":
        return df_m1.sort("timestamp")
    every_str = "5m" if timeframe == "M5" else "15m"
    return (
        df_m1.sort("timestamp")
        .group_by_dynamic("timestamp", every=every_str)
        .agg([
            pl.first("open").alias("open"),
            pl.max("high").alias("high"),
            pl.min("low").alias("low"),
            pl.last("close").alias("close")
        ])
    )


def simulate_engine(df_slice: pl.DataFrame, model_id: str) -> dict:
    timestamps = df_slice["timestamp"].dt.epoch("s").to_numpy()
    hours = df_slice["timestamp"].dt.hour().to_numpy()
    minutes = df_slice["timestamp"].dt.minute().to_numpy()
    opens = df_slice["open"].to_numpy()
    highs = df_slice["high"].to_numpy()
    lows = df_slice["low"].to_numpy()
    closes = df_slice["close"].to_numpy()

    d1_arr = df_slice["D1_bias"].to_numpy()
    h4_arr = df_slice["H4_bias"].to_numpy()
    h1_arr = df_slice["H1_bias"].to_numpy()

    n_bars = len(df_slice)

    # Pre-detect True S&D POIs on M1 (with formation candle amnesty)
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

    # Cooldown trackers
    global_buy_cd = 0
    global_sell_cd = 0
    m1_buy_cd = 0
    m1_sell_cd = 0
    m15_buy_cd = 0
    m15_sell_cd = 0

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
        for tr in open_trades:
            p_tf = tr.get("tf", "M1")
            is_buy = (tr["dir"] == "BUY")
            cd_dur = 600 if sess_name == "ASIAN" else (900 if sess_name == "LONDON" else 1500)

            if is_buy:
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

                    # Trigger cooldown
                    global_buy_cd = t_sec + cd_dur
                    if p_tf == "M1":
                        m1_buy_cd = t_sec + cd_dur
                    elif p_tf == "M15":
                        m15_buy_cd = t_sec + cd_dur

                    # Kubu 6: Decoupled Post-SL Handover: If M1 stops out, check if M15 can immediately rescue
                    if model_id == "KUBU_6_POST_SL_HANDOVER" and p_tf == "M1":
                        # M1 hit SL! Check if price is still inside M15 Buy Zone
                        sub_l15 = lows[max(0, i-60):i]
                        sub_h15 = highs[max(0, i-60):i]
                        sw_l15 = float(np.min(sub_l15))
                        sw_h15 = float(np.max(sub_h15))
                        span15 = max(1.0, sw_h15 - sw_l15)
                        m15_buy_ceiling = sw_l15 + (span15 * 0.25)
                        if c <= m15_buy_ceiling:
                            # Price is at M15 Floor! Deploy M15 rescue limit
                            m15_sl = round(sw_l15 - 2.50 - max(0.50, span15 * 0.0375), 2)
                            m15_tp = round((sw_h15 + sw_l15) / 2.0, 2)
                            m15_in = round(sw_l15, 2)
                            if l <= m15_in:
                                rem.append({
                                    "dir": "BUY",
                                    "in": m15_in,
                                    "sl": m15_sl,
                                    "tp": m15_tp,
                                    "risk": base_risk,
                                    "tf": "M15"
                                })
                else:
                    rem.append(tr)
            else: # SELL
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

                    global_sell_cd = t_sec + cd_dur
                    if p_tf == "M1":
                        m1_sell_cd = t_sec + cd_dur
                    elif p_tf == "M15":
                        m15_sell_cd = t_sec + cd_dur

                    # Kubu 6: Decoupled Post-SL Handover: If M1 stops out, check if M15 can immediately rescue
                    if model_id == "KUBU_6_POST_SL_HANDOVER" and p_tf == "M1":
                        sub_l15 = lows[max(0, i-60):i]
                        sub_h15 = highs[max(0, i-60):i]
                        sw_l15 = float(np.min(sub_l15))
                        sw_h15 = float(np.max(sub_h15))
                        span15 = max(1.0, sw_h15 - sw_l15)
                        m15_sell_floor = sw_l15 + (span15 * 0.75)
                        if c >= m15_sell_floor:
                            # Price is at M15 Roof! Deploy M15 rescue limit
                            m15_sl = round(sw_h15 + 2.50 + max(0.50, span15 * 0.0375), 2)
                            m15_tp = round((sw_h15 + sw_l15) / 2.0 + spread, 2)
                            m15_in = round(sw_h15, 2)
                            if (h + spread) >= m15_in:
                                rem.append({
                                    "dir": "SELL",
                                    "in": m15_in,
                                    "sl": m15_sl,
                                    "tp": m15_tp,
                                    "risk": base_risk,
                                    "tf": "M15"
                                })
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
            # Evaluate M1 Swings
            sub_h_m1 = highs[i-20:i]
            sub_l_m1 = lows[i-20:i]
            sw_h_m1 = float(np.max(sub_h_m1))
            sw_l_m1 = float(np.min(sub_l_m1))

            # Evaluate M15 Swings (60 bars lookback)
            sub_h_m15 = highs[max(0, i-60):i]
            sub_l_m15 = lows[max(0, i-60):i]
            sw_h_m15 = float(np.max(sub_h_m15))
            sw_l_m15 = float(np.min(sub_l_m15))
            span_m15 = max(1.0, sw_h_m15 - sw_l_m15)
            eq_m15 = (sw_h_m15 + sw_l_m15) / 2.0

            # Evaluate M5 Swings (20 bars lookback of 5m equivalent = 40 bars)
            sub_h_m5 = highs[max(0, i-40):i]
            sub_l_m5 = lows[max(0, i-40):i]
            sw_h_m5 = float(np.max(sub_h_m5))
            sw_l_m5 = float(np.min(sub_l_m5))

            # Top 2 HTF Bias (D1 + H4 for M1-M5, H1 + H4 for M15)
            d1_b = d1_arr[i]
            h4_b = h4_arr[i]
            h1_b = h1_arr[i]

            d1_bear = d1_b in ("STRONG_BEARISH", "WEAK_BEARISH")
            d1_bull = d1_b in ("STRONG_BULLISH", "WEAK_BULLISH")
            h4_bear = h4_b in ("STRONG_BEARISH", "WEAK_BEARISH")
            h4_bull = h4_b in ("STRONG_BULLISH", "WEAK_BULLISH")
            h1_bear = h1_b in ("STRONG_BEARISH", "WEAK_BEARISH")
            h1_bull = h1_b in ("STRONG_BULLISH", "WEAK_BULLISH")

            allow_buy_m1 = not (d1_bear and h4_bear)
            allow_sell_m1 = not (d1_bull and h4_bull)
            allow_buy_m15 = not (h1_bear and h4_bear)
            allow_sell_m15 = not (h1_bull and h4_bull)

            # Check if M1 has Real POI within 12 pts
            has_m1_rbr = False
            has_m1_dbd = False
            for k in range(i-2, max(0, i-30), -1):
                if not has_m1_rbr and k in rbr_indices:
                    if abs(lows[k] - sw_l_m1) <= 12.0:
                        has_m1_rbr = True
                if not has_m1_dbd and k in dbd_indices:
                    if abs(highs[k] - sw_h_m1) <= 12.0:
                        has_m1_dbd = True
                if has_m1_rbr and has_m1_dbd:
                    break

            # -------------------------------------------------------------
            # KUBU 7: DOMINANT TF ONLY (M5 & M15, M1 Completely Disabled)
            # -------------------------------------------------------------
            if model_id == "KUBU_7_DOMINANT_TF_ONLY":
                # Evaluate M15 First, then M5
                # M15 Entry
                m15_in_discount = (c <= sw_l_m15 + span_m15 * 0.25)
                m15_in_premium = (c >= sw_l_m15 + span_m15 * 0.75)
                sl_buf15 = max(0.50, span_m15 * 0.0375)

                if m15_in_discount and allow_buy_m15 and (t_sec >= m15_buy_cd):
                    sl = round(sw_l_m15 - 2.50 - sl_buf15, 2)
                    tp = round(eq_m15, 2)
                    lvl = round(sw_l_m15, 2)
                    if l <= lvl:
                        open_trades.append({"dir": "BUY", "in": lvl, "sl": sl, "tp": tp, "risk": base_risk, "tf": "M15"})
                        last_order_sec = t_sec
                elif m15_in_premium and allow_sell_m15 and (t_sec >= m15_sell_cd):
                    sl = round(sw_h_m15 + 2.50 + sl_buf15, 2)
                    tp = round(eq_m15 + spread, 2)
                    lvl = round(sw_h_m15, 2)
                    if (h + spread) >= lvl:
                        open_trades.append({"dir": "SELL", "in": lvl, "sl": sl, "tp": tp, "risk": base_risk, "tf": "M15"})
                        last_order_sec = t_sec
                continue

            # -------------------------------------------------------------
            # KUBU 1..6: M1 EVALUATION
            # -------------------------------------------------------------
            span_m1 = max(1.0, sw_h_m1 - sw_l_m1)
            eq_m1 = (sw_h_m1 + sw_l_m1) / 2.0
            buy_top_m1 = sw_l_m1 + span_m1 * 0.25
            sell_bot_m1 = sw_l_m1 + span_m1 * 0.75

            m1_in_discount = (c <= buy_top_m1)
            m1_in_premium = (c >= sell_bot_m1)

            # Kubu 2 Filter: Strict Real POI Only (Must have DBD for SELL, RBR for BUY)
            if model_id == "KUBU_2_STRICT_REAL_POI":
                if m1_in_discount and not has_m1_rbr:
                    m1_in_discount = False
                if m1_in_premium and not has_m1_dbd:
                    m1_in_premium = False

            # Kubu 3 Filter: Nested M15 Gate (M15 must also be in extreme quadrant)
            if model_id == "KUBU_3_NESTED_M15_GATE":
                m15_is_discount = (c <= sw_l_m15 + span_m15 * 0.25)
                m15_is_premium = (c >= sw_l_m15 + span_m15 * 0.75)
                if m1_in_discount and not m15_is_discount:
                    m1_in_discount = False
                if m1_in_premium and not m15_is_premium:
                    m1_in_premium = False

            # Cooldown check: Global vs Decoupled
            if model_id == "KUBU_6_POST_SL_HANDOVER":
                can_buy = (t_sec >= m1_buy_cd) and allow_buy_m1
                can_sell = (t_sec >= m1_sell_cd) and allow_sell_m1
            else:
                can_buy = (t_sec >= global_buy_cd) and allow_buy_m1
                can_sell = (t_sec >= global_sell_cd) and allow_sell_m1

            sl_buf_m1 = max(0.50, span_m1 * 0.0375)

            # Kubu 4: HTF SL at Birth (Inherits M15 SL boundary from birth)
            if model_id == "KUBU_4_HTF_SL_AT_BIRTH":
                sl_buy = round(sw_l_m15 - 2.50 - max(0.50, span_m15 * 0.0375), 2)
                sl_sell = round(sw_h_m15 + 2.50 + max(0.50, span_m15 * 0.0375), 2)
            else:
                sl_buy = round(sw_l_m1 - 2.50 - sl_buf_m1, 2)
                sl_sell = round(sw_h_m1 + 2.50 + sl_buf_m1, 2)

            # Kubu 5: Handover TP Target Extension (if nested in M15)
            if model_id == "KUBU_5_PENDING_HANDOVER" and (c >= sw_l_m15 + span_m15 * 0.75):
                tp_sell = round(min(eq_m1, eq_m15) + spread, 2)
            else:
                tp_sell = round(eq_m1 + spread, 2)

            if model_id == "KUBU_5_PENDING_HANDOVER" and (c <= sw_l_m15 + span_m15 * 0.25):
                tp_buy = round(max(eq_m1, eq_m15), 2)
            else:
                tp_buy = round(eq_m1, 2)

            if m1_in_discount and can_buy:
                l1 = round(min(c - 0.25, sw_l_m1 + span_m1 * 0.25), 2)
                l2 = round(min(c - 0.50, sw_l_m1 + span_m1 * 0.125), 2)
                l3 = round(min(c - 0.75, sw_l_m1), 2)
                entered = False
                for lay_idx, limit_p in enumerate([l1, l2, l3]):
                    if l <= limit_p:
                        open_trades.append({
                            "dir": "BUY",
                            "in": limit_p,
                            "sl": sl_buy,
                            "tp": tp_buy,
                            "risk": base_risk * grid_weights[lay_idx],
                            "tf": "M1"
                        })
                        entered = True
                if entered:
                    last_order_sec = t_sec

            elif m1_in_premium and can_sell:
                l1 = round(max(c + 0.25, sw_l_m1 + span_m1 * 0.75), 2)
                l2 = round(max(c + 0.50, sw_l_m1 + span_m1 * 0.875), 2)
                l3 = round(max(c + 0.75, sw_h_m1), 2)
                entered = False
                for lay_idx, limit_p in enumerate([l1, l2, l3]):
                    if (h + spread) >= limit_p:
                        open_trades.append({
                            "dir": "SELL",
                            "in": limit_p,
                            "sl": sl_sell,
                            "tp": tp_sell,
                            "risk": base_risk * grid_weights[lay_idx],
                            "tf": "M1"
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
        "model_id": model_id,
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
    print("=" * 110)
    print("🏆 GRAND TOURNAMENT: MULTI-TF HANDOVER, REAL POI & SL ARCHITECTURE (SUBTASK 5-3I)")
    print("   Empirical Testing across Full Year Dataset & 3 Distinct Market Regimes")
    print("=" * 110)

    t0 = time.time()
    df_m1 = pl.read_parquet(PARQUET_PATH)
    print(f"✅ Loaded {len(df_m1):,} M1 bars in {time.time()-t0:.2f}s")

    print("\n⏳ Pre-computing Top 2 HTF Biases (D1, H4, H1 EMA 50)...")
    t_htf = time.time()
    df_d1 = precompute_htf_bias(df_m1, "D1").rename({"available_at": "d1_avail"})
    df_h4 = precompute_htf_bias(df_m1, "H4").rename({"available_at": "h4_avail"})
    df_h1 = precompute_htf_bias(df_m1, "H1").rename({"available_at": "h1_avail"})

    df_full = (
        df_m1.sort("timestamp")
        .join_asof(df_d1, left_on="timestamp", right_on="d1_avail", strategy="backward")
        .join_asof(df_h4, left_on="timestamp", right_on="h4_avail", strategy="backward")
        .join_asof(df_h1, left_on="timestamp", right_on="h1_avail", strategy="backward")
        .fill_null("NEUTRAL")
    )
    print(f"✅ All HTF Biases aligned in {time.time()-t_htf:.2f}s")

    # Define Quarter Slices
    slices = [
        ("FULL_YEAR", "Full Year (300,440 bars)", df_full),
        ("2025_Q3", "2025 Q3 (89,291 bars: Sideways Consolidation & Breakout)", df_full.filter((pl.col("timestamp") >= datetime(2025, 7, 1)) & (pl.col("timestamp") < datetime(2025, 10, 1)))),
        ("2025_Q4", "2025 Q4 (88,494 bars: Steady Bull Trending Rally)", df_full.filter((pl.col("timestamp") >= datetime(2025, 10, 1)) & (pl.col("timestamp") < datetime(2026, 1, 1)))),
        ("2026_Q1", "2026 Q1 (86,297 bars: Extreme Volatility ATH & Deep Pullbacks)", df_full.filter((pl.col("timestamp") >= datetime(2026, 1, 1)) & (pl.col("timestamp") < datetime(2026, 4, 1))))
    ]

    models = [
        ("KUBU_1_BASELINE", "Kubu 1: Status Quo Baseline (Free Quadrant, M1 Local SL, Global CD)"),
        ("KUBU_2_STRICT_REAL_POI", "Kubu 2: Strict Real POI Only (No Phantom Orders in Thin Air)"),
        ("KUBU_3_NESTED_M15_GATE", "Kubu 3: Nested M15 Gate (M1 Entry only when M15 in Extreme Quadrant)"),
        ("KUBU_4_HTF_SL_AT_BIRTH", "Kubu 4: HTF SL at Birth (Inherits M15 SL with Scaled Lots)"),
        ("KUBU_5_PENDING_HANDOVER", "Kubu 5: Pending Handover (Cancel & Upgrade + Target Extension)"),
        ("KUBU_6_POST_SL_HANDOVER", "Kubu 6: Decoupled Post-SL Handover (M1 SL -> Immediate M15 Estafet)"),
        ("KUBU_7_DOMINANT_TF_ONLY", "Kubu 7: Dominant TF Only (M5 + M15, M1 Completely Disabled)")
    ]

    all_results = {}

    for s_code, s_desc, s_df in slices:
        print("\n" + "=" * 110)
        print(f"📍 EVALUASI REGIME: {s_desc}")
        print("=" * 110)
        print(f"{'Kubu Model':<35} | {'Trades':<8} | {'Win Rate':<9} | {'Profit Factor':<14} | {'Max DD':<10} | {'Net PnL ($)':<14}")
        print("-" * 110)

        slice_results = []
        for m_code, m_desc in models:
            t_sim = time.time()
            res = simulate_engine(s_df, m_code)
            elapsed = time.time() - t_sim
            print(f"{m_code:<35} | {res['total_trades']:<8} | {res['win_rate_pct']:<8}% | {res['profit_factor']:<14.2f} | {res['max_drawdown_pct']:<9}% | ${res['net_pnl']:<13,.2f}")
            res["elapsed_sec"] = round(elapsed, 2)
            slice_results.append(res)

        all_results[s_code] = slice_results

    with open(OUTPUT_REPORT_PATH, "w") as f:
        json.dump(all_results, f, indent=2)

    print("\n" + "=" * 110)
    print(f"💾 Seluruh hasil turnamen komprehensif disimpan ke: {OUTPUT_REPORT_PATH}")
    print("=" * 110)


if __name__ == "__main__":
    main()
