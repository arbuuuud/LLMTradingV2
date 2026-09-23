"""
Deterministic Candlestick Confirmation Pattern Recognition for SMC & POI Execution.
Implements strict institutional rules:
1. Engulfing (Bullish & Bearish)
   - Body engulfs previous body (Body_curr > Body_prev)
   - Previous candle must be strictly opposite color
   - Closing dominance: closing wick <= 25% of range
   - Minimum momentum: range >= 0.8x avg range of last 5 bars
2. Pin Bar / Rejection Wick (Hammer & Shooting Star)
   - Rejection wick >= 60% of total candle range
   - Body <= 30% of total range (located in top 35% for Hammer, bottom 35% for Star)
   - Opposing wick <= 20% of range
3. Morning Star & Evening Star (3-Bar Reversal)
   - Candle 1: Strong trend candle with body >= 50%
   - Candle 2: Small star/doji with body <= 35%
   - Candle 3: Aggressive reversal closing beyond 50% midpoint of Candle 1 body
4. Momentum Marubozu (Displacement Expansion)
   - Body >= 75% of candle range (wicks <= 25% combined)
   - Relative size expansion: range >= 1.3x avg range of last 5 bars

Enriches patterns with POI contextual location (at OB, FVG, or Fibo OTE).
"""

from typing import List, Optional, Tuple
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
    Detects high-probability confirmation candlestick patterns according to strict institutional criteria.
    Optionally filters patterns to only those occurring at an active POI (OB, FVG, or OTE).
    """
    patterns: List[CandlePattern] = []
    n = len(closes)
    if n < 2:
        return patterns

    obs = active_obs or []
    fvgs = active_fvgs or []

    # Precalculate candle ranges for relative size comparison
    all_ranges = highs - lows

    def check_poi_overlap(p_high: float, p_low: float, direction: Direction) -> Tuple[bool, Optional[str], Optional[str]]:
        """Checks if a price range touches or penetrates an active POI."""
        # 1. Check Order Blocks
        for ob in obs:
            if not ob.is_fully_used:
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
        body_prev = abs(c_prev - o_prev)
        range_prev = max(h_prev - l_prev, 1e-5)

        upper_wick = h - max(o, c)
        lower_wick = min(o, c) - l
        upper_wick_ratio = upper_wick / c_range
        lower_wick_ratio = lower_wick / c_range

        # Local benchmark range (avg range of past up to 5 bars)
        lookback_start = max(0, i - 5)
        avg_range = float(np.mean(all_ranges[lookback_start:i])) if i > lookback_start else c_range
        avg_range = max(avg_range, 1e-5)

        pat_type: Optional[CandlePatternType] = None
        direction: Optional[Direction] = None

        # 1. Morning Star & Evening Star (3-candle patterns, evaluated first, requires i >= 2)
        if i >= 2:
            o_p2 = float(opens[i - 2])
            h_p2 = float(highs[i - 2])
            l_p2 = float(lows[i - 2])
            c_p2 = float(closes[i - 2])
            body_p2 = abs(c_p2 - o_p2)
            range_p2 = max(h_p2 - l_p2, 1e-5)

            # Candle 1 must have meaningful body (>= 50% range)
            is_c1_bear = (c_p2 < o_p2) and (body_p2 / range_p2 >= 0.50)
            is_c1_bull = (c_p2 > o_p2) and (body_p2 / range_p2 >= 0.50)
            # Candle 2 (star) must be a small indecision candle (body <= 35% range)
            is_star = (body_prev / range_prev <= 0.35)

            # Morning Star: C1 bear -> C2 star -> C3 bull closing > 50% midpoint of C1 body
            if is_c1_bear and is_star and (c > o):
                mid_p2 = (o_p2 + c_p2) / 2.0
                if c >= mid_p2:
                    pat_type = CandlePatternType.MORNING_STAR
                    direction = Direction.BUY

            # Evening Star: C1 bull -> C2 star -> C3 bear closing < 50% midpoint of C1 body
            elif is_c1_bull and is_star and (c < o):
                mid_p2 = (o_p2 + c_p2) / 2.0
                if c <= mid_p2:
                    pat_type = CandlePatternType.EVENING_STAR
                    direction = Direction.SELL

        # 2. Bullish Engulfing
        # - Prev was red
        # - Curr is green
        # - Body strictly engulfs previous body (body > body_prev and close >= open_prev and open <= close_prev)
        # - Closing dominance: upper wick <= 25% of range
        # - Meaningful size: range >= 0.8 * avg_range
        if pat_type is None and c_prev < o_prev and c > o:
            if body > body_prev and c >= o_prev and o <= c_prev:
                if upper_wick_ratio <= 0.25 and c_range >= 0.8 * avg_range:
                    pat_type = CandlePatternType.BULLISH_ENGULFING
                    direction = Direction.BUY

        # 3. Bearish Engulfing
        # - Prev was green
        # - Curr is red
        # - Body strictly engulfs previous body
        # - Closing dominance: lower wick <= 25% of range
        # - Meaningful size: range >= 0.8 * avg_range
        elif pat_type is None and c_prev > o_prev and c < o and body > body_prev and c <= o_prev and o >= c_prev:
            if lower_wick_ratio <= 0.25 and c_range >= 0.8 * avg_range:
                pat_type = CandlePatternType.BEARISH_ENGULFING
                direction = Direction.SELL

        # 4. Bullish Pin Bar / Hammer
        # - Lower rejection wick >= 60% of range
        # - Body <= 30% of range (located in top 35% of candle: min(o,c) >= l + 0.60 * c_range)
        # - Upper wick <= 20% of range
        if pat_type is None and lower_wick_ratio >= 0.60 and body_ratio <= 0.30 and upper_wick_ratio <= 0.20:
            if min(o, c) >= l + 0.55 * c_range:
                pat_type = CandlePatternType.BULLISH_PIN_BAR
                direction = Direction.BUY

        # 5. Bearish Pin Bar / Shooting Star
        # - Upper rejection wick >= 60% of range
        # - Body <= 30% of range (located in bottom 35% of candle: max(o,c) <= h - 0.60 * c_range)
        # - Lower wick <= 20% of range
        if pat_type is None and upper_wick_ratio >= 0.60 and body_ratio <= 0.30 and lower_wick_ratio <= 0.20:
            if max(o, c) <= h - 0.55 * c_range:
                pat_type = CandlePatternType.BEARISH_PIN_BAR
                direction = Direction.SELL

        # 6. Momentum Marubozu (Displacement Expansion)
        # - Body >= 75% of range (minimal wicks)
        # - Range expansion: range >= 1.3 * avg_range
        elif pat_type is None and body_ratio >= 0.75 and c_range >= 1.3 * avg_range:
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
