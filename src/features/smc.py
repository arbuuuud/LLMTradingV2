from typing import List, Tuple, Optional
from datetime import datetime
import numpy as np
from src.core.types import (
    FairValueGap,
    InversionFVG,
    FVGConfluenceZone,
    OrderBlock,
    OrderBlockType,
    Direction
)


def detect_fvgs(
    highs: np.ndarray,
    lows: np.ndarray,
    timestamps: List[datetime],
    min_gap_points: float = 0.0
) -> List[FairValueGap]:
    """
    Detects Fair Value Gaps (3-bar pattern):
    - Bullish FVG: Low of candle 0 > High of candle 2 (gap between candle 0 low and candle 2 high)
    - Bearish FVG: High of candle 0 < Low of candle 2
    """
    fvgs: List[FairValueGap] = []
    n = len(highs)
    if n < 3:
        return fvgs

    for i in range(2, n):
        # Bullish FVG: candle i's low > candle i-2's high
        if lows[i] - highs[i - 2] > min_gap_points:
            gap_bottom = float(highs[i - 2])
            gap_top = float(lows[i])
            fvgs.append(
                FairValueGap(
                    id=f"FVG-BULL-{i}",
                    direction=Direction.BUY,
                    top=gap_top,
                    bottom=gap_bottom,
                    ce_price=(gap_top + gap_bottom) / 2.0,
                    timestamp=timestamps[i],
                    bar_index=i,
                    is_inversion=False,
                    is_mitigated=False
                )
            )
        # Bearish FVG: candle i-2's low - candle i's high > min_gap_points
        elif lows[i - 2] - highs[i] > min_gap_points:
            gap_top = float(lows[i - 2])
            gap_bottom = float(highs[i])
            fvgs.append(
                FairValueGap(
                    id=f"FVG-BEAR-{i}",
                    direction=Direction.SELL,
                    top=gap_top,
                    bottom=gap_bottom,
                    ce_price=(gap_top + gap_bottom) / 2.0,
                    timestamp=timestamps[i],
                    bar_index=i,
                    is_inversion=False,
                    is_mitigated=False
                )
            )

    return fvgs


def update_fvg_mitigation(
    fvgs: List[FairValueGap],
    latest_high: float,
    latest_low: float,
    latest_close: float
) -> List[FairValueGap]:
    """
    Updates mitigation and inversion status of active FVGs:
    - Mitigated: Candle body closed inside or penetrated the gap.
    - Fully Used: All orders consumed (wick or body swept 100% across the opposite boundary).
    - Inversion: Candle body closed beyond opposite boundary.
    """
    for fvg in fvgs:
        if fvg.direction == Direction.BUY:
            # Touched: wick or body enters gap
            # Increments only when penetrating deeper than previous touch price
            if latest_low <= fvg.top and latest_high >= fvg.bottom:
                fvg.is_touched = True
                if fvg.deepest_touch_price is None:
                    fvg.touch_count = 1
                    fvg.deepest_touch_price = float(latest_low)
                elif latest_low < fvg.deepest_touch_price:
                    fvg.touch_count += 1
                    fvg.deepest_touch_price = float(latest_low)
                fvg.tested_count = fvg.touch_count

            # Mitigated: body close inside the gap
            if latest_close <= fvg.top and latest_close >= fvg.bottom:
                fvg.is_mitigated = True
            # Fully Used: wick or body penetrated all the way to bottom
            if latest_low <= fvg.bottom:
                fvg.is_fully_used = True
            # Inversion: body closed below bottom
            if latest_close < fvg.bottom:
                fvg.is_inversion = True

        elif fvg.direction == Direction.SELL:
            # Touched: wick or body enters gap
            # Increments only when penetrating deeper than previous touch price
            if latest_high >= fvg.bottom and latest_low <= fvg.top:
                fvg.is_touched = True
                if fvg.deepest_touch_price is None:
                    fvg.touch_count = 1
                    fvg.deepest_touch_price = float(latest_high)
                elif latest_high > fvg.deepest_touch_price:
                    fvg.touch_count += 1
                    fvg.deepest_touch_price = float(latest_high)
                fvg.tested_count = fvg.touch_count

            # Mitigated: body close inside the gap
            if latest_close >= fvg.bottom and latest_close <= fvg.top:
                fvg.is_mitigated = True
            # Fully Used: wick or body penetrated all the way to top
            if latest_high >= fvg.top:
                fvg.is_fully_used = True
            # Inversion: body closed above top
            if latest_close > fvg.top:
                fvg.is_inversion = True

    return fvgs


