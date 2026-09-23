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
    is_confluence: bool = False  # True if merged from overlapping OB + S&D
    confluence_desc: Optional[str] = None
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


class CandlePatternType(str, Enum):
    BULLISH_ENGULFING = "BULLISH_ENGULFING"
    BEARISH_ENGULFING = "BEARISH_ENGULFING"
    BULLISH_PIN_BAR = "BULLISH_PIN_BAR"         # Hammer / Dragonfly Doji / Rejection wick at floor
    BEARISH_PIN_BAR = "BEARISH_PIN_BAR"         # Shooting Star / Gravestone Doji / Rejection wick at roof
    MORNING_STAR = "MORNING_STAR"               # 3-bar reversal at floor
    EVENING_STAR = "EVENING_STAR"               # 3-bar reversal at roof
    MOMENTUM_MARUBOZU_BULL = "MOMENTUM_MARUBOZU_BULL"
    MOMENTUM_MARUBOZU_BEAR = "MOMENTUM_MARUBOZU_BEAR"


class CandlePattern(BaseModel):
    id: str
    pattern_type: CandlePatternType
    direction: Direction
    timestamp: datetime
    bar_index: int
    open: float
    high: float
    low: float
    close: float
    body_ratio: float
    rejection_wick_ratio: float
    at_poi: bool = False
    poi_type: Optional[str] = None      # e.g. "OB", "FVG", "OTE"
    poi_id: Optional[str] = None
    poi_confluence_score: float = 1.0


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
    active_candle_patterns: List[CandlePattern] = Field(default_factory=list)
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


class TradingStyle(str, Enum):
    SCALPING = "SCALPING"
    INTRADAY = "INTRADAY"
    SWING = "SWING"


class SessionKillzone(str, Enum):
    ASIAN = "ASIAN"                 # 00:00 - 08:00 UTC
    LONDON_OPEN = "LONDON_OPEN"     # 07:00 - 11:00 UTC
    NY_OVERLAP = "NY_OVERLAP"       # 12:00 - 17:00 UTC
    ALL_DAY = "ALL_DAY"


class ForceClosePolicy(str, Enum):
    INSTANT_KILL = "INSTANT_KILL"                 # Exit 100% on counter-signal
    PARTIAL_50_BEP = "PARTIAL_50_BEP"             # Close 50% lot and move SL to BEP
    COUNTER_MOM_ONLY = "COUNTER_MOM_ONLY"         # Close only if opposite Momentum Marubozu occurs
    COUNTER_POI_TOUCH = "COUNTER_POI_TOUCH"       # Close when price touches new opposing POI
    PASSIVE_HOLD = "PASSIVE_HOLD"                 # No force close, strictly hold until Hard TP/SL


class PACRetestMode(str, Enum):
    FIRST_RETEST_ONLY = "FIRST_RETEST_ONLY"       # Only trade virgin/first retest of the zone
    MULTI_RETEST_DEEPER = "MULTI_RETEST_DEEPER"   # Trade multiple retests only if penetrating deeper
    UNLIMITED_UNTIL_BREACH = "UNLIMITED"          # Keep limits active until floor/roof broken


class PACHandoverMode(str, Enum):
    DYNAMIC_TARGET_SHIFT = "DYNAMIC_SHIFT"        # Move TP to new equilibrium and lock BEP
    PARTIAL_EXIT_BEP = "PARTIAL_EXIT_BEP"         # Close 50% lot immediately, let runner hit new/old TP
    STRICT_ANCHOR_HOLD = "STRICT_HOLD"            # Maintain original anchor TP 50% regardless of new POI


class MethodologyInput(BaseModel):
    """User input defining a core trading methodology and research objective."""
    name: str = "PAC"                             # Pivot and Control
    trading_style: TradingStyle = TradingStyle.SCALPING
    daily_profit_target_pct: float = 1.0          # 1% per day
    monthly_profit_target_pct: float = 20.0       # 20% per month
    description: str = ""
    parameters: Dict[str, Any] = Field(default_factory=dict)


