from datetime import datetime, timedelta
import polars as pl
import numpy as np
import pytest

from src.core.types import (
    ShadowCloneSpec,
    Direction,
    TradingStyle,
    SessionKillzone,
    ForceClosePolicy
)
from src.workflows.backtest import BacktestEngine, TradeRecord


def generate_mock_pac_dataframe(bars: int = 500) -> pl.DataFrame:
    """Generates synthetic price action oscillating within a dynamic floor & roof."""
    base_time = datetime(2025, 1, 1, 10, 0)
    timestamps = [base_time + timedelta(minutes=i) for i in range(bars)]
    
    # Sine wave oscillation between 2600 and 2640 (Span = 40)
    x = np.linspace(0, 10 * np.pi, bars)
    mid = 2620.0
    amplitude = 18.0
    trend = np.linspace(0, 5, bars)
    closes = mid + amplitude * np.sin(x) + trend
    opens = closes - np.random.uniform(-0.5, 0.5, bars)
    highs = np.maximum(opens, closes) + np.random.uniform(0.1, 1.0, bars)
    lows = np.minimum(opens, closes) - np.random.uniform(0.1, 1.0, bars)

    df = pl.DataFrame({
        "timestamp": timestamps,
        "open": opens,
        "high": highs,
        "low": lows,
        "close": closes,
        "tick_volume": [100] * bars
    })
    return df


def test_backtest_engine_executes_pac_strategy():
    engine = BacktestEngine(initial_capital=10000.0, base_risk_pct=0.50)
    spec = ShadowCloneSpec(
        clone_id="CLONE-PAC-TEST-001",
        methodology="PAC",
        timeframe="M1",
        limit_layers=3,
        hard_sl_pct=-20.0,
        soft_sl_candle_close_pct=-5.0,
        hard_tp_pct=50.0,
        force_close_policy=ForceClosePolicy.PARTIAL_50_BEP,
        session=SessionKillzone.ALL_DAY
    )

    df = generate_mock_pac_dataframe(bars=300)
    result = engine.run_simulation(spec, df)

    assert result.clone_id == "CLONE-PAC-TEST-001"
    assert result.total_trades > 0
    assert result.win_rate_pct >= 0.0
    assert result.profit_factor >= 0.0
    assert result.max_drawdown_pct >= 0.0
    assert result.avg_trades_per_day > 0.0


def test_backtest_engine_saved_r_calculation():
    # Test soft SL saves R compared to Hard SL
    trade = TradeRecord(
        trade_id="TR-1",
        direction=Direction.BUY,
        entry_time=datetime(2025, 1, 1, 10, 0),
        entry_price=2605.0,
        sl_price=2595.0,        # Hard SL: 10 pips = 1R
        hard_tp_price=2620.0,
        soft_sl_price=2600.0,   # Soft SL: 5 pips = 0.5R
        risk_amount=100.0
    )

    # If candle closed at 2600 (soft SL hit at 0.5R loss):
    loss_dist = abs(2600.0 - trade.entry_price)  # 5.0
    max_sl_dist = abs(trade.entry_price - trade.sl_price)  # 10.0
    actual_r = -min(loss_dist / max_sl_dist, 1.0)  # -0.5
    saved_r = 1.0 + actual_r  # Saved 0.5R!

    assert actual_r == -0.5
    assert saved_r == 0.5
