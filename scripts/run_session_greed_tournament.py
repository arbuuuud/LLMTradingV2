"""
Turnamen Kage Bunshin 18 Klon: Multi-Session Equity Budgeting & Dynamic Greed Trailing
Diuji pada 300.440 bar M1 XAUUSD (Mei 2025 - April 2026) dengan Friksi Nyata MT5:
Spread 0.25 pt, Slippage 0.05 pt, Grid Pyramid 20-30-50, Base Capital $10,000.
"""

import sys
import json
import polars as pl
import numpy as np
from pathlib import Path
from datetime import datetime
from collections import defaultdict

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.core.types import Direction
from src.workflows.backtest import TradeRecord
from src.features.structure import detect_swing_points

print("=" * 80)
print("🥋 MEMULAI TURNAMEN KAGE BUNSHIN 18 KLON (SESSION BUDGET & GREED TRAILING)")
print("=" * 80)

parquet_path = PROJECT_ROOT / "data" / "parquet" / "XAUUSD" / "M1" / "XAUUSD_M1.parquet"
df = pl.read_parquet(parquet_path)
n = len(df)
print(f"Dataset Ground Truth: {n:,} bar M1 XAUUSD")

opens = df["open"].to_numpy()
highs = df["high"].to_numpy()
lows = df["low"].to_numpy()
closes = df["close"].to_numpy()
timestamps = df["timestamp"].to_list()
hours = np.array([t.hour for t in timestamps])
minutes = np.array([t.minute for t in timestamps])

shs, sls = detect_swing_points(highs, lows, timestamps, window=5)
sh_dict = {sh.index: sh.price for sh in shs}
sl_dict = {sl.index: sl.price for sl in sls}
print("Struktur Fractal Swing Floor & Roof selesai diindeks.\n")

# Fungsi helper klasifikasi sesi
def get_session_info(hr, mn, mode):
    # Time in minutes from midnight
    t_min = hr * 60 + mn

    if mode == "DAILY":
        return "DAILY"

    elif mode == "3_SESSIONS":
        # Asia: 00:00 - 07:00 UTC (0 - 420)
        # London: 07:00 - 13:30 UTC (420 - 810)
        # NY: 13:30 - 21:00 UTC (810 - 1260)
        if 0 <= t_min < 420: return "ASIAN"
        elif 420 <= t_min < 810: return "LONDON"
        elif 810 <= t_min < 1260: return "NY"
        return "OFF_HOURS"

    elif mode == "2_PRIME":
        # Skip Asia & Lunch (12:00-13:30)
        # London Morning: 07:00 - 12:00 UTC (420 - 720)
        # NY Overlap: 13:30 - 21:00 UTC (810 - 1260)
        if 420 <= t_min < 720: return "LONDON_PRIME"
        elif 810 <= t_min < 1260: return "NY_PRIME"
        return "OFF_HOURS"

    elif mode == "ASIAN_LITE":
        # Same as 3 sessions but Asia has reduced risk
        if 0 <= t_min < 420: return "ASIAN_LITE"
        elif 420 <= t_min < 810: return "LONDON"
        elif 810 <= t_min < 1260: return "NY"
        return "OFF_HOURS"

    elif mode == "4_MICRO":
        # Asia: 00:00 - 07:00
        # London: 07:00 - 12:00
        # NY Open: 13:30 - 17:00
        # Late NY: 17:00 - 21:00
        if 0 <= t_min < 420: return "ASIAN"
        elif 420 <= t_min < 720: return "LONDON"
        elif 810 <= t_min < 1020: return "NY_OPEN"
        elif 1020 <= t_min < 1260: return "NY_LATE"
        return "OFF_HOURS"

    return "OFF_HOURS"

