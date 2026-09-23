from pathlib import Path
from datetime import datetime
import pytest

from src.core.types import MarketStateSnapshot, Direction, Trend, PriceQuote, StructureState
from src.data.adapter import BrokerAdapter, BrokerSpec
from src.workflows.live_execution import (
    CircuitBreakerSentinel,
    LiveExecutionPipeline,
    ExecutionDecision
)


def test_circuit_breaker_sentinel_trips_on_drawdown():
    sentinel = CircuitBreakerSentinel(max_daily_drawdown_pct=3.0, handbrake_path="tests/temp_handbrake.lock")
    sentinel.reset_daily_equity(10000.0)

    # 1. Equity normal
    safe, msg = sentinel.check_safety(9800.0)  # -2.0% DD
    assert safe is True

    # 2. Equity breached 3.0%
    safe, msg = sentinel.check_safety(9690.0)  # -3.1% DD
    assert safe is False
    assert "CIRCUIT_BREAKER" in msg
    assert sentinel.is_tripped is True


def test_manual_handbrake_engagement(tmp_path):
    lock_file = tmp_path / "handbrake.lock"
    sentinel = CircuitBreakerSentinel(max_daily_drawdown_pct=3.0, handbrake_path=str(lock_file))

    # Without lock
    safe, _ = sentinel.check_safety(10000.0)
    assert safe is True

    # Create lock file
    lock_file.write_text("MANUAL EMERGENCY PAUSE")
    safe, msg = sentinel.check_safety(10000.0)
    assert safe is False
    assert msg == "MANUAL_HANDBRAKE_ENGAGED"


def test_live_execution_pipeline_approves_valid_trade():
    spec = BrokerSpec(broker_name="ICMarkets", broker_symbol="XAUUSD")
    adapter = BrokerAdapter(spec=spec)
    sentinel = CircuitBreakerSentinel(max_daily_drawdown_pct=3.0, handbrake_path="configs/non_existent.lock")
    pipeline = LiveExecutionPipeline(
        broker_adapter=adapter,
        circuit_breaker=sentinel,
        base_risk_pct=0.50,
        min_checklist_score=8.0
    )

    now = datetime.now()
    snapshot = MarketStateSnapshot(
        timestamp=now,
        symbol="XAUUSD",
        timeframe="M1",
        current_price=PriceQuote(bid=2650.0, ask=2650.2, spread=0.2, timestamp=now),
        htf_trend=Trend.BULLISH,
        structure=StructureState()
    )

    # Case A: Low checklist score -> Rejected
    dec, cmd, msg = pipeline.evaluate_and_dispatch(
        snapshot=snapshot,
        candidate_direction=Direction.BUY,
        entry_price=2645.0,
        sl_price=2640.0,
        tp_price=2655.0,
        checklist_score=6.5,
        current_equity=10000.0
    )
    assert dec == ExecutionDecision.INSUFFICIENT_CHECKLIST_SCORE
    assert cmd is None

    # Case B: High checklist score & Safe Sentinel -> Approved
    dec, cmd, msg = pipeline.evaluate_and_dispatch(
        snapshot=snapshot,
        candidate_direction=Direction.BUY,
        entry_price=2645.0,
        sl_price=2640.0,
        tp_price=2655.0,
        checklist_score=9.0,
        current_equity=10000.0
    )
    assert dec == ExecutionDecision.APPROVED
    assert cmd is not None
    assert cmd.lots > 0.0
    assert cmd.order_type == "BUY_LIMIT"
    assert cmd.symbol == "XAUUSD"
