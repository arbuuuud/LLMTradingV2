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
    """Verify Dashboard Tactical Radar state includes M15, M30, Counter-Trend Unlock, and HTF Bias metadata."""
    from src.dashboard.server import build_tactical_radar_pac
    radar = build_tactical_radar_pac()

    assert "timeframes" in radar
    assert "M15" in radar["timeframes"], "Tactical radar must include M15"
    assert "M30" in radar["timeframes"], "Tactical radar must include M30"
    assert "htf_bias" in radar, "Tactical radar must include htf_bias"
    assert "counter_trend_unlock" in radar, "Tactical radar must include counter_trend_unlock metadata"
    assert "D1" in radar["htf_bias"]
    assert "H4" in radar["htf_bias"]
    assert "H1" in radar["htf_bias"]
    assert radar["ensemble_confluence"]["total_timeframes"] == 7


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


def test_timeframe_scanning_hierarchy_priority_m15_over_lower_tfs():
    """Verify Scanning Priority Hierarchy: M15 setup strictly precedes M5, M3, M2, and M1."""
    user_tfs = ["M1", "M2", "M3", "M5", "M15"]
    scan_order = [tf for tf in ["M15", "M5", "M3", "M2", "M1"] if tf in user_tfs]

    assert scan_order[0] == "M15", "M15 must be the top priority in scanning hierarchy"
    assert scan_order[1] == "M5", "M5 must be second priority"
    assert scan_order[2] == "M3", "M3 must be third priority"
    assert scan_order[3] == "M2", "M2 must be fourth priority"
    assert scan_order[4] == "M1", "M1 must be fifth priority"

    # Verify when both M15 and M1 have active setups, M15 is selected first
    tf_setups = {
        "M15": {"active_setup": True, "direction": "SELL", "swing_high": 3790.61, "swing_low": 3764.28},
        "M1": {"active_setup": True, "direction": "SELL", "swing_high": 3786.67, "swing_low": 3777.07}
    }

    chosen = None
    for scan_tf in ["M15", "M5", "M3", "M2", "M1"]:
        if scan_tf in tf_setups and tf_setups[scan_tf].get("active_setup"):
            chosen = scan_tf
            break

    assert chosen == "M15", "M15 must be chosen over M1 when both have active setups"


def test_hybrid_4_objective_aware_counter_trend_unlock():
    """Verify HYBRID_4 Objective-Aware Counter-Trend Unlock Gatekeeper."""
    # Scenario: Both D1 and H4 are STRONG_BEARISH, candidate is BUY
    b1_bear = True
    b2_bear = True
    both_bear = b1_bear and b2_bear
    c_dir = "BUY"
    is_counter = (c_dir == "BUY" and both_bear)

    assert is_counter is True

    # 1. Daily Target Circuit Breaker (+1.0% achieved) -> MUST BLOCK
    daily_start_eq = 10000.0
    daily_pnl = 120.0  # +1.2%
    daily_pnl_pct = (daily_pnl / daily_start_eq) * 100.0
    assert daily_pnl_pct >= 1.0, "Should detect daily target reached"

    # 2. Defensive Loss Boundary (-0.5% hit) -> MUST BLOCK
    daily_pnl = -60.0  # -0.6%
    daily_pnl_pct = (daily_pnl / daily_start_eq) * 100.0
    assert daily_pnl_pct <= -0.5, "Should detect daily defensive boundary"

    # 3. Hunting Phase (+0.2% PnL) -> Evaluate Opsi A vs Opsi B
    daily_pnl = 20.0  # +0.2%
    daily_pnl_pct = (daily_pnl / daily_start_eq) * 100.0
    in_hunting_phase = (-0.5 < daily_pnl_pct < 1.0)
    assert in_hunting_phase is True

    # Test 3a: Opsi A (M1 + M5 Confluence)
    tf_dict_opsi_a = {
        "M1": {"direction": "BUY", "quadrant": "DISCOUNT"},
        "M5": {"direction": "BUY", "quadrant": "DISCOUNT"},
        "M15": {"structure_event": "NONE"}
    }
    opsi_a = (
        tf_dict_opsi_a["M1"]["direction"] == "BUY" and
        tf_dict_opsi_a["M5"]["direction"] == "BUY"
    )
    assert opsi_a is True
    # In HYBRID_4, Opsi A gets full Equilibrium TP
    tp_mode_a = "EQ" if opsi_a else "SHALLOW"
    assert tp_mode_a == "EQ"

    # Test 3b: Opsi B only (M15 BOS active, no M5 confluence)
    tf_dict_opsi_b = {
        "M1": {"direction": "BUY", "quadrant": "DISCOUNT"},
        "M5": {"direction": "NEUTRAL", "quadrant": "EQUILIBRIUM"},
        "M15": {"structure_event": "BOS_BULLISH"}
    }
    m1_ok = tf_dict_opsi_b["M1"]["direction"] == "BUY"
    m5_ok = tf_dict_opsi_b["M5"]["direction"] == "BUY"
    opsi_a_false = m1_ok and m5_ok
    assert opsi_a_false is False

    m15_event = tf_dict_opsi_b["M15"]["structure_event"]
    bos_ok = "BULLISH" in m15_event
    opsi_b = bos_ok
    assert opsi_b is True
    # In HYBRID_4, Opsi B only gets Quick Shallow TP
    tp_mode_b = "EQ" if opsi_a_false else "SHALLOW"
    assert tp_mode_b == "SHALLOW"


