"""
Batch 1 & Batch 2 Kage Bunshin Tournament (Subtask 5-3G / DEC-019).
Exploits 32 Shadow Clones across 300,440 M1 bars of XAUUSD to test:
- Batch 1: HTF & Dynamic ATR SL Buffer (Avoid wick hunts like $4295)
- Batch 2A: ADX Trend-Spike Gatekeeper (ADX < 25, 30, 35, 40)
- Batch 2B: VWAP Institutional Price Gravity (Daily Anchored VWAP Filter)
- Batch 2C: RVOL Volume Surge Confluence (RVOL >= 1.0, 1.25, 1.5, 2.0)
- Baseline: Unfiltered Champion (DEC-028 Clone-08)
"""

import sys
import time
import json
from pathlib import Path
from typing import List, Dict, Any
import polars as pl

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.core.types import (
    ShadowCloneSpec,
    ShadowCloneResult,
    Direction,
    TradingStyle,
    SessionKillzone,
    ForceClosePolicy,
    PACRetestMode,
    PACHandoverMode
)
from src.workflows.backtest import BacktestEngine


def build_32_clones() -> List[ShadowCloneSpec]:
    clones = []

    # Baseline Champion (CLONE-08 dari DEC-028)
    clones.append(ShadowCloneSpec(
        clone_id="CLONE-00-BASELINE-CHAMPION",
        methodology="PAC",
        timeframe="M1",
        trading_style=TradingStyle.SCALPING,
        limit_layers=3,
        hard_sl_pct=-15.0,
        hard_tp_pct=50.0,
        pac_retest_mode=PACRetestMode.MULTI_RETEST_DEEPER,
        cancel_remaining_on_tp=True,
        pac_handover_mode=PACHandoverMode.DYNAMIC_TARGET_SHIFT,
        force_close_policy=ForceClosePolicy.SASUKE_PARTIAL_TRAILING,
        session=SessionKillzone.ALL_DAY,
        risk_per_trade_pct=0.50,
        htf_sl_buffer_mode="LOCAL_M1",
        grid_weight_mode="INVERTED_50_25_25"
    ))

    # =========================================================================
    # KELOMPOK 1: HTF & Dynamic ATR SL Buffer (Menjawab Kasus Wick $4295)
    # Variasi buffer: 0.25x, 0.50x, 0.75x, 1.0x, 1.25x, 1.5x ATR/Span buffer
    # =========================================================================
    for mult in [0.25, 0.50, 0.75, 1.0, 1.25, 1.5, 2.0]:
        clones.append(ShadowCloneSpec(
            clone_id=f"CLONE-HTF-BUFFER-{mult}x",
            methodology="PAC",
            timeframe="M1",
            trading_style=TradingStyle.SCALPING,
            limit_layers=3,
            hard_sl_pct=-15.0,
            hard_tp_pct=50.0,
            pac_retest_mode=PACRetestMode.MULTI_RETEST_DEEPER,
            cancel_remaining_on_tp=True,
            pac_handover_mode=PACHandoverMode.DYNAMIC_TARGET_SHIFT,
            force_close_policy=ForceClosePolicy.SASUKE_PARTIAL_TRAILING,
            session=SessionKillzone.ALL_DAY,
            risk_per_trade_pct=0.50,
            htf_sl_buffer_mode="ATR_BUFFER",
            htf_sl_atr_multiplier=mult,
            grid_weight_mode="INVERTED_50_25_25"
        ))

    # =========================================================================
    # KELOMPOK 2: ADX Trend-Spike Gatekeeper (Subtask 5-3G Pilar 1)
    # Tolak limit order jika ADX > threshold (menghindari menghadang kereta cepat)
    # Thresholds: 20, 25, 30, 35, 40, 45, 50
    # =========================================================================
    for adx_max in [20.0, 25.0, 30.0, 35.0, 40.0, 45.0, 50.0]:
        clones.append(ShadowCloneSpec(
            clone_id=f"CLONE-ADX-MAX-{int(adx_max)}",
            methodology="PAC",
            timeframe="M1",
            trading_style=TradingStyle.SCALPING,
            limit_layers=3,
            hard_sl_pct=-15.0,
            hard_tp_pct=50.0,
            pac_retest_mode=PACRetestMode.MULTI_RETEST_DEEPER,
            cancel_remaining_on_tp=True,
            pac_handover_mode=PACHandoverMode.DYNAMIC_TARGET_SHIFT,
            force_close_policy=ForceClosePolicy.SASUKE_PARTIAL_TRAILING,
            session=SessionKillzone.ALL_DAY,
            risk_per_trade_pct=0.50,
            adx_max_entry_gate=adx_max,
            grid_weight_mode="INVERTED_50_25_25"
        ))

    # =========================================================================
    # KELOMPOK 3: VWAP Institutional Price Gravity (Subtask 5-3G Pilar 2)
    # BUY hanya di bawah VWAP (true discount) / SELL hanya di atas VWAP (premium)
    # =========================================================================
    clones.append(ShadowCloneSpec(
        clone_id="CLONE-VWAP-DISCOUNT-ONLY",
        methodology="PAC",
        timeframe="M1",
        trading_style=TradingStyle.SCALPING,
        limit_layers=3,
        hard_sl_pct=-15.0,
        hard_tp_pct=50.0,
        pac_retest_mode=PACRetestMode.MULTI_RETEST_DEEPER,
        cancel_remaining_on_tp=True,
        pac_handover_mode=PACHandoverMode.DYNAMIC_TARGET_SHIFT,
        force_close_policy=ForceClosePolicy.SASUKE_PARTIAL_TRAILING,
        session=SessionKillzone.ALL_DAY,
        risk_per_trade_pct=0.50,
        vwap_filter_mode="BUY_BELOW_VWAP", # Buy below, Sell above
        grid_weight_mode="INVERTED_50_25_25"
    ))

    # =========================================================================
    # KELOMPOK 4: RVOL Volume Surge Confluence (Subtask 5-3G Pilar 3)
    # Entry hanya jika volume saat itu aktif/terkonfirmasi (RVOL >= threshold)
    # =========================================================================
    for rvol_gate in [0.75, 1.0, 1.25, 1.5, 1.75, 2.0]:
        clones.append(ShadowCloneSpec(
            clone_id=f"CLONE-RVOL-MIN-{rvol_gate}",
            methodology="PAC",
            timeframe="M1",
            trading_style=TradingStyle.SCALPING,
            limit_layers=3,
            hard_sl_pct=-15.0,
            hard_tp_pct=50.0,
            pac_retest_mode=PACRetestMode.MULTI_RETEST_DEEPER,
            cancel_remaining_on_tp=True,
            pac_handover_mode=PACHandoverMode.DYNAMIC_TARGET_SHIFT,
            force_close_policy=ForceClosePolicy.SASUKE_PARTIAL_TRAILING,
            session=SessionKillzone.ALL_DAY,
            risk_per_trade_pct=0.50,
            rvol_min_reaction_gate=rvol_gate,
            grid_weight_mode="INVERTED_50_25_25"
        ))

    # =========================================================================
    # KELOMPOK 5: Synergy Candidates (Best Combinations for Pre-Test)
    # Menggabungkan Buffer + Filter terbaik
    # =========================================================================
    for buf in [0.50, 1.0]:
        for adx in [35.0, 45.0]:
            clones.append(ShadowCloneSpec(
                clone_id=f"CLONE-SYNERGY-BUF{buf}-ADX{int(adx)}",
                methodology="PAC",
                timeframe="M1",
                trading_style=TradingStyle.SCALPING,
                limit_layers=3,
                hard_sl_pct=-15.0,
                hard_tp_pct=50.0,
                pac_retest_mode=PACRetestMode.MULTI_RETEST_DEEPER,
                cancel_remaining_on_tp=True,
                pac_handover_mode=PACHandoverMode.DYNAMIC_TARGET_SHIFT,
                force_close_policy=ForceClosePolicy.SASUKE_PARTIAL_TRAILING,
                session=SessionKillzone.ALL_DAY,
                risk_per_trade_pct=0.50,
                htf_sl_buffer_mode="ATR_BUFFER",
                htf_sl_atr_multiplier=buf,
                adx_max_entry_gate=adx,
                grid_weight_mode="INVERTED_50_25_25"
            ))

    for buf in [0.50, 1.0]:
        clones.append(ShadowCloneSpec(
            clone_id=f"CLONE-SYNERGY-BUF{buf}-VWAP",
            methodology="PAC",
            timeframe="M1",
            trading_style=TradingStyle.SCALPING,
            limit_layers=3,
            hard_sl_pct=-15.0,
            hard_tp_pct=50.0,
            pac_retest_mode=PACRetestMode.MULTI_RETEST_DEEPER,
            cancel_remaining_on_tp=True,
            pac_handover_mode=PACHandoverMode.DYNAMIC_TARGET_SHIFT,
            force_close_policy=ForceClosePolicy.SASUKE_PARTIAL_TRAILING,
            session=SessionKillzone.ALL_DAY,
            risk_per_trade_pct=0.50,
            htf_sl_buffer_mode="ATR_BUFFER",
            htf_sl_atr_multiplier=buf,
            vwap_filter_mode="BUY_BELOW_VWAP",
            grid_weight_mode="INVERTED_50_25_25"
        ))

    for buf in [0.50, 1.0]:
        clones.append(ShadowCloneSpec(
            clone_id=f"CLONE-SYNERGY-BUF{buf}-ADX40-VWAP",
            methodology="PAC",
            timeframe="M1",
            trading_style=TradingStyle.SCALPING,
            limit_layers=3,
            hard_sl_pct=-15.0,
            hard_tp_pct=50.0,
            pac_retest_mode=PACRetestMode.MULTI_RETEST_DEEPER,
            cancel_remaining_on_tp=True,
            pac_handover_mode=PACHandoverMode.DYNAMIC_TARGET_SHIFT,
            force_close_policy=ForceClosePolicy.SASUKE_PARTIAL_TRAILING,
            session=SessionKillzone.ALL_DAY,
            risk_per_trade_pct=0.50,
            htf_sl_buffer_mode="ATR_BUFFER",
            htf_sl_atr_multiplier=buf,
            adx_max_entry_gate=40.0,
            vwap_filter_mode="BUY_BELOW_VWAP",
            grid_weight_mode="INVERTED_50_25_25"
        ))

    return clones