# Definisi 18 Klon
clone_specs = [
    # 1. Baseline Kontrol
    {"id": "CLONE-01", "name": "Baseline Harian Greed 0.5%", "part_mode": "DAILY", "loss_budget": 100.0, "step_mode": "STEP_05", "carry_mode": "NONE"},
    {"id": "CLONE-02", "name": "Baseline Harian Flat 1%", "part_mode": "DAILY", "loss_budget": 100.0, "step_mode": "FLAT_1PCT", "carry_mode": "NONE"},

    # 2. 3 Sesi Mandiri (Asia, London, NY)
    {"id": "CLONE-03", "name": "3-Sesi Loss -0.33% Step 0.5%", "part_mode": "3_SESSIONS", "loss_budget": 33.3, "step_mode": "STEP_05", "carry_mode": "INDEPENDENT"},
    {"id": "CLONE-04", "name": "3-Sesi Loss -0.50% Step 0.5% (Ide Anda)", "part_mode": "3_SESSIONS", "loss_budget": 50.0, "step_mode": "STEP_05", "carry_mode": "INDEPENDENT"},
    {"id": "CLONE-05", "name": "3-Sesi Loss -0.50% Step 0.25% (Tight)", "part_mode": "3_SESSIONS", "loss_budget": 50.0, "step_mode": "STEP_025", "carry_mode": "INDEPENDENT"},
    {"id": "CLONE-06", "name": "3-Sesi Dynamic Loss (25/50/75)", "part_mode": "3_SESSIONS", "loss_budget": "DYNAMIC", "step_mode": "STEP_05", "carry_mode": "INDEPENDENT"},
    {"id": "CLONE-07", "name": "3-Sesi Adaptive Step (Asia 0.25/Ldn 0.5)", "part_mode": "3_SESSIONS", "loss_budget": 50.0, "step_mode": "ADAPTIVE", "carry_mode": "INDEPENDENT"},
    {"id": "CLONE-08", "name": "3-Sesi House Money (Carry Win)", "part_mode": "3_SESSIONS", "loss_budget": 50.0, "step_mode": "STEP_05", "carry_mode": "HOUSE_MONEY"},
    {"id": "CLONE-09", "name": "3-Sesi Recovery Guard Lock", "part_mode": "3_SESSIONS", "loss_budget": 50.0, "step_mode": "STEP_05", "carry_mode": "RECOVERY_GUARD"},

    # 3. 2 Mega Prime Sesi (London Morning + NY Overlap)
    {"id": "CLONE-10", "name": "2-Prime Loss -0.50% Step 0.50%", "part_mode": "2_PRIME", "loss_budget": 50.0, "step_mode": "STEP_05", "carry_mode": "INDEPENDENT"},
    {"id": "CLONE-11", "name": "2-Prime Loss -0.50% Step 0.25% (Tight)", "part_mode": "2_PRIME", "loss_budget": 50.0, "step_mode": "STEP_025", "carry_mode": "INDEPENDENT"},
    {"id": "CLONE-12", "name": "2-Prime Loss -0.75% Step 0.50%", "part_mode": "2_PRIME", "loss_budget": 75.0, "step_mode": "STEP_05", "carry_mode": "INDEPENDENT"},
    {"id": "CLONE-13", "name": "2-Prime House Money (Carry Ldn Win)", "part_mode": "2_PRIME", "loss_budget": 50.0, "step_mode": "STEP_05", "carry_mode": "HOUSE_MONEY"},

    # 4. Asian Lite (Asia 50% Risk) + London + NY
    {"id": "CLONE-14", "name": "Asian-Lite Loss -0.50% Step 0.50%", "part_mode": "ASIAN_LITE", "loss_budget": 50.0, "step_mode": "STEP_05", "carry_mode": "INDEPENDENT"},
    {"id": "CLONE-15", "name": "Asian-Lite Adaptive Step (0.25/0.50)", "part_mode": "ASIAN_LITE", "loss_budget": 50.0, "step_mode": "ADAPTIVE", "carry_mode": "INDEPENDENT"},
    {"id": "CLONE-16", "name": "Asian-Lite House Money", "part_mode": "ASIAN_LITE", "loss_budget": 50.0, "step_mode": "STEP_05", "carry_mode": "HOUSE_MONEY"},

    # 5. 4 Sesi Mikro
    {"id": "CLONE-17", "name": "4-Micro Sesi Loss -0.35% Step 0.35%", "part_mode": "4_MICRO", "loss_budget": 35.0, "step_mode": "STEP_035", "carry_mode": "INDEPENDENT"},
    {"id": "CLONE-18", "name": "4-Micro Sesi House Money", "part_mode": "4_MICRO", "loss_budget": 35.0, "step_mode": "STEP_035", "carry_mode": "HOUSE_MONEY"}
]

