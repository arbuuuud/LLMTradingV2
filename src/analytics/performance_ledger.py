"""
Performance & Objective Ledger Module (DEC-040: Auto Daily & Weekly Performance Ledger).
Tracks baseline starting balances, daily realized PnL, weekly realized PnL,
and historical achievement logs across trading days and weeks.
"""
from typing import Dict, Any, List, Optional
import os
import json
import logging
from pathlib import Path
from datetime import datetime, timezone

logger = logging.getLogger("performance_ledger")

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DATA_DIR = PROJECT_ROOT / "data"
LEDGER_FILE = DATA_DIR / "performance_ledger.json"
FORWARD_TRADES_VPS = DATA_DIR / "forward_trades_vps.json"
FORWARD_TRADES_LOCAL = DATA_DIR / "forward_trades_local.json"
FORWARD_TRADES_PULLED = DATA_DIR / "forward_trades_vps_pulled.json"
ACCOUNTS_CONFIG = PROJECT_ROOT / "configs" / "accounts.yaml"


class PerformanceLedger:
    """
    Manages daily and weekly PnL tracking, starting balances,
    and historical trade reconciliation.
    """

    def __init__(self, ledger_path: Path = LEDGER_FILE):
        self.ledger_path = ledger_path
        self.ledger_path.parent.mkdir(parents=True, exist_ok=True)
        self.data: Dict[str, Any] = self._load()

    def _load(self) -> Dict[str, Any]:
        if self.ledger_path.exists():
            try:
                return json.loads(self.ledger_path.read_text(encoding="utf-8"))
            except Exception as e:
                logger.warning(f"Failed to read existing ledger file: {e}. Reinitializing.")
        return {
            "version": "1.0",
            "accounts": {},
            "updated_at": datetime.now(timezone.utc).isoformat()
        }

    def save(self) -> None:
        try:
            self.data["updated_at"] = datetime.now(timezone.utc).isoformat()
            temp_path = self.ledger_path.with_suffix(".tmp")
            temp_path.write_text(json.dumps(self.data, indent=2), encoding="utf-8")
            temp_path.replace(self.ledger_path)
        except Exception as e:
            logger.error(f"Failed to save performance ledger: {e}")

    def update_live_telemetry(self, acc_id: str, tick: Dict[str, Any]) -> None:
        """
        Ingests high-frequency tick telemetry from MT5 containing
        broker-calculated daily and weekly performance metrics.
        """
        acc_str = str(acc_id)
        if "accounts" not in self.data:
            self.data["accounts"] = {}

        acc_node = self.data["accounts"].setdefault(acc_str, {
            "account_number": acc_str,
            "risk_profile": tick.get("risk_profile", "unknown"),
            "live": {},
            "daily_history": {},
            "weekly_history": {}
        })

        # Extract values
        balance = float(tick.get("balance", acc_node.get("live", {}).get("balance", 10000.0)))
        equity = float(tick.get("equity", acc_node.get("live", {}).get("equity", balance)))
        unrealized = float(tick.get("unrealized", 0.0))

        daily_pnl = float(tick.get("daily_pnl", 0.0))
        daily_start_bal = float(tick.get("daily_start_balance", max(1.0, balance - daily_pnl)))
        daily_pnl_pct = float(tick.get("daily_pnl_pct", (daily_pnl / max(1.0, daily_start_bal)) * 100.0))

        weekly_pnl = float(tick.get("weekly_pnl", 0.0))
        weekly_start_bal = float(tick.get("weekly_start_balance", max(1.0, balance - weekly_pnl)))
        weekly_pnl_pct = float(tick.get("weekly_pnl_pct", (weekly_pnl / max(1.0, weekly_start_bal)) * 100.0))

        now_utc = datetime.now(timezone.utc)
        today_str = now_utc.strftime("%Y-%m-%d")
        week_num = now_utc.isocalendar()[1]
        week_id = f"{now_utc.year}-W{week_num:02d}"

        daily_target_hit = daily_pnl_pct >= 1.0
        weekly_target_hit = weekly_pnl_pct >= 5.0

        # Update Live Node
        acc_node["live"] = {
            "balance": round(balance, 2),
            "equity": round(equity, 2),
            "unrealized": round(unrealized, 2),
            "daily_start_balance": round(daily_start_bal, 2),
            "daily_pnl": round(daily_pnl, 2),
            "daily_pnl_pct": round(daily_pnl_pct, 2),
            "daily_target_hit": daily_target_hit,
            "weekly_start_balance": round(weekly_start_bal, 2),
            "weekly_pnl": round(weekly_pnl, 2),
            "weekly_pnl_pct": round(weekly_pnl_pct, 2),
            "weekly_target_hit": weekly_target_hit,
            "updated_at": now_utc.isoformat()
        }

        # Update Today in daily_history
        today_entry = acc_node["daily_history"].setdefault(today_str, {
            "date": today_str,
            "day_name": now_utc.strftime("%A"),
            "account_number": acc_str,
            "start_balance": round(daily_start_bal, 2),
            "end_balance": round(balance, 2),
            "realized_pnl": round(daily_pnl, 2),
            "pnl_pct": round(daily_pnl_pct, 2),
            "target_pct": 1.0,
            "target_hit": daily_target_hit,
            "status": "🎯 1% SECURED" if daily_target_hit else "🏹 HUNTING",
            "trades": 0,
            "wins": 0,
            "losses": 0,
            "win_rate": 0.0
        })
        today_entry["start_balance"] = round(daily_start_bal, 2)
        today_entry["end_balance"] = round(balance, 2)
        today_entry["realized_pnl"] = round(daily_pnl, 2)
        today_entry["pnl_pct"] = round(daily_pnl_pct, 2)
        today_entry["target_hit"] = daily_target_hit
        today_entry["status"] = "🎯 1% SECURED" if daily_target_hit else "🏹 HUNTING"

        # Update Current Week in weekly_history
        week_entry = acc_node["weekly_history"].setdefault(week_id, {
            "week_id": week_id,
            "account_number": acc_str,
            "start_balance": round(weekly_start_bal, 2),
            "end_balance": round(balance, 2),
            "realized_pnl": round(weekly_pnl, 2),
            "pnl_pct": round(weekly_pnl_pct, 2),
            "target_pct": 5.0,
            "target_hit": weekly_target_hit,
            "status": "🏆 5% SECURED" if weekly_target_hit else "📈 IN PROGRESS"
        })
        week_entry["start_balance"] = round(weekly_start_bal, 2)
        week_entry["end_balance"] = round(balance, 2)
        week_entry["realized_pnl"] = round(weekly_pnl, 2)
        week_entry["pnl_pct"] = round(weekly_pnl_pct, 2)
        week_entry["target_hit"] = weekly_target_hit
        week_entry["status"] = "🏆 5% SECURED" if weekly_target_hit else "📈 IN PROGRESS"

    def reconstruct_from_trades(self, trades: List[Dict[str, Any]]) -> None:
        """
        Reconstructs past historical daily and weekly ledger rows from closed trade records.
        """
        if not trades:
            return

        # Sort trades by exit time
        sorted_trades = sorted(
            [t for t in trades if t.get("exit_time")],
            key=lambda x: str(x.get("exit_time", ""))
        )

        # Group by account and date
        acc_trades: Dict[str, Dict[str, List[Dict[str, Any]]]] = {}
        for t in sorted_trades:
            acc = str(t.get("account_number") or t.get("account_id") or "default")
            exit_t = str(t.get("exit_time", ""))[:10]
            if not exit_t:
                continue
            if acc not in acc_trades:
                acc_trades[acc] = {}
            if exit_t not in acc_trades[acc]:
                acc_trades[acc][exit_t] = []
            acc_trades[acc][exit_t].append(t)

        if "accounts" not in self.data:
            self.data["accounts"] = {}

        for acc, dates_map in acc_trades.items():
            acc_node = self.data["accounts"].setdefault(acc, {
                "account_number": acc,
                "risk_profile": "unknown",
                "live": {},
                "daily_history": {},
                "weekly_history": {}
            })

            # Reconstruct daily history
            running_balance = None
            for dt_str in sorted(dates_map.keys()):
                d_trades = dates_map[dt_str]
                pnl_sum = round(sum(float(x.get("pnl", 0.0)) for x in d_trades), 2)
                t_count = len(d_trades)
                w_count = sum(1 for x in d_trades if float(x.get("pnl", 0.0)) > 0)
                l_count = sum(1 for x in d_trades if float(x.get("pnl", 0.0)) < 0)
                wr = round((w_count / max(1, t_count)) * 100.0, 1)

                profile = d_trades[0].get("risk_profile", acc_node.get("risk_profile", "unknown"))
                acc_node["risk_profile"] = profile

                # If running balance is not established, infer from initial risk profile or config
                if running_balance is None:
                    # Default nominal baselines
                    nominal_map = {
                        "prop_firm": 100000.0,
                        "sweet_spot": 10000.0,
                        "aggressive": 3000.0,
                        "yolo": 500.0
                    }
                    running_balance = nominal_map.get(profile.lower(), 10000.0)

                start_bal = running_balance
                end_bal = round(start_bal + pnl_sum, 2)
                running_balance = end_bal

                gain_pct = round((pnl_sum / max(1.0, start_bal)) * 100.0, 2)
                target_hit = gain_pct >= 1.0

                try:
                    d_obj = datetime.strptime(dt_str, "%Y-%m-%d")
                    day_name = d_obj.strftime("%A")
                    week_num = d_obj.isocalendar()[1]
                    week_id = f"{d_obj.year}-W{week_num:02d}"
                except Exception:
                    day_name = "Trading Day"
                    week_id = "2026-W47"

                acc_node["daily_history"][dt_str] = {
                    "date": dt_str,
                    "day_name": day_name,
                    "account_number": acc,
                    "risk_profile": profile,
                    "start_balance": round(start_bal, 2),
                    "end_balance": round(end_bal, 2),
                    "realized_pnl": pnl_sum,
                    "pnl_pct": gain_pct,
                    "target_pct": 1.0,
                    "target_hit": target_hit,
                    "status": "🎯 1% SECURED" if target_hit else "COMPLETED",
                    "trades": t_count,
                    "wins": w_count,
                    "losses": l_count,
                    "win_rate": wr,
                    "week_id": week_id
                }

            # Reconstruct weekly history from daily history
            weeks_map: Dict[str, List[Dict[str, Any]]] = {}
            for d_entry in acc_node["daily_history"].values():
                w_id = d_entry.get("week_id", "2026-W47")
                weeks_map.setdefault(w_id, []).append(d_entry)

            for w_id, d_entries in sorted(weeks_map.items()):
                d_sorted = sorted(d_entries, key=lambda x: x["date"])
                w_start_bal = d_sorted[0]["start_balance"]
                w_end_bal = d_sorted[-1]["end_balance"]
                w_pnl = round(sum(x["realized_pnl"] for x in d_sorted), 2)
                w_pct = round((w_pnl / max(1.0, w_start_bal)) * 100.0, 2)
                w_target_hit = w_pct >= 5.0
                days_hit = sum(1 for x in d_sorted if x.get("target_hit", False))

                acc_node["weekly_history"][w_id] = {
                    "week_id": w_id,
                    "start_date": d_sorted[0]["date"],
                    "end_date": d_sorted[-1]["date"],
                    "account_number": acc,
                    "start_balance": round(w_start_bal, 2),
                    "end_balance": round(w_end_bal, 2),
                    "realized_pnl": w_pnl,
                    "pnl_pct": w_pct,
                    "target_pct": 5.0,
                    "target_hit": w_target_hit,
                    "days_target_hit": days_hit,
                    "total_days_active": len(d_sorted),
                    "status": "🏆 5% SECURED" if w_target_hit else ("PROGRESS" if w_pct > 0 else "COMPLETED")
                }

    def get_summary_payload(self, acc_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Builds presentation payload for Web Dashboard.
        """
        accounts_out = {}
        total_today_pnl = 0.0
        total_week_pnl = 0.0

        for a_id, a_data in self.data.get("accounts", {}).items():
            if acc_id and str(a_id) != str(acc_id):
                continue

            live = a_data.get("live", {})
            total_today_pnl += live.get("daily_pnl", 0.0)
            total_week_pnl += live.get("weekly_pnl", 0.0)

            # Sort daily history descending
            d_hist = sorted(
                a_data.get("daily_history", {}).values(),
                key=lambda x: x.get("date", ""),
                reverse=True
            )

            # Sort weekly history descending
            w_hist = sorted(
                a_data.get("weekly_history", {}).values(),
                key=lambda x: x.get("week_id", ""),
                reverse=True
            )

            accounts_out[a_id] = {
                "account_number": a_id,
                "risk_profile": a_data.get("risk_profile", "unknown"),
                "live": live,
                "daily_history": d_hist,
                "weekly_history": w_hist
            }

        return {
            "summary": {
                "today_total_pnl": round(total_today_pnl, 2),
                "week_total_pnl": round(total_week_pnl, 2),
                "active_accounts_count": len(accounts_out)
            },
            "accounts": accounts_out,
            "updated_at": self.data.get("updated_at", datetime.now(timezone.utc).isoformat())
        }


# Global Singleton Helper
_ledger_instance: Optional[PerformanceLedger] = None


def get_performance_ledger() -> PerformanceLedger:
    global _ledger_instance
    if _ledger_instance is None:
        _ledger_instance = PerformanceLedger()
        # Seed with forward trades if ledger has no history yet
        if not _ledger_instance.data.get("accounts"):
            trades = []
            target_p = FORWARD_TRADES_VPS if FORWARD_TRADES_VPS.exists() and FORWARD_TRADES_VPS.stat().st_size > 10 else FORWARD_TRADES_PULLED
            if target_p.exists():
                try:
                    trades = json.loads(target_p.read_text(encoding="utf-8"))
                except Exception:
                    trades = []
            if trades:
                _ledger_instance.reconstruct_from_trades(trades)
                _ledger_instance.save()
    return _ledger_instance