def process_fvg_inversions(
    fvgs: List[FairValueGap],
    latest_high: float,
    latest_low: float,
    latest_close: float,
    current_time: datetime,
    existing_ifvgs: Optional[List[InversionFVG]] = None
) -> Tuple[List[FairValueGap], List[InversionFVG]]:
    """
    Tracks touches, mitigation, full order consumption, and breaches of FVGs, spawning distinct InversionFVG objects.
    - Touched: increments only when price penetrates deeper than previous touch price
    - Mitigated: body close inside
    - Fully used: orders 100% consumed by wick/body
    - If candle close breaches opposite boundary, FVG becomes an iFVG.
    """
    ifvgs: List[InversionFVG] = list(existing_ifvgs or [])
    active_regular_fvgs: List[FairValueGap] = []

    for fvg in fvgs:
        if fvg.direction == Direction.BUY:
            if latest_low <= fvg.top and latest_high >= fvg.bottom:
                fvg.is_touched = True
                if fvg.deepest_touch_price is None:
                    fvg.touch_count = 1
                    fvg.deepest_touch_price = float(latest_low)
                elif latest_low < fvg.deepest_touch_price:
                    fvg.touch_count += 1
                    fvg.deepest_touch_price = float(latest_low)
                fvg.tested_count = fvg.touch_count

            if latest_close <= fvg.top:
                fvg.is_mitigated = True
            if latest_low <= fvg.bottom:
                fvg.is_fully_used = True

            # Breach below bottom -> Inverted to Resistance
            if latest_close < fvg.bottom:
                fvg.is_inversion = True
                ifvg_id = f"IFVG-{fvg.id}"
                if not any(item.id == ifvg_id for item in ifvgs):
                    counter_fvg = next((cf for cf in fvgs if cf.direction == Direction.SELL and abs(cf.bar_index - fvg.bar_index) <= 3), None)
                    ifvgs.append(
                        InversionFVG(
                            id=ifvg_id,
                            original_fvg_id=fvg.id,
                            direction=Direction.SELL, # Now Resistance
                            top=fvg.top,
                            bottom=fvg.bottom,
                            ce_price=fvg.ce_price,
                            invert_time=current_time,
                            breached_with_counter_fvg=bool(counter_fvg),
                            counter_fvg_id=counter_fvg.id if counter_fvg else None
                        )
                    )
            else:
                active_regular_fvgs.append(fvg)
        else: # Bearish FVG
            if latest_high >= fvg.bottom and latest_low <= fvg.top:
                fvg.is_touched = True
                if fvg.deepest_touch_price is None:
                    fvg.touch_count = 1
                    fvg.deepest_touch_price = float(latest_high)
                elif latest_high > fvg.deepest_touch_price:
                    fvg.touch_count += 1
                    fvg.deepest_touch_price = float(latest_high)
                fvg.tested_count = fvg.touch_count

            if latest_close >= fvg.bottom:
                fvg.is_mitigated = True
            if latest_high >= fvg.top:
                fvg.is_fully_used = True

            # Breach above top -> Inverted to Support
            if latest_close > fvg.top:
                fvg.is_inversion = True
                ifvg_id = f"IFVG-{fvg.id}"
                if not any(item.id == ifvg_id for item in ifvgs):
                    counter_fvg = next((cf for cf in fvgs if cf.direction == Direction.BUY and abs(cf.bar_index - fvg.bar_index) <= 3), None)
                    ifvgs.append(
                        InversionFVG(
                            id=ifvg_id,
                            original_fvg_id=fvg.id,
                            direction=Direction.BUY, # Now Support
                            top=fvg.top,
                            bottom=fvg.bottom,
                            ce_price=fvg.ce_price,
                            invert_time=current_time,
                            breached_with_counter_fvg=bool(counter_fvg),
                            counter_fvg_id=counter_fvg.id if counter_fvg else None
                        )
                    )
            else:
                active_regular_fvgs.append(fvg)

    return active_regular_fvgs, ifvgs


