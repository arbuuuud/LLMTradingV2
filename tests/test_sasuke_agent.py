import pytest
from src.agents.sasuke import (
    SasukeSharinganAgent,
    SharinganPerceptionLevel,
    SasukeAction
)
from src.core.types import Direction


def test_sasuke_daily_circuit_breaker():
    sasuke = SasukeSharinganAgent(daily_max_loss_pct=-1.0)
    assert not sasuke.check_daily_circuit_breaker(account_equity=9950.0, starting_equity=10000.0)  # -0.5% (Aman)
    assert sasuke.check_daily_circuit_breaker(account_equity=9890.0, starting_equity=10000.0)   # -1.1% (Terkunci)
    assert sasuke.daily_lockout_active


def test_sasuke_greed_trailing_step():
    sasuke = SasukeSharinganAgent(greed_trailing_enabled=True)
    pos = {
        "ticket": 12345,
        "type": "BUY",
        "entry_price": 2650.0,
        "sl": 2646.5,  # 3.5 pts risk
        "tp": 2660.0
    }
    # Current price running 2.1R (+7.35 pts -> 2657.35)
    current_candle = {"close": 2657.35, "high": 2657.5, "low": 2657.0, "open": 2657.1}
    verdict = sasuke.evaluate_position_with_sharingan(
        pos=pos,
        current_candle=current_candle,
        recent_m1_candles=[],
        account_equity=10070.0,
        initial_balance=10000.0
    )
    assert verdict.action == SasukeAction.GREED_TRAILING_STEP
    assert verdict.target_sl > pos["entry_price"]  # Mengunci profit positif


def test_sasuke_reversal_cognition_evening_star():
    sasuke = SasukeSharinganAgent(reversal_cognition_enabled=True)
    pos = {
        "ticket": 67890,
        "type": "BUY",
        "entry_price": 2650.0,
        "sl": 2647.0,  # 3.0 pts risk
        "tp": 2660.0
    }
    # Running 1.2R, tapi muncul Evening Star di pucuk
    c1 = {"time": 100, "open": 2652.0, "high": 2654.0, "low": 2651.8, "close": 2653.8}
    c2 = {"time": 160, "open": 2653.8, "high": 2654.5, "low": 2653.5, "close": 2653.9}  # Small doji star
    c3 = {"time": 220, "open": 2653.9, "high": 2654.0, "low": 2651.5, "close": 2651.6}  # Heavy drop
    current_candle = c3

    verdict = sasuke.evaluate_position_with_sharingan(
        pos=pos,
        current_candle=current_candle,
        recent_m1_candles=[c1, c2, c3],
        account_equity=10030.0,
        initial_balance=10000.0
    )
    assert verdict.action == SasukeAction.FORCE_TP_REVERSAL
    assert verdict.reversal_signal is not None
    assert verdict.reversal_signal.pattern == "EVENING_STAR"