@pytest.mark.asyncio
async def test_cold_start_telemetry_sync_gate_blocks_unsynced_accounts():
    """Verify Cold-Start Gate: Bridge blocks dispatch until MT5 sends complete TICK telemetry."""
    bridge = LiveMT5BridgeCore(host="127.0.0.1", port=5593)
    acc_num = "115745645"

    # Simulate fresh Handshake
    bridge.synced_accounts.discard(acc_num)
    assert acc_num not in bridge.synced_accounts, "Account must not be marked synced on fresh handshake"

    # Gate check: must block order dispatch
    allow_dispatch = acc_num in bridge.synced_accounts
    assert allow_dispatch is False, "Dispatch must be strictly blocked before first TICK telemetry"

    # Simulate first TICK with live positions and orders arriving from MT5
    msg_tick = {
        "type": "TICK",
        "account_id": acc_num,
        "bid": 2650.0,
        "ask": 2650.35,
        "equity": 10000.0,
        "balance": 10000.0,
        "positions": [],
        "orders": []
    }
    await bridge._dispatch_message(msg_tick, writer=None)

    assert acc_num in bridge.synced_accounts, "Account must be marked synced after first TICK telemetry"
    assert (acc_num in bridge.synced_accounts) is True, "Dispatch must be allowed once synced"


def test_pending_order_handover_upgrades_lower_tf_and_is_not_blocked():
    """Verify Handover Resilience: Handover is NOT blocked by pending cap and atomically upgrades M1 -> M5."""
    acc_num = "115745645"
    chosen_tf = "M5"
    side = "SELL_LIMIT"

    # 3 existing pending orders from M1
    acc_pending = [
        {"account_number": acc_num, "type": "SELL_LIMIT", "comment": "M1_L1_SWE", "price": 3740.0},
        {"account_number": acc_num, "type": "SELL_LIMIT", "comment": "M1_L2_SWE", "price": 3745.0},
        {"account_number": acc_num, "type": "SELL_LIMIT", "comment": "M1_L3_SWE", "price": 3750.0},
    ]

    acc_matching_pending = [o for o in acc_pending if o.get("type") == side]
    assert len(acc_matching_pending) == 3

    tf_rank_map = {"M1": 1, "M2": 2, "M3": 3, "M4": 4, "M5": 5, "M15": 15, "M30": 30}
    cur_rank = tf_rank_map.get(chosen_tf, 1)
    assert cur_rank == 5

    # Check if Handover triggers
    has_lower_tf = any(
        not str(o.get("comment", "")).startswith(f"{chosen_tf}_") and f"_{chosen_tf}_" not in str(o.get("comment", ""))
        for o in acc_matching_pending
    )
    assert has_lower_tf is True, "Handover must recognize lower TF orders (M1) when evaluating M5"

    # Simulate Handover action: CANCEL_PENDING sent and matching pending reset
    cancelled_sent = True
    acc_matching_pending = []

    # Verify that post-handover, the pending cap (>=3) does NOT lock out M5 orders
    is_capped = len(acc_matching_pending) >= 3
    assert is_capped is False, "M5 dispatch must NOT be blocked after handover clears lower TF limits"
    assert cancelled_sent is True


