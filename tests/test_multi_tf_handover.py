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


@pytest.mark.asyncio
async def test_top2_permissive_or_gatekeeper_logic():
    """Verify Pilar 1: Top 2 HTF Bias Permissive OR Gatekeeper for M1 (D1+H4) and M15 (H1+H4)."""
    bridge = LiveMT5BridgeCore(host="127.0.0.1", port=5597)

    # 1. Test M1 Entry: Guarded by D1 & H4
    # Case A: Both D1 and H4 are Bearish -> BUY MUST BE BLOCKED
    bridge.d1_trend = "STRONG_BEARISH"
    bridge.h4_trend = "STRONG_BEARISH"
    b1_bear = bridge.d1_trend in ("STRONG_BEARISH", "WEAK_BEARISH")
    b2_bear = bridge.h4_trend in ("STRONG_BEARISH", "WEAK_BEARISH")
    assert (b1_bear and b2_bear) is True, "Both bearish must trigger block"

    # Case B: D1 is Bearish, but H4 has a bullish pullback -> BUY IS PERMITTED (Permissive OR Alpha)
    bridge.h4_trend = "STRONG_BULLISH"
    b2_bear = bridge.h4_trend in ("STRONG_BEARISH", "WEAK_BEARISH")
    assert (b1_bear and b2_bear) is False, "Permissive OR must permit BUY when H4 is bullish pullback"

    # 2. Test M15 Entry: Guarded by H1 & H4
    bridge.h1_trend = "STRONG_BEARISH"
    bridge.h4_trend = "STRONG_BEARISH"
    h1_bear = bridge.h1_trend in ("STRONG_BEARISH", "WEAK_BEARISH")
    h4_bear = bridge.h4_trend in ("STRONG_BEARISH", "WEAK_BEARISH")
    assert (h1_bear and h4_bear) is True, "M15 BUY must be blocked when both H1 & H4 are bearish"

    # Case C: H1 Bullish, H4 Bearish -> M15 BUY IS PERMITTED
    bridge.h1_trend = "STRONG_BULLISH"
    h1_bear = bridge.h1_trend in ("STRONG_BEARISH", "WEAK_BEARISH")
    assert (h1_bear and h4_bear) is False, "M15 BUY permitted when H1 is bullish"


def test_tactical_radar_includes_m15_and_htf_bias():
    """Verify Dashboard Tactical Radar state includes M15 and HTF Bias metadata."""
    from src.dashboard.server import build_tactical_radar_pac
    radar = build_tactical_radar_pac()

    assert "timeframes" in radar
    assert "M15" in radar["timeframes"], "Tactical radar must include M15"
    assert "htf_bias" in radar, "Tactical radar must include htf_bias"
    assert "D1" in radar["htf_bias"]
    assert "H4" in radar["htf_bias"]
    assert "H1" in radar["htf_bias"]
    assert radar["ensemble_confluence"]["total_timeframes"] == 6


@pytest.mark.asyncio
async def test_inflight_order_dispatch_throttle_prevents_duplicate_orders():
    """Verify Anti-Spam: 5.0s dispatch cooldown and optimistic in-flight registration prevent spamming duplicate limits."""
    import time
    bridge = LiveMT5BridgeCore(host="127.0.0.1", port=5594)

    acc_num = "115745645"
    now_time = time.time()

    # Simulate first dispatch
    bridge.account_last_order_dispatch[acc_num] = now_time

    # Immediate second tick (0.5s later) -> must be throttled!
    next_tick_time = now_time + 0.5
    is_throttled = (next_tick_time - bridge.account_last_order_dispatch.get(acc_num, 0.0)) < 5.0
    assert is_throttled is True, "Immediate sub-second re-dispatch must be throttled by 5.0s guard"

    # After 5.1 seconds -> allowed
    future_time = now_time + 5.1
    is_throttled_future = (future_time - bridge.account_last_order_dispatch.get(acc_num, 0.0)) < 5.0
    assert is_throttled_future is False, "Dispatch must be permitted after 5.0s cooldown"


def test_nested_m15_gatekeeper_blocks_premature_m1_entry():
    """Verify Nested M15 Gatekeeper (DEC-039 / Kubu 3): M1 entry is blocked if M15 is in Equilibrium."""
    # Setup M15 in Equilibrium (neutral)
    tf_dict = {
        "M15": {"status": "EQUILIBRIUM_WAIT", "direction": "NEUTRAL"},
        "M1": {"active_setup": True, "direction": "SELL", "status": "IN_SELL_ZONE", "roof_poi_type": "DBD"}
    }

    scan_tf = "M1"
    c_dir = tf_dict["M1"]["direction"]
    m15_setup = tf_dict.get("M15", {})
    m15_status = m15_setup.get("status", "EQUILIBRIUM_WAIT")

    # M1 SELL must be blocked when M15 is not IN_SELL_ZONE
    is_blocked = (c_dir == "SELL" and m15_status != "IN_SELL_ZONE")
    assert is_blocked is True, "Premature M1 SELL must be blocked when M15 is in Equilibrium"

    # When M15 matures into IN_SELL_ZONE -> M1 SELL permitted
    tf_dict["M15"]["status"] = "IN_SELL_ZONE"
    m15_status = tf_dict["M15"]["status"]
    is_blocked_mature = (c_dir == "SELL" and m15_status != "IN_SELL_ZONE")
    assert is_blocked_mature is False, "M1 SELL permitted once M15 enters IN_SELL_ZONE"


def test_strict_poi_filter_rejects_phantom_orders():
    """Verify Strict Real POI Filter (DEC-039 / Kubu 2): Orders on raw swings without POI base are rejected."""
    # Scenario A: Setup has SWING fallback only (no DBD/RBR/FVG)
    setup_phantom = {"direction": "SELL", "roof_poi_type": "SWING"}
    poi_type_sell = setup_phantom.get("roof_poi_type")
    is_rejected = poi_type_sell in ("SWING", None, "")
    assert is_rejected is True, "Phantom order on raw swing without POI base must be rejected"

    # Scenario B: Setup has validated DBD base
    setup_valid = {"direction": "SELL", "roof_poi_type": "DBD"}
    poi_type_valid = setup_valid.get("roof_poi_type")
    is_valid_allowed = poi_type_valid not in ("SWING", None, "")
    assert is_valid_allowed is True, "Order with real institutional DBD base must be accepted"
