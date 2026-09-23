import math
from typing import Dict, Optional
from pydantic import BaseModel, Field


class BrokerSpec(BaseModel):
    """Specification of broker-specific symbol properties and execution rules."""
    broker_name: str
    canonical_symbol: str = "XAUUSD"
    broker_symbol: str = "XAUUSD"
    digits: int = 2
    point: float = 0.01
    contract_size: float = 100.0  # Units per 1.0 standard lot
    min_lot: float = 0.01
    max_lot: float = 100.0
    lot_step: float = 0.01
    lot_decimals: int = 2
    tick_size: float = 0.01
    tick_value: float = 1.0  # Profit in quote currency for 1 point movement on 1.0 lot


class BrokerAdapter:
    """
    Translates between Internal Canonical representation and Broker-specific execution specs.
    Isolates the AI agents and trading engines from broker quirks.
    """

    def __init__(self, spec: BrokerSpec):
        self.spec = spec

    def to_broker_symbol(self, canonical_symbol: str) -> str:
        """Translates canonical symbol (e.g. 'XAUUSD') to broker symbol (e.g. 'XAUUSD.u')."""
        if canonical_symbol.upper() == self.spec.canonical_symbol.upper():
            return self.spec.broker_symbol
        return canonical_symbol

    def to_canonical_symbol(self, broker_symbol: str) -> str:
        """Translates broker symbol back to canonical symbol."""
        if broker_symbol == self.spec.broker_symbol:
            return self.spec.canonical_symbol
        return broker_symbol

    def normalize_price(self, price: float) -> float:
        """Rounds price to broker's configured digits precision."""
        return round(price, self.spec.digits)

    def normalize_lot(self, raw_lot: float) -> float:
        """
        Clamps and quantizes raw lot size to broker's valid step, bounds, and decimals.
        Prevents broker order rejection due to invalid volume step.
        """
        if raw_lot <= 0:
            return 0.0

        # 1. Clamp between min_lot and max_lot
        clamped = max(self.spec.min_lot, min(raw_lot, self.spec.max_lot))

        # 2. Quantize according to lot_step
        # Example: if lot_step is 0.01 and clamped is 0.156 -> 0.15
        steps = math.floor((clamped - self.spec.min_lot) / self.spec.lot_step + 1e-9)
        quantized = self.spec.min_lot + (steps * self.spec.lot_step)

        # 3. Final round to lot_decimals to eliminate IEEE-754 floating point artifacts
        return round(quantized, self.spec.lot_decimals)

    def calculate_lot(
        self,
        equity: float,
        risk_pct: float,
        sl_distance_points: float
    ) -> float:
        """
        Calculates position lot size based on Fixed Fractional Equity Risk.
        
        Formula:
        Risk Amount ($) = Equity * (risk_pct / 100)
        Raw Lot = Risk Amount / (SL Distance in Points * (tick_value / (tick_size / point)))
        """
        if equity <= 0 or risk_pct <= 0 or sl_distance_points <= 0:
            return 0.0

        risk_dollars = equity * (risk_pct / 100.0)
        # Cost per point per 1.0 lot
        point_value = self.spec.tick_value * (self.spec.point / self.spec.tick_size) if self.spec.tick_size > 0 else 1.0
        cost_per_lot = sl_distance_points * point_value

        if cost_per_lot <= 0:
            return 0.0

        raw_lot = risk_dollars / cost_per_lot
        return self.normalize_lot(raw_lot)
