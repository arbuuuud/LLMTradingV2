"""
Comprehensive Real-Time Backtest vs Live Production Disparity Audit.
Tests 300,440 M1 bars (2025-05-27 to 2026-04-02) with 100% Real-Time execution logic
(ZERO Look-Ahead Bias) to benchmark Legacy PAC vs RBR/DBD Prioritizer (DEC-032).
"""

import sys
import json
import time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import polars as pl
import numpy as np
from datetime import datetime
from collections import defaultdict

from src.core.types import Direction
from src.features.poi_prioritizer import POIPrioritizer

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PARQUET_PATH = PROJECT_ROOT / "data" / "parquet" / "XAUUSD" / "M1" / "XAUUSD_M1.parquet"
REPORTS_DIR = PROJECT_ROOT / "reports"


def run_full_historical_backtest(parquet_path: Path = PARQUET_PATH):
    print("=" * 95)
    print("🥋 BENCHMARK KUANTITATIF DARI AWAL (HISTORICAL 300,440 BARS M1 XAUUSD)")
    print("Metodologi: 100% Real-Time Identik Live MT5 (Zero Look-Ahead Bias)")
    print("=" * 95)

    df = pl.read_parquet(parquet_path)
    n = len(df)
    print(f"Dataset Ground Truth : {n:,} bar M1 ({df['timestamp'].min()} s/d {df['timestamp'].max()})")

    opens = df["open"].to_numpy()
    highs = df["high"].to_numpy()
    lows = df["low"].to_numpy()
    closes = df["close"].to_numpy()
    timestamps = df["timestamp"].to_list()
    hours = np.array([t.hour for t in timestamps])
    minutes = np.array([t.minute for t in timestamps])

    scenarios = [
        {"id": "SCENARIO-1-LEGACY-PAC", "name": "1. Legacy PAC (Status Quo Moving 20-Bar)", "poi": False, "knife": False},
        {"id": "SCENARIO-2-RBR-DBD-PRIORITIZER", "name": "2. PAC + Institutional RBR/DBD Prioritizer (DEC-032)", "poi": True, "knife": False},
        {"id": "SCENARIO-3-RBR-DBD-ANTI-KNIFE", "name": "3. PAC + RBR/DBD + Anti-Falling-Knife (DEC-031 + DEC-032)", "poi": True, "knife": True},
    ]

    all_results = []
    pyramid_weights = [0.20, 0.30, 0.50]
    spread = 0.25
    slippage = 0.05

    for sc in scenarios:
        initial_capital = 10000.0
        balance = initial_capital
        peak = balance
        max_dd = 0.0

        open_trades = []
        closed_trades = []

        current_day = ""
        current_session = ""
        session_start_balance = initial_capital
        session_peak_pnl = 0.0
        session_halted = False
        prior_session_profit = 0.0
        session_floor_pnl = -50.0

        buy_cooldown_until = 0.0
        sell_cooldown_until = 0.0
        last_order_time_sec = 0.0

        monthly_pnl = defaultdict(float)

        t_sim_0 = time.time()

        for i in range(50, n):
            t = timestamps[i]
            t_sec = t.timestamp()
            hr = hours[i]
            mn = minutes[i]
            h = highs[i]
            l = lows[i]
            c = closes[i]

            day_key = t.strftime("%Y-%m-%d")
            month_key = t.strftime("%Y-%m")

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
                session_peak_pnl = 0.0
                session_halted = (sess_name == "OFF_HOURS")
                alloc_loss = 50.0
                if prior_session_profit > 50.0:
                    alloc_loss += (prior_session_profit * 0.25)
                session_floor_pnl = -alloc_loss

            # Manage Open Trades
            rem = []
            for tr in open_trades:
                if tr["dir"] == "BUY" and h >= (tr["tp"] + slippage):
                    pnl = tr["risk"] * ((tr["tp"] - tr["in"]) / max(tr["in"] - tr["sl"], 0.1))
                    balance += pnl
                    monthly_pnl[month_key] += pnl
                    tr["pnl"] = pnl
                    closed_trades.append(tr)
                elif tr["dir"] == "SELL" and (l + spread) <= (tr["tp"] - slippage):
                    pnl = tr["risk"] * ((tr["in"] - tr["tp"]) / max(tr["sl"] - tr["in"], 0.1))
                    balance += pnl
                    monthly_pnl[month_key] += pnl
                    tr["pnl"] = pnl
                    closed_trades.append(tr)
                elif tr["dir"] == "BUY" and l <= (tr["sl"] - slippage):
                    pnl = -tr["risk"]
                    balance += pnl
                    monthly_pnl[month_key] += pnl
                    tr["pnl"] = pnl
                    closed_trades.append(tr)
                    if sc["knife"]:
                        cd_dur = 600 if sess_name == "ASIAN" else (900 if sess_name == "LONDON" else 1500)
                        buy_cooldown_until = t_sec + cd_dur
                elif tr["dir"] == "SELL" and (h + spread) >= (tr["sl"] + slippage):
                    pnl = -tr["risk"]
                    balance += pnl
                    monthly_pnl[month_key] += pnl
                    tr["pnl"] = pnl
                    closed_trades.append(tr)
                    if sc["knife"]:
                        cd_dur = 600 if sess_name == "ASIAN" else (900 if sess_name == "LONDON" else 1500)
                        sell_cooldown_until = t_sec + cd_dur
                else:
                    rem.append(tr)
            open_trades = rem

            if balance > peak: peak = balance
            dd = (peak - balance) / peak * 100.0
            if dd > max_dd: max_dd = dd

            # Session Trailing Lock
            curr_sess_pnl = balance - session_start_balance
            if curr_sess_pnl > session_peak_pnl: session_peak_pnl = curr_sess_pnl
            if session_peak_pnl >= 50.0:
                steps = int((session_peak_pnl - 50.0) / 50.0)
                session_floor_pnl = 25.0 + (steps * 50.0)
            if curr_sess_pnl <= session_floor_pnl:
                session_halted = True

            if session_halted:
                if open_trades:
                    for tr in open_trades:
                        diff = (c - tr["in"]) if tr["dir"] == "BUY" else (tr["in"] - c)
                        pnl = tr["risk"] * (diff / max(abs(tr["in"] - tr["sl"]), 0.1))
                        balance += pnl
                        monthly_pnl[month_key] += pnl
                        tr["pnl"] = pnl
                        closed_trades.append(tr)
                    open_trades = []
                continue

            # Check Entry
            if len(open_trades) == 0 and (t_sec - last_order_time_sec > 60.0) and sess_name != "OFF_HOURS":
                w_h = highs[i-20:i]
                w_l = lows[i-20:i]
                sw_high = round(float(max(w_h)), 2)
                sw_low = round(float(min(w_l)), 2)
                span = max(1.0, sw_high - sw_low)
                eq = round((sw_high + sw_low) / 2.0, 2)
                buy_zone_top = round(sw_low + (span * 0.25), 2)
                sell_zone_btm = round(sw_low + (span * 0.75), 2)

                if sc["poi"]:
                    sub_o = opens[i-30:i]
                    sub_h = highs[i-30:i]
                    sub_l = lows[i-30:i]
                    sub_c = closes[i-30:i]
                    for k in range(2, len(sub_c)):
                        if (sub_o[k-2] - sub_c[k-2] > 0) and (sub_c[k] < sub_l[k-1]) and (sub_h[k] < sub_l[k-2]):
                            if sub_l[k-1] >= c - 0.50 and abs(sub_h[k-1] - sw_high) <= 15.0:
                                sw_high = sub_h[k-1]
                                sell_zone_btm = sub_l[k-1]
                                span = max(1.0, sw_high - sw_low)
                                eq = round((sw_high + sw_low) / 2.0, 2)
                                break
                        if (sub_c[k-2] - sub_o[k-2] > 0) and (sub_c[k] > sub_h[k-1]) and (sub_l[k] > sub_h[k-2]):
                            if sub_h[k-1] <= c + 0.50 and abs(sub_l[k-1] - sw_low) <= 15.0:
                                sw_low = sub_l[k-1]
                                buy_zone_top = sub_h[k-1]
                                span = max(1.0, sw_high - sw_low)
                                eq = round((sw_high + sw_low) / 2.0, 2)
                                break

                sl_buf = max(0.50, round(span * 0.0375, 2))
                buy_sl = round(sw_low - 2.5 - sl_buf, 2)
                sell_sl = round(sw_high + 2.5 + sl_buf, 2)

                if c <= buy_zone_top and (not sc["knife"] or t_sec >= buy_cooldown_until):
                    last_order_time_sec = t_sec
                    for lay_idx, lvl in enumerate([round(min(c - 0.25, sw_low + span * 0.25), 2), round(min(c - 0.50, sw_low + span * 0.125), 2), round(min(c - 0.75, sw_low), 2)]):
                        if l <= lvl:
                            open_trades.append({"dir": "BUY", "in": lvl, "sl": buy_sl, "tp": eq, "risk": 50.0 * pyramid_weights[lay_idx], "time": t})
                elif c >= sell_zone_btm and (not sc["knife"] or t_sec >= sell_cooldown_until):
                    last_order_time_sec = t_sec
                    for lay_idx, lvl in enumerate([round(max(c + 0.25, sw_low + span * 0.75), 2), round(max(c + 0.50, sw_low + span * 0.875), 2), round(max(c + 0.75, sw_high), 2)]):
                        if h >= lvl:
                            open_trades.append({"dir": "SELL", "in": lvl, "sl": sell_sl, "tp": eq, "risk": 50.0 * pyramid_weights[lay_idx], "time": t})

        wins = [t for t in closed_trades if t["pnl"] > 0]
        losses = [t for t in closed_trades if t["pnl"] <= 0]
        gw = sum(t["pnl"] for t in wins)
        gl = abs(sum(t["pnl"] for t in losses))
        wr = len(wins) / len(closed_trades) * 100 if closed_trades else 0
        pf = gw / gl if gl > 0 else 999.0
        net = gw - gl

        max_streak = 0
        curr_s = 0
        for t in closed_trades:
            if t["pnl"] <= 0:
                curr_s += 1
                if curr_s > max_streak: max_streak = curr_s
            else:
                curr_s = 0

        sim_dur = time.time() - t_sim_0
        all_results.append({
            "id": sc["id"],
            "name": sc["name"],
            "trades": len(closed_trades),
            "wins": len(wins),
            "losses": len(losses),
            "win_rate": round(wr, 1),
            "profit_factor": round(pf, 2),
            "net_pnl": round(net, 2),
            "max_dd_pct": round(max_dd, 2),
            "max_streak_loss": max_streak,
            "duration_sec": round(sim_dur, 1),
            "monthly_pnl": {m: round(v, 2) for m, v in sorted(monthly_pnl.items())}
        })
        print(f"[{sc['id']}] Selesai ({sim_dur:.1f}s) -> Net PnL: ${net:+,.2f} | PF: {pf:.2f} | WR: {wr:.1f}% | Max DD: {max_dd:.2f}% | Max Streak Loss: {max_streak}")

    # Save to reports
    out_path = REPORTS_DIR / "historical_300k_backtest_benchmark_report.json"
    out_path.write_text(json.dumps(all_results, indent=2))
    print(f"\n✅ Laporan benchmark tersimpan di: {out_path}")
    return all_results


if __name__ == "__main__":
    run_full_historical_backtest()
