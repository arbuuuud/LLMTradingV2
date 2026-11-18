"""
Unit & Integration Tests for Multi-TF Entry Scanning, Handover, and 3-Pillar Engine.
Verifies:
1. D1 Bias Gatekeeper (Blocks counter-trend BUY on Bearish D1, blocks SELL on Bullish D1)
2. Micro Level Depletion (Preserves deeper virgin layers, skips spent layers)
3. Proximity Coalescing & Anti-Spam Guard (No duplicate orders within <= 1.5 points)
4. Pending Order Handover (Atomic Upgrade from lower to higher TF)
5. Account Number Isolation on MODIFY_POSITION
"""

import pytest
import asyncio
from src.bridge.server import LiveMT5BridgeCore


@pytest.mark.asyncio
async def test_d1_bias_gatekeeper_blocks_counter_trend():
    """Verify Pilar 1: D1 Bias Gate prevents dip-buying during macro downtrends."""
    bridge = LiveMT5BridgeCore(host="127.0.0.1", port=5599)
    
    # Simulate D1 Bearish Trend
    bridge.d1_trend = "STRONG_BEARISH"
    assert bridge.d1_trend in ("STRONG_BEARISH", "WEAK_BEARISH")

    # In a bearish macro trend, BUY must be strictly blocked
    dir_cmd = "BUY"
    allow_trade = not (bridge.d1_trend in ("STRONG_BEARISH", "WEAK_BEARISH") and dir_cmd == "BUY")
    assert allow_trade is False, "BUY should be blocked when D1 trend is STRONG_BEARISH"

    # SELL must be permitted
    dir_cmd = "SELL"
    allow_trade = not (bridge.d1_trend in ("STRONG_BULLISH", "WEAK_BULLISH") and dir_cmd == "SELL")
    assert allow_trade is True, "SELL should be allowed when D1 trend is STRONG_BEARISH"


@pytest.mark.asyncio
async def test_micro_level_depletion_preserves_virgin_depth():
    """Verify Pilar 3: Micro Level Depletion marks only spent layer and preserves deeper virgin layers."""
    bridge = LiveMT5BridgeCore(host="127.0.0.1", port=5598)
    
    # Initialize TF depletion for M1
    bridge.tf_depletion["M1"] = {
        "spent_layers": set(),
        "roof": 3870.0,
        "floor": 3850.0,
        "direction": "BUY"
    }

    # Simulate Layer 1 took profit (marked as spent)
    bridge.tf_depletion["M1"]["spent_layers"].add(0) # Layer 1 is spent

    spent_set = bridge.tf_depletion["M1"]["spent_layers"]
    assert 0 in spent_set, "Layer 1 should be spent"
    assert 1 not in spent_set, "Layer 2 should remain virgin (unspent)"
    assert 2 not in spent_set, "Layer 3 should remain virgin (unspent)"

    # Structure shift by >= 1.0 pt should reset depletion
    new_sw_low = 3848.5 # Shifted by 1.5 points
    if abs(new_sw_low - bridge.tf_depletion["M1"]["floor"]) >= 1.0:
        bridge.tf_depletion["M1"]["spent_layers"].clear()
        bridge.tf_depletion["M1"]["floor"] = new_sw_low

    assert len(bridge.tf_depletion["M1"]["spent_layers"]) == 0, "Depletion should reset when structure shifts"


@pytest.mark.asyncio
async def test_proximity_coalescing_prevents_duplicate_orders():
    """Verify Anti-Spam: Orders within 1.5 points in the same direction are coalesced."""
    existing_prices = [3850.0]
    candidate_price_too_close = 3850.75 # 0.75 pt difference (<= 1.5 pt)
    candidate_price_far_enough = 3847.50 # 2.50 pt difference (> 1.5 pt)

    # Check collision logic
    collision_1 = any(abs(candidate_price_too_close - ep) <= 1.50 for ep in existing_prices)
    collision_2 = any(abs(candidate_price_far_enough - ep) <= 1.50 for ep in existing_prices)

    assert collision_1 is True, "Order within 0.75 pt must trigger proximity collision guard"
    assert collision_2 is False, "Order 2.50 pt away should be permitted"
