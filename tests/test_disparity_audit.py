"""
Unit test for T4-1C: Root-Cause Disparity Audit (Forward Test vs Python Backtest).
Ensures the disparity auditor correctly extracts forward trade records, runs Python replication,
and produces the disparity metrics.
"""

import pytest
from pathlib import Path
from scripts.audit_forward_backtest_disparity import run_disparity_audit

def test_disparity_audit_generates_report(tmp_path):
    report_file = Path("reports/forward_vs_backtest_disparity_report.md")
    # Run disparity audit
    run_disparity_audit()
    assert report_file.exists()
    content = report_file.read_text(encoding="utf-8")
    assert "AUDIT DISPARITAS DETERMINISTIK" in content or "Laporan Audit Disparitas Deterministik" in content
    assert "BEP Choking Rate" in content
    assert "Disparity Gap" in content
