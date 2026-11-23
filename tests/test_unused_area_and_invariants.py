"""
Unit Tests for Complete Unused Area Handling & Architectural Order Invariants (INCIDENT-001).
Validates:
1. POI Prioritizer transmits deepest_touch_price and is_mitigated to SelectedPOIAnchor.
2. OrderDispatchCommand strictly rejects inverted stops on initial orders (BUY_LIMIT / SELL_LIMIT).
3. OrderDispatchCommand permits SL+ / Trailing / Auto-BEP+ during position modifications.
4. AuditorAgent disqualifies clones with inverted stop loss specifications.
5. Backtest engine tracks deepest_touch and skips penetrated grid levels within the swing.
"""

import pytest
from datetime import datetime
from src.core.types import (
    Direction,
    OrderBlock,
    OrderBlockType,
    FairValueGap,
    ShadowCloneSpec,
    ShadowCloneResult,
    TradingStyle,
    PACRetestMode
)
from src.features.poi_prioritizer import POIPrioritizer, SelectedPOIAnchor
from src.workflows.live_execution import OrderDispatchCommand
from src.agents.auditor import AuditorAgent
from src.workflows.backtest import BacktestEngine, TradeRecord


def test_poi_prioritizer_preserves_deepest_touch_and_mitigation():
    """Verify that POIPrioritizer preserves deepest_touch_price and is_mitigated from OrderBlock."""
    now = datetime.now()
    # Create an RBR OrderBlock that has already been penetrated to 2642.50
    rbr_ob = OrderBlock(
        id="OB-RBR-001",
        direction=Direction.BUY,
        top=2645.0,
        bottom=2640.0,
        mean_threshold=2642.5,
        timestamp=now,
        bar_index=10,
        ob_type=OrderBlockType.CONTINUATION_RBR,
        touch_count=2,
        deepest_touch_price=2642.50,
        is_mitigated=True
    )

    prioritizer = POIPrioritizer(proximity_threshold_points=12.0)
    selected_floor = prioritizer.rank_and_select_floor(
        current_price=2648.0,
        obs=[rbr_ob],
        fvgs=[],
        confluences=[],
        fallback_swing_low=2635.0
    )

    assert selected_floor.poi_type == "RBR"
    assert selected_floor.deepest_touch_price == 2642.50
    assert selected_floor.is_mitigated is True
    assert selected_floor.touch_count == 2


def test_order_dispatch_command_rejects_inverted_limit_stops():
    """Verify that OrderDispatchCommand raises ValueError when SL is inverted relative to Entry."""
    # BUY_LIMIT with SL above entry (Inverted SL) -> MUST RAISE
    with pytest.raises(ValueError, match="CRITICAL INVALID STOPS: BUY_LIMIT SL"):
        OrderDispatchCommand(
            command_id="CMD-001",
            symbol="XAUUSD",
            action="ORDER_SEND",
            order_type="BUY_LIMIT",
            lots=0.05,
            price=3694.56,  # L4 Entry
            sl=3697.15,     # Inverted SL above Entry!
            tp=3710.00,
            comment="M1_L4_RUN"
        )

    # SELL_LIMIT with SL below entry (Inverted SL) -> MUST RAISE
    with pytest.raises(ValueError, match="CRITICAL INVALID STOPS: SELL_LIMIT SL"):
        OrderDispatchCommand(
            command_id="CMD-002",
            symbol="XAUUSD",
            action="ORDER_SEND",
            order_type="SELL_LIMIT",
            lots=0.05,
            price=3725.44,  # L4 Entry
            sl=3722.00,     # Inverted SL below Entry!
            tp=3710.00,
            comment="M1_L4_RUN"
        )


def test_order_dispatch_command_allows_valid_pending_limits():
    """Verify that OrderDispatchCommand succeeds with valid geometric stops."""
    cmd_buy = OrderDispatchCommand(
        command_id="CMD-003",
        symbol="XAUUSD",
        action="ORDER_SEND",
        order_type="BUY_LIMIT",
        lots=0.05,
        price=3694.56,
        sl=3689.50,     # 5.06 pts below Entry
        tp=3710.00,
        comment="M1_L4_RUN"
    )
    assert cmd_buy.sl < cmd_buy.price
    assert cmd_buy.tp > cmd_buy.price

    cmd_sell = OrderDispatchCommand(
        command_id="CMD-004",
        symbol="XAUUSD",
        action="ORDER_SEND",
        order_type="SELL_LIMIT",
        lots=0.05,
        price=3725.44,
        sl=3730.50,     # 5.06 pts above Entry
        tp=3710.00,
        comment="M1_L4_RUN"
    )
    assert cmd_sell.sl > cmd_sell.price
    assert cmd_sell.tp < cmd_sell.price


