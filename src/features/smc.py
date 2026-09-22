from typing import List
from datetime import datetime
import numpy as np
from src.core.types import FairValueGap, OrderBlock, Direction


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
    - If price touches inside the gap, tested_count increments and marked mitigated.
    - If price closes completely beyond the opposite boundary, it becomes an Inversion FVG (iFVG).
    """
    for fvg in fvgs:
        if fvg.direction == Direction.BUY:
            # Bullish FVG tested if price dips into it
            if latest_low <= fvg.top and latest_high >= fvg.bottom:
                fvg.is_mitigated = True
                fvg.tested_count += 1
            # If price closes below the bottom, it flips to Bearish Inversion FVG
            if latest_close < fvg.bottom:
                fvg.is_inversion = True
        elif fvg.direction == Direction.SELL:
            # Bearish FVG tested if price rallies into it
            if latest_high >= fvg.bottom and latest_low <= fvg.top:
                fvg.is_mitigated = True
                fvg.tested_count += 1
            # If price closes above the top, it flips to Bullish Inversion FVG
            if latest_close > fvg.top:
                fvg.is_inversion = True

    return fvgs


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