def detect_fvg_confluences(
    fvgs: List[FairValueGap],
    ifvgs: List[InversionFVG]
) -> List[FVGConfluenceZone]:
    """
    Detects high-probability confluence zones where an active FVG and an active iFVG
    overlap in price range.
    """
    confluences: List[FVGConfluenceZone] = []

    for fvg in fvgs:
        if fvg.is_inversion:
            continue
        for ifvg in ifvgs:
            overlap_top = min(fvg.top, ifvg.top)
            overlap_btm = max(fvg.bottom, ifvg.bottom)

            if overlap_top > overlap_btm: # Overlapping zone!
                conf_id = f"CONF-{fvg.id}-{ifvg.id}"
                score = 9.0 if ifvg.breached_with_counter_fvg else 8.0
                confluences.append(
                    FVGConfluenceZone(
                        id=conf_id,
                        fvg_id=fvg.id,
                        ifvg_id=ifvg.id,
                        overlap_top=float(overlap_top),
                        overlap_bottom=float(overlap_btm),
                        confluence_type="OVERLAPPING_ZONE",
                        has_counter_fvg_breach=ifvg.breached_with_counter_fvg,
                        probability_score=score
                    )
                )

    return confluences


def detect_order_blocks(
    opens: np.ndarray,
    highs: np.ndarray,
    lows: np.ndarray,
    closes: np.ndarray,
    timestamps: List[datetime],
    fvgs: List[FairValueGap],
    max_base_candles: int = 3,
    min_impulse_ratio: float = 1.5
) -> List[OrderBlock]:
    """
    Detects Institutional Order Blocks and S&D Patterns:
    - Reversals: DBR (Drop-Base-Rally) & RBD (Rally-Base-Drop) at swing extrema
    - Continuations: RBR (Rally-Base-Rally) & DBD (Drop-Base-Drop) with strict Leg-In, Base (1-3c), and Leg-Out rules
    - Validates with FVG displacement, calculates 50% Mean Threshold, and checks liquidity sweep.
    """
    obs: List[OrderBlock] = []
    fvg_indices = {fvg.bar_index: fvg for fvg in fvgs}

    for idx, fvg in fvg_indices.items():
        # In a 3-bar FVG at index `idx`:
        # bar idx - 2: left candle before displacement
        # bar idx - 1: strong displacement candle (Leg-Out)
        # bar idx: confirming candle
        origin_idx = idx - 2 if idx >= 2 else idx - 1
        if fvg.direction == Direction.BUY:
            if origin_idx >= 0 and closes[origin_idx] > opens[origin_idx]:
                if idx - 1 >= 0 and closes[idx - 1] < opens[idx - 1]:
                    origin_idx = idx - 1
                elif idx - 3 >= 0 and closes[idx - 3] < opens[idx - 3]:
                    origin_idx = idx - 3
        elif fvg.direction == Direction.SELL:
            if origin_idx >= 0 and closes[origin_idx] < opens[origin_idx]:
                if idx - 1 >= 0 and closes[idx - 1] > opens[idx - 1]:
                    origin_idx = idx - 1
                elif idx - 3 >= 0 and closes[idx - 3] > opens[idx - 3]:
                    origin_idx = idx - 3

        if origin_idx < 0:
            continue

        # Count base candles prior to displacement (up to max_base_candles)
        base_count = 1
        base_high = float(highs[origin_idx])
        base_low = float(lows[origin_idx])
        
        # Check if previous bars are also part of a tight base (boring candles with body <= 45% of range)
        for b in range(1, max_base_candles):
            check_b = origin_idx - b
            if check_b < 0:
                break
            b_range = highs[check_b] - lows[check_b]
            b_body = abs(closes[check_b] - opens[check_b])
            # True base candle: body <= 45% of candle range (tight consolidation / doji / spinning top)
            if b_range > 0 and (b_body / b_range <= 0.45):
                base_count += 1
                base_high = max(base_high, float(highs[check_b]))
                base_low = min(base_low, float(lows[check_b]))
            else:
                break

        # Leg-Out displacement strength
        leg_out_idx = idx - 1
        leg_out_range = float(highs[leg_out_idx] - lows[leg_out_idx])
        base_range = max(base_high - base_low, 1e-5)
        imp_ratio = leg_out_range / base_range

        prior_idx = origin_idx - base_count
        is_prior_bearish = (closes[prior_idx] < opens[prior_idx]) if prior_idx >= 0 else (closes[origin_idx] < opens[origin_idx])
        is_prior_bullish = (closes[prior_idx] > opens[prior_idx]) if prior_idx >= 0 else (closes[origin_idx] > opens[origin_idx])

        top = base_high
        bottom = base_low
        mt = (top + bottom) / 2.0

        if fvg.direction == Direction.BUY:
            # Bullish (+OB)
            # Prior move: Drop -> DBR (Reversal), else RBR (Continuation)
            if is_prior_bearish:
                ob_type = OrderBlockType.REVERSAL_DBR
            else:
                # Continuation RBR requires base <= max_base_candles and good impulse ratio
                if base_count > max_base_candles or imp_ratio < min_impulse_ratio:
                    continue
                ob_type = OrderBlockType.CONTINUATION_RBR

            swept = bool(prior_idx >= 0 and lows[origin_idx] < lows[prior_idx])
            obs.append(
                OrderBlock(
                    id=f"OB-BULL-{origin_idx}",
                    direction=Direction.BUY,
                    ob_type=ob_type,
                    top=top,
                    bottom=bottom,
                    mean_threshold=mt,
                    timestamp=timestamps[origin_idx],
                    bar_index=origin_idx,
                    has_fvg=True,
                    fvg_id=fvg.id,
                    has_swept_liquidity=swept,
                    base_candle_count=base_count,
                    impulse_ratio=round(imp_ratio, 2)
                )
            )
        elif fvg.direction == Direction.SELL:
            # Bearish (-OB)
            if is_prior_bullish:
                ob_type = OrderBlockType.REVERSAL_RBD
            else:
                # Continuation DBD requires base <= max_base_candles and good impulse ratio
                if base_count > max_base_candles or imp_ratio < min_impulse_ratio:
                    continue
                ob_type = OrderBlockType.CONTINUATION_DBD

            swept = bool(prior_idx >= 0 and highs[origin_idx] > highs[prior_idx])
            obs.append(
                OrderBlock(
                    id=f"OB-BEAR-{origin_idx}",
                    direction=Direction.SELL,
                    ob_type=ob_type,
                    top=top,
                    bottom=bottom,
                    mean_threshold=mt,
                    timestamp=timestamps[origin_idx],
                    bar_index=origin_idx,
                    has_fvg=True,
                    fvg_id=fvg.id,
                    has_swept_liquidity=swept,
                    base_candle_count=base_count,
                    impulse_ratio=round(imp_ratio, 2)
                )
            )

    return obs


