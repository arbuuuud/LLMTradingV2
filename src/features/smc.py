from typing import List, Tuple, Optional
from datetime import datetime
import numpy as np
from src.core.types import FairValueGap, InversionFVG, FVGConfluenceZone, OrderBlock, Direction


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

            # Mitigated: body close inside or below top
            if latest_close <= fvg.top:
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

            # Mitigated: body close inside or above bottom
            if latest_close >= fvg.bottom:
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
    fvgs: List[FairValueGap]
) -> List[OrderBlock]:
    """
    Detects Order Blocks:
    The last opposite-colored candle prior to a displacement candle that generated an FVG.
    """
    obs: List[OrderBlock] = []
    fvg_indices = {fvg.bar_index: fvg for fvg in fvgs}

    for idx, fvg in fvg_indices.items():
        # Look back 1 or 2 bars for the origin candle
        origin_idx = idx - 1
        if origin_idx < 0:
            continue

        is_bearish_candle = closes[origin_idx] < opens[origin_idx]
        is_bullish_candle = closes[origin_idx] > opens[origin_idx]

        if fvg.direction == Direction.BUY and is_bearish_candle:
            # Bullish OB: Last down candle before strong rally
            obs.append(
                OrderBlock(
                    id=f"OB-BULL-{origin_idx}",
                    direction=Direction.BUY,
                    top=float(highs[origin_idx]),
                    bottom=float(lows[origin_idx]),
                    timestamp=timestamps[origin_idx],
                    bar_index=origin_idx
                )
            )
        elif fvg.direction == Direction.SELL and is_bullish_candle:
            # Bearish OB: Last up candle before strong drop
            obs.append(
                OrderBlock(
                    id=f"OB-BEAR-{origin_idx}",
                    direction=Direction.SELL,
                    top=float(highs[origin_idx]),
                    bottom=float(lows[origin_idx]),
                    timestamp=timestamps[origin_idx],
                    bar_index=origin_idx
                )
            )

    return obs
