from datetime import datetime
import numpy as np
from src.features.smc import detect_fvgs, update_fvg_mitigation, detect_order_blocks
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