def run_clone_simulation(c_spec):
    initial_capital = 10000.0
    balance = initial_capital
    peak = balance
    max_dd = 0.0

    current_floor = 0.0
    current_roof = 0.0
    zone_completed = False

    open_trades = []
    daily_pnl = defaultdict(float)
    monthly_pnl = defaultdict(float)

    # State Sesi
    current_day = ""
    current_session = ""
    session_start_balance = initial_capital
    session_peak_pnl = 0.0
    session_halted = False
    session_floor_pnl = -50.0
    prior_session_profit = 0.0

    spread = 0.25
    slippage = 0.05
    start_bar = 5 * 2 + 10
    pyramid_weights = [0.20, 0.30, 0.50]

    for i in range(start_bar, n):
        t = timestamps[i]
        o = opens[i]
        h = highs[i]
        l = lows[i]
        c = closes[i]
        hr = hours[i]
        mn = minutes[i]

        day_key = t.strftime("%Y-%m-%d")
        month_key = t.strftime("%Y-%m")
        sess_name = get_session_info(hr, mn, c_spec["part_mode"])

        # Reset Harian
        if day_key != current_day:
            current_day = day_key
            prior_session_profit = 0.0

        # Pergantian Sesi
        if sess_name != current_session:
            # Simpan hasil sesi sebelumnya untuk House Money / Recovery
            if current_session != "" and current_session != "OFF_HOURS":
                sess_pnl = balance - session_start_balance
                prior_session_profit = sess_pnl

            current_session = sess_name
            session_start_balance = balance
            session_peak_pnl = 0.0
            session_halted = (sess_name == "OFF_HOURS")

            # Tentukan budget loss sesi
            b_loss = c_spec["loss_budget"]
            if b_loss == "DYNAMIC":
                if sess_name == "ASIAN": alloc_loss = 25.0
                elif sess_name == "LONDON": alloc_loss = 50.0
                elif sess_name == "NY": alloc_loss = 75.0
                else: alloc_loss = 50.0
            else:
                alloc_loss = float(b_loss)

            # Aturan House Money / Recovery Guard
            if c_spec["carry_mode"] == "HOUSE_MONEY" and prior_session_profit > 50.0:
                # Tambahkan 25% dari profit sesi sebelumnya ke budget loss sesi ini
                alloc_loss += (prior_session_profit * 0.25)
            elif c_spec["carry_mode"] == "RECOVERY_GUARD" and prior_session_profit < 0.0:
                # Perketat loss limit jika sesi sebelumnya rugi
                alloc_loss = max(25.0, alloc_loss * 0.50)

            session_floor_pnl = -alloc_loss

        new_floor = current_floor
        new_roof = current_roof
        if i in sl_dict: new_floor = sl_dict[i]
        if i in sh_dict: new_roof = sh_dict[i]

        if (new_floor != current_floor and new_floor > 0.0) or (new_roof != current_roof and new_roof > 0.0):
            current_floor = new_floor if new_floor > 0.0 else current_floor
            current_roof = new_roof if new_roof > 0.0 else current_roof
            span = current_roof - current_floor
            zone_completed = False
            if open_trades and span > 0.5:
                for tr in open_trades:
                    tr.hard_tp_price = current_floor + span * 0.50

        span = current_roof - current_floor
        remaining_trades = []

        # Kelola Posisi Terbuka
        for tr in open_trades:
            if tr.direction == Direction.BUY and h >= (tr.hard_tp_price + slippage):
                r_gain = (tr.hard_tp_price - tr.entry_price) / max(tr.entry_price - tr.sl_price, 0.1)
                pnl = tr.risk_amount * max(r_gain, 1.0)
                balance += pnl
                daily_pnl[day_key] += pnl
                monthly_pnl[month_key] += pnl
                zone_completed = True
            elif tr.direction == Direction.SELL and (l + spread) <= (tr.hard_tp_price - slippage):
                r_gain = (tr.entry_price - tr.hard_tp_price) / max(tr.sl_price - tr.entry_price, 0.1)
                pnl = tr.risk_amount * max(r_gain, 1.0)
                balance += pnl
                daily_pnl[day_key] += pnl
                monthly_pnl[month_key] += pnl
                zone_completed = True
            elif tr.direction == Direction.BUY and l <= (tr.sl_price - slippage):
                pnl = tr.risk_amount * (tr.r_multiple if tr.is_bep_locked else -1.0)
                balance += pnl
                daily_pnl[day_key] += pnl
                monthly_pnl[month_key] += pnl
            elif tr.direction == Direction.SELL and (h + spread) >= (tr.sl_price + slippage):
                pnl = tr.risk_amount * (tr.r_multiple if tr.is_bep_locked else -1.0)
                balance += pnl
                daily_pnl[day_key] += pnl
                monthly_pnl[month_key] += pnl
            else:
                pts_diff = (c - tr.entry_price) if tr.direction == Direction.BUY else (tr.entry_price - c)
                sl_dist = max(abs(tr.entry_price - tr.sl_price), 0.1)
                r_running = pts_diff / sl_dist
                if r_running >= 2.0:
                    tr.is_bep_locked = True
                    tr.r_multiple = 1.5
                    lock_p = tr.entry_price + (1.5 * sl_dist if tr.direction == Direction.BUY else -1.5 * sl_dist)
                    tr.sl_price = lock_p if (tr.direction == Direction.BUY and lock_p > tr.sl_price) or (tr.direction == Direction.SELL and lock_p < tr.sl_price) else tr.sl_price
                elif r_running >= 1.5:
                    tr.is_bep_locked = True
                    tr.r_multiple = 1.0
                    lock_p = tr.entry_price + (1.0 * sl_dist if tr.direction == Direction.BUY else -1.0 * sl_dist)
                    tr.sl_price = lock_p if (tr.direction == Direction.BUY and lock_p > tr.sl_price) or (tr.direction == Direction.SELL and lock_p < tr.sl_price) else tr.sl_price
                elif r_running >= 1.0:
                    tr.is_bep_locked = True
                    tr.r_multiple = 0.5
                    lock_p = tr.entry_price + (0.5 * sl_dist if tr.direction == Direction.BUY else -0.5 * sl_dist)
                    tr.sl_price = lock_p if (tr.direction == Direction.BUY and lock_p > tr.sl_price) or (tr.direction == Direction.SELL and lock_p < tr.sl_price) else tr.sl_price

                remaining_trades.append(tr)

        open_trades = remaining_trades
        if balance > peak: peak = balance
        dd = (peak - balance) / peak * 100.0
        if dd > max_dd: max_dd = dd

        # Evaluasi Sesi Greed Trailing
        curr_sess_pnl = balance - session_start_balance
        if curr_sess_pnl > session_peak_pnl:
            session_peak_pnl = curr_sess_pnl

        step_mode = c_spec["step_mode"]

        if step_mode == "FLAT_1PCT":
            if curr_sess_pnl >= 100.0 or curr_sess_pnl <= session_floor_pnl:
                session_halted = True

        elif step_mode == "STEP_05":
            # Capai +$50 lock +$25, capai +$100 lock +$50, capai +$150 lock +$100, dst
            if session_peak_pnl >= 50.0:
                steps = int((session_peak_pnl - 50.0) / 50.0)
                session_floor_pnl = 25.0 + (steps * 50.0)
            if curr_sess_pnl <= session_floor_pnl:
                session_halted = True

        elif step_mode == "STEP_025":
            # Capai +$50 lock +$35, capai +$75 lock +$50, dst
            if session_peak_pnl >= 50.0:
                steps = int((session_peak_pnl - 50.0) / 25.0)
                session_floor_pnl = 35.0 + (steps * 25.0)
            if curr_sess_pnl <= session_floor_pnl:
                session_halted = True

        elif step_mode == "STEP_035":
            if session_peak_pnl >= 35.0:
                steps = int((session_peak_pnl - 35.0) / 35.0)
                session_floor_pnl = 20.0 + (steps * 35.0)
            if curr_sess_pnl <= session_floor_pnl:
                session_halted = True

        elif step_mode == "ADAPTIVE":
            # Asia ketat (0.25), London & NY lebar (0.50)
            if "ASIAN" in sess_name:
                if session_peak_pnl >= 35.0:
                    steps = int((session_peak_pnl - 35.0) / 25.0)
                    session_floor_pnl = 20.0 + (steps * 25.0)
            else:
                if session_peak_pnl >= 50.0:
                    steps = int((session_peak_pnl - 50.0) / 50.0)
                    session_floor_pnl = 25.0 + (steps * 50.0)
            if curr_sess_pnl <= session_floor_pnl:
                session_halted = True

        if session_halted:
            if open_trades:
                for tr in open_trades:
                    diff = (c - tr.entry_price) if tr.direction == Direction.BUY else (tr.entry_price - c)
                    pnl = tr.risk_amount * (diff / max(abs(tr.entry_price - tr.sl_price), 0.1))
                    balance += pnl
                    daily_pnl[day_key] += pnl
                    monthly_pnl[month_key] += pnl
                open_trades = []
            continue

        # Entry PAC Sesi Aktif
        if span > 1.0 and len(open_trades) < 3 and not session_halted and sess_name != "OFF_HOURS":
            if zone_completed: continue
            buy_zone_ceiling = current_floor + span * 0.25
            sell_zone_floor = current_floor + span * 0.75
            mid_eq = current_floor + span * 0.50

            base_risk = 50.0
            if sess_name == "ASIAN_LITE":
                base_risk = 25.0 # Risiko 50% di Asia Lite

            if l <= buy_zone_ceiling and c > current_floor:
                hard_sl = current_floor - span * 0.15
                target_tp = mid_eq
                depth_pcts = [0.25, 0.125, 0.0]
                for lay_idx, dp in enumerate(depth_pcts):
                    order_level = current_floor + span * dp
                    if l <= (order_level + slippage) and len(open_trades) < 3:
                        if any(abs(tr.entry_price - order_level) < 0.10 for tr in open_trades): continue
                        tr = TradeRecord(
                            trade_id="T", direction=Direction.BUY, entry_time=t,
                            entry_price=order_level, sl_price=hard_sl, hard_tp_price=target_tp,
                            risk_amount=base_risk * pyramid_weights[lay_idx]
                        )
                        open_trades.append(tr)

            elif h >= sell_zone_floor and c < current_roof:
                hard_sl = current_roof + span * 0.15
                target_tp = mid_eq
                depth_pcts = [0.75, 0.875, 1.0]
                for lay_idx, dp in enumerate(depth_pcts):
                    order_level = current_floor + span * dp
                    if (h + spread) >= (order_level - slippage) and len(open_trades) < 3:
                        if any(abs(tr.entry_price - order_level) < 0.10 for tr in open_trades): continue
                        tr = TradeRecord(
                            trade_id="T", direction=Direction.SELL, entry_time=t,
                            entry_price=order_level, sl_price=hard_sl, hard_tp_price=target_tp,
                            risk_amount=base_risk * pyramid_weights[lay_idx]
                        )
                        open_trades.append(tr)

    # Hitung Metrik Bulanan & Harian
    months_list = sorted(monthly_pnl.keys())
    monthly_rois = []
    months_ge_20 = 0
    for m in months_list:
        pnl_m = monthly_pnl[m]
        roi_m = (pnl_m / initial_capital) * 100.0
        monthly_rois.append(roi_m)
        if roi_m >= 20.0:
            months_ge_20 += 1

    avg_monthly_roi = float(np.mean(monthly_rois))
    trading_days = list(daily_pnl.keys())
    win_days = [d for d in trading_days if daily_pnl[d] > 0]
    win_day_rate = (len(win_days) / len(trading_days) * 100.0) if trading_days else 0.0

    return {
        "id": c_spec["id"],
        "name": c_spec["name"],
        "final_balance": balance,
        "net_pnl": balance - initial_capital,
        "max_dd_pct": max_dd,
        "win_day_rate": win_day_rate,
        "total_days": len(trading_days),
        "total_months": len(months_list),
        "months_ge_20": months_ge_20,
        "pct_months_ge_20": (months_ge_20 / len(months_list) * 100.0) if months_list else 0.0,
        "avg_monthly_roi": avg_monthly_roi
    }

