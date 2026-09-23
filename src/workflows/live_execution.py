"""
Live Trading Execution Pipeline & Independent Circuit Breaker Sentinel (Workflow 3 - T4-2 & T4-3).

Core Architecture:
1. Tactician Agent: Consumes MarketStateSnapshot and applies Strategy Checklist.
2. Risk Governor: Enforces Hard Caps, Daily Drawdown Limits (<= 3%), and Broker Lot Normalization.
3. Sentinel Circuit Breaker: Independent daemon watching equity peak-to-trough; trips instant EMERGENCY KILL SWITCH if breached.
4. Bridge Dispatcher: Translates canonical XAUUSD orders to MT5 socket command protocol.
"""

from pathlib import Path
from typing import Dict, Any, Optional, List, Tuple
from datetime import datetime
from enum import Enum
from pydantic import BaseModel, Field

from src.core.types import (
    MarketStateSnapshot,
    Direction,
    TradingStyle,
    ForceCloseAction
)
from src.data.adapter import BrokerAdapter


class ExecutionDecision(str, Enum):
    APPROVED = "APPROVED"
    VETOED_RISK = "VETOED_RISK"
    CIRCUIT_BREAKER_TRIPPED = "CIRCUIT_BREAKER_TRIPPED"
    MANUAL_HANDBRAKE_ACTIVE = "MANUAL_HANDBRAKE"
    INSUFFICIENT_CHECKLIST_SCORE = "CHECKLIST_FAILED"


class OrderDispatchCommand(BaseModel):
    """Normalized order dispatch payload ready for MT5 Bridge."""
    command_id: str
    symbol: str
    action: str = "ORDER_SEND"
    order_type: str                            # BUY, SELL, BUY_LIMIT, SELL_LIMIT
    lots: float
    price: float
    sl: float
    tp: float
    comment: str
    magic: int = 123456
    created_at: datetime = Field(default_factory=datetime.now)


class CircuitBreakerSentinel:
    """Independent safety watchdog enforcing absolute daily loss limits and handbrake."""

    def __init__(
        self,
        max_daily_drawdown_pct: float = 3.0,
        handbrake_path: str = "configs/handbrake.lock"
    ):
        self.max_daily_dd = max_daily_drawdown_pct
        self.handbrake_file = Path(handbrake_path)
        self.day_start_equity = 10000.0
        self.is_tripped = False
        self.trip_reason = ""

    def reset_daily_equity(self, starting_equity: float):
        self.day_start_equity = starting_equity
        self.is_tripped = False
        self.trip_reason = ""

    def check_safety(self, current_equity: float) -> Tuple[bool, str]:
        """
        Returns (is_safe, reason). If false, all execution must cease immediately.
        """
        # 1. Check Manual Handbrake
        if self.handbrake_file.exists():
            return False, "MANUAL_HANDBRAKE_ENGAGED"

        # 2. Check Daily Drawdown Limit
        daily_dd_amt = max(self.day_start_equity - current_equity, 0.0)
        daily_dd_pct = (daily_dd_amt / max(self.day_start_equity, 1.0)) * 100.0

        if daily_dd_pct >= self.max_daily_dd:
            self.is_tripped = True
            self.trip_reason = f"CIRCUIT_BREAKER: Daily Drawdown ({daily_dd_pct:.2f}%) hit threshold ({self.max_daily_dd:.2f}%)"
            return False, self.trip_reason

        return True, "SAFE"


class LiveExecutionPipeline:
    """Coordinates Tactician -> Risk Governor -> Sentinel -> MT5 Bridge Dispatch."""

    def __init__(
        self,
        broker_adapter: BrokerAdapter,
        circuit_breaker: CircuitBreakerSentinel,
        base_risk_pct: float = 0.50,
        min_checklist_score: float = 8.0
    ):
        self.adapter = broker_adapter
        self.sentinel = circuit_breaker
        self.base_risk_pct = base_risk_pct
        self.min_score = min_checklist_score

    def evaluate_and_dispatch(
        self,
        snapshot: MarketStateSnapshot,
        candidate_direction: Direction,
        entry_price: float,
        sl_price: float,
        tp_price: float,
        checklist_score: float,
        current_equity: float
    ) -> Tuple[ExecutionDecision, Optional[OrderDispatchCommand], str]:
        """
        Processes an execution candidate through the strict defense chain.
        """
        # Step 1: Circuit Breaker Sentinel Check
        is_safe, sentinel_reason = self.sentinel.check_safety(current_equity)
        if not is_safe:
            decision = (
                ExecutionDecision.MANUAL_HANDBRAKE_ACTIVE
                if "HANDBRAKE" in sentinel_reason
                else ExecutionDecision.CIRCUIT_BREAKER_TRIPPED
            )
            return decision, None, sentinel_reason

        # Step 2: Tactician Checklist Evaluation
        if checklist_score < self.min_score:
            return (
                ExecutionDecision.INSUFFICIENT_CHECKLIST_SCORE,
                None,
                f"Checklist score {checklist_score:.1f} < threshold {self.min_score:.1f}"
            )

        # Step 3: Risk Governor Lot Sizing & Normalization
        sl_distance = abs(entry_price - sl_price)
        if sl_distance <= 0.0:
            return ExecutionDecision.VETOED_RISK, None, "Invalid SL distance"

        # Points distance = price difference / point
        pts_dist = sl_distance / self.adapter.spec.point
        raw_lots = self.adapter.calculate_lot(
            equity=current_equity,
            risk_pct=self.base_risk_pct,
            sl_distance_points=pts_dist
        )
        normalized_lots = self.adapter.normalize_lot(raw_lots)

        if normalized_lots <= 0.0:
            return ExecutionDecision.VETOED_RISK, None, "Normalized lot size is 0.0"

        # Step 4: Dispatch Command Assembly
        order_type = "BUY_LIMIT" if candidate_direction == Direction.BUY else "SELL_LIMIT"
        broker_symbol = self.adapter.to_broker_symbol(snapshot.symbol)

        command = OrderDispatchCommand(
            command_id=f"CMD-{snapshot.symbol}-{int(datetime.now().timestamp())}",
            symbol=broker_symbol,
            order_type=order_type,
            lots=normalized_lots,
            price=entry_price,
            sl=sl_price,
            tp=tp_price,
            comment="LLMV2-PAC-PAC50"
        )

        return ExecutionDecision.APPROVED, command, "APPROVED_FOR_DISPATCH"
