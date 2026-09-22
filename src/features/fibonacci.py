from typing import Optional
from src.core.types import FibonacciOTE, Direction


def calculate_fibonacci_ote(
    high_anchor: float,
    low_anchor: float,
    current_price: float,
    direction: Direction
) -> Optional[FibonacciOTE]:
    """
    Calculates Fibonacci Equilibrium (0.50) and Optimal Trade Entry (OTE) levels:
    - 0.618: Standard Golden Ratio
    - 0.705: Institutional Sweet Spot (Midpoint between 0.618 & 0.786)
    - 0.786: Square root of 0.618 (Deep Discount / Deep Premium)
    """
    range_diff = high_anchor - low_anchor
    if range_diff <= 0:
        return None

    if direction == Direction.BUY:
        # Pullback into discount from high
        level_500 = high_anchor - 0.500 * range_diff
        level_618 = high_anchor - 0.618 * range_diff
        level_705 = high_anchor - 0.705 * range_diff
        level_786 = high_anchor - 0.786 * range_diff
        # In OTE zone if price between 0.618 and 0.786
        in_ote = level_786 <= current_price <= level_618
    else:
        # Rally into premium from low
        level_500 = low_anchor + 0.500 * range_diff
        level_618 = low_anchor + 0.618 * range_diff
        level_705 = low_anchor + 0.705 * range_diff
        level_786 = low_anchor + 0.786 * range_diff
        # In OTE zone if price between 0.618 and 0.786
        in_ote = level_618 <= current_price <= level_786

    return FibonacciOTE(
        anchor_high=high_anchor,
        anchor_low=low_anchor,
        level_500=float(level_500),
        level_618=float(level_618),
        level_705=float(level_705),
        level_786=float(level_786),
        in_ote_zone=in_ote
    )
