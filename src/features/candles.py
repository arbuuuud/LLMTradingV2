"""
Deterministic Candle Pattern Recognition for SMC & POI Confirmation.
Detects:
1. Engulfing (Bullish & Bearish)
2. Pin Bar / Rejection Wick (Hammer, Shooting Star, Long Wick Doji)
3. Morning Star & Evening Star (3-bar reversal)
4. Momentum Marubozu (Displacement expansion candle)

Enriches detected patterns with POI contextual location (at OB, FVG, or Fibo OTE).
"""

from typing import List, Optional, Tuple, Dict, Any
from datetime import datetime
import numpy as np

from src.core.types import (
    CandlePattern,
    CandlePatternType,
    Direction,
    OrderBlock,
    FairValueGap,
    FibonacciOTE
)


def detect_candle_patterns(
    opens: np.ndarray,
    highs: np.ndarray,
    lows: np.ndarray,
    closes: np.ndarray,
    timestamps: List[datetime],
    active_obs: Optional[List[OrderBlock]] = None,
    active_fvgs: Optional[List[FairValueGap]] = None,
    fibonacci_ote: Optional[FibonacciOTE] = None,
    require_poi_confluence: bool = False
) -> List[CandlePattern]:
    """
    Detects high-probability confirmation candlestick patterns.
    Optionally filters patterns to only those occurring at an active POI (OB, FVG, or OTE).
    """
    patterns: List[CandlePattern] = []
    n = len(closes)
    if n < 2:
        return patterns

    obs = active_obs or []
    fvgs = active_fvgs or []

    def check_poi_overlap(p_high: float, p_low: float, direction: Direction) -> Tuple[bool, Optional[str], Optional[str]]:
        """Checks if a price range touches or penetrates an active POI."""
        # 1. Check Order Blocks
        for ob in obs:
            if not ob.is_fully_used:
                # Floor demand touches bull pattern, roof supply touches bear pattern
                if direction == Direction.BUY and ob.direction == Direction.BUY:
                    if p_low <= ob.top and p_high >= ob.bottom:
                        return True, "OB", ob.id
                elif direction == Direction.SELL and ob.direction == Direction.SELL:
                    if p_high >= ob.bottom and p_low <= ob.top:
                        return True, "OB", ob.id

        # 2. Check FVGs
        for fvg in fvgs:
            if not fvg.is_fully_used and not fvg.is_inversion:
                if direction == Direction.BUY and fvg.direction == Direction.BUY:
                    if p_low <= fvg.top and p_high >= fvg.bottom:
                        return True, "FVG", fvg.id
                elif direction == Direction.SELL and fvg.direction == Direction.SELL:
                    if p_high >= fvg.bottom and p_low <= fvg.top:
                        return True, "FVG", fvg.id

        # 3. Check Fibonacci OTE
        if fibonacci_ote and fibonacci_ote.in_ote_zone:
            ote_min = min(fibonacci_ote.level_618, fibonacci_ote.level_786)
            ote_max = max(fibonacci_ote.level_618, fibonacci_ote.level_786)
            if p_low <= ote_max and p_high >= ote_min:
                return True, "OTE", "FIBO_OTE_ZONE"

        return False, None, None

    for i in range(1, n):
        o = float(opens[i])
        h = float(highs[i])
        l = float(lows[i])
        c = float(closes[i])
        c_range = max(h - l, 1e-5)
        body = abs(c - o)
        body_ratio = body / c_range

        o_prev = float(opens[i - 1])
        h_prev = float(highs[i - 1])
        l_prev = float(lows[i - 1])
        c_prev = float(closes[i - 1])

        # Upper and lower wicks
        upper_wick = h - max(o, c)
        lower_wick = min(o, c) - l
        upper_wick_ratio = upper_wick / c_range
        lower_wick_ratio = lower_wick / c_range

        pat_type: Optional[CandlePatternType] = None
        direction: Optional[Direction] = None

        # 1. Morning Star & Evening Star (3-candle patterns evaluated first, requires i >= 2)
        if i >= 2:
            o_p2 = float(opens[i - 2])
            c_p2 = float(closes[i - 2])
            body_prev = abs(c_prev - o_prev)
            range_prev = max(h_prev - l_prev, 1e-5)

            # Morning Star: Bar 0 bearish, Bar 1 small doji/star, Bar 2 strong bullish close above 50% of Bar 0
            if (c_p2 < o_p2) and (body_prev / range_prev <= 0.40) and (c > o):
                mid_p2 = (o_p2 + c_p2) / 2.0
                if c >= mid_p2:
                    pat_type = CandlePatternType.MORNING_STAR
                    direction = Direction.BUY

            # Evening Star: Bar 0 bullish, Bar 1 small doji/star, Bar 2 strong bearish close below 50% of Bar 0
            elif (c_p2 > o_p2) and (body_prev / range_prev <= 0.40) and (c < o):
                mid_p2 = (o_p2 + c_p2) / 2.0
                if c <= mid_p2:
                    pat_type = CandlePatternType.EVENING_STAR
                    direction = Direction.SELL

        # 2. Bullish Engulfing (Prev red, curr green, curr body engulfs prev body)
        if pat_type is None and c_prev < o_prev and c > o and c >= o_prev and o <= c_prev:
            pat_type = CandlePatternType.BULLISH_ENGULFING
            direction = Direction.BUY

        # 3. Bearish Engulfing (Prev green, curr red, curr body engulfs prev body)
        elif pat_type is None and c_prev > o_prev and c < o and c <= o_prev and o >= c_prev:
            pat_type = CandlePatternType.BEARISH_ENGULFING
            direction = Direction.SELL

        # 4. Bullish Pin Bar / Hammer (Long lower rejection wick >= 55%, body in upper 45%)
        elif pat_type is None and lower_wick_ratio >= 0.55 and body_ratio <= 0.40 and upper_wick_ratio <= 0.25:
            pat_type = CandlePatternType.BULLISH_PIN_BAR
            direction = Direction.BUY

        # 5. Bearish Pin Bar / Shooting Star (Long upper rejection wick >= 55%, body in lower 45%)
        elif pat_type is None and upper_wick_ratio >= 0.55 and body_ratio <= 0.40 and lower_wick_ratio <= 0.25:
            pat_type = CandlePatternType.BEARISH_PIN_BAR
            direction = Direction.SELL

        # 6. Momentum Marubozu (Huge directional body >= 75% of range, minimal wicks)
        elif pat_type is None and body_ratio >= 0.75:
            if c > o:
                pat_type = CandlePatternType.MOMENTUM_MARUBOZU_BULL
                direction = Direction.BUY
            else:
                pat_type = CandlePatternType.MOMENTUM_MARUBOZU_BEAR
                direction = Direction.SELL

        if pat_type and direction:
            at_poi, poi_type, poi_id = check_poi_overlap(h, l, direction)

            if require_poi_confluence and not at_poi:
                continue

            patterns.append(
                CandlePattern(
                    id=f"{pat_type.value}-{i}",
                    pattern_type=pat_type,
                    direction=direction,
                    timestamp=timestamps[i],
                    bar_index=i,
                    open=o,
                    high=h,
                    low=l,
                    close=c,
                    body_ratio=round(body_ratio, 2),
                    rejection_wick_ratio=round(max(upper_wick_ratio, lower_wick_ratio), 2),
                    at_poi=at_poi,
                    poi_type=poi_type,
                    poi_id=poi_id,
                    poi_confluence_score=1.5 if at_poi else 1.0
                )
            )

    return patterns
