from datetime import datetime
from enum import Enum
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field


class Direction(str, Enum):
    BUY = "BUY"
    SELL = "SELL"
    WAIT = "WAIT"


class Trend(str, Enum):
    BULLISH = "BULLISH"
    BEARISH = "BEARISH"
    RANGING = "RANGING"


class StructureEventType(str, Enum):
    BOS_BULLISH = "BOS_BULLISH"
    BOS_BEARISH = "BOS_BEARISH"
    CHOCH_BULLISH = "CHOCH_BULLISH"
    CHOCH_BEARISH = "CHOCH_BEARISH"
    NONE = "NONE"


class ForceCloseAction(str, Enum):
    HOLD = "HOLD"
    MOVE_SL_BE = "MOVE_SL_BE"
    PARTIAL_CLOSE = "PARTIAL_CLOSE"
    FORCE_CLOSE_MARKET = "FORCE_CLOSE_MARKET"


class SwingPoint(BaseModel):
    index: int
    price: float
    timestamp: datetime
    confirmed: bool = True
    label: Optional[str] = None  # "HH", "HL", "LH", "LL", "EQH", "EQL"
    is_strong: bool = False      # Protected structural high/low
    retrace_ratio: Optional[float] = None    # Retracement ratio (e.g. 0.618, 0.382)
    extension_ratio: Optional[float] = None  # Expansion/Extension ratio (e.g. 1.272, 1.618)
    fibo_zone: Optional[str] = None          # "SHALLOW" (0.382-0.5), "EQ" (0.5), "OTE" (0.618-0.786), "DEEP" (>0.786)


class StructureState(BaseModel):
    last_swing_high: Optional[SwingPoint] = None
    last_swing_low: Optional[SwingPoint] = None
    last_event: StructureEventType = StructureEventType.NONE
    last_event_price: Optional[float] = None
    last_event_time: Optional[datetime] = None


class FairValueGap(BaseModel):
    id: str
    direction: Direction
    top: float
    bottom: float
    ce_price: float = 0.0  # 50% Consequent Encroachment
    timestamp: datetime
    bar_index: int
    is_inversion: bool = False
    is_touched: bool = False     # Kesenggol (wick/body entered gap)
    touch_count: int = 0         # Increments only when price penetrates deeper than previous touch
    deepest_touch_price: Optional[float] = None # Extreme price reached so far inside gap
    is_mitigated: bool = False   # Body closed inside or through gap
    is_fully_used: bool = False  # Orders 100% consumed by wick/body (swept to opposite boundary)
    tested_count: int = 0


class InversionFVG(BaseModel):
    """Flipped Fair Value Gap acting as newly inverted Support or Resistance."""
    id: str
    original_fvg_id: str
    direction: Direction  # Flipped role: BUY = Support, SELL = Resistance
    top: float
    bottom: float
    ce_price: float = 0.0
    invert_time: datetime
    breached_with_counter_fvg: bool = False
    counter_fvg_id: Optional[str] = None
    is_touched: bool = False     # Kesenggol setelah invert
    touch_count: int = 0         # Increments only when price penetrates deeper than previous touch
    deepest_touch_price: Optional[float] = None
    is_mitigated: bool = False   # Body closed inside or through gap
    is_fully_used: bool = False  # Orders 100% consumed by wick/body
    tested_count: int = 0


class FVGConfluenceZone(BaseModel):
    """High-probability confluence where an active FVG and an active iFVG overlap or co-exist."""
    id: str
    fvg_id: str
    ifvg_id: str
    overlap_top: float
    overlap_bottom: float
    confluence_type: str = "OVERLAPPING_ZONE"  # OVERLAPPING_ZONE or SAME_SWING
    has_counter_fvg_breach: bool = False
    probability_score: float = 8.5  # Boosted confidence weight


class OrderBlockType(str, Enum):
    REVERSAL_DBR = "REVERSAL_DBR"         # Drop-Base-Rally (+OB Reversal)
    REVERSAL_RBD = "REVERSAL_RBD"         # Rally-Base-Drop (-OB Reversal)
    CONTINUATION_RBR = "CONTINUATION_RBR" # Rally-Base-Rally (+OB Continuation)
    CONTINUATION_DBD = "CONTINUATION_DBD" # Drop-Base-Drop (-OB Continuation)
    BREAKER_BULLISH = "BREAKER_BULLISH"   # Breaker Block Support (Flipped from -OB)
    BREAKER_BEARISH = "BREAKER_BEARISH"   # Breaker Block Resistance (Flipped from +OB)


class OrderBlock(BaseModel):
    id: str
    direction: Direction
    ob_type: OrderBlockType = OrderBlockType.REVERSAL_DBR
    top: float
    bottom: float
    mean_threshold: float = 0.0  # 50% Mean Threshold
    timestamp: datetime
    bar_index: int
    has_fvg: bool = True
    fvg_id: Optional[str] = None
    has_swept_liquidity: bool = False
    base_candle_count: int = 1   # Number of base candles (1-3 for valid S&D)
    impulse_ratio: float = 1.0   # Leg-Out Range / Base Range
    is_breaker: bool = False
    breaker_time: Optional[datetime] = None
    is_touched: bool = False
    touch_count: int = 0
    deepest_touch_price: Optional[float] = None
    is_mitigated: bool = False
    is_fully_used: bool = False


class FibonacciOTE(BaseModel):
    anchor_high: float
    anchor_low: float
    level_500: float  # Equilibrium
    level_618: float  # Golden pocket entry
    level_705: float  # Institutional sweet spot
    level_786: float  # Deep discount
    in_ote_zone: bool = False


class LiquidityState(BaseModel):
    buy_side_swept: bool = False
    sell_side_swept: bool = False
    equal_highs: Optional[float] = None
    equal_lows: Optional[float] = None


class PriceQuote(BaseModel):
    bid: float
    ask: float
    spread: float
    timestamp: datetime


class MarketStateSnapshot(BaseModel):
    """Enriched state output generated deterministically by W1 (Live Data Feed)."""
    symbol: str
    timestamp: datetime
    timeframe: str
    current_price: PriceQuote
    htf_trend: Trend
    structure: StructureState
    active_fvgs: List[FairValueGap] = Field(default_factory=list)
    active_ifvgs: List[InversionFVG] = Field(default_factory=list)
    fvg_confluences: List[FVGConfluenceZone] = Field(default_factory=list)
    active_obs: List[OrderBlock] = Field(default_factory=list)
    active_breakers: List[OrderBlock] = Field(default_factory=list)
    fibonacci: Optional[FibonacciOTE] = None
    liquidity: LiquidityState = Field(default_factory=LiquidityState)


class ChecklistRule(BaseModel):
    id: str
    description: str
    weight: float
    mandatory: bool = False


class ChecklistEvaluation(BaseModel):
    """Evaluation result of a MarketStateSnapshot against a Strategy Checklist."""
    strategy_id: str
    direction: Direction
    total_score: float
    max_possible_score: float
    passed: bool
    criteria_met: Dict[str, bool]
    score_percentage: float
    rationale: Optional[str] = None


class ForceCloseTrigger(BaseModel):
    """Instruction emitted by ForceClose Guardian Agent to manage open positions."""
    position_id: str
    action: ForceCloseAction
    reason: str
    details: Dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime
