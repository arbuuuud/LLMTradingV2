from typing import List, Optional, Tuple
from datetime import datetime
import numpy as np
from src.core.types import SwingPoint, StructureState, StructureEventType, Trend


def classify_fibo_zone(ratio: float) -> str:
    if 0.382 <= ratio <= 0.500:
        return "SHALLOW"
    elif 0.500 < ratio < 0.618:
        return "EQ"
    elif 0.618 <= ratio <= 0.786:
        return "OTE"
    elif ratio > 0.786:
        return "DEEP"
    return "MINOR"


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

    # Assign classification labels (HH, LH, EQH / HL, LL, EQL)
    for idx, sh in enumerate(swing_highs):
        if idx == 0:
            sh.label = "SH"
        elif sh.price > swing_highs[idx - 1].price:
            sh.label = "HH"
        elif sh.price < swing_highs[idx - 1].price:
            sh.label = "LH"
        else:
            sh.label = "EQH"

    for idx, sl in enumerate(swing_lows):
        if idx == 0:
            sl.label = "SL"
        elif sl.price > swing_lows[idx - 1].price:
            sl.label = "HL"
        elif sl.price < swing_lows[idx - 1].price:
            sl.label = "LL"
        else:
            sl.label = "EQL"

    # Compute Fibo Retracement & Extension on Swings
    for idx, sl in enumerate(swing_lows):
        if idx > 0 and len(swing_highs) > 0:
            # Find preceding swing high
            prev_highs = [sh for sh in swing_highs if sh.index < sl.index]
            if prev_highs:
                prev_h = prev_highs[-1]
                prev_l = swing_lows[idx - 1]
                base_range = prev_h.price - prev_l.price
                if base_range > 0:
                    if sl.label == "HL":
                        retrace = (prev_h.price - sl.price) / base_range
                        sl.retrace_ratio = round(float(retrace), 4)
                        sl.fibo_zone = classify_fibo_zone(sl.retrace_ratio)
                    elif sl.label == "LL":
                        ext = (prev_h.price - sl.price) / base_range
                        sl.extension_ratio = round(float(ext), 4)

    for idx, sh in enumerate(swing_highs):
        if idx > 0 and len(swing_lows) > 0:
            # Find preceding swing low
            prev_lows = [sl for sl in swing_lows if sl.index < sh.index]
            if prev_lows:
                prev_l = prev_lows[-1]
                prev_h = swing_highs[idx - 1]
                base_range = prev_h.price - prev_l.price
                if base_range > 0:
                    if sh.label == "LH":
                        retrace = (sh.price - prev_l.price) / base_range
                        sh.retrace_ratio = round(float(retrace), 4)
                        sh.fibo_zone = classify_fibo_zone(sh.retrace_ratio)
                    elif sh.label == "HH":
                        ext = (sh.price - prev_l.price) / base_range
                        sh.extension_ratio = round(float(ext), 4)

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
