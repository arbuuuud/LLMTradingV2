from datetime import datetime, timedelta
import numpy as np
import pytest

from src.core.types import Direction, CandlePatternType, OrderBlock, OrderBlockType, FairValueGap
from src.features.candles import detect_candle_patterns


def test_detect_bullish_and_bearish_engulfing():
    times = [datetime(2025, 1, 1, 10, i) for i in range(5)]
    # Bar 0: Down candle (100 -> 95)
    # Bar 1: Bullish engulfing (94 -> 102, completely engulfs 100-95)
    # Bar 2: Up candle (102 -> 108)
    # Bar 3: Bearish engulfing (109 -> 101, completely engulfs 102-108)
    opens = np.array([100.0, 94.0, 102.0, 109.0, 101.0])
    highs = np.array([101.0, 103.0, 108.5, 110.0, 102.0])
    lows = np.array([94.5, 93.5, 101.5, 100.5, 99.0])
    closes = np.array([95.0, 102.0, 108.0, 101.0, 100.0])

    pats = detect_candle_patterns(opens, highs, lows, closes, times)
    types_found = [p.pattern_type for p in pats]

    assert CandlePatternType.BULLISH_ENGULFING in types_found
    assert CandlePatternType.BEARISH_ENGULFING in types_found

    engulf_bull = next(p for p in pats if p.pattern_type == CandlePatternType.BULLISH_ENGULFING)
    assert engulf_bull.direction == Direction.BUY
    assert engulf_bull.bar_index == 1

    engulf_bear = next(p for p in pats if p.pattern_type == CandlePatternType.BEARISH_ENGULFING)
    assert engulf_bear.direction == Direction.SELL
    assert engulf_bear.bar_index == 3


def test_detect_pin_bar_rejection_wicks():
    times = [datetime(2025, 1, 1, 11, i) for i in range(3)]
    # Bar 0: Normal
    # Bar 1: Bullish Pin Bar (Hammer): open=100, close=101, high=101.5, low=90 (lower wick 10 / range 11.5 = 87%)
    # Bar 2: Bearish Pin Bar (Shooting Star): open=100, close=99, high=110, low=98.5 (upper wick 10 / range 11.5 = 87%)
    opens = np.array([98.0, 100.0, 100.0])
    highs = np.array([99.0, 101.5, 110.0])
    lows = np.array([97.0, 90.0, 98.5])
    closes = np.array([98.5, 101.0, 99.0])

    pats = detect_candle_patterns(opens, highs, lows, closes, times)
    types_found = [p.pattern_type for p in pats]

    assert CandlePatternType.BULLISH_PIN_BAR in types_found
    assert CandlePatternType.BEARISH_PIN_BAR in types_found


def test_detect_morning_and_evening_star():
    times = [datetime(2025, 1, 1, 12, i) for i in range(4)]
    # Morning Star 3-bar:
    # Bar 0: Long bearish (110 -> 100)
    # Bar 1: Small doji base (99 -> 99.5, range 98-100)
    # Bar 2: Strong bullish reversal (99.5 -> 106, close above midpoint 105)
    opens = np.array([110.0, 99.0, 99.5, 106.0])
    highs = np.array([111.0, 100.0, 106.5, 107.0])
    lows = np.array([99.5, 98.0, 99.0, 105.0])
    closes = np.array([100.0, 99.5, 106.0, 106.5])

    pats = detect_candle_patterns(opens, highs, lows, closes, times)
    types_found = [p.pattern_type for p in pats]
    assert CandlePatternType.MORNING_STAR in types_found


def test_detect_momentum_marubozu():
    times = [datetime(2025, 1, 1, 13, i) for i in range(2)]
    # Bar 1: Huge Bullish Marubozu (Open=100, High=120, Low=99.8, Close=119.8 -> body 19.8 / range 20.2 = 98%)
    opens = np.array([98.0, 100.0])
    highs = np.array([99.0, 120.0])
    lows = np.array([97.0, 99.8])
    closes = np.array([98.5, 119.8])

    pats = detect_candle_patterns(opens, highs, lows, closes, times)
    types_found = [p.pattern_type for p in pats]
    assert CandlePatternType.MOMENTUM_MARUBOZU_BULL in types_found


def test_poi_confluence_filter():
    times = [datetime(2025, 1, 1, 14, i) for i in range(2)]
    # Bullish Pin bar at price 90-101.5
    opens = np.array([98.0, 100.0])
    highs = np.array([99.0, 101.5])
    lows = np.array([97.0, 90.0])
    closes = np.array([98.5, 101.0])

    # Case A: Filter enabled, but NO active POI -> 0 patterns returned
    pats_no_poi = detect_candle_patterns(opens, highs, lows, closes, times, require_poi_confluence=True)
    assert len(pats_no_poi) == 0

    # Case B: Active Order Block Demand at 88.0 - 95.0 (touches pin bar low 90.0!)
    active_ob = OrderBlock(
        id="OB-DEMAND-1",
        direction=Direction.BUY,
        ob_type=OrderBlockType.REVERSAL_DBR,
        top=95.0,
        bottom=88.0,
        mean_threshold=91.5,
        timestamp=times[0],
        bar_index=0
    )
    pats_with_poi = detect_candle_patterns(
        opens, highs, lows, closes, times,
        active_obs=[active_ob],
        require_poi_confluence=True
    )
    assert len(pats_with_poi) == 1
    p = pats_with_poi[0]
    assert p.pattern_type == CandlePatternType.BULLISH_PIN_BAR
    assert p.at_poi is True
    assert p.poi_type == "OB"
    assert p.poi_id == "OB-DEMAND-1"
    assert p.poi_confluence_score == 1.5
