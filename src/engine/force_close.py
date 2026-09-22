from datetime import datetime
from typing import Optional
from src.core.types import (
    ForceCloseTrigger,
    ForceCloseAction,
    Direction,
    StructureEventType,
    MarketStateSnapshot
)


class ForceCloseGuardianEngine:
    """
    Evaluates open active positions against market state changes
    to detect structural invalidation and trigger protective exits.
    """

    def evaluate_position(
        self,
        position_id: str,
        direction: Direction,
        entry_price: float,
        current_snapshot: MarketStateSnapshot,
        open_time: datetime,
        max_duration_seconds: Optional[int] = None
    ) -> ForceCloseTrigger:
        current_bid = current_snapshot.current_price.bid
        current_ask = current_snapshot.current_price.ask
        struct_event = current_snapshot.structure.last_event
        now = current_snapshot.timestamp

        # 1. Structural Invalidation: Opposite CHoCH detected
        if direction == Direction.BUY and struct_event == StructureEventType.CHOCH_BEARISH:
            return ForceCloseTrigger(
                position_id=position_id,
                action=ForceCloseAction.FORCE_CLOSE_MARKET,
                reason="STRUCTURAL_INVALIDATION: Bearish CHoCH occurred against active BUY",
                details={"event": struct_event, "bid": current_bid},
                timestamp=now
            )
        elif direction == Direction.SELL and struct_event == StructureEventType.CHOCH_BULLISH:
            return ForceCloseTrigger(
                position_id=position_id,
                action=ForceCloseAction.FORCE_CLOSE_MARKET,
                reason="STRUCTURAL_INVALIDATION: Bullish CHoCH occurred against active SELL",
                details={"event": struct_event, "ask": current_ask},
                timestamp=now
            )

        # 2. Inversion FVG Invalidation
        if direction == Direction.BUY:
            violated_ifvgs = [f for f in current_snapshot.active_fvgs if f.direction == Direction.BUY and f.is_inversion]
            if violated_ifvgs:
                return ForceCloseTrigger(
                    position_id=position_id,
                    action=ForceCloseAction.FORCE_CLOSE_MARKET,
                    reason="STRUCTURAL_INVALIDATION: Bullish FVG violated and inverted into Bearish Resistance",
                    details={"fvg_id": violated_ifvgs[0].id},
                    timestamp=now
                )
        elif direction == Direction.SELL:
            violated_ifvgs = [f for f in current_snapshot.active_fvgs if f.direction == Direction.SELL and f.is_inversion]
            if violated_ifvgs:
                return ForceCloseTrigger(
                    position_id=position_id,
                    action=ForceCloseAction.FORCE_CLOSE_MARKET,
                    reason="STRUCTURAL_INVALIDATION: Bearish FVG violated and inverted into Bullish Support",
                    details={"fvg_id": violated_ifvgs[0].id},
                    timestamp=now
                )

        # 3. Time Decay Check (Stall protection)
        if max_duration_seconds is not None:
            elapsed = (now - open_time).total_seconds()
            if elapsed > max_duration_seconds:
                return ForceCloseTrigger(
                    position_id=position_id,
                    action=ForceCloseAction.FORCE_CLOSE_MARKET,
                    reason=f"TIME_DECAY: Position exceeded max duration threshold ({elapsed:.0f}s > {max_duration_seconds}s)",
                    details={"elapsed_seconds": elapsed},
                    timestamp=now
                )

        # Default: Hold position
        return ForceCloseTrigger(
            position_id=position_id,
            action=ForceCloseAction.HOLD,
            reason="HEALTHY: No structural invalidation detected",
            timestamp=now
        )