def process_order_block_lifecycle(
    obs: List[OrderBlock],
    latest_high: float,
    latest_low: float,
    latest_close: float,
    current_time: datetime
) -> Tuple[List[OrderBlock], List[OrderBlock]]:
    """
    Updates Order Block lifecycle:
    - Touches: deeper penetration increment (+1)
    - Mitigated: candle closed inside the OB body/range
    - Fully Used: orders 100% consumed through opposite boundary
    - Breaker Block Flip: candle body closed beyond opposite boundary
    Returns (active_obs, active_breakers).
    """
    active_obs: List[OrderBlock] = []
    active_breakers: List[OrderBlock] = []

    for ob in obs:
        if ob.direction == Direction.BUY:
            # Touched
            if latest_low <= ob.top and latest_high >= ob.bottom:
                ob.is_touched = True
                if ob.deepest_touch_price is None:
                    ob.touch_count = 1
                    ob.deepest_touch_price = float(latest_low)
                elif latest_low < ob.deepest_touch_price:
                    ob.touch_count += 1
                    ob.deepest_touch_price = float(latest_low)

            # Mitigated (closed inside)
            if latest_close <= ob.top and latest_close >= ob.bottom:
                ob.is_mitigated = True
            # Fully used (swept 100% through bottom)
            if latest_low <= ob.bottom:
                ob.is_fully_used = True

            # Breaker flip: closed below bottom -> Bearish Breaker Resistance
            if latest_close < ob.bottom:
                ob.is_breaker = True
                ob.direction = Direction.SELL
                ob.ob_type = OrderBlockType.BREAKER_BEARISH
                ob.breaker_time = current_time
                active_breakers.append(ob)
            else:
                active_obs.append(ob)

        elif ob.direction == Direction.SELL:
            # Touched
            if latest_high >= ob.bottom and latest_low <= ob.top:
                ob.is_touched = True
                if ob.deepest_touch_price is None:
                    ob.touch_count = 1
                    ob.deepest_touch_price = float(latest_high)
                elif latest_high > ob.deepest_touch_price:
                    ob.touch_count += 1
                    ob.deepest_touch_price = float(latest_high)

            # Mitigated (closed inside)
            if latest_close >= ob.bottom and latest_close <= ob.top:
                ob.is_mitigated = True
            # Fully used (swept 100% through top)
            if latest_high >= ob.top:
                ob.is_fully_used = True

            # Breaker flip: closed above top -> Bullish Breaker Support
            if latest_close > ob.top:
                ob.is_breaker = True
                ob.direction = Direction.BUY
                ob.ob_type = OrderBlockType.BREAKER_BULLISH
                ob.breaker_time = current_time
                active_breakers.append(ob)
            else:
                active_obs.append(ob)

    return active_obs, active_breakers
