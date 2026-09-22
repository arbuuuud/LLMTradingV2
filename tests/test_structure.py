from datetime import datetime, timedelta
import numpy as np
from src.features.structure import detect_swing_points, evaluate_market_structure
from src.core.types import Trend, StructureEventType


def test_detect_swing_points():
    # Construct synthetic V and inverted-V patterns
    highs = np.array([100.0, 102.0, 105.0, 103.0, 101.0, 100.0, 99.0])
    lows = np.array([98.0, 99.0, 103.0, 101.0, 97.0, 96.0, 95.0])
    times = [datetime(2025, 1, 1, 10, i) for i in range(len(highs))]

    shs, sls = detect_swing_points(highs, lows, times, window=2)

    assert len(shs) == 1
    assert shs[0].price == 105.0
    assert shs[0].index == 2


def test_evaluate_bos():
    highs = np.array([100.0, 105.0, 102.0, 100.0, 104.0])
    lows = np.array([98.0, 102.0, 99.0, 97.0, 101.0])
    times = [datetime(2025, 1, 1, 10, i) for i in range(len(highs))]

    shs, sls = detect_swing_points(highs, lows, times, window=1)
    
    # Close price breaks above previous swing high in a bullish trend
    closes = np.array([106.0])
    state = evaluate_market_structure(closes, shs, sls, [times[-1]], current_trend=Trend.BULLISH)

    assert state.last_event == StructureEventType.BOS_BULLISH
    assert state.last_event_price == 106.0


def test_swing_classification_hh_hl():
    # Sequence of two swings forming HH and HL
    # Low 0 (95), High 0 (105), Low 1 (98 - HL), High 1 (110 - HH)
    highs = np.array([96.0, 105.0, 99.0, 97.0, 100.0, 110.0, 102.0])
    lows  = np.array([94.0, 98.0,  95.0, 98.0, 96.0, 101.0, 97.0])
    times = [datetime(2025, 1, 1, 10, i) for i in range(len(highs))]

    shs, sls = detect_swing_points(highs, lows, times, window=1)

    assert len(shs) >= 2
    assert shs[0].label == "SH"
    assert shs[1].label == "HH"
    assert shs[1].price > shs[0].price

    assert len(sls) >= 2
    assert sls[0].label == "SL"
    assert sls[1].label == "HL"
    assert sls[1].price > sls[0].price
