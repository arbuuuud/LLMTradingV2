import pytest
from datetime import datetime, timezone
from src.core.types import Direction, OrderBlock, OrderBlockType, FairValueGap
from src.features.poi_prioritizer import POIPrioritizer, SelectedPOIAnchor


def test_poi_prioritizer_ranks_dbd_over_ob_in_proximity():
    """
    Test user exact scenario:
    Bearish OB at 4000 (top 4002, bottom 3998),
    but there is a DBD at 4010 (top 4012, bottom 4008).
    With current price at 3980:
    The prioritizer MUST select DBD as the primary Roof!
    """
    prioritizer = POIPrioritizer(proximity_threshold_points=15.0)

    now = datetime.now(timezone.utc)
    ob_bear = OrderBlock(
        id="OB-BEAR-1",
        direction=Direction.SELL,
        ob_type=OrderBlockType.REVERSAL_RBD,
        top=4002.0,
        bottom=3998.0,
        mean_threshold=4000.0,
        timestamp=now,
        bar_index=10,
        has_fvg=True,
        fvg_id="FVG-1",
        has_swept_liquidity=True,
        touch_count=0
    )

    dbd_cont = OrderBlock(
        id="OB-DBD-2",
        direction=Direction.SELL,
        ob_type=OrderBlockType.CONTINUATION_DBD,
        top=4012.0,
        bottom=4008.0,
        mean_threshold=4010.0,
        timestamp=now,
        bar_index=15,
        has_fvg=True,
        fvg_id="FVG-2",
        has_swept_liquidity=False,
        touch_count=0
    )

    selected_roof = prioritizer.rank_and_select_roof(
        current_price=3980.0,
        obs=[ob_bear, dbd_cont],
        fvgs=[],
        confluences=[],
        fallback_swing_high=4020.0
    )

    assert selected_roof.poi_type == "DBD"
    assert selected_roof.top == 4012.0 # Consolidated to DBD peak
    assert selected_roof.bottom == 3998.0 # Bottom merged with adjacent cluster
    assert selected_roof.proximity_merged is True


def test_poi_prioritizer_ranks_rbr_over_dbr_floor():
    """Test RBR takes priority over DBR as demand floor."""
    prioritizer = POIPrioritizer(proximity_threshold_points=12.0)
    now = datetime.now(timezone.utc)

    dbr_ob = OrderBlock(
        id="OB-BULL-1",
        direction=Direction.BUY,
        ob_type=OrderBlockType.REVERSAL_DBR,
        top=2650.0,
        bottom=2646.0,
        mean_threshold=2648.0,
        timestamp=now,
        bar_index=10,
        has_fvg=True,
        fvg_id="FVG-1",
        touch_count=1
    )

    rbr_cont = OrderBlock(
        id="OB-RBR-2",
        direction=Direction.BUY,
        ob_type=OrderBlockType.CONTINUATION_RBR,
        top=2654.0,
        bottom=2651.0,
        mean_threshold=2652.5,
        timestamp=now,
        bar_index=14,
        has_fvg=True,
        fvg_id="FVG-2",
        touch_count=0 # fresh virgin
    )

    selected_floor = prioritizer.rank_and_select_floor(
        current_price=2670.0,
        obs=[dbr_ob, rbr_cont],
        fvgs=[],
        confluences=[],
        fallback_swing_low=2630.0
    )

    assert selected_floor.poi_type == "RBR"
    assert selected_floor.is_virgin is True
