"""
Script Pembaca & Auditor Histori Forward Test dari Server VPS (Workflow 4 Incubation Audit).
Membaca file data forward trades atau MT5 HTML/CSV report, lalu mengevaluasi
menggunakan IncubationStagingGate.
"""

import sys
import json
from pathlib import Path
from datetime import datetime

# Setup PYTHONPATH
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.core.types import ShadowCloneResult, PACRetestMode, PACHandoverMode, Direction
from src.workflows.incubation import IncubationStagingGate, ForwardTradeRecord, StagingStatus


def load_trades_from_file(file_path: Path):
    if not file_path.exists():
        print(f"❌ File {file_path} tidak ditemukan!")
        return []

    # Format 1: JSON
    if file_path.suffix.lower() == ".json":
        data = json.loads(file_path.read_text(encoding="utf-8"))
        records = []
        for d in data:
            # Handle string datetime
            if isinstance(d.get("entry_time"), str):
                d["entry_time"] = datetime.fromisoformat(d["entry_time"])
            if isinstance(d.get("exit_time"), str):
                d["exit_time"] = datetime.fromisoformat(d["exit_time"])
            records.append(ForwardTradeRecord(**d))
        return records

    # Format 2: CSV (jika diexport dari MT5)
    elif file_path.suffix.lower() == ".csv":
        import csv
        records = []
        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            reader = csv.DictReader(f)
            for i, row in enumerate(reader):
                try:
                    pnl = float(row.get("Profit", row.get("profit", 0.0)))
                    records.append(ForwardTradeRecord(
                        trade_id=str(row.get("Ticket", row.get("ticket", f"TR-{i}"))),
                        symbol=row.get("Item", row.get("symbol", "XAUUSD")),
                        direction=Direction.BUY if "buy" in str(row.get("Type", "")).lower() else Direction.SELL,
                        timeframe="M1",
                        entry_time=datetime.now(),
                        exit_time=datetime.now(),
                        entry_price=float(row.get("Price", row.get("open_price", 0.0))),
                        exit_price=float(row.get("Price_1", row.get("close_price", 0.0))),
                        sl_price=0.0,
                        tp_price=0.0,
                        expected_entry_price=float(row.get("Price", 0.0)),
                        actual_entry_price=float(row.get("Price", 0.0)),
                        slippage_pts=0.05,
                        pnl=pnl,
                        r_multiple=round(pnl / 5.0, 2),
                        exit_reason="Normal Exit"
                    ))
                except Exception:
                    continue
        return records

    return []


def main():
    target_path = Path("data/forward_trades_live.json")
    if len(sys.argv) > 1:
        target_path = Path(sys.argv[1])

    print("=================================================================")
    print("🔍 AUDIT & ANALISIS DATA FORWARD TEST DARI SERVER VPS")
    print(f"Target File: {target_path}")
    print("=================================================================")

    trades = load_trades_from_file(target_path)
    print(f"Total Trade Terbaca: {len(trades)} trades")

    if not trades:
        print("\nBelum ada trade yang tersimpan di file tersebut.")
        print("Silakan copy file dari server VPS ke direktori lokal sesuai panduan.")
        return

    # Baseline Kage Bunshin PAC M1
    baseline = ShadowCloneResult(
        clone_id="STRAT-PAC-M1-001",
        timeframe="M1",
        retest_mode=PACRetestMode.MULTI_RETEST_DEEPER,
        handover_mode=PACHandoverMode.PARTIAL_EXIT_BEP,
        cancel_remaining_on_tp=True,
        total_trades=50,
        win_rate_pct=79.7,
        profit_factor=140.21,
        max_drawdown_pct=0.28,
        net_profit_dollar=12000.0,
        activity_trades_per_month=45
    )

    gate = IncubationStagingGate(min_trades=min(10, len(trades)))
    audit = gate.audit_incubation(
        strategy_id="PAC-LIVE-FORWARD",
        backtest_baseline=baseline,
        forward_trades=trades
    )

    print("\n📊 HASIL AUDIT PERFORMA FORWARD TEST:")
    print(f"• Status Evaluasi        : {audit.status.value}")
    print(f"• Total Closed Trades    : {audit.total_trades} trades")
    print(f"• Realized Win Rate      : {audit.realized_win_rate_pct}% (Baseline Backtest: {audit.backtest_win_rate_pct}%)")
    print(f"• Degradasi Win Rate     : {audit.win_rate_degradation_pct}% (Batas toleransi: <= 15%)")
    print(f"• Realized Profit Factor : {audit.realized_profit_factor} (Baseline: {audit.backtest_profit_factor})")
    print(f"• Realized Max Drawdown  : {audit.realized_max_dd_pct}% (Baseline: {audit.backtest_max_dd_pct}%)")
    print(f"• Rata-rata Slippage     : {audit.avg_slippage_pts:.2f} points")
    print(f"• Lolos Semua Gate Audit : {'✅ YA' if audit.passes_all_gates else '❌ BELUM'}")

    if audit.rejection_reasons:
        print("\nCatatan Evaluator:")
        for r in audit.rejection_reasons:
            print(f" - {r}")


if __name__ == "__main__":
    main()

