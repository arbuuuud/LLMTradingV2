"""
Multi-Environment Forward Test Auditor & Comparative Learning Engine.
Membaca dan membandingkan performa Forward Test dari:
1. Akun Lokal (data/forward_trades_local.json)
2. Akun Production VPS (data/forward_trades_vps.json)
3. Komparasi Head-to-Head & Sintesis Pembelajaran Kuantitatif
"""

import sys
import json
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any, Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.core.types import ShadowCloneResult, PACRetestMode, PACHandoverMode, Direction
from src.workflows.incubation import IncubationStagingGate, ForwardTradeRecord, StagingStatus


def load_env_trades(file_path: Path) -> List[ForwardTradeRecord]:
    if not file_path.exists():
        return []
    try:
        data = json.loads(file_path.read_text(encoding="utf-8"))
        records = []
        for d in data:
            if isinstance(d.get("entry_time"), str):
                d["entry_time"] = datetime.fromisoformat(d["entry_time"])
            if isinstance(d.get("exit_time"), str):
                d["exit_time"] = datetime.fromisoformat(d["exit_time"])
            records.append(ForwardTradeRecord(**d))
        return records
    except Exception as e:
        print(f"⚠️ Error parsing {file_path.name}: {e}")
        return []


def format_stats(trades: List[ForwardTradeRecord], env_name: str) -> Dict[str, Any]:
    total = len(trades)
    if total == 0:
        return {
            "env": env_name,
            "total": 0,
            "win_rate": 0.0,
            "profit_factor": 0.0,
            "net_pnl": 0.0,
            "max_dd_pct": 0.0,
            "avg_slippage": 0.0,
            "buys": 0,
            "sells": 0
        }

    wins = [t for t in trades if t.pnl > 0.0]
    losses = [t for t in trades if t.pnl < 0.0]
    buys = len([t for t in trades if t.direction == Direction.BUY])
    sells = len([t for t in trades if t.direction == Direction.SELL])

    gross_profit = sum(t.pnl for t in wins)
    gross_loss = abs(sum(t.pnl for t in losses))
    net_pnl = sum(t.pnl for t in trades)
    wr = (len(wins) / total) * 100.0 if total > 0 else 0.0
    pf = (gross_profit / max(1.0, gross_loss)) if gross_loss > 0 else (gross_profit if gross_profit > 0 else 0.0)

    # Max Drawdown
    bal = 10000.0
    peak = bal
    max_dd = 0.0
    for t in trades:
        bal += t.pnl
        if bal > peak:
            peak = bal
        dd = peak - bal
        if dd > max_dd:
            max_dd = dd
    max_dd_pct = (max_dd / peak) * 100.0 if peak > 0 else 0.0

    avg_slip = sum(t.slippage_pts for t in trades) / total if total > 0 else 0.0

    return {
        "env": env_name,
        "total": total,
        "win_rate": round(wr, 1),
        "profit_factor": round(pf, 2),
        "net_pnl": round(net_pnl, 2),
        "max_dd_pct": round(max_dd_pct, 2),
        "avg_slippage": round(avg_slip, 3),
        "buys": buys,
        "sells": sells
    }


def main():
    path_local = PROJECT_ROOT / "data" / "forward_trades_local.json"
    path_vps = PROJECT_ROOT / "data" / "forward_trades_vps.json"
    path_legacy = PROJECT_ROOT / "data" / "forward_trades_live.json"

    # Fallback jika belum direname
    trades_local = load_env_trades(path_local)
    if not trades_local and path_legacy.exists():
        trades_local = load_env_trades(path_legacy)

    trades_vps = load_env_trades(path_vps)

    print("==========================================================================================")
    print("🔬 COMPARATIVE FORWARD TEST AUDITOR: LOCAL ($1,000) VS PRODUCTION VPS ($10,000)")
    print("==========================================================================================")
    print(f"📁 Local File : {path_local.name} -> {len(trades_local)} trades")
    print(f"📁 VPS File   : {path_vps.name} -> {len(trades_vps)} trades")
    print("------------------------------------------------------------------------------------------")

    stat_loc = format_stats(trades_local, "LOCAL (Mac)")
    stat_vps = format_stats(trades_vps, "PRODUCTION (VPS)")

    print(f"{'METRIK EVALUASI':<30} | {'LOCAL MAC':<20} | {'PRODUCTION VPS':<20}")
    print("-" * 76)
    print(f"{'Total Closed Trades':<30} | {stat_loc['total']:<20} | {stat_vps['total']:<20}")
    print(f"{'Win Rate (%)':<30} | {str(stat_loc['win_rate']) + '%':<20} | {str(stat_vps['win_rate']) + '%':<20}")
    print(f"{'Profit Factor':<30} | {stat_loc['profit_factor']:<20} | {stat_vps['profit_factor']:<20}")
    print(f"{'Net Realized PnL ($)':<30} | {'$' + str(stat_loc['net_pnl']):<20} | {'$' + str(stat_vps['net_pnl']):<20}")
    print(f"{'Max Drawdown (%)':<30} | {str(stat_loc['max_dd_pct']) + '%':<20} | {str(stat_vps['max_dd_pct']) + '%':<20}")
    print(f"{'Average Slippage (pts)':<30} | {stat_loc['avg_slippage']:<20} | {stat_vps['avg_slippage']:<20}")
    print(f"{'Direction Split (Buy/Sell)':<30} | {str(stat_loc['buys']) + 'B / ' + str(stat_loc['sells']) + 'S':<20} | {str(stat_vps['buys']) + 'B / ' + str(stat_vps['sells']) + 'S':<20}")
    print("==========================================================================================")

    # Sintesis Pembelajaran Kuantitatif
    combined_trades = trades_local + trades_vps
    print("\n🧠 SINTESIS PEMBELAJARAN KUANTITATIF (DUAL-ENVIRONMENT FEEDBACK):")
    if len(combined_trades) == 0:
        print("ℹ️ Belum ada closed trade yang terkumpul di kedua environment.")
        print("  • Pastikan file dari VPS disimpan dengan nama: data/forward_trades_vps.json")
        print("  • Data lokal tersimpan di: data/forward_trades_local.json")
    else:
        print(f"• Total Data Tergabung: {len(combined_trades)} / 50 Target Kelulusan ({(len(combined_trades)/50)*100:.1f}%)")
        stat_all = format_stats(combined_trades, "COMBINED")
        print(f"• Combined Win Rate   : {stat_all['win_rate']}%")
        print(f"• Combined Profit Fac : {stat_all['profit_factor']}")
        print(f"• Total Net Profit    : ${stat_all['net_pnl']:,.2f}")


if __name__ == "__main__":
    main()
