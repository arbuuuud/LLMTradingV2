from typing import List, Optional, Tuple
from datetime import datetime
import numpy as np
from src.core.types import SwingPoint, StructureState, StructureEventType, Trend


def detect_swing_points(
    highs: np.ndarray,
    lows: np.ndarray,
    timestamps: List[datetime],
    window: int = 3
) -> Tuple[List[SwingPoint], List[SwingPoint]]:
    """
    Detects fractal swing highs and lows using a symmetric window [i - window, i + window].
    Deterministic and vectorized.
    """
    n = len(highs)
    swing_highs: List[SwingPoint] = []
    swing_lows: List[SwingPoint] = []

    if n < 2 * window + 1:
        return swing_highs, swing_lows

    for i in range(window, n - window):
        # Check swing high
        is_sh = True
        current_high = highs[i]
        for w in range(1, window + 1):
            if highs[i - w] >= current_high or highs[i + w] >= current_high:
                is_sh = False
                break
        if is_sh:
            swing_highs.append(
                SwingPoint(index=i, price=float(current_high), timestamp=timestamps[i])
            )

        # Check swing low
        is_sl = True
        current_low = lows[i]
        for w in range(1, window + 1):
            if lows[i - w] <= current_low or lows[i + w] <= current_low:
                is_sl = False
                break
        if is_sl:
            swing_lows.append(
                SwingPoint(index=i, price=float(current_low), timestamp=timestamps[i])
            )

    return swing_highs, swing_lows


def evaluate_market_structure(
    closes: np.ndarray,
    swing_highs: List[SwingPoint],
    swing_lows: List[SwingPoint],
    timestamps: List[datetime],
    current_trend: Trend = Trend.RANGING
) -> StructureState:
    """
    Evaluates Break of Structure (BOS) and Change of Character (CHoCH).
    BOS: Body close penetrates the recent swing in the direction of the prevailing trend.
    CHoCH: Body close penetrates the recent swing opposite to the prevailing trend.
    """
    state = StructureState()
    if swing_highs:
        state.last_swing_high = swing_highs[-1]
    if swing_lows:
        state.last_swing_low = swing_lows[-1]

    if not swing_highs or not swing_lows or len(closes) == 0:
        return state

    latest_close = closes[-1]
    latest_time = timestamps[-1]
    recent_sh = swing_highs[-1].price
    recent_sl = swing_lows[-1].price

    if latest_close > recent_sh:
        if current_trend == Trend.BULLISH:
            state.last_event = StructureEventType.BOS_BULLISH
        else:
            state.last_event = StructureEventType.CHOCH_BULLISH
        state.last_event_price = float(latest_close)
        state.last_event_time = latest_time
    elif latest_close < recent_sl:
        if current_trend == Trend.BEARISH:
            state.last_event = StructureEventType.BOS_BEARISH
        else:
            state.last_event = StructureEventType.CHOCH_BEARISH
        state.last_event_price = float(latest_close)
        state.last_event_time = latest_time

    return state
