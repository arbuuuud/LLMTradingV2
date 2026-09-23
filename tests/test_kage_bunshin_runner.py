from datetime import datetime
import pytest
from src.core.types import MethodologyInput, TradingStyle
from src.workflows.kage_bunshin import KageBunshinRunner


def test_kage_bunshin_parallel_tournament():
    runner = KageBunshinRunner()
    methodology = MethodologyInput(
        name="PAC",
        trading_style=TradingStyle.SCALPING,
        daily_profit_target_pct=1.0,
        monthly_profit_target_pct=20.0
    )

    # Run tournament over a compact slice
    ranked, report = runner.run_tournament(methodology, intensity="FAST", slice_bars=2000)

    assert len(ranked) > 0
    assert report is not None
    assert report.strategy_id == "STRAT-PAC-001"
    assert report.champion_clone_id != ""

    # Verify 4 risk profiles exist
    assert report.prop_firm.base_risk_pct == 0.50
    assert report.sweet_spot.base_risk_pct == 0.75
    assert report.aggressive.base_risk_pct == 1.00
    assert report.yolo.base_risk_pct == 2.00
