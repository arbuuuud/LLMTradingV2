from datetime import datetime
import pytest
from src.core.types import (
    MethodologyInput,
    TradingStyle,
    ShadowCloneSpec,
    ShadowCloneResult,
    SessionKillzone,
    ForceClosePolicy
)
from src.agents.naruto import NarutoAgent
from src.agents.auditor import AuditorAgent


def test_naruto_agent_spawns_multi_dimensional_clones():
    naruto = NarutoAgent()
    methodology = MethodologyInput(
        name="PAC",
        trading_style=TradingStyle.SCALPING,
        daily_profit_target_pct=1.0,
        monthly_profit_target_pct=20.0
    )

    clones = naruto.spawn_clones(methodology)
    assert len(clones) > 0

    # Verify that clones cover multiple timeframes
    tfs = {c.timeframe for c in clones}
    assert "M1" in tfs
    assert "M5" in tfs

    # Verify that 4 dimensions are populated
    wave_regimes = {c.wave_regime for c in clones}
    assert "IMPULSIVE" in wave_regimes
    assert "ALL" in wave_regimes

    poi_types = {tuple(c.poi_types) for c in clones}
    assert len(poi_types) >= 2

    sessions = {c.session for c in clones}
    assert SessionKillzone.ALL_DAY in sessions
    assert SessionKillzone.NY_OVERLAP in sessions


def test_auditor_agent_disqualifies_dormant_clones():
    auditor = AuditorAgent(min_trades_per_month=30)
    spec = ShadowCloneSpec(
        clone_id="CLONE-001",
        methodology="PAC",
        timeframe="M1"
    )

    # Clone A: High win rate but dormant (only 12 trades, 0.4 trades/day) -> Analysis Paralysis!
    clone_dormant = ShadowCloneResult(
        clone_id="CLONE-DORMANT",
        spec=spec,
        total_trades=12,
        win_rate_pct=75.0,
        profit_factor=2.1,
        net_pnl=500.0,
        roi_pct=10.0,
        max_drawdown_pct=3.0,
        avg_trades_per_day=0.4,
        monthly_green_pct=80.0
    )

    # Clone B: Active healthy scalper (150 trades, 5.0 trades/day)
    clone_active = ShadowCloneResult(
        clone_id="CLONE-ACTIVE",
        spec=spec,
        total_trades=150,
        win_rate_pct=52.0,
        profit_factor=1.65,
        net_pnl=2500.0,
        roi_pct=25.0,
        max_drawdown_pct=6.5,
        avg_trades_per_day=5.0,
        monthly_green_pct=75.0
    )

    ranked = auditor.audit_and_rank_clones([clone_dormant, clone_active])

    # Clone dormant must be disqualified despite high win rate
    assert clone_dormant.is_disqualified is True
    assert "DORMANT" in clone_dormant.disqualification_reason

    # Clone active must be the champion
    assert clone_active.is_disqualified is False
    assert ranked[0].clone_id == "CLONE-ACTIVE"


def test_auditor_agent_generates_four_risk_profiles():
    auditor = AuditorAgent()
    spec = ShadowCloneSpec(
        clone_id="CLONE-PAC-M1-CHAMP",
        methodology="PAC",
        timeframe="M1"
    )
    champion = ShadowCloneResult(
        clone_id="CLONE-PAC-M1-CHAMP",
        spec=spec,
        total_trades=200,
        win_rate_pct=55.0,
        profit_factor=1.75,
        net_pnl=3000.0,
        roi_pct=30.0,
        max_drawdown_pct=5.0,
        avg_trades_per_day=6.0,
        monthly_green_pct=85.0
    )

    report = auditor.generate_four_risk_profiles(champion, strategy_id="STRAT-PAC-001")
    assert report.strategy_id == "STRAT-PAC-001"
    assert report.champion_clone_id == "CLONE-PAC-M1-CHAMP"

    # Prop Firm (1.0x Base, 0.50% risk)
    assert report.prop_firm.base_risk_pct == 0.50
    assert report.prop_firm.max_drawdown_pct == 5.0
    assert report.prop_firm.passes_hurdle is True

    # Sweet Spot (1.5x Base, 0.75% risk)
    assert report.sweet_spot.base_risk_pct == 0.75
    assert report.sweet_spot.max_drawdown_pct == 7.5
    assert report.sweet_spot.passes_hurdle is True

    # Aggressive (2.0x Base, 1.00% risk)
    assert report.aggressive.base_risk_pct == 1.00
    assert report.aggressive.max_drawdown_pct == 10.0
    assert report.aggressive.passes_hurdle is True

    # YOLO (4.0x Base, 2.00% risk)
    assert report.yolo.base_risk_pct == 2.00
    assert report.yolo.max_drawdown_pct == 20.0
    assert report.yolo.passes_hurdle is True
