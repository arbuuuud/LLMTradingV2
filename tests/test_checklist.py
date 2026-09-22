from datetime import datetime
from src.core.types import (
    MarketStateSnapshot,
    PriceQuote,
    Trend,
    StructureState,
    LiquidityState,
    ChecklistRule,
    Direction,
    FairValueGap
)
from src.engine.checklist import ChecklistScoringEngine


def test_checklist_scoring_pass():
    rules = [
        ChecklistRule(id="HTF_TREND_ALIGNED", description="HTF align", weight=3.0, mandatory=True),
        ChecklistRule(id="ACTIVE_POI_PRESENT", description="POI present", weight=4.0, mandatory=True),
        ChecklistRule(id="LIQUIDITY_SWEPT", description="Sweep done", weight=3.0, mandatory=False),
    ]
    engine = ChecklistScoringEngine(strategy_id="TEST-01", rules=rules, min_score_threshold=7.0)

    now = datetime(2025, 1, 1, 12, 0)
    snapshot = MarketStateSnapshot(
        symbol="XAUUSD",
        timestamp=now,
        timeframe="M1",
        current_price=PriceQuote(bid=2600.0, ask=2600.2, spread=0.2, timestamp=now),
        htf_trend=Trend.BULLISH,
        structure=StructureState(),
        active_fvgs=[
            FairValueGap(
                id="FVG-1",
                direction=Direction.BUY,
                top=2605.0,
                bottom=2595.0,
                timestamp=now,
                bar_index=1,
                is_mitigated=False
            )
        ],
        liquidity=LiquidityState(sell_side_swept=True)
    )

    evaluation = engine.evaluate(snapshot, target_direction=Direction.BUY)

    assert evaluation.passed is True
    assert evaluation.total_score == 10.0
    assert evaluation.direction == Direction.BUY


def test_checklist_scoring_failed_mandatory():
    rules = [
        ChecklistRule(id="HTF_TREND_ALIGNED", description="HTF align", weight=5.0, mandatory=True),
        ChecklistRule(id="LIQUIDITY_SWEPT", description="Sweep done", weight=5.0, mandatory=False),
    ]
    engine = ChecklistScoringEngine(strategy_id="TEST-01", rules=rules, min_score_threshold=5.0)

    now = datetime(2025, 1, 1, 12, 0)
    # Trend is BEARISH, but target direction is BUY -> mandatory fails!
    snapshot = MarketStateSnapshot(
        symbol="XAUUSD",
        timestamp=now,
        timeframe="M1",
        current_price=PriceQuote(bid=2600.0, ask=2600.2, spread=0.2, timestamp=now),
        htf_trend=Trend.BEARISH,
        structure=StructureState(),
        liquidity=LiquidityState(sell_side_swept=True)
    )

    evaluation = engine.evaluate(snapshot, target_direction=Direction.BUY)

    assert evaluation.passed is False
    assert evaluation.direction == Direction.WAIT