# Eksekusi Turnamen 18 Klon
results = []
for idx, cs in enumerate(clone_specs):
    print(f"[{idx+1}/18] Menjalankan {cs['id']} - {cs['name']}...")
    res = run_clone_simulation(cs)
    results.append(res)

print("\n" + "=" * 105)
print(f"{'RANK':<5} | {'ID':<9} | {'NAMA KLON':<35} | {'NET PNL':<12} | {'WIN DAY':<8} | {'MAX DD':<7} | {'>=20% BLN':<9} | {'AVG ROI/BLN'}")
print("=" * 105)

# Urutkan berdasarkan Net PnL dan Drawdown
sorted_results = sorted(results, key=lambda x: (x["net_pnl"], -x["max_dd_pct"]), reverse=True)

for rank, r in enumerate(sorted_results, 1):
    cid = r["id"]
    name = r["name"][:35]
    pnl = f"${r['net_pnl']:,.2f}"
    wdr = f"{r['win_day_rate']:.1f}%"
    mdd = f"{r['max_dd_pct']:.2f}%"
    m20 = f"{r['months_ge_20']}/{r['total_months']} ({r['pct_months_ge_20']:.0f}%)"
    amr = f"{r['avg_monthly_roi']:.1f}%"
    print(f"{rank:<5} | {cid:<9} | {name:<35} | {pnl:<12} | {wdr:<8} | {mdd:<7} | {m20:<9} | {amr}")
print("=" * 105)

# Save JSON Report
output_json = PROJECT_ROOT / "reports" / "kage_bunshin_session_greed_tournament.json"
with open(output_json, "w", encoding="utf-8") as f:
    json.dump(sorted_results, f, indent=2)
print(f"\n✅ Laporan lengkap turnamen berhasil disimpan ke: {output_json}")
