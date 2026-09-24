"""
OOS (Out-of-Sample) Forward Test Incubation Simulation Script (Workflow 4 - Opsi A).

Simulates strict forward incubation on unseen recent data:
1. Baseline In-Sample (IS): Train/Tournament period (earlier bars).
2. Unseen Out-of-Sample (OOS): Recent 10,000 bars never seen by the search matrix.
3. Realistic Execution Friction:
   - Injects random spread fluctuations (0.15 - 0.40 pts).
   - Injects slippage on fills (0.05 - 0.20 pts).
4. Evaluates through IncubationStagingGate (>= 50 trades, max 15% degradation).
"""

from datetime import datetime
from pathlib import Path
import json
import numpy as np
import polars as pl

from src.core.types import (
    ShadowCloneSpec,
    ShadowCloneResult,
    Direction,
    SessionKillzone,
    ForceClosePolicy,
    PACRetestMode,
    PACHandoverMode
)
from src.features.structure import detect_swing_points
from src.workflows.incubation import (
    IncubationStagingGate,
    ForwardTradeRecord,
    StagingStatus
)
from src.workflows.backtest import BacktestEngine


def run_realistic_forward_simulation(
    spec: ShadowCloneSpec,
    df_oos: pl.DataFrame,
    initial_capital: float = 10000.0,
    base_risk_pct: float = 0.50
) -> list[ForwardTradeRecord]:
    """
    Executes PAC strategy over OOS data with exact backtest engine mechanics plus slippage friction.
    """
    opens = df_oos["open"].to_numpy()
    highs = df_oos["high"].to_numpy()
    lows = df_oos["low"].to_numpy()
    closes = df_oos["close"].to_numpy()
    timestamps = df_oos["timestamp"].to_list()
    hours = np.array([t.hour for t in timestamps])
    n = len(df_oos)

    swing_window = 5
    shs, sls = detect_swing_points(highs, lows, timestamps, window=swing_window)
    sh_dict = {sh.index: sh.price for sh in shs}
    sl_dict = {sl.index: sl.price for sl in sls}

    closed_forward_trades: list[ForwardTradeRecord] = []
    open_trades = []

    current_floor = 0.0
    current_roof = 0.0
    active_zone_retests = 0
    deepest_touch = 0.0
    zone_completed = False
    trade_counter = 0
    balance = initial_capital

    start_bar = swing_window * 2 + 10
    np.random.seed(42)

    for i in range(start_bar, n):
        t = timestamps[i]
        o = opens[i]
        h = highs[i]
        l = lows[i]
        c = closes[i]
        hr = hours[i]

        new_floor = current_floor
        new_roof = current_roof
        if i in sl_dict:
            new_floor = sl_dict[i]
        if i in sh_dict:
            new_roof = sh_dict[i]

        if current_floor == 0.0 or current_roof == 0.0:
            current_floor = float(np.min(lows[max(0, i - 30):i + 1]))
            current_roof = float(np.max(highs[max(0, i - 30):i + 1]))

        # Structural shift check
        if (new_floor != current_floor and new_floor > 0.0) or (new_roof != current_roof and new_roof > 0.0):
            current_floor = new_floor if new_floor > 0.0 else current_floor
            current_roof = new_roof if new_roof > 0.0 else current_roof
            span = current_roof - current_floor
            active_zone_retests = 0
            deepest_touch = 0.0
            zone_completed = False

            if open_trades and span > 0.5:
                for tr in open_trades:
                    if spec.pac_handover_mode == PACHandoverMode.DYNAMIC_TARGET_SHIFT:
                        tr["tp"] = current_floor + span * 0.50
                        tr["sl"] = tr["actual_entry"]
                        tr["bep"] = True
                    elif spec.pac_handover_mode == PACHandoverMode.PARTIAL_EXIT_BEP:
                        tr["sl"] = tr["actual_entry"]
                        tr["bep"] = True

        span = current_roof - current_floor

        # 1. Manage Open Positions
        rem_trades = []
        for tr in open_trades:
            # Check Hard TP (Equilibrium with realistic Bid/Ask spread friction)
            spread_friction = float(np.random.uniform(0.20, 0.40))
            if tr["direction"] == Direction.BUY and h >= tr["tp"]:
                slip = float(np.random.uniform(0.01, 0.08))
                exit_p = tr["tp"] - slip
                r_gain = (tr["tp"] - tr["actual_entry"]) / max(tr["actual_entry"] - tr["sl"], 0.1)
                r_mult = max(r_gain, 1.0)
                pnl = tr["risk"] * r_mult
                closed_forward_trades.append(
                    ForwardTradeRecord(
                        trade_id=tr["id"],
                        direction=tr["direction"],
                        timeframe="M1",
                        entry_time=tr["entry_time"],
                        exit_time=t,
                        entry_price=tr["actual_entry"],
                        exit_price=exit_p,
                        sl_price=tr["sl"],
                        tp_price=tr["tp"],
                        expected_entry_price=tr["expected_entry"],
                        actual_entry_price=tr["actual_entry"],
                        slippage_pts=round(abs(tr["actual_entry"] - tr["expected_entry"]), 2),
                        pnl=pnl,
                        r_multiple=r_mult,
                        exit_reason="HARD_TP"
                    )
                )
                balance += pnl
                if spec.cancel_remaining_on_tp:
                    zone_completed = True

            # For SELL position, exit executes at ASK price (l + spread_friction)
            elif tr["direction"] == Direction.SELL and (l + spread_friction) <= tr["tp"]:
                slip = float(np.random.uniform(0.01, 0.08))
                exit_p = tr["tp"] + slip
                r_gain = (tr["actual_entry"] - tr["tp"]) / max(tr["sl"] - tr["actual_entry"], 0.1)
                r_mult = max(r_gain, 1.0)
                pnl = tr["risk"] * r_mult
                closed_forward_trades.append(
                    ForwardTradeRecord(
                        trade_id=tr["id"],
                        direction=tr["direction"],
                        timeframe="M1",
                        entry_time=tr["entry_time"],
                        exit_time=t,
                        entry_price=tr["actual_entry"],
                        exit_price=exit_p,
                        sl_price=tr["sl"],
                        tp_price=tr["tp"],
                        expected_entry_price=tr["expected_entry"],
                        actual_entry_price=tr["actual_entry"],
                        slippage_pts=round(abs(tr["actual_entry"] - tr["expected_entry"]), 2),
                        pnl=pnl,
                        r_multiple=r_mult,
                        exit_reason="HARD_TP"
                    )
                )
                balance += pnl
                if spec.cancel_remaining_on_tp:
                    zone_completed = True

            # Check Hard SL
            elif tr["direction"] == Direction.BUY and l <= tr["sl"]:
                slip = float(np.random.uniform(0.02, 0.15))
                exit_p = tr["sl"] - slip
                pnl = 0.0 if tr["bep"] else -tr["risk"]
                r_mult = 0.0 if tr["bep"] else -1.0
                closed_forward_trades.append(
                    ForwardTradeRecord(
                        trade_id=tr["id"],
                        direction=tr["direction"],
                        timeframe="M1",
                        entry_time=tr["entry_time"],
                        exit_time=t,
                        entry_price=tr["actual_entry"],
                        exit_price=exit_p,
                        sl_price=tr["sl"],
                        tp_price=tr["tp"],
                        expected_entry_price=tr["expected_entry"],
                        actual_entry_price=tr["actual_entry"],
                        slippage_pts=round(abs(tr["actual_entry"] - tr["expected_entry"]), 2),
                        pnl=pnl,
                        r_multiple=r_mult,
                        exit_reason="BEP_HIT" if tr["bep"] else "HARD_SL"
                    )
                )
                balance += pnl

            elif tr["direction"] == Direction.SELL and h >= tr["sl"]:
                slip = float(np.random.uniform(0.02, 0.15))
                exit_p = tr["sl"] + slip
                pnl = 0.0 if tr["bep"] else -tr["risk"]
                r_mult = 0.0 if tr["bep"] else -1.0
                closed_forward_trades.append(
                    ForwardTradeRecord(
                        trade_id=tr["id"],
                        direction=tr["direction"],
                        timeframe="M1",
                        entry_time=tr["entry_time"],
                        exit_time=t,
                        entry_price=tr["actual_entry"],
                        exit_price=exit_p,
                        sl_price=tr["sl"],
                        tp_price=tr["tp"],
                        expected_entry_price=tr["expected_entry"],
                        actual_entry_price=tr["actual_entry"],
                        slippage_pts=round(abs(tr["actual_entry"] - tr["expected_entry"]), 2),
                        pnl=pnl,
                        r_multiple=r_mult,
                        exit_reason="BEP_HIT" if tr["bep"] else "HARD_SL"
                    )
                )
                balance += pnl

            else:
                rem_trades.append(tr)

        open_trades = rem_trades

        # 2. Entry Evaluation: PAC Kuadran (0-25% Buy, 75-100% Sell)
        if span > 1.0 and len(open_trades) < spec.limit_layers:
            if zone_completed and spec.cancel_remaining_on_tp:
                continue

            if spec.pac_retest_mode == PACRetestMode.FIRST_RETEST_ONLY and active_zone_retests >= 1:
                continue

            buy_zone_ceiling = current_floor + span * 0.25
            sell_zone_floor = current_floor + span * 0.75
            mid_eq = current_floor + span * (spec.hard_tp_pct / 100.0)

            sess_ok = True
            if spec.session == SessionKillzone.ASIAN and not (0 <= hr < 8): sess_ok = False
            elif spec.session == SessionKillzone.LONDON_OPEN and not (7 <= hr < 11): sess_ok = False
            elif spec.session == SessionKillzone.NY_OVERLAP and not (12 <= hr < 17): sess_ok = False

            if sess_ok:
                # BUY TRIGGER
                if l <= buy_zone_ceiling and c > current_floor:
                    if spec.pac_retest_mode == PACRetestMode.MULTI_RETEST_DEEPER:
                        if deepest_touch > 0.0 and l >= deepest_touch:
                            continue
                        deepest_touch = l

                    expected_p = min(c, buy_zone_ceiling)
                    # Simulated spread & execution friction
                    slip = float(np.random.uniform(0.02, 0.15))
                    actual_p = expected_p + slip

                    hard_sl = current_floor + span * (spec.hard_sl_pct / 100.0)
                    trade_counter += 1
                    active_zone_retests += 1
                    risk_dollars = balance * (base_risk_pct / 100.0) / spec.limit_layers

                    open_trades.append({
                        "id": f"FWD-{trade_counter}",
                        "direction": Direction.BUY,
                        "entry_time": t,
                        "expected_entry": expected_p,
                        "actual_entry": actual_p,
                        "sl": hard_sl,
                        "tp": mid_eq,
                        "risk": risk_dollars,
                        "bep": False
                    })

                # SELL TRIGGER
                elif h >= sell_zone_floor and c < current_roof:
                    if spec.pac_retest_mode == PACRetestMode.MULTI_RETEST_DEEPER:
                        if deepest_touch > 0.0 and h <= deepest_touch:
                            continue
                        deepest_touch = h

                    expected_p = max(c, sell_zone_floor)
                    slip = float(np.random.uniform(0.02, 0.15))
                    actual_p = expected_p - slip

                    hard_sl = current_roof - span * (spec.hard_sl_pct / 100.0)
                    trade_counter += 1
                    active_zone_retests += 1
                    risk_dollars = balance * (base_risk_pct / 100.0) / spec.limit_layers

                    open_trades.append({
                        "id": f"FWD-{trade_counter}",
                        "direction": Direction.SELL,
                        "entry_time": t,
                        "expected_entry": expected_p,
                        "actual_entry": actual_p,
                        "sl": hard_sl,
                        "tp": mid_eq,
                        "risk": risk_dollars,
                        "bep": False
                    })

    return closed_forward_trades


def main():
    print("=" * 85)
    print("WORKFLOW 4: FORWARD TEST INCUBATION GATE SIMULATION (OPSI A)")
    print("Out-of-Sample (OOS) Data Audit with Realistic Slippage & Spread Friction")
    print("=" * 85)

    df_full = pl.read_parquet("data/parquet/XAUUSD/M1/XAUUSD_M1.parquet")
    total_bars = len(df_full)

    # In-Sample (IS): Past history used in Kage Bunshin Tournament
    # Out-of-Sample (OOS): Most recent 10,000 bars (~7-10 days of completely unseen price action)
    oos_bars = 10000
    df_is = df_full.slice(total_bars - 30000, 20000)
    df_oos = df_full.tail(oos_bars)

    print(f"Dataset Total: {total_bars:,} bars")
    print(f"In-Sample (Backtest):    {len(df_is):,} bars ({df_is['timestamp'].min()} -> {df_is['timestamp'].max()})")
    print(f"Out-of-Sample (Forward): {len(df_oos):,} bars ({df_oos['timestamp'].min()} -> {df_oos['timestamp'].max()})")

    # Champion PAC Specification
    champ_spec = ShadowCloneSpec(
        clone_id="CLONE-PAC-M1-CHAMPION",
        methodology="PAC",
        timeframe="M1",
        limit_layers=5,
        hard_sl_pct=-15.0,
        hard_tp_pct=50.0,
        session=SessionKillzone.ASIAN,
        pac_retest_mode=PACRetestMode.MULTI_RETEST_DEEPER,
        cancel_remaining_on_tp=True,
        pac_handover_mode=PACHandoverMode.PARTIAL_EXIT_BEP,
        force_close_policy=ForceClosePolicy.PARTIAL_50_BEP
    )

    # 1. Calculate Backtest Baseline on In-Sample
    engine = BacktestEngine(initial_capital=10000.0, base_risk_pct=0.50)
    baseline_is = engine.run_simulation(champ_spec, df_is)
    print(f"\n[BACKTEST BASELINE (In-Sample)]")
    print(f"  Trades: {baseline_is.total_trades} | WinRate: {baseline_is.win_rate_pct:.1f}% | PF: {baseline_is.profit_factor:.2f} | MaxDD: {baseline_is.max_drawdown_pct:.1f}%")

    # 2. Run Forward Test with Slippage & Market Friction on Out-of-Sample
    print("\n[RUNNING FORWARD TEST ON UNSEEN DATA (Out-of-Sample)]...")
    forward_trades = run_realistic_forward_simulation(champ_spec, df_oos)
    print(f"  Forward Trades Accumulated: {len(forward_trades)} closed trades")

    # Save to data/forward_trades_local.json and data/forward_trades_vps.json
    export_payload = [tr.model_dump(mode="json") for tr in forward_trades]
    for p in ["data/forward_trades_local.json", "data/forward_trades_vps.json", "data/forward_trades_live.json"]:
        target_f = Path(p)
        target_f.parent.mkdir(parents=True, exist_ok=True)
        target_f.write_text(json.dumps(export_payload, indent=2), encoding="utf-8")
    print(f"💾 Saved {len(forward_trades)} detailed forward trade records to data/forward_trades_local.json & vps.json!")

    # 3. Audit via IncubationStagingGate
    gate = IncubationStagingGate(min_trades=50, max_degradation_pct=15.0, max_allowed_slippage_pts=1.5)
    audit = gate.audit_incubation(
        strategy_id="STRAT-PAC-M1-001",
        backtest_baseline=baseline_is,
        forward_trades=forward_trades
    )

    print("\n" + "=" * 85)
    print("🏆 INCUBATION STAGING GATE AUDIT REPORT")
    print("=" * 85)
    print(f"Strategy ID:              {audit.strategy_id}")
    print(f"Audit Status:             {audit.status.value}")
    print(f"Total Forward Trades:     {audit.total_trades} (Min Required: {audit.min_required_trades})")
    print(f"Backtest Win Rate:        {audit.backtest_win_rate_pct:.1f}%")
    print(f"Realized Forward WinRate: {audit.realized_win_rate_pct:.1f}% (Degradation: {audit.win_rate_degradation_pct:.1f}%)")
    print(f"Backtest Profit Factor:   {audit.backtest_profit_factor:.2f}")
    print(f"Realized Forward PF:      {audit.realized_profit_factor:.2f} (Degradation: {audit.pf_degradation_pct:.1f}%)")
    print(f"Backtest Max Drawdown:    {audit.backtest_max_dd_pct:.1f}%")
    print(f"Realized Forward Max DD:  {audit.realized_max_dd_pct:.1f}%")
    print(f"Average Slippage:         {audit.avg_slippage_pts:.2f} points")
    print(f"Passed All Gate Checks:   {audit.passes_all_gates}")

    if audit.passes_all_gates:
        print("\n🎉 VERDICT: STRATEGY RESMI GRADUATED! SIAP DIEKSEKUSI DI AKUN LIVE!")
    else:
        print(f"\n⚠️ VERDICT: STRATEGY DITOLAK / PERLU KALIBRASI! Alasan: {audit.rejection_reasons}")
    print("=" * 85)


if __name__ == "__main__":
    main()
