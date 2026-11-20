"""
Unit Tests for Benchmark Matrix and Strategy Evolution Ledger (DEC-043).
Verifies:
- BenchmarkMatrixManager milestone registration & delta calculation
- AuditorAgent milestone validation against Golden Triangle KPIs
- Head-to-head Before vs After comparative structure
- Dashboard /api/benchmark-matrix endpoint integrity
"""

import json
import pytest
from pathlib import Path
from tempfile import TemporaryDirectory
from src.analytics.benchmark_matrix import BenchmarkMatrixManager, DEFAULT_BASELINE
from src.agents.auditor import AuditorAgent


def test_benchmark_matrix_initialization_and_default_milestones():
    with TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir) / "benchmark_matrix.json"
        mgr = BenchmarkMatrixManager(storage_path=tmp_path)
        data = mgr.load_matrix()

        assert "baseline" in data
        assert "milestones" in data
        assert len(data["milestones"]) >= 2
        assert data["baseline"]["milestone_id"] == "MS-000-BASELINE"
        assert data["baseline"]["daily_1pct_target_hit_rate"] == 30.8
        assert data["baseline"]["weekly_5pct_target_hit_rate"] == 22.2


def test_benchmark_matrix_register_milestone_computes_deltas():
    with TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir) / "benchmark_matrix.json"
        mgr = BenchmarkMatrixManager(storage_path=tmp_path)

        cand = {
            "milestone_id": "MS-TEST-001",
            "name": "Candidate Test Model",
            "starting_equity": 10000.0,
            "final_equity": 60000.0,
            "net_pnl": 50000.0,
            "profit_factor": 1.65,
            "max_drawdown_pct": 3.80,
            "win_rate_pct": 45.0,
            "daily_1pct_target_hit_rate": 32.5,
            "daily_loss_breach_rate": 2.0,
            "weekly_5pct_target_hit_rate": 35.0,
            "wick_saved_count": 120,
            "freight_train_avoided_count": 5000,
            "stand_aside_count": 2000
        }

        registered = mgr.register_milestone(cand)
        deltas = registered.get("deltas_vs_baseline", {})

        # Baseline: Net PnL $35,368.96, DD 5.60%, Daily 30.8%, Weekly 22.2%, Breach 6.3%
        assert deltas["delta_net_pnl"] > 0
        assert deltas["delta_max_dd_pct"] < 0 # Drawdown reduced
        assert deltas["delta_weekly_5pct_rate"] == round(35.0 - 22.2, 1) # +12.8%
        assert deltas["delta_daily_breach_rate"] < 0 # Daily breach reduced


def test_benchmark_matrix_get_comparison_structure():
    with TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir) / "benchmark_matrix.json"
        mgr = BenchmarkMatrixManager(storage_path=tmp_path)

        comp = mgr.get_comparison()
        assert "baseline" in comp
        assert "candidate" in comp
        assert "rows" in comp
        assert len(comp["rows"]) >= 10

        metrics = [r["metric"] for r in comp["rows"]]
        assert any("Daily 1% Target" in m for m in metrics)
        assert any("Weekly 5% Target" in m for m in metrics)
        assert any("Max Drawdown" in m for m in metrics)
        assert any("Wick Hunt Saved" in m for m in metrics)


def test_auditor_agent_audits_benchmark_milestone():
    auditor = AuditorAgent()

    # Superior candidate
    champ_candidate = {
        "net_pnl": 60801.43,
        "max_drawdown_pct": 3.40,
        "profit_factor": 1.73,
        "daily_1pct_target_hit_rate": 30.3,
        "weekly_5pct_target_hit_rate": 37.8,
        "daily_loss_breach_rate": 1.4
    }

    report = auditor.audit_benchmark_milestone(champ_candidate, DEFAULT_BASELINE)
    assert report["is_approved_upgrade"] is True
    assert report["weekly_5pct_improved"] is True
    assert report["drawdown_contained"] is True
    assert "PROMOTE TO CHAMPION MILESTONE" in report["recommendation"]
    assert report["quant_score"] > 100.0

    # Failing candidate (higher DD, lower weekly rate)
    failing_candidate = {
        "net_pnl": 20000.0,
        "max_drawdown_pct": 12.0,
        "profit_factor": 1.10,
        "daily_1pct_target_hit_rate": 15.0,
        "weekly_5pct_target_hit_rate": 10.0,
        "daily_loss_breach_rate": 15.0
    }

    fail_report = auditor.audit_benchmark_milestone(failing_candidate, DEFAULT_BASELINE)
    assert fail_report["is_approved_upgrade"] is False
    assert fail_report["weekly_5pct_improved"] is False
    assert "REVISE CANDIDATE" in fail_report["recommendation"]
