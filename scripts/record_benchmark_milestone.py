"""
Workflow Script: Record Benchmark Milestone (DEC-043).
Executes standard 300,440 M1 backtest, runs AuditorAgent validation,
records candidate metrics into data/benchmark_matrix.json,
and prints the Before vs After comparison table.

Usage:
  python scripts/record_benchmark_milestone.py --name "Smart Judas Fortress + Reflex Active Guard" --id "MS-001-SMART-FORTRESS-REFLEX"
"""

import sys
import os
import argparse
import json
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.analytics.benchmark_matrix import get_benchmark_matrix_manager, DEFAULT_BASELINE
from src.agents.auditor import AuditorAgent
from scripts.run_head_to_head_before_after import (
    PARQUET_PATH,
    precompute_htf_biases,
    precompute_tf_features,
    precompute_poi_arrays,
    precompute_atr,
    run_simulation
)
import polars as pl
import numpy as np


def main():
    parser = argparse.ArgumentParser(description="Record strategy benchmark milestone")
    parser.add_argument("--name", type=str, default="Smart Judas Fortress + Reflex Active Guard", help="Milestone Strategy Name")
    parser.add_argument("--id", type=str, default="MS-001-SMART-FORTRESS-REFLEX", help="Milestone ID")
    parser.add_argument("--desc", type=str, default="Smart SL (OB/Fibo -13%), Grid 4 Lapis (-27.2%), Velocity Gate (1.8x ATR), Volatility Stand-Aside.", help="Milestone description")
    args = parser.parse_args()

    print("=" * 85)
    print(f"🏛️ RECORDING STRATEGY BENCHMARK MILESTONE: {args.id}")
    print(f"Strategy Name: {args.name}")
    print("=" * 85)

    print("[1/3] Loading 300,440 M1 dataset and features...")
    df = pl.read_parquet(PARQUET_PATH)
    htf_biases = precompute_htf_biases(df)
    
    tf_features = {}
    for tf_m, code in [(1, "M1"), (2, "M2"), (3, "M3"), (5, "M5"), (15, "M15"), (30, "M30")]:
        tf_features[code] = precompute_tf_features(df, tf_m)

    t_secs = (df["timestamp"].dt.timestamp().to_numpy() / 1_000_000).astype(np.float64)
    hours = df["timestamp"].dt.hour().to_numpy()
    minutes = df["timestamp"].dt.minute().to_numpy()
    highs = df["high"].to_numpy()
    lows = df["low"].to_numpy()
    closes = df["close"].to_numpy()
    opens = df["open"].to_numpy()
    days = df["timestamp"].dt.strftime("%Y-%m-%d").to_list()
    iso_weeks = df["timestamp"].dt.strftime("%G-W%V").to_list()

    htf_aligned = {}
    for code in ["D1", "H4", "H1"]:
        joined = df.select(["timestamp"]).join_asof(
            htf_biases[code],
            left_on="timestamp",
            right_on="available_at",
            strategy="backward"
        )
        htf_aligned[code] = joined[f"{code}_bias"].fill_null("NEUTRAL").to_numpy()
    d1_bias = htf_aligned["D1"]
    h4_bias = htf_aligned["H4"]

    micro_disc = tf_features["M1"]["in_discount"] | tf_features["M2"]["in_discount"] | tf_features["M3"]["in_discount"]
    inter_disc = tf_features["M5"]["in_discount"] | tf_features["M15"]["in_discount"]
    micro_prem = tf_features["M1"]["in_premium"] | tf_features["M2"]["in_premium"] | tf_features["M3"]["in_premium"]
    inter_prem = tf_features["M5"]["in_premium"] | tf_features["M15"]["in_premium"]
    bos_bull_inter = tf_features["M15"]["bos_bull"] | tf_features["M30"]["bos_bull"]
    bos_bear_inter = tf_features["M15"]["bos_bear"] | tf_features["M30"]["bos_bear"]

    sw_h = tf_features["M1"]["sw_high"]
    sw_l = tf_features["M1"]["sw_low"]
    poi_data = precompute_poi_arrays(highs, lows, opens, closes, sw_h, sw_l)

    atr_arr = precompute_atr(highs, lows, closes, 14)
    cs_atr = np.cumsum(atr_arr)
    atr_base = np.zeros(len(atr_arr), dtype=np.float64)
    atr_base[100:] = (cs_atr[100:] - cs_atr[:-100]) / 100.0
    atr_base[:100] = atr_arr[:100]

    bundle = {
        "t_secs": t_secs,
        "hours": hours,
        "minutes": minutes,
        "highs": highs,
        "lows": lows,
        "closes": closes,
        "opens": opens,
        "days": days,
        "iso_weeks": iso_weeks,
        "sw_h_m1": sw_h,
        "sw_l_m1": sw_l,
        "span_m1": tf_features["M1"]["span"],
        "in_disc_m1": tf_features["M1"]["in_discount"],
        "in_prem_m1": tf_features["M1"]["in_premium"],
        "in_disc_m5": tf_features["M5"]["in_discount"],
        "in_prem_m5": tf_features["M5"]["in_premium"],
        "micro_disc": micro_disc,
        "inter_disc": inter_disc,
        "micro_prem": micro_prem,
        "inter_prem": inter_prem,
        "bos_bull_inter": bos_bull_inter,
        "bos_bear_inter": bos_bear_inter,
        "d1_bias": d1_bias,
        "h4_bias": h4_bias,
        "atr": atr_arr,
        "atr_base": atr_base,
        **poi_data
    }

    print("[2/3] Simulating candidate strategy on 300,440 M1 bars...")
    t0 = time.time()
    res = run_simulation(bundle, "AFTER_SMART_FORTRESS")
    print(f"Simulation completed in {time.time() - t0:.2f}s.")

    milestone_record = {
        "milestone_id": args.id,
        "name": args.name,
        "description": args.desc,
        "dataset_bars": len(df),
        "starting_equity": res["starting_equity"],
        "final_equity": res["final_equity"],
        "net_pnl": res["net_pnl"],
        "return_pct": res["return_pct"],
        "profit_factor": res["profit_factor"],
        "max_drawdown_pct": res["max_drawdown_pct"],
        "win_rate_pct": res["win_rate_pct"],
        "total_trades": res["total_trades"],
        "daily_1pct_target_hit_rate": res["daily_1pct_target_hit_rate"],
        "daily_loss_breach_rate": res["daily_loss_breach_rate"],
        "weekly_5pct_target_hit_rate": res["weekly_5pct_target_hit_rate"],
        "wick_saved_count": res["wick_saved_count"],
        "freight_train_avoided_count": res["freight_train_avoided_count"],
        "stand_aside_count": res["stand_aside_count"],
        "ttl_cancelled_count": res.get("ttl_cancelled_count", 0)
    }

    print("[3/3] Running Quantitative Auditor Agent Verification...")
    auditor = AuditorAgent()
    audit_report = auditor.audit_benchmark_milestone(milestone_record, DEFAULT_BASELINE)
    print(f"Audit Approval Status: {'APPROVED ✅' if audit_report['is_approved_upgrade'] else 'NOT APPROVED ❌'}")
    print(f"Recommendation: {audit_report['recommendation']}")
    print(f"Quant Composite Score: {audit_report['quant_score']}")

    # Register into Matrix
    matrix_mgr = get_benchmark_matrix_manager()
    registered = matrix_mgr.register_milestone(milestone_record)
    comp = matrix_mgr.get_comparison(args.id)

    print("\n" + "=" * 90)
    print(f"📊 TABEL HEAD-TO-HEAD BEFORE vs AFTER: {args.name}")
    print("=" * 90)
    print(f"{'Metrik Evaluasi':32} | {'BEFORE (Baseline)':20} | {'AFTER (Candidate)':20} | {'Delta':15}")
    print("-" * 90)
    for r in comp["rows"]:
        print(f"{r['metric']:32} | {r['before']:>20} | {r['after']:>20} | {r['delta']:>15}")
    print("=" * 90)
    print(f"✅ Successfully registered milestone into {matrix_mgr.storage_path}")


if __name__ == "__main__":
    main()
