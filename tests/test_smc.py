from datetime import datetime
import numpy as np
from src.features.smc import (
    detect_fvgs,
    update_fvg_mitigation,
    detect_order_blocks,
    process_fvg_inversions,
    detect_fvg_confluences
)
from src.core.types import Direction


def test_detect_bullish_fvg():
    # 3-bar sequence: bar 0 high = 100, bar 1 displacement, bar 2 low = 102
    highs = np.array([100.0, 105.0, 108.0])
    lows = np.array([95.0, 99.0, 102.0])
    times = [datetime(2025, 1, 1, 10, i) for i in range(3)]

    fvgs = detect_fvgs(highs, lows, times)

    assert len(fvgs) == 1
    assert fvgs[0].direction == Direction.BUY
    assert fvgs[0].bottom == 100.0
    assert fvgs[0].top == 102.0
    assert not fvgs[0].is_mitigated


def test_fvg_mitigation_and_inversion():
    highs = np.array([100.0, 105.0, 108.0])
    lows = np.array([95.0, 99.0, 102.0])
    times = [datetime(2025, 1, 1, 10, i) for i in range(3)]

    fvgs = detect_fvgs(highs, lows, times)
    assert len(fvgs) == 1

    # Price re-enters gap (mitigated)
    update_fvg_mitigation(fvgs, latest_high=104.0, latest_low=101.0, latest_close=101.5)
    assert fvgs[0].is_mitigated is True
    assert fvgs[0].is_inversion is False

    # Price closes below gap bottom (inversion!)
    update_fvg_mitigation(fvgs, latest_high=101.0, latest_low=98.0, latest_close=99.0)
    assert fvgs[0].is_inversion is True


def test_fvg_inversion_distinct_object_and_confluence():
    # 1. Bullish FVG formed at 100-102
    highs = np.array([100.0, 105.0, 108.0])
    lows = np.array([95.0, 99.0, 102.0])
    times = [datetime(2025, 1, 1, 10, i) for i in range(3)]
    fvgs = detect_fvgs(highs, lows, times)

    assert len(fvgs) == 1
    assert fvgs[0].ce_price == 101.0

    # 2. Strong Bearish displacement closes below bottom (99.0) -> Spawns distinct InversionFVG
    now = datetime(2025, 1, 1, 10, 5)
    active_reg, ifvgs = process_fvg_inversions(
        fvgs, latest_high=101.0, latest_low=98.0, latest_close=99.0, current_time=now
    )

    assert len(ifvgs) == 1
    ifvg = ifvgs[0]
    assert ifvg.original_fvg_id == fvgs[0].id
    assert ifvg.direction == Direction.SELL # Now acting as Resistance
    assert ifvg.top == 102.0
    assert ifvg.bottom == 100.0

    # 3. Suppose a new Bearish FVG forms overlapping at 101-104
    from src.core.types import FairValueGap
    new_bear_fvg = FairValueGap(
        id="FVG-BEAR-99",
        direction=Direction.SELL,
        top=103.0,
        bottom=101.0,
        ce_price=102.0,
        timestamp=now,
        bar_index=5
    )

    confluences = detect_fvg_confluences([new_bear_fvg], ifvgs)
    assert len(confluences) == 1
    conf = confluences[0]
    assert conf.overlap_top == 102.0 # min(103, 102)
    assert conf.overlap_bottom == 101.0 # max(101, 100)
    assert conf.probability_score >= 8.0


def test_fvg_touch_count_deeper_penetration_only():
    # Bullish FVG with top=110, bottom=100
    highs = np.array([100.0, 115.0, 120.0])
    lows = np.array([90.0, 108.0, 110.0])
    times = [datetime(2025, 1, 1, 10, i) for i in range(3)]
    fvgs = detect_fvgs(highs, lows, times)

    assert fvgs[0].touch_count == 0
    assert fvgs[0].is_touched is False

    # Candle 1: dips to low 108 (enters gap, top is 110) -> touch_count = 1
    update_fvg_mitigation(fvgs, latest_high=115.0, latest_low=108.0, latest_close=112.0)
    assert fvgs[0].touch_count == 1
    assert fvgs[0].deepest_touch_price == 108.0

    # Candle 2: dips to low 109 (doesn't penetrate deeper than 108) -> touch_count STILL 1!
    update_fvg_mitigation(fvgs, latest_high=114.0, latest_low=109.0, latest_close=111.0)
    assert fvgs[0].touch_count == 1
    assert fvgs[0].deepest_touch_price == 108.0

    # Candle 3: penetrates deeper to low 104 -> ngambil harga baru, touch_count becomes 2!
    update_fvg_mitigation(fvgs, latest_high=112.0, latest_low=104.0, latest_close=111.0)
    assert fvgs[0].touch_count == 2
    assert fvgs[0].deepest_touch_price == 104.0
