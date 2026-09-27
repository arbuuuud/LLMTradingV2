"""
Turnamen Akbar Kage Bunshin Anti-Falling-Knife (30 Klon):
Menguji proteksi directional streak & HTF Trend Alignment di 300.440 bar M1 XAUUSD (Mei 2025 - April 2026).
Tujuan: Menghentikan kebobolan beruntun (seperti Wave #26 crash -$1,013 di live VPS) tanpa mengorbankan win rate.
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

print("=" * 85)
print("🥋 MEMULAI TURNAMEN AKBAR KAGE BUNSHIN 30 KLON (ANTI-FALLING-KNIFE SHOWDOWN)")
print("=" * 85)

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

# Pra-kalkulasi Simple HTF Trend (M15 / M5 EMA-20 slope atau Moving Average)
# M15 Trend: Simple SMA-15 bar M15 = 225 bar M1
ma_window_fast = 60   # 1 jam
ma_window_slow = 240  # 4 jam
ma_fast = df["close"].rolling_mean(window_size=ma_window_fast).to_numpy()
ma_slow = df["close"].rolling_mean(window_size=ma_window_slow).to_numpy()

# 30 Varian Klon:
# Dimensi 1: Directional Loss Cooldown (0 min, 10 min, 15 min, 20 min, 30 min)
# Dimensi 2: Max Consecutive Directional Losses (1 loss, 2 losses, 3 losses, unlimited)
# Dimensi 3: HTF Trend Filter (None, M15 SMA Filter: Only Buy if Fast > Slow, Only Sell if Fast < Slow)
# Dimensi 4: Trailing Buffer (0.25x ATR Dynamic SL Buffer)

clone_specs = [
    # KELOMPOK 0: Baseline Kontrol Tanpa Proteksi (Status Quo VPS)
    {"id": "CLONE-BASE-00", "cooldown_bars": 0, "max_dir_loss": 999, "htf_filter": False, "buffer": 0.0, "desc": "Baseline Murni Tanpa Filter (Status Quo)"},
    {"id": "CLONE-BASE-BUF", "cooldown_bars": 0, "max_dir_loss": 999, "htf_filter": False, "buffer": 0.25, "desc": "Baseline + 0.25x Dynamic Buffer (DEC-029)"},

    # KELOMPOK 1: Directional Loss Cooldown Setelah 1x Loss (10m, 15m, 20m, 30m, 45m, 60m)
    {"id": "CLONE-CD-10M", "cooldown_bars": 10, "max_dir_loss": 1, "htf_filter": False, "buffer": 0.25, "desc": "10 Min Cooldown after 1x Loss"},
    {"id": "CLONE-CD-15M", "cooldown_bars": 15, "max_dir_loss": 1, "htf_filter": False, "buffer": 0.25, "desc": "15 Min Cooldown after 1x Loss"},
    {"id": "CLONE-CD-20M", "cooldown_bars": 20, "max_dir_loss": 1, "htf_filter": False, "buffer": 0.25, "desc": "20 Min Cooldown after 1x Loss"},
    {"id": "CLONE-CD-30M", "cooldown_bars": 30, "max_dir_loss": 1, "htf_filter": False, "buffer": 0.25, "desc": "30 Min Cooldown after 1x Loss"},
    {"id": "CLONE-CD-45M", "cooldown_bars": 45, "max_dir_loss": 1, "htf_filter": False, "buffer": 0.25, "desc": "45 Min Cooldown after 1x Loss"},
    {"id": "CLONE-CD-60M", "cooldown_bars": 60, "max_dir_loss": 1, "htf_filter": False, "buffer": 0.25, "desc": "60 Min Cooldown after 1x Loss"},

    # KELOMPOK 2: Toleransi 2x Loss Berturut-turut Sebelum Cooldown (Toleransi 1 Strike)
    {"id": "CLONE-2STRIKE-10M", "cooldown_bars": 10, "max_dir_loss": 2, "htf_filter": False, "buffer": 0.25, "desc": "2 Strikes Loss -> 10 Min Cooldown"},
    {"id": "CLONE-2STRIKE-15M", "cooldown_bars": 15, "max_dir_loss": 2, "htf_filter": False, "buffer": 0.25, "desc": "2 Strikes Loss -> 15 Min Cooldown"},
    {"id": "CLONE-2STRIKE-20M", "cooldown_bars": 20, "max_dir_loss": 2, "htf_filter": False, "buffer": 0.25, "desc": "2 Strikes Loss -> 20 Min Cooldown"},
    {"id": "CLONE-2STRIKE-30M", "cooldown_bars": 30, "max_dir_loss": 2, "htf_filter": False, "buffer": 0.25, "desc": "2 Strikes Loss -> 30 Min Cooldown"},
    {"id": "CLONE-2STRIKE-45M", "cooldown_bars": 45, "max_dir_loss": 2, "htf_filter": False, "buffer": 0.25, "desc": "2 Strikes Loss -> 45 Min Cooldown"},

    # KELOMPOK 3: Toleransi 3x Loss Berturut-turut Sebelum Cooldown
    {"id": "CLONE-3STRIKE-15M", "cooldown_bars": 15, "max_dir_loss": 3, "htf_filter": False, "buffer": 0.25, "desc": "3 Strikes Loss -> 15 Min Cooldown"},
    {"id": "CLONE-3STRIKE-30M", "cooldown_bars": 30, "max_dir_loss": 3, "htf_filter": False, "buffer": 0.25, "desc": "3 Strikes Loss -> 30 Min Cooldown"},
    {"id": "CLONE-3STRIKE-60M", "cooldown_bars": 60, "max_dir_loss": 3, "htf_filter": False, "buffer": 0.25, "desc": "3 Strikes Loss -> 60 Min Cooldown"},

    # KELOMPOK 4: HTF Trend Filter (M15 Macro SMA Trend Alignment)
    {"id": "CLONE-HTF-TREND", "cooldown_bars": 0, "max_dir_loss": 999, "htf_filter": True, "buffer": 0.25, "desc": "HTF Trend Filter Murni (No CD)"},
    {"id": "CLONE-HTF-CD-10M", "cooldown_bars": 10, "max_dir_loss": 1, "htf_filter": True, "buffer": 0.25, "desc": "HTF Trend + 10 Min Cooldown after 1x Loss"},
    {"id": "CLONE-HTF-CD-15M", "cooldown_bars": 15, "max_dir_loss": 1, "htf_filter": True, "buffer": 0.25, "desc": "HTF Trend + 15 Min Cooldown after 1x Loss"},
    {"id": "CLONE-HTF-CD-20M", "cooldown_bars": 20, "max_dir_loss": 1, "htf_filter": True, "buffer": 0.25, "desc": "HTF Trend + 20 Min Cooldown after 1x Loss"},
    {"id": "CLONE-HTF-CD-30M", "cooldown_bars": 30, "max_dir_loss": 1, "htf_filter": True, "buffer": 0.25, "desc": "HTF Trend + 30 Min Cooldown after 1x Loss"},
    {"id": "CLONE-HTF-2STRIKE-15M", "cooldown_bars": 15, "max_dir_loss": 2, "htf_filter": True, "buffer": 0.25, "desc": "HTF Trend + 2 Strikes -> 15 Min CD"},
    {"id": "CLONE-HTF-2STRIKE-30M", "cooldown_bars": 30, "max_dir_loss": 2, "htf_filter": True, "buffer": 0.25, "desc": "HTF Trend + 2 Strikes -> 30 Min CD"},

    # KELOMPOK 5: Dynamic Hybrid (Volatile Session Scaling: Cooldown Ketat di NY Overlap)
    {"id": "CLONE-SESSION-ADAPT-15M", "cooldown_bars": "ADAPTIVE", "max_dir_loss": 1, "htf_filter": False, "buffer": 0.25, "desc": "Adaptive CD (Asia 10m / Ldn 15m / NY 25m)"},
    {"id": "CLONE-SESSION-ADAPT-30M", "cooldown_bars": "ADAPTIVE_DEEP", "max_dir_loss": 1, "htf_filter": False, "buffer": 0.25, "desc": "Deep Adaptive CD (Asia 15m / Ldn 30m / NY 45m)"},
    {"id": "CLONE-SESSION-ADAPT-2STRIKE", "cooldown_bars": "ADAPTIVE", "max_dir_loss": 2, "htf_filter": False, "buffer": 0.25, "desc": "Adaptive CD with 2 Strikes"},
    {"id": "CLONE-HYBRID-CHAMPION-A", "cooldown_bars": 15, "max_dir_loss": 2, "htf_filter": False, "buffer": 0.35, "desc": "Hybrid: 2 Strikes -> 15m CD + 0.35x Buffer"},
    {"id": "CLONE-HYBRID-CHAMPION-B", "cooldown_bars": 20, "max_dir_loss": 2, "htf_filter": False, "buffer": 0.30, "desc": "Hybrid: 2 Strikes -> 20m CD + 0.30x Buffer"},
    {"id": "CLONE-HYBRID-CHAMPION-C", "cooldown_bars": 30, "max_dir_loss": 1, "htf_filter": False, "buffer": 0.30, "desc": "Hybrid: 1 Strike -> 30m CD + 0.30x Buffer"},
    {"id": "CLONE-HYBRID-CHAMPION-D", "cooldown_bars": 20, "max_dir_loss": 1, "htf_filter": True, "buffer": 0.30, "desc": "Hybrid: HTF + 1 Strike -> 20m CD + 0.30x Buffer"},
]

print(f"Total Klon yang Akan Diadu: {len(clone_specs)} Klon!")

pyramid_weights = [0.20, 0.30, 0.50]
spread = 0.25
slippage = 0.05

def simulate_anti_knife_clone(c_spec):
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

    # State Sesi & Greed Trailing (CLONE-08)
    current_day = ""
    current_session = ""
    session_start_balance = initial_capital
    session_peak_pnl = 0.0
    session_halted = False
    prior_session_profit = 0.0
    session_floor_pnl = -50.0

    # State Directional Streak Cooldown (Anti-Falling-Knife Engine)
    buy_loss_streak = 0
    sell_loss_streak = 0
    buy_cooldown_until = -1
    sell_cooldown_until = -1

    total_trades_count = 0
    total_wins = 0
    total_losses = 0
    max_consecutive_losses = 0
    curr_streak = 0

    for i in range(240, n):
        t = timestamps[i]
        hr = hours[i]
        mn = minutes[i]
        o = opens[i]
        h = highs[i]
        l = lows[i]
        c = closes[i]

        day_key = t.strftime("%Y-%m-%d")
        month_key = t.strftime("%Y-%m")

        # Cek Ganti Hari
        if day_key != current_day:
            current_day = day_key
            prior_session_profit = 0.0

        # Klasifikasi 3 Sesi
        t_min = hr * 60 + mn
        if 0 <= t_min < 420: sess_name = "ASIAN"
        elif 420 <= t_min < 810: sess_name = "LONDON"
        elif 810 <= t_min < 1260: sess_name = "NY"
        else: sess_name = "OFF_HOURS"

        # Cek Ganti Sesi
        if sess_name != current_session:
            if current_session != "" and current_session != "OFF_HOURS":
                prior_session_profit = balance - session_start_balance

            current_session = sess_name
            session_start_balance = balance
            session_peak_pnl = 0.0
            session_halted = (sess_name == "OFF_HOURS")

            alloc_loss = 50.0
            if prior_session_profit > 50.0:
                alloc_loss += (prior_session_profit * 0.25) # House Money (CLONE-08)
            session_floor_pnl = -alloc_loss

        # Update Swings
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
            # TP Hit
            if tr.direction == Direction.BUY and h >= (tr.hard_tp_price + slippage):
                r_gain = (tr.hard_tp_price - tr.entry_price) / max(tr.entry_price - tr.sl_price, 0.1)
                pnl = tr.risk_amount * max(r_gain, 1.0)
                balance += pnl
                daily_pnl[day_key] += pnl
                monthly_pnl[month_key] += pnl
                zone_completed = True
                total_trades_count += 1
                total_wins += 1
                curr_streak = 0
                buy_loss_streak = 0 # Reset streak on win
            elif tr.direction == Direction.SELL and (l + spread) <= (tr.hard_tp_price - slippage):
                r_gain = (tr.entry_price - tr.hard_tp_price) / max(tr.sl_price - tr.entry_price, 0.1)
                pnl = tr.risk_amount * max(r_gain, 1.0)
                balance += pnl
                daily_pnl[day_key] += pnl
                monthly_pnl[month_key] += pnl
                zone_completed = True
                total_trades_count += 1
                total_wins += 1
                curr_streak = 0
                sell_loss_streak = 0 # Reset streak on win

            # SL Hit
            elif tr.direction == Direction.BUY and l <= (tr.sl_price - slippage):
                pnl = tr.risk_amount * (tr.r_multiple if tr.is_bep_locked else -1.0)
                balance += pnl
                daily_pnl[day_key] += pnl
                monthly_pnl[month_key] += pnl
                total_trades_count += 1
                if pnl <= 0:
                    total_losses += 1
                    curr_streak += 1
                    if curr_streak > max_consecutive_losses: max_consecutive_losses = curr_streak
                    buy_loss_streak += 1
                    # Evaluasi Cooldown
                    if buy_loss_streak >= c_spec["max_dir_loss"]:
                        # Hitung durasi bars
                        cd_mode = c_spec["cooldown_bars"]
                        if cd_mode == "ADAPTIVE":
                            cd_len = 10 if sess_name == "ASIAN" else (15 if sess_name == "LONDON" else 25)
                        elif cd_mode == "ADAPTIVE_DEEP":
                            cd_len = 15 if sess_name == "ASIAN" else (30 if sess_name == "LONDON" else 45)
                        else:
                            cd_len = int(cd_mode)
                        buy_cooldown_until = i + cd_len
                else:
                    total_wins += 1
                    curr_streak = 0
                    buy_loss_streak = 0

            elif tr.direction == Direction.SELL and (h + spread) >= (tr.sl_price + slippage):
                pnl = tr.risk_amount * (tr.r_multiple if tr.is_bep_locked else -1.0)
                balance += pnl
                daily_pnl[day_key] += pnl
                monthly_pnl[month_key] += pnl
                total_trades_count += 1
                if pnl <= 0:
                    total_losses += 1
                    curr_streak += 1
                    if curr_streak > max_consecutive_losses: max_consecutive_losses = curr_streak
                    sell_loss_streak += 1
                    # Evaluasi Cooldown
                    if sell_loss_streak >= c_spec["max_dir_loss"]:
                        cd_mode = c_spec["cooldown_bars"]
                        if cd_mode == "ADAPTIVE":
                            cd_len = 10 if sess_name == "ASIAN" else (15 if sess_name == "LONDON" else 25)
                        elif cd_mode == "ADAPTIVE_DEEP":
                            cd_len = 15 if sess_name == "ASIAN" else (30 if sess_name == "LONDON" else 45)
                        else:
                            cd_len = int(cd_mode)
                        sell_cooldown_until = i + cd_len
                else:
                    total_wins += 1
                    curr_streak = 0
                    sell_loss_streak = 0

            else:
                # Trailing step
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

        # Evaluasi Greed Trailing Sesi (STEP 0.50%)
        curr_sess_pnl = balance - session_start_balance
        if curr_sess_pnl > session_peak_pnl:
            session_peak_pnl = curr_sess_pnl

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
            buf_mult = c_spec.get("buffer", 0.25)
            sl_buf_pts = max(0.50, span * (buf_mult * 0.15))

            # HTF Trend Check (Fast MA vs Slow MA)
            htf_ok_buy = True
            htf_ok_sell = True
            if c_spec.get("htf_filter"):
                htf_ok_buy = (ma_fast[i] >= ma_slow[i]) # Trend Bullish
                htf_ok_sell = (ma_fast[i] <= ma_slow[i]) # Trend Bearish

            # Evaluasi BUY Setup
            if l <= buy_zone_ceiling and c > current_floor:
                # Cek Cooldown Anti-Falling-Knife
                if i < buy_cooldown_until:
                    continue # Sedang dalam masa hukuman cooling down setelah kena SL!
                if not htf_ok_buy:
                    continue # Tertahan filter tren makro!

                hard_sl = current_floor - span * 0.15 - sl_buf_pts
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

            # Evaluasi SELL Setup
            elif h >= sell_zone_floor and c < current_roof:
                # Cek Cooldown Anti-Falling-Knife
                if i < sell_cooldown_until:
                    continue # Sedang dalam masa hukuman cooling down setelah kena SL!
                if not htf_ok_sell:
                    continue # Tertahan filter tren makro!

                hard_sl = current_roof + span * 0.15 + sl_buf_pts
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

    # Evaluasi Hasil Akhir
    months_list = sorted(monthly_pnl.keys())
    monthly_rois = [(monthly_pnl[m] / initial_capital) * 100.0 for m in months_list]
    months_ge_20 = sum(1 for r in monthly_rois if r >= 20.0)

    trading_days = list(daily_pnl.keys())
    win_days = [d for d in trading_days if daily_pnl[d] > 0]
    win_day_rate = (len(win_days) / len(trading_days) * 100.0) if trading_days else 0.0
    win_rate = (total_wins / total_trades_count * 100.0) if total_trades_count > 0 else 0.0

    return {
        "id": c_spec["id"],
        "desc": c_spec["desc"],
        "final_balance": balance,
        "net_pnl": balance - initial_capital,
        "max_dd_pct": max_dd,
        "win_rate": win_rate,
        "win_day_rate": win_day_rate,
        "total_trades": total_trades_count,
        "max_loss_streak": max_consecutive_losses,
        "months_ge_20": months_ge_20,
        "avg_monthly_roi": float(np.mean(monthly_rois)) if monthly_rois else 0.0
    }

print("\n🚀 Memulai simulasi 30 klon di 300.440 bar data lake...")
results = []
for idx, spec in enumerate(clone_specs):
    res = simulate_anti_knife_clone(spec)
    results.append(res)
    print(f"[{idx+1:02d}/30] {res['id']:<24}: Net PnL=${res['net_pnl']:>12,.2f} | Max DD={res['max_dd_pct']:>5.2f}% | WR={res['win_rate']:>5.1f}% | MaxStreakLoss={res['max_loss_streak']:>2d} | Trades={res['total_trades']:,}")

# Sort by lowest Max Drawdown and Net PnL
results.sort(key=lambda x: (x["max_dd_pct"], -x["net_pnl"]))

print("\n" + "=" * 105)
print("🏆 PAPAN KLASEMEN AKHIR TURNAMEN AKBAR 30 KLON ANTI-FALLING-KNIFE")
print("=" * 105)
print(f"{'Rank':<4} | {'Clone ID':<24} | {'Net PnL ($)':<16} | {'Max DD (%)':<10} | {'Win Rate':<10} | {'Max Streak Loss':<16} | {'Total Trades':<12}")
print("-" * 105)

for rank, r in enumerate(results, 1):
    med = "🥇" if rank == 1 else ("🥈" if rank == 2 else ("🥉" if rank == 3 else f"{rank:2d}"))
    print(f"{med:<4} | {r['id']:<24} | ${r['net_pnl']:>14,.2f} | {r['max_dd_pct']:>8.2f}% | {r['win_rate']:>8.1f}% | {r['max_loss_streak']:>15d} | {r['total_trades']:>12,}")

# Save JSON Report
report_path = PROJECT_ROOT / "reports" / "anti_falling_knife_tournament_report.json"
report_path.parent.mkdir(parents=True, exist_ok=True)
with open(report_path, "w") as f:
    json.dump(results, f, indent=2)

print(f"\n✅ Laporan lengkap tersimpan di: {report_path}")

