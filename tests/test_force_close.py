from datetime import datetime, timedelta
from src.core.types import (
    MarketStateSnapshot,
    PriceQuote,
    Trend,
    StructureState,
    StructureEventType,
    Direction,
    ForceCloseAction,
    FairValueGap
)
from src.engine.force_close import ForceCloseGuardianEngine


def test_force_close_structural_invalidation():
    guardian = ForceCloseGuardianEngine()
    now = datetime(2025, 1, 1, 12, 0)
    open_time = now - timedelta(minutes=5)

    # Position is BUY, but snapshot emits CHOCH_BEARISH!
    snapshot = MarketStateSnapshot(
        symbol="XAUUSD",
        timestamp=now,
        timeframe="M1",
        current_price=PriceQuote(bid=2600.0, ask=2600.2, spread=0.2, timestamp=now),
        htf_trend=Trend.BULLISH,
        structure=StructureState(last_event=StructureEventType.CHOCH_BEARISH)
    )

    trigger = guardian.evaluate_position(
        position_id="POS-001",
        direction=Direction.BUY,
        entry_price=2605.0,
        current_snapshot=snapshot,
        open_time=open_time
    )

    assert trigger.action == ForceCloseAction.FORCE_CLOSE_MARKET
    assert "Bearish CHoCH" in trigger.reason


def test_force_close_healthy_hold():
    guardian = ForceCloseGuardianEngine()
    now = datetime(2025, 1, 1, 12, 0)
    open_time = now - timedelta(minutes=2)

    snapshot = MarketStateSnapshot(
        symbol="XAUUSD",
        timestamp=now,
        timeframe="M1",
        current_price=PriceQuote(bid=2600.0, ask=2600.2, spread=0.2, timestamp=now),
        htf_trend=Trend.BULLISH,
        structure=StructureState(last_event=StructureEventType.BOS_BULLISH)
    )

    trigger = guardian.evaluate_position(
        position_id="POS-002",
        direction=Direction.BUY,
        entry_price=2598.0,
        current_snapshot=snapshot,
        open_time=open_time
    )

    assert trigger.action == ForceCloseAction.HOLD