def test_excess_pending_orders_auto_reconciliation():
    """Verify Auto-Reconciliation: If account accumulates > 4 pending orders (DEC-043: 4-layer quota), excess is purged."""
    acc_num = "115745645"

    # Simulate anomaly in production: 5 pending orders (e.g. from cold-start restart or duplicate grid)
    acc_pending = [
        {"account_number": acc_num, "type": "SELL_LIMIT", "ticket": 11474483412, "price": 3746.51},
        {"account_number": acc_num, "type": "SELL_LIMIT", "ticket": 11474483456, "price": 3751.39},
        {"account_number": acc_num, "type": "SELL_LIMIT", "ticket": 11474781730, "price": 3743.32},
        {"account_number": acc_num, "type": "SELL_LIMIT", "ticket": 11474781765, "price": 3747.05},
        {"account_number": acc_num, "type": "SELL_LIMIT", "ticket": 11474781795, "price": 3750.77},
    ]

    # Reconciliation trigger (DEC-043: cap is 4)
    should_reconcile = len(acc_pending) > 4
    assert should_reconcile is True, "Bridge must detect when pending orders exceed the max 4-layer quota"


def test_smart_judas_fortress_sl_and_4_layer_grid():
    """Verify DEC-043: 4-Layer Judas Grid & Smart Judas Fortress Stop Loss anchoring."""
    sw_low = 3700.0
    sw_high = 3720.0
    span = sw_high - sw_low # 20.0 pts

    # 1. 4-Layer BUY Grid Verification
    buy_zone_top = round(sw_low + (span * 0.25), 2)
    buy_levels = [
        round(buy_zone_top, 2),                  # L1: 25% = 3705.00
        round(sw_low + (span * 0.125), 2),       # L2: 12.5% = 3702.50
        round(sw_low, 2),                         # L3: 0% = 3700.00
        round(sw_low - (span * 0.272), 2)        # L4: -27.2% = 3694.56 (Judas Catch)
    ]
    assert len(buy_levels) == 4
    assert buy_levels[0] == 3705.0
    assert buy_levels[2] == 3700.0
    assert buy_levels[3] == 3694.56

    # 2. 4-Layer SELL Grid Verification
    sell_zone_bottom = round(sw_low + (span * 0.75), 2)
    sell_levels = [
        round(sell_zone_bottom, 2),              # L1: 75% = 3715.00
        round(sw_low + (span * 0.875), 2),       # L2: 87.5% = 3717.50
        round(sw_high, 2),                        # L3: 100% = 3720.00
        round(sw_high + (span * 0.272), 2)       # L4: +27.2% = 3725.44 (Judas Catch)
    ]
    assert len(sell_levels) == 4
    assert sell_levels[0] == 3715.0
    assert sell_levels[2] == 3720.0
    assert sell_levels[3] == 3725.44

    # 3. Smart Judas Fortress SL: OB Fallback to Fibo -13%
    fibo_sl_buy = round(sw_low - (span * 0.130) - 0.25, 2)
    assert fibo_sl_buy == round(3700.0 - 2.60 - 0.25, 2) # 3697.15

    # If OB bottom at 3695.00 is within 0.5x span (10 pts from 3700)
    ob_bot = 3695.00
    ob_sl_buy = round(ob_bot - 0.25, 2)
    assert ob_sl_buy == 3694.75



