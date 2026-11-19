"""
Unit tests for PerformanceLedger (DEC-040: Auto Daily & Weekly Performance Ledger).
"""
import pytest
from pathlib import Path
from datetime import datetime, timezone
from src.analytics.performance_ledger import PerformanceLedger


def test_performance_ledger_reconstruct_and_live_update(tmp_path):
    ledger_file = tmp_path / "test_ledger.json"
    ledger = PerformanceLedger(ledger_path=ledger_file)

    # 1. Test trade reconstruction
    sample_trades = [
        {
            "trade_id": "1001",
            "account_number": "115745645",
            "risk_profile": "sweet_spot",
            "pnl": 50.0,
            "entry_time": "2026-11-18T08:00:00+00:00",
            "exit_time": "2026-11-18T08:30:00+00:00"
        },
        {
            "trade_id": "1002",
            "account_number": "115745645",
            "risk_profile": "sweet_spot",
            "pnl": 70.0,
            "entry_time": "2026-11-18T10:00:00+00:00",
            "exit_time": "2026-11-18T10:45:00+00:00"
        },
        {
            "trade_id": "1003",
            "account_number": "115745645",
            "risk_profile": "sweet_spot",
            "pnl": -30.0,
            "entry_time": "2026-11-19T04:00:00+00:00",
            "exit_time": "2026-11-19T04:20:00+00:00"
        },
        {
            "trade_id": "1004",
            "account_number": "115745645",
            "risk_profile": "sweet_spot",
            "pnl": 121.34,
            "entry_time": "2026-11-19T06:00:00+00:00",
            "exit_time": "2026-11-19T06:40:00+00:00"
        }
    ]

    ledger.reconstruct_from_trades(sample_trades)
    ledger.save()

    acc = ledger.data["accounts"]["115745645"]
    assert "daily_history" in acc
    assert "2026-11-18" in acc["daily_history"]
    assert "2026-11-19" in acc["daily_history"]

    # 2026-11-18: 50 + 70 = 120 (Target 1% on $10k is $100 -> Target Hit!)
    day18 = acc["daily_history"]["2026-11-18"]
    assert day18["realized_pnl"] == 120.0
    assert day18["start_balance"] == 10000.0
    assert day18["end_balance"] == 10120.0
    assert day18["target_hit"] is True

    # 2026-11-19: -30 + 121.34 = 91.34
    day19 = acc["daily_history"]["2026-11-19"]
    assert day19["start_balance"] == 10120.0
    assert day19["realized_pnl"] == 91.34
    assert day19["end_balance"] == 10211.34

    # Weekly history
    assert "weekly_history" in acc
    assert len(acc["weekly_history"]) >= 1

    # 2. Test live telemetry ingestion from MT5 TICK
    live_tick = {
        "balance": 10091.34,
        "equity": 10091.34,
        "unrealized": 0.0,
        "daily_start_balance": 10000.0,
        "daily_pnl": 91.34,
        "daily_pnl_pct": 0.91,
        "weekly_start_balance": 9800.0,
        "weekly_pnl": 291.34,
        "weekly_pnl_pct": 2.97,
        "risk_profile": "sweet_spot"
    }

    ledger.update_live_telemetry("115745645", live_tick)
    ledger.save()

    summary = ledger.get_summary_payload()
    acc_summary = summary["accounts"]["115745645"]
    assert acc_summary["live"]["daily_start_balance"] == 10000.0
    assert acc_summary["live"]["daily_pnl"] == 91.34
    assert acc_summary["live"]["weekly_start_balance"] == 9800.0
    assert acc_summary["live"]["weekly_pnl"] == 291.34

    # Verify reloading from disk preserves values
    reloaded_ledger = PerformanceLedger(ledger_path=ledger_file)
    assert reloaded_ledger.data["accounts"]["115745645"]["live"]["daily_pnl"] == 91.34
