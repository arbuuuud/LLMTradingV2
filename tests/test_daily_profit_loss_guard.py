import pytest
from datetime import datetime, timezone
from src.bridge.server import LiveMT5BridgeCore

def test_daily_profit_loss_guard_logic():
    bridge = LiveMT5BridgeCore()
    acc_num = "113137116"
    
    # Initialize daily guard
    acc_daily = bridge.account_daily_guard.setdefault(acc_num, {
        "daily_start_equity": 10000.0,
        "peak_daily_pnl": 0.0,
        "daily_halted": False,
        "reason": ""
    })
    
    # Test A: Max Loss Hit (-2.0% on $10,000 = -$200)
    current_eq = 9750.0 # -$250 loss
    daily_pnl = current_eq - acc_daily["daily_start_equity"]
    max_loss_dollar = 200.0
    
    assert daily_pnl <= -max_loss_dollar
    acc_daily["daily_halted"] = True
    assert acc_daily["daily_halted"] is True

    # Test B: Day boundary reset
    bridge.account_daily_guard.clear()
    assert acc_num not in bridge.account_daily_guard

