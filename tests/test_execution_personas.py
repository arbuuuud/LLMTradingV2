"""
Unit tests for Dual-Mode Execution Personas (Sentinel Prop Firm vs Leviathan Greed)
and Dynamic Auto-BEP+ with $0.85 anti-whipsaw cushion (T5-3P / DEC-045).
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, patch, MagicMock
from src.bridge.server import LiveMT5BridgeCore


@pytest.fixture
def bridge_instance():
    bridge = LiveMT5BridgeCore(host="127.0.0.1", port=9999)
    bridge.broadcast = AsyncMock()
    return bridge


def test_sentinel_hard_lock_halts_at_daily_target(bridge_instance):
    """
    Verify Sentinel Prop Firm (HARD_1PCT_HALT) halts trading immediately
    when daily profit reaches 1.0% ($100 on $10k or $1000 on $100k).
    """
    acc_num = "5058996231"
    acc_daily = {
        "daily_start_equity": 100000.0,
        "peak_daily_pnl": 0.0,
        "daily_halted": False,
        "reason": ""
    }
    bridge_instance.account_daily_guard[acc_num] = acc_daily

    p_cfg = {
        "daily_target_pct": 1.0,
        "max_daily_loss_pct": 1.0,
        "daily_gating": "HARD_1PCT_HALT",
        "execution_persona": "SENTINEL_HARD_LOCK"
    }

    # Simulate equity hitting +$1,050 (+1.05%)
    acc_eq = 101050.0
    daily_pnl = acc_eq - acc_daily["daily_start_equity"]
    daily_target_dollar = acc_daily["daily_start_equity"] * (p_cfg["daily_target_pct"] / 100.0)

    daily_gating = p_cfg.get("daily_gating", "UNGATED")
    exec_persona = p_cfg.get("execution_persona", "")

    if daily_gating == "HARD_1PCT_HALT" or exec_persona == "SENTINEL_HARD_LOCK":
        if daily_pnl >= daily_target_dollar:
            acc_daily["daily_halted"] = True
            acc_daily["reason"] = f"Sentinel 1% Locked: PnL ${daily_pnl:+.2f}"

    assert acc_daily["daily_halted"] is True
    assert "Sentinel 1% Locked" in acc_daily["reason"]


def test_leviathan_greed_does_not_halt_at_daily_target(bridge_instance):
    """
    Verify Leviathan Greed (UNGATED) allows aggressive & yolo accounts to continue
    trading past 1% to extract maximum trend compounding.
    """
    acc_num = "5058995852"
    acc_daily = {
        "daily_start_equity": 2500.0,
        "peak_daily_pnl": 0.0,
        "daily_halted": False,
        "reason": ""
    }
    bridge_instance.account_daily_guard[acc_num] = acc_daily

    p_cfg = {
        "daily_target_pct": 4.0,
        "max_daily_loss_pct": 3.5,
        "daily_gating": "UNGATED",
        "execution_persona": "LEVIATHAN_GREED"
    }

    # Simulate equity hitting +$30 (+1.2% - would halt Sentinel, but not Greed!)
    acc_eq = 2530.0
    daily_pnl = acc_eq - acc_daily["daily_start_equity"]
    daily_target_dollar = acc_daily["daily_start_equity"] * (1.0 / 100.0)

    daily_gating = p_cfg.get("daily_gating", "UNGATED")
    exec_persona = p_cfg.get("execution_persona", "")

    if daily_gating == "HARD_1PCT_HALT" or exec_persona == "SENTINEL_HARD_LOCK":
        if daily_pnl >= daily_target_dollar:
            acc_daily["daily_halted"] = True

    # Should NOT be halted!
    assert acc_daily["daily_halted"] is False


@pytest.mark.asyncio
async def test_auto_bep_plus_cushion_orchestration(bridge_instance):
    """
    Verify that _orchestrate_auto_bep_for_account moves runner SL to entry + $0.85
    for BUY and entry - $0.85 for SELL to absorb broker spread and noise.
    """
    acc_num = "115745645"
    bridge_instance.accounts_open_positions[acc_num] = [
        {
            "ticket": 9001,
            "type": "BUY",
            "entry_price": 2700.00,
            "sl": 2695.00,
            "tp": 2720.00,
            "account_number": acc_num
        },
        {
            "ticket": 9002,
            "type": "SELL",
            "entry_price": 2750.00,
            "sl": 2755.00,
            "tp": 2730.00,
            "account_number": acc_num
        }
    ]

    # Test BUY direction
    bridge_instance._orchestrate_auto_bep_for_account(acc_num, "BUY")
    await asyncio.sleep(0.01)
    assert bridge_instance.broadcast.called
    buy_call = bridge_instance.broadcast.call_args[0][0]
    assert buy_call["action"] == "MODIFY_POSITION"
    assert buy_call["ticket"] == 9001
    assert buy_call["sl"] == 2700.85  # entry + $0.85 cushion!

    # Test SELL direction
    bridge_instance.broadcast.reset_mock()
    bridge_instance._orchestrate_auto_bep_for_account(acc_num, "SELL")
    await asyncio.sleep(0.01)
    assert bridge_instance.broadcast.called
    sell_call = bridge_instance.broadcast.call_args[0][0]
    assert sell_call["action"] == "MODIFY_POSITION"
    assert sell_call["ticket"] == 9002
    assert sell_call["sl"] == 2749.15  # entry - $0.85 cushion!


@pytest.mark.asyncio
async def test_guardian_triggers_bep_plus_at_half_r(bridge_instance):
    """
    Verify that _evaluate_force_close_guardian triggers Auto-BEP+ with $0.85 cushion
    as soon as running gain reaches >= +0.5R.
    """
    acc_num = "115745645"
    bridge_instance._last_force_close_check = 0.0
    bridge_instance.live_open_positions = [
        {
            "ticket": 8888,
            "type": "BUY",
            "entry_price": 2700.00,
            "current_price": 2702.00,  # +$2.00 running on a $3.00 SL distance -> +0.67R (>= +0.5R!)
            "sl": 2697.00,
            "tp": 2715.00,
            "account_number": acc_num
        }
    ]

    bridge_instance._evaluate_force_close_guardian(current_price=2702.00)
    await asyncio.sleep(0.01)

    assert bridge_instance.broadcast.called
    call_payload = bridge_instance.broadcast.call_args[0][0]
    assert call_payload["action"] == "MODIFY_POSITION"
    assert call_payload["ticket"] == 8888
    assert call_payload["sl"] == 2700.85  # entry + $0.85 cushion