class ShadowCloneSpec(BaseModel):
    """Independent specification of a single Shadow Clone in the Kage Bunshin matrix."""
    clone_id: str
    methodology: str
    timeframe: str = "M1"
    trading_style: TradingStyle = TradingStyle.SCALPING

    # Dimensi 1: Structure & Wave
    wave_regime: str = "ALL"                      # IMPULSIVE, PULLBACK, SIDEWAY, ALL
    require_bos_or_choch: bool = False
    require_fibo_ote: bool = False

    # Dimensi 2: POI Selection
    poi_types: List[str] = Field(default_factory=lambda: ["OB", "CONTINUATION_SD", "CONFLUENCE"])
    require_swept_liquidity: bool = False
    max_touch_count: int = 2

    # Dimensi 3: Execution & Candlesticks
    execution_mode: str = "LIMIT_GRID"            # LIMIT_GRID or CONFIRMED_REACTION
    limit_layers: int = 5                         # 3, 5, or 10 layers in 0-25% zone
    hard_sl_pct: float = -20.0                    # Distance below Floor (0%) in %
    soft_sl_candle_close_pct: Optional[float] = -5.0
    hard_tp_pct: float = 50.0                     # Midpoint Equilibrium
    force_close_policy: ForceClosePolicy = ForceClosePolicy.PARTIAL_50_BEP

    # Dimensi Tambahan Khusus PAC Lifecycle (Naruto Research Task)
    pac_retest_mode: PACRetestMode = PACRetestMode.FIRST_RETEST_ONLY
    cancel_remaining_on_tp: bool = True           # Cancel standing limits once TP 50% is achieved
    pac_handover_mode: PACHandoverMode = PACHandoverMode.DYNAMIC_TARGET_SHIFT

    # Dimensi 4: Session
    session: SessionKillzone = SessionKillzone.ALL_DAY

    # Anti-Overfitting Safeguards
    min_trades_per_month: int = 30                # Disqualify if dormant


class ShadowCloneResult(BaseModel):
    """Performance evaluation output of a single Shadow Clone."""
    clone_id: str
    spec: ShadowCloneSpec
    total_trades: int
    win_rate_pct: float
    profit_factor: float
    net_pnl: float
    roi_pct: float
    max_drawdown_pct: float
    avg_trades_per_day: float
    monthly_green_pct: float
    saved_r_amount: float = 0.0
    is_disqualified: bool = False
    disqualification_reason: Optional[str] = None


class RiskProfileMetrics(BaseModel):
    label: str
    risk_multiplier: float
    base_risk_pct: float
    total_trades: int
    win_rate_pct: float
    profit_factor: float
    net_pnl: float
    roi_pct: float
    max_drawdown_pct: float
    passes_hurdle: bool


class FourRiskProfilesReport(BaseModel):
    """Production evaluation mapping winning strategy to 4 standardized risk tiers."""
    strategy_id: str
    methodology: str
    timeframe: str
    generated_at: datetime
    prop_firm: RiskProfileMetrics      # 0.50% Base Risk (FTMO Safe, Max DD <= 7.8%)
    sweet_spot: RiskProfileMetrics     # 0.75% Base Risk (Live Account Recommendation, Max DD <= 10.7%)
    aggressive: RiskProfileMetrics     # 1.00% Base Risk (Compounding, Max DD <= 13.1%)
    yolo: RiskProfileMetrics           # 2.00% Base Risk (Max Velocity, Max DD <= 22.0%)
    champion_clone_id: str
    robustness_score: float = 0.0      # Scale 0 - 100


class ForceCloseTrigger(BaseModel):
    """Instruction emitted by ForceClose Guardian Agent to manage open positions."""
    position_id: str
    action: ForceCloseAction
    reason: str
    details: Dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime
