from datetime import datetime, timedelta
import pytest

from src.core.types import (
    ShadowCloneSpec,
    ShadowCloneResult,
    Direction
)
from src.workflows.incubation import (
    IncubationStagingGate,
    ForwardTradeRecord,
    StagingStatus
)


def test_incubation_gate_insufficient_sample():
    gate = IncubationStagingGate(min_trades=50)
    spec = ShadowCloneSpec(clone_id="CLONE-PAC-M1", methodology="PAC", timeframe="M1")
    baseline = ShadowCloneResult(
        clone_id="CLONE-PAC-M1",
        spec=spec,
        total_trades=500,
        win_rate_pct=78.0,
        profit_factor=3.5,
        net_pnl=5000.0,
        roi_pct=50.0,
        max_drawdown_pct=2.0,
        avg_trades_per_day=35.0,
        monthly_green_pct=100.0
    )

    trades = [
        ForwardTradeRecord(
            trade_id=f"TR-{i}",
            direction=Direction.BUY,
            timeframe="M1",
            entry_time=datetime.now(),
            entry_price=2650.0,
            exit_price=2652.0,
            sl_price=2648.0,
            tp_price=2652.0,
            expected_entry_price=2650.0,
            actual_entry_price=2650.1,
            slippage_pts=0.1,
            pnl=20.0,
            r_multiple=1.0,
            exit_reason="HARD_TP"
        )
        for i in range(25)
    ]

    res = gate.audit_incubation("STRAT-PAC-001", baseline, trades)
    assert res.status == StagingStatus.INSUFFICIENT_SAMPLE
    assert res.passes_all_gates is False
    assert res.total_trades == 25


def test_incubation_gate_graduates_robust_strategy():
    gate = IncubationStagingGate(min_trades=50, max_degradation_pct=15.0)
    spec = ShadowCloneSpec(clone_id="CLONE-PAC-M1", methodology="PAC", timeframe="M1")
    baseline = ShadowCloneResult(
        clone_id="CLONE-PAC-M1",
        spec=spec,
        total_trades=500,
        win_rate_pct=75.0,
        profit_factor=3.0,
        net_pnl=5000.0,
        roi_pct=50.0,
        max_drawdown_pct=2.5,
        avg_trades_per_day=35.0,
        monthly_green_pct=100.0
    )

    # 40 wins, 10 losses (80% WR, PF high, slippage minimal)
    trades = []
    for i in range(50):
        is_win = (i < 40)
        trades.append(
            ForwardTradeRecord(
                trade_id=f"TR-{i}",
                direction=Direction.BUY,
                timeframe="M1",
                entry_time=datetime.now(),
                entry_price=2650.0,
                exit_price=2652.0 if is_win else 2648.0,
                sl_price=2648.0,
                tp_price=2652.0,
                expected_entry_price=2650.0,
                actual_entry_price=2650.1,
                slippage_pts=0.1,
                pnl=20.0 if is_win else -10.0,
                r_multiple=1.0 if is_win else -1.0,
                exit_reason="HARD_TP" if is_win else "HARD_SL"
            )
        )

    res = gate.audit_incubation("STRAT-PAC-001", baseline, trades)
    assert res.status == StagingStatus.GRADUATED_LIVE
    assert res.passes_all_gates is True
    assert res.realized_win_rate_pct == 80.0