def run_tournament():
    print("=" * 105)
    print("⚔️ NARUTO 32-CLONE KAGE BUNSHIN SHOWDOWN: HTF BUFFER, ADX, VWAP, RVOL PILLARS (300.440 BARS)")
    print("=" * 105)

    parquet_path = PROJECT_ROOT / "data" / "parquet" / "XAUUSD" / "M1" / "XAUUSD_M1.parquet"
    if not parquet_path.exists():
        print(f"❌ Parquet data lake tidak ditemukan di {parquet_path}")
        return

    print("📥 Memuat data lake 300.440 bar M1 XAUUSD...")
    t0 = time.time()
    df = pl.read_parquet(parquet_path)
    total_bars = len(df)
    load_time = time.time() - t0
    print(f"✅ Data loaded: {total_bars:,} bars dalam {load_time:.2f} detik.")

    # Precompute Indicators Once on the Entire DataFrame to avoid repeating per clone
    print("⚡ Precomputing Feature Pillars (ADX, VWAP, RVOL) secara vectorized...")
    t_feat = time.time()
    from src.features.indicators import calculate_adx, calculate_vwap, calculate_rvol
    df = calculate_adx(df, period=14)
    df = calculate_vwap(df, anchor="D")
    df = calculate_rvol(df, lookback=20)
    print(f"✅ Precomputed Pillars selesai dalam {time.time() - t_feat:.2f} detik.")

    engine = BacktestEngine(initial_capital=10000.0, base_risk_pct=0.50)
    clones = build_32_clones()
    print(f"🥷 Memanggil {len(clones)} Shadow Clones Naruto & Sasuke untuk adu tanding massal...\n")

    results: List[ShadowCloneResult] = []
    start_all = time.time()

    for idx, clone in enumerate(clones, 1):
        t_c = time.time()
        res = engine.run_simulation(clone, df)
        dur = time.time() - t_c
        results.append(res)
        print(f"[{idx:02d}/{len(clones):02d}] {clone.clone_id:<32} | Trades: {res.total_trades:>5} | WR: {res.win_rate_pct:>5.1f}% | PF: {res.profit_factor:>4.2f} | NetPnL: ${res.net_pnl:>9.2f} | MaxDD: {res.max_drawdown_pct:>4.2f}% ({dur:.1f}s)")

    total_sim_time = time.time() - start_all
    print("\n" + "=" * 105)
    print(f"🏁 TOURNAMENT SELESAI ({total_sim_time:.2f} detik). AUDITING LEADERBOARD & JURI EMPIRIS:")
    print("=" * 105)

    # Sort by Net PnL descending
    sorted_results = sorted(results, key=lambda x: x.net_pnl, reverse=True)

    header = f"{'RANK':<5} | {'CLONE ID':<32} | {'TRADES':<7} | {'WIN RATE':<9} | {'PF':<6} | {'NET PNL ($)':<12} | {'MAX DD %':<9} | {'STATUS'}"
    print(header)
    print("-" * len(header))

    for rank, r in enumerate(sorted_results, 1):
        status = "DISQUALIFIED" if r.is_disqualified else ("CHAMPION 👑" if rank == 1 else "ACTIVE")
        print(f"#{rank:<4} | {r.clone_id:<32} | {r.total_trades:>7} | {r.win_rate_pct:>8.1f}% | {r.profit_factor:>6.2f} | ${r.net_pnl:>11.2f} | {r.max_drawdown_pct:>8.2f}% | {status}")

    # Save to report JSON
    out_path = PROJECT_ROOT / "reports" / "htf_pillars_32_clones_tournament_report.json"
    data_to_save = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "total_bars": total_bars,
        "total_clones": len(clones),
        "execution_time_sec": round(total_sim_time, 2),
        "results": [
            {
                "clone_id": r.clone_id,
                "total_trades": r.total_trades,
                "win_rate_pct": r.win_rate_pct,
                "profit_factor": r.profit_factor,
                "net_pnl": round(r.net_pnl, 2),
                "roi_pct": round(r.roi_pct, 2),
                "max_drawdown_pct": round(r.max_drawdown_pct, 2),
                "disqualified": r.is_disqualified
            }
            for r in sorted_results
        ]
    }
    out_path.write_text(json.dumps(data_to_save, indent=2), encoding="utf-8")
    print(f"\n💾 Laporan lengkap tersimpan di: {out_path}")


if __name__ == "__main__":
    run_tournament()