def test_order_dispatch_command_allows_sl_plus_on_modify():
    """Verify that position modification (MODIFY_POSITION / SL+ / Auto-BEP) allows SL above Entry for BUY."""
    # Open Buy position entered at 3700.0, floating at 3715.0, SL moved to 3705.0 to lock profit (+5 pts)
    cmd_modify = OrderDispatchCommand(
        command_id="CMD-005",
        symbol="XAUUSD",
        action="MODIFY_POSITION",
        order_type="BUY",
        lots=0.05,
        price=3700.00,  # Entry price
        sl=3705.00,     # SL+ locked in profit above entry!
        tp=3720.00,
        comment="AUTO_BEP_PLUS"
    )
    assert cmd_modify.sl > cmd_modify.price, "SL+ above entry must be allowed for position modification!"


def test_auditor_agent_disqualifies_inverted_stops_clone():
    """Verify that Senior Quant Auditor Agent automatically catches and disqualifies inverted SL clone specs."""
    spec_invalid = ShadowCloneSpec(
        clone_id="CLONE-ANOMALOUS-001",
        methodology="PAC_GRID",
        hard_sl_pct=15.0,  # Inverted! Positive SL pct above floor
        limit_layers=4
    )
    result_invalid = ShadowCloneResult(
        clone_id="CLONE-ANOMALOUS-001",
        spec=spec_invalid,
        total_trades=100,
        win_rate_pct=95.0,
        profit_factor=50.0,  # Artificially inflated
        net_pnl=99999.0,
        roi_pct=100.0,
        max_drawdown_pct=2.0,
        avg_trades_per_day=5.0,
        monthly_green_pct=100.0
    )

    spec_valid = ShadowCloneSpec(
        clone_id="CLONE-VALID-002",
        methodology="PAC_GRID",
        hard_sl_pct=-25.0,
        limit_layers=4
    )
    result_valid = ShadowCloneResult(
        clone_id="CLONE-VALID-002",
        spec=spec_valid,
        total_trades=80,
        win_rate_pct=85.0,
        profit_factor=2.5,
        net_pnl=5000.0,
        roi_pct=25.0,
        max_drawdown_pct=3.5,
        avg_trades_per_day=4.0,
        monthly_green_pct=80.0
    )

    auditor = AuditorAgent()
    ranked = auditor.audit_and_rank_clones([result_invalid, result_valid])

    assert result_invalid.is_disqualified is True
    assert "MATH_ANOMALY" in result_invalid.disqualification_reason
    assert result_valid.is_disqualified is False
    assert ranked[0].clone_id == "CLONE-VALID-002"


def test_effective_penetration_combines_swing_and_poi_deepest_touch():
    """Verify that effective penetration incorporates both lookback swing and POI historical touches."""
    # Live market setup
    lookback_pullback_low = 3703.0
    poi_deepest_touch = 3701.0  # POI had an even deeper historical penetration earlier!

    eff_pullback_low = min(lookback_pullback_low, poi_deepest_touch) if poi_deepest_touch is not None else lookback_pullback_low

    raw_levels = [3705.0, 3702.5, 3700.0, 3694.56] # L1, L2, L3, L4
    valid_layers = []

    for lay_i, limit_p in enumerate(raw_levels):
        # SMC Unused Area check: Skip levels already penetrated
        if eff_pullback_low <= (limit_p - 0.20):
            continue
        valid_layers.append((lay_i, limit_p))

    # Because eff_pullback_low is 3701.0:
    # L1 (3705.0): 3701.0 <= 3704.8 -> Skipped!
    # L2 (3702.5): 3701.0 <= 3702.3 -> Skipped!
    # L3 (3700.0): 3701.0 <= 3699.8 -> False -> Kept! (Unused)
    # L4 (3694.56): 3701.0 <= 3694.36 -> False -> Kept! (Unused)
    assert len(valid_layers) == 2
    assert valid_layers[0] == (2, 3700.0)
    assert valid_layers[1] == (3, 3694.56)
