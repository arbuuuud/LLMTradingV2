"""
High-Speed Live Bridge Server & Tactical Radar Generator (Port 5555).
Persis dengan arsitektur live di LLMTrading:
- Menerima REGISTER (Account login, broker, balance, equity)
- Menerima BAR_SYNC (Batch historical bars langsung dari chart MT5)
- Menerima TICK (Real-time live bid/ask/spread & bar aggregation)
- Menulis secara real-time ke reports/radar_state.json untuk Dashboard
"""

import sys
import os
import json
import time
import asyncio
import logging
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional, Set
from collections import defaultdict
import numpy as np

from src.data.adapter import BrokerAdapter, BrokerSpec
from src.engine.force_close import ForceCloseGuardianEngine, ForceCloseAction
from src.agents.sasuke import SasukeSharinganAgent, SharinganPerceptionLevel, SasukeAction
from src.features.structure import detect_swing_points, evaluate_market_structure
from src.features.smc import detect_fvgs, detect_order_blocks, detect_fvg_confluences
from src.features.poi_prioritizer import POIPrioritizer

# Ensure project root in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

REPORTS_DIR = PROJECT_ROOT / "reports"
RADAR_STATE_PATH = REPORTS_DIR / "radar_state.json"
CONFIGS_DIR = PROJECT_ROOT / "configs"
ACCOUNTS_CONFIG_PATH = CONFIGS_DIR / "accounts.yaml"
LOGS_DIR = PROJECT_ROOT / "logs"
BRIDGE_LOG_FILE = LOGS_DIR / "bridge.log"

LOGS_DIR.mkdir(parents=True, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [Bridge]: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(BRIDGE_LOG_FILE, mode="a", encoding="utf-8")
    ]
)
logger = logging.getLogger("BridgeServer")


class LiveMT5BridgeCore:
    def __init__(self, host: str = "127.0.0.1", port: int = 5555):
        self.host = host
        self.port = port
        self.server: Optional[asyncio.Server] = None
        self.active_writers: List[asyncio.StreamWriter] = []
        # Targeted Unicast Socket Routing (DEC-042): acc_number -> set of active writers
        self.account_writers: Dict[str, Set[asyncio.StreamWriter]] = defaultdict(set)
        self.history_m1: List[Dict[str, Any]] = []
        self.latest_tick: Optional[Dict[str, Any]] = None
        self.active_account_id = ""
        self.account_company = ""
        self.balance = 0.0
        self.equity = 0.0
        self._last_radar_save = 0.0

        # Live Order Dispatching & Notification State
        self.last_dispatched_order: Optional[Dict[str, Any]] = None
        self.pending_notifications: List[Dict[str, Any]] = []
        self._last_order_direction = None
        self._last_order_time = 0.0
        self._last_account_persist = 0.0

        # Live Open Positions & Pending Orders Telemetry from MT5 (multi-account keyed)
        self.accounts_open_positions: Dict[str, List[Dict[str, Any]]] = {}
        self.accounts_pending_orders: Dict[str, List[Dict[str, Any]]] = {}
        self.live_open_positions: List[Dict[str, Any]] = []
        self.live_pending_orders: List[Dict[str, Any]] = []
        self.synced_accounts: Set[str] = set()
        self.unrealized_pnl: float = 0.0

        # Callbacks for backward compatibility with test suites
        self.on_handshake_callback = None
        self.on_bar_callback = None
        self.on_tick_callback = None
        self.on_order_status_callback = None

        # Force Close Guardian Agent Engine & Sasuke Sharingan Overseer
        self.force_close_guardian = ForceCloseGuardianEngine()
        self.sasuke_overseer = SasukeSharinganAgent(perception_level=SharinganPerceptionLevel.MANGEKYO, daily_max_loss_pct=-1.0)
        self._last_force_close_check = 0.0

        # Institutional Broker Adapter for Dynamic Lot Sizing
        # Institutional Broker Adapters for Standard and Cent accounts
        self.adapter = BrokerAdapter(BrokerSpec(
            broker_name="MetaQuotes",
            broker_symbol="XAUUSD",
            point=0.01,
            contract_size=100.0,
            min_lot=0.01,
            max_lot=100.0,
            lot_step=0.01
        ))

        self.cent_adapter = BrokerAdapter(BrokerSpec(
            broker_name="PUPrime_Cent",
            broker_symbol="XAUUSD.sc",
            digits=2,
            point=0.01,
            contract_size=100.0,
            min_lot=0.01,
            max_lot=100.0,
            lot_step=0.01,
            lot_decimals=2,
            tick_size=0.01,
            tick_value=1.0  # 1 point move (0.01) on 1.0 lot = 1.00 USC in cent account currency
        ))

        # Dynamic Multi-Session Equity Budgeting & Greed Trailing Overseer (DEC-028 Champion)
        self.current_session_name: str = ""
        self.session_start_equity: float = 10000.0
        self.session_peak_pnl: float = 0.0
        self.session_halted: bool = False
        self.prior_session_pnl: float = 0.0
        self.current_session_day: str = ""
        self.session_status_desc: str = "Active"

        # Per-Account Dynamic Session Budgeting (DEC-030: Independent Account Isolation)
        # acc_id -> {"start_equity": float, "peak_pnl": float, "halted": bool, "prior_pnl": float, "status": str}
        self.account_sessions: Dict[str, Dict[str, Any]] = {}

        # Per-Account Daily Profit Target & Max Loss Tracking (DEC-034 Master Daily Risk Guard)
        # acc_id -> {"daily_start_equity": float, "peak_daily_pnl": float, "daily_halted": bool, "status_desc": str}
        self.account_daily_guard: Dict[str, Dict[str, Any]] = {}

        # Zone Completion & Invalidation State (DEC-035: Single Harvest per Structural Zone)
        self.zone_completed: bool = False
        self.completed_floor: float = 0.0
        self.completed_roof: float = 0.0
        self.completed_direction: str = "NEUTRAL"
        self._current_sw_low: float = 0.0
        self._current_sw_high: float = 0.0

        # Directional Anti-Falling-Knife Cooldown (DEC-031 Champion: CLONE-SESSION-ADAPT-15M)
        # Timestamps until which BUY or SELL orders are paused after consecutive loss
        self.buy_cooldown_until: float = 0.0
        self.sell_cooldown_until: float = 0.0
        self.consecutive_buy_losses: int = 0
        self.consecutive_sell_losses: int = 0

        # Higher Timeframe Directional Trend Bias (Pilar 1: D1, H4, and H1 Trend Gates)
        self.d1_trend: str = "NEUTRAL"
        self.h4_trend: str = "NEUTRAL"
        self.h1_trend: str = "NEUTRAL"

        # Per-Account Order Dispatch Throttle (In-Flight Anti-Spam Guard)
        # acc_id -> timestamp of last limit order dispatch (5.0s cooldown per account)
        self.account_last_order_dispatch: Dict[str, float] = {}

        # Micro Level Depletion Tracking per Timeframe (Pilar 3: Virgin Depth Preservation)
        # tf -> {"spent_layers": set(), "roof": float, "floor": float, "direction": str}
        self.tf_depletion: Dict[str, Dict[str, Any]] = {}

        # Pending Order Birth Times (DEC-043: Order TTL Auto-Purge 30m)
        self.pending_order_birth_times: Dict[str, float] = {}

        # Reflex Active Guard Telemetry (DEC-043)
        self.latest_reflex_guard: Dict[str, Any] = {
            "status": "NOMINAL",
            "is_freight_train": False,
            "is_volatile_spike": False,
            "current_atr14": 0.50,
            "last_bar_range": 0.0,
            "base_atr100": 0.50,
            "atr_ratio": 1.0,
            "velocity_threshold": 0.90
        }

        # Buffer incoming bar batches
        self._pending_sync_bars: List[Dict[str, Any]] = []

    @staticmethod
    def _normalize_account_id(acc_id: Any) -> str:
        """
        Standardizes account IDs so 'ACC-115745645', '115745645', and 115745645 map to identical key.
        """
        if not acc_id:
            return ""
        s = str(acc_id).strip()
        if s.startswith("ACC-"):
            s = s[4:].strip()
        return s

    def _auto_register_account(self, acc_id: str, company: str, server: str, balance: float, equity: float):
        if not acc_id or not str(acc_id).strip():
            return
        if not ACCOUNTS_CONFIG_PATH.exists():
            return
        try:
            import yaml
            with open(ACCOUNTS_CONFIG_PATH, "r", encoding="utf-8") as f:
                cfg = yaml.safe_load(f) or {}

            accounts = cfg.setdefault("accounts", {})
            acc_key = f"ACC-{acc_id.strip()}"

            if acc_key not in accounts:
                # Newly discovered MT5 account -> Default to NONE and INACTIVE for safety
                accounts[acc_key] = {
                    "account_number": str(acc_id),
                    "broker_name": company,
                    "server": server or "MetaQuotes-Demo",
                    "account_type": "DEMO",
                    "risk_profile": "none",
                    "active": False,
                    "status": "CONNECTED",
                    "balance": balance,
                    "equity": equity,
                    "assigned_timeframes": ["M1", "M2", "M3", "M5", "M15"],
                    "updated_at": datetime.now().isoformat()
                }
                logger.info(f"✨ [AUTO-REGISTER] New Live MT5 Account #{acc_id} detected! Profile='none', Active=False. Configure in Dashboard!")
            else:
                # Update existing account's live balance/equity/status without overriding user-set profile or active flag
                accounts[acc_key]["balance"] = balance
                accounts[acc_key]["equity"] = equity
                accounts[acc_key]["status"] = "CONNECTED"
                accounts[acc_key]["updated_at"] = datetime.now().isoformat()
                logger.info(f"🔄 [AUTO-REGISTER] Refreshed MT5 Account #{acc_id}! Profile='{accounts[acc_key].get('risk_profile')}', Active={accounts[acc_key].get('active', False)}")

            with open(ACCOUNTS_CONFIG_PATH, "w", encoding="utf-8") as f:
                yaml.dump(cfg, f, default_flow_style=False, sort_keys=False, allow_unicode=True)
        except Exception as e:
            logger.error(f"Error auto-registering account #{acc_id}: {e}")

    def _record_closed_trade(self, data: Dict[str, Any]):
        """
        Appends closed deal to the appropriate forward test storage file
        (forward_trades_vps.json if on VPS, forward_trades_local.json if on Mac).
        """
        # Distinguish local vs VPS by OS / user path
        is_windows = os.name == 'nt' or 'C:' in str(PROJECT_ROOT)
        target_filename = "forward_trades_vps.json" if is_windows else "forward_trades_local.json"
        target_path = PROJECT_ROOT / "data" / target_filename
        target_path.parent.mkdir(parents=True, exist_ok=True)

        existing = []
        if target_path.exists():
            try:
                existing = json.loads(target_path.read_text(encoding="utf-8"))
            except Exception:
                existing = []

        # Avoid duplicate tickets
        trade_id = str(data.get("trade_id"))
        if any(str(t.get("trade_id")) == trade_id for t in existing):
            return

        # Look up account metadata & risk profile from accounts.yaml
        acc_num = str(data.get("account_number") or data.get("account_id") or self.active_account_id)
        acc_profile = "none"
        if ACCOUNTS_CONFIG_PATH.exists():
            try:
                import yaml
                with open(ACCOUNTS_CONFIG_PATH, "r", encoding="utf-8") as f:
                    cfg = yaml.safe_load(f) or {}
                acc_obj = cfg.get("accounts", {}).get(f"ACC-{acc_num}")
                if acc_obj:
                    acc_profile = acc_obj.get("risk_profile", "none")
            except Exception:
                pass

        exit_t_sec = data.get("exit_time", time.time())
        exit_dt_str = datetime.fromtimestamp(exit_t_sec, tz=timezone.utc).isoformat()

        entry_t_sec = data.get("entry_time", exit_t_sec)
        entry_dt_str = datetime.fromtimestamp(entry_t_sec, tz=timezone.utc).isoformat()

        entry_p = float(data.get("entry_price", data.get("exit_price", 0.0)))
        exit_p = float(data.get("exit_price", entry_p))
        lots = float(data.get("lots", 0.01))

        record = {
            "trade_id": trade_id,
            "position_id": str(data.get("position_id", trade_id)),
            "account_number": acc_num,
            "risk_profile": acc_profile,
            "symbol": data.get("symbol", "XAUUSD"),
            "direction": data.get("direction", "BUY"),
            "timeframe": "M1",
            "entry_time": entry_dt_str,
            "exit_time": exit_dt_str,
            "entry_price": entry_p,
            "exit_price": exit_p,
            "lots": lots,
            "sl_price": 0.0,
            "tp_price": 0.0,
            "expected_entry_price": entry_p,
            "actual_entry_price": entry_p,
            "slippage_pts": 0.05,
            "pnl": float(data.get("pnl", 0.0)),
            "r_multiple": round(float(data.get("pnl", 0.0)) / 5.0, 2),
            "exit_reason": "TP/BEP Closed"
        }

        existing.append(record)
        try:
            # Atomic Write: write to .tmp then atomic os.replace to prevent corruption on crash
            tmp_path = target_path.with_suffix(".tmp")
            tmp_path.write_text(json.dumps(existing, indent=2), encoding="utf-8")
            os.replace(tmp_path, target_path)
            logger.info(f"💾 [FORWARD STORAGE] Saved Closed Trade #{trade_id} (PnL: ${record['pnl']:.2f}) -> {target_filename} (Total: {len(existing)}) [ATOMIC]")

            # Update Performance & Objective Ledger (DEC-040)
            try:
                from src.analytics.performance_ledger import get_performance_ledger
                get_performance_ledger().reconstruct_from_trades([record])
                get_performance_ledger().save()
            except Exception as e:
                logger.debug(f"Performance ledger trade update error: {e}")

            # Update Directional Loss Streak & Cooldown (DEC-031 Champion)
            trade_pnl = float(data.get("pnl", 0.0))
            trade_dir = str(data.get("direction", "BUY")).upper()
            now_ts = time.time()

            # Tentukan durasi cooldown berdasarkan sesi saat ini
            # Asia: 10 menit, London: 15 menit, NY Overlap: 25 menit (Juara CLONE-SESSION-ADAPT-15M)
            now_h = datetime.now(timezone.utc).hour
            if 0 <= now_h < 7:
                cd_seconds = 10 * 60.0
            elif 7 <= now_h < 13:
                cd_seconds = 15 * 60.0
            else:
                cd_seconds = 25 * 60.0

            if trade_pnl < 0:
                if trade_dir == "BUY":
                    self.consecutive_buy_losses += 1
                    self.buy_cooldown_until = now_ts + cd_seconds
                    logger.warning(f"🛡️ [ANTI-FALLING-KNIFE] BUY Loss #{self.consecutive_buy_losses} recorded! Cooldown BUY paused for {cd_seconds/60:.0f} mins until {datetime.fromtimestamp(self.buy_cooldown_until, tz=timezone.utc).strftime('%H:%M:%S UTC')}")
                elif trade_dir == "SELL":
                    self.consecutive_sell_losses += 1
                    self.sell_cooldown_until = now_ts + cd_seconds
                    logger.warning(f"🛡️ [ANTI-FALLING-KNIFE] SELL Loss #{self.consecutive_sell_losses} recorded! Cooldown SELL paused for {cd_seconds/60:.0f} mins until {datetime.fromtimestamp(self.sell_cooldown_until, tz=timezone.utc).strftime('%H:%M:%S UTC')}")
            else:
                # Reset loss streak upon profitable exit
                if trade_dir == "BUY":
                    self.consecutive_buy_losses = 0
                elif trade_dir == "SELL":
                    self.consecutive_sell_losses = 0

                # Micro Level Depletion (Pilar 3: Virgin Depth Preservation)
                t_comm = str(data.get("comment", "")).upper()
                spent_lay = 0
                if "_L2" in t_comm or "L2" in t_comm:
                    spent_lay = 1
                elif "_L3" in t_comm or "L3" in t_comm:
                    spent_lay = 2

                for dep_tf, dep_data in self.tf_depletion.items():
                    if dep_data.get("direction") == trade_dir:
                        dep_data.setdefault("spent_layers", set()).add(spent_lay)
                        logger.info(f"🏆 [MICRO DEPLETION] {dep_tf} Layer {spent_lay+1} marked as SPENT upon Take Profit. Deeper virgin layers remain active!")

                # Mark active structural zone as COMPLETED / SPENT upon Take Profit (DEC-035)
                self.zone_completed = True
                self.completed_direction = trade_dir
                self.completed_floor = self._current_sw_low
                self.completed_roof = self._current_sw_high
                logger.info(f"🏆 [TAKE PROFIT HARVEST] Take profit achieved for {trade_dir}! Zone (${self.completed_floor:.2f} - ${self.completed_roof:.2f}).")
        except Exception as e:
            logger.error(f"Failed to save closed trade record: {e}")

    def _update_account_equity(self, acc_id: str, balance: float, equity: float):
        if not acc_id or not str(acc_id).strip():
            return
        if not ACCOUNTS_CONFIG_PATH.exists():
            return
        try:
            import yaml
            with open(ACCOUNTS_CONFIG_PATH, "r", encoding="utf-8") as f:
                cfg = yaml.safe_load(f) or {}

            accounts = cfg.setdefault("accounts", {})
            acc_key = f"ACC-{acc_id.strip()}"
            if acc_key in accounts:
                accounts[acc_key]["balance"] = round(balance, 2)
                accounts[acc_key]["equity"] = round(equity, 2)
                accounts[acc_key]["status"] = "CONNECTED"
                accounts[acc_key]["updated_at"] = datetime.now().isoformat()
                with open(ACCOUNTS_CONFIG_PATH, "w", encoding="utf-8") as f:
                    yaml.dump(cfg, f, default_flow_style=False, sort_keys=False, allow_unicode=True)
        except Exception as e:
            logger.debug(f"Failed to update account equity in accounts.yaml: {e}")

    def _evaluate_force_close_guardian(self, current_price: float):
        """
        Actively monitors open positions against structural invalidation,
        triggering instant CLOSE_ALL or BEP lock commands to MT5 EA.
        """
        now = time.time()
        if now - self._last_force_close_check < 1.0:
            return
        self._last_force_close_check = now

        for pos in list(self.live_open_positions):
            ticket = pos.get("ticket")
            side = pos.get("type")
            entry_p = pos.get("entry_price", current_price)
            cur_p = pos.get("current_price", current_price)
            sl = pos.get("sl", 0.0)

            spread_val = max(0.20, round(self.latest_tick.get("ask", 0) - self.latest_tick.get("bid", 0), 2)) if self.latest_tick else 0.35

            # 1. Sasuke Sharingan Greed Trailing (Pilar 2 Relaksasi)
            pts_diff = (cur_p - entry_p) if side == "BUY" else (entry_p - cur_p)
            sl_dist = max(abs(entry_p - pos.get("sl", entry_p - 3.0)), 0.5)
            r_running = pts_diff / sl_dist

            # Trailing Stepped Lock (Relaxed to avoid premature choking):
            # >= +2.5R -> lock SL at +1.5R
            # >= +2.0R -> lock SL at +1.0R
            target_lock_r = None
            if r_running >= 2.5:
                target_lock_r = 1.5
            elif r_running >= 2.0:
                target_lock_r = 1.0

            if target_lock_r is not None:
                new_trail_sl = round(entry_p + (target_lock_r * sl_dist if side == "BUY" else -target_lock_r * sl_dist), 2)
                cur_sl = float(pos.get("sl", 0.0))
                should_update = (cur_sl == 0.0) or (side == "BUY" and new_trail_sl > cur_sl) or (side == "SELL" and new_trail_sl < cur_sl)

                if should_update:
                    logger.info(f"👁️ [SASUKE GREED TRAILING] Locking SL on {side} #{ticket} @ ${new_trail_sl:.2f} (+{target_lock_r}R Locked | Running: +{r_running:.2f}R)")
                    asyncio.create_task(self.broadcast({
                        "action": "MODIFY_POSITION",
                        "account_number": str(pos.get("account_number", "")),
                        "ticket": ticket,
                        "sl": new_trail_sl,
                        "tp": pos.get("tp", 0.0)
                    }))

                    notif = {
                        "id": int(now * 1000),
                        "timestamp": datetime.now().strftime("%H:%M:%S"),
                        "title": f"👁️ Sasuke Greed Trailing Lock!",
                        "message": f"{side} #{ticket} locked at +{target_lock_r}R (${new_trail_sl:.2f})",
                        "type": "BEP",
                        "price": new_trail_sl
                    }
                    self.pending_notifications.append(notif)
                    if len(self.pending_notifications) > 10:
                        self.pending_notifications.pop(0)

            # 2. Sasuke Sharingan Structural & Reversal Evaluation (Replaces naive 3.5pt emergency cut)
            # Evaluate using recent M1 candles from history
            if len(self.history_m1) >= 5:
                recent_candles = self.history_m1[-10:]
                current_candle = self.history_m1[-1]

                sasuke_verdict = self.sasuke_overseer.evaluate_position_with_sharingan(
                    pos=pos,
                    current_candle=current_candle,
                    recent_m1_candles=recent_candles,
                    account_equity=self.equity,
                    initial_balance=self.balance
                )

                if sasuke_verdict.action == SasukeAction.FORCE_TP_REVERSAL:
                    logger.warning(f"👁️ [SASUKE SHARINGAN] Force TP triggered on #{ticket}! Reason: {sasuke_verdict.rationale}")
                    asyncio.create_task(self.broadcast({
                        "action": "CLOSE_ALL",
                        "account_number": str(pos.get("account_number", "")),
                        "symbol": "XAUUSD",
                        "magic": pos.get("magic", 1001)
                    }))

                    notif = {
                        "id": int(now * 1000),
                        "timestamp": datetime.now().strftime("%H:%M:%S"),
                        "title": f"👁️ SASUKE REVERSAL FORCE TP!",
                        "message": f"{side} #{ticket} closed: {sasuke_verdict.rationale}",
                        "type": "FORCE_CLOSE",
                        "price": cur_p
                    }
                    self.pending_notifications.append(notif)
                    if len(self.pending_notifications) > 10:
                        self.pending_notifications.pop(0)

                elif sasuke_verdict.action == SasukeAction.GREED_TRAILING_STEP:
                    new_sl = sasuke_verdict.target_sl
                    cur_sl = float(pos.get("sl", 0.0))
                    should_update = (cur_sl == 0.0) or (side == "BUY" and new_sl > cur_sl) or (side == "SELL" and new_sl < cur_sl)

                    if should_update and new_sl > 0:
                        logger.info(f"👁️ [SASUKE GREED TRAILING] Updating SL on #{ticket} to ${new_sl:.2f}: {sasuke_verdict.rationale}")
                        asyncio.create_task(self.broadcast({
                            "action": "MODIFY_POSITION",
                            "account_number": str(pos.get("account_number", "")),
                            "ticket": ticket,
                            "sl": new_sl,
                            "tp": pos.get("tp", 0.0)
                        }))

                        notif = {
                            "id": int(now * 1000),
                            "timestamp": datetime.now().strftime("%H:%M:%S"),
                            "title": f"👁️ SASUKE GREED TRAILING!",
                            "message": f"{side} #{ticket} SL locked at ${new_sl:.2f}",
                            "type": "BEP",
                            "price": new_sl
                        }
                        self.pending_notifications.append(notif)
                        if len(self.pending_notifications) > 10:
                            self.pending_notifications.pop(0)

        # 3. Naruto 2: Multi-Layer Summary BEP + $2.00 Trailing Engine (DEC-033 Champion)
        # Evaluates positions grouped by account when multiple grid layers are filled
        from collections import defaultdict
        pos_by_account = defaultdict(list)
        for p in self.live_open_positions:
            acc_key = str(p.get("account_number", self.active_account_id))
            pos_by_account[acc_key].append(p)

        for acc_k, p_list in pos_by_account.items():
            if len(p_list) >= 2: # 2 or 3 layers filled together
                side = p_list[0].get("type")
                tot_lots = sum(float(x.get("lots", 0.01)) for x in p_list)
                if tot_lots > 0:
                    weighted_entry = sum(float(x.get("entry_price", current_price)) * float(x.get("lots", 0.01)) for x in p_list) / tot_lots
                    summary_bep = round(weighted_entry, 2)

                    should_trail = False
                    trail_target_sl = None

                    if side == "BUY":
                        # If price reaches +$3.00 above summary BEP (relaxed from $2.00 to avoid micro-pullback noise)
                        if current_price >= summary_bep + 3.0:
                            should_trail = True
                            trail_target_sl = max(summary_bep, round(current_price - 2.50, 2))
                    elif side == "SELL":
                        # If price reaches -$3.00 below summary BEP (relaxed from $2.00)
                        if current_price <= summary_bep - 3.0:
                            should_trail = True
                            trail_target_sl = min(summary_bep, round(current_price + 2.50, 2))

                    if should_trail and trail_target_sl is not None:
                        for p in p_list:
                            t_num = p.get("ticket")
                            cur_p_sl = float(p.get("sl", 0.0))
                            update_needed = (cur_p_sl == 0.0) or (side == "BUY" and trail_target_sl > cur_p_sl) or (side == "SELL" and trail_target_sl < cur_p_sl)
                            if update_needed:
                                logger.info(f"🥋 [NARUTO 2 SUMMARY TRAILING] Account #{acc_k} {side} #{t_num} SL trailed to ${trail_target_sl:.2f} (Summary BEP: ${summary_bep:.2f} | Price: ${current_price:.2f})")
                                asyncio.create_task(self.broadcast({
                                    "action": "MODIFY_POSITION",
                                    "account_number": str(p.get("account_number", acc_k)),
                                    "ticket": t_num,
                                    "sl": trail_target_sl,
                                    "tp": p.get("tp", 0.0)
                                }))

    async def _handle_client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        client_addr = writer.get_extra_info("peername")
        logger.info(f"🟢 MT5 EA Client connected from {client_addr}")
        self.active_writers.append(writer)
        connected_acc_id: Optional[str] = None

        buffer = ""
        try:
            while True:
                data = await reader.read(8192)
                if not data:
                    break

                buffer += data.decode("utf-8", errors="replace")
                while "\n" in buffer:
                    line, buffer = buffer.split("\n", 1)
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        msg = json.loads(line)
                        acc_msg = msg.get("account_id") or (msg.get("data", {}).get("account_number") if isinstance(msg.get("data"), dict) else None)
                        if acc_msg:
                            norm_acc = self._normalize_account_id(acc_msg)
                            connected_acc_id = norm_acc
                            self.account_writers[norm_acc].add(writer)
                        await self._dispatch_message(msg, writer)
                    except Exception as err:
                        logger.error(f"Error parsing incoming JSON: {err} | Raw: {line[:120]}")
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"Client connection error: {e}")
        finally:
            logger.info(f"🔴 MT5 Client disconnected: {client_addr} (Account: #{connected_acc_id or 'unknown'})")
            if writer in self.active_writers:
                self.active_writers.remove(writer)
            for acc_k, writers in list(self.account_writers.items()):
                writers.discard(writer)
                if not writers:
                    self.account_writers.pop(acc_k, None)
            if connected_acc_id:
                self.synced_accounts.discard(connected_acc_id)
            self._save_radar_state()

    async def _dispatch_message(self, msg: Dict[str, Any], writer: asyncio.StreamWriter):
        msg_type = msg.get("type") or msg.get("action")

        # 1. REGISTER / HANDSHAKE
        if msg_type in ("REGISTER", "HANDSHAKE"):
            data_dict = msg.get("data", {}) if isinstance(msg.get("data"), dict) else {}
            acc_id = str(msg.get("account_id") or data_dict.get("account_number") or self.active_account_id)
            norm_acc = self._normalize_account_id(acc_id)
            if norm_acc:
                self.account_writers[norm_acc].add(writer)
            company = str(msg.get("company") or data_dict.get("broker_name") or "MetaQuotes")
            server = str(msg.get("server") or data_dict.get("server") or "MetaQuotes-Demo")
            balance = float(msg.get("balance") or data_dict.get("balance") or 10000.0)
            equity = float(msg.get("equity") or data_dict.get("equity") or balance)

            self.active_account_id = acc_id
            self.account_company = company
            self.balance = balance
            self.equity = equity
            # Require full TICK telemetry sync before allowing order dispatch
            self.synced_accounts.discard(acc_id)

            if self.on_handshake_callback:
                self.on_handshake_callback(data_dict or msg)

            logger.info(f"📥 [MT5 HANDSHAKE] Account #{acc_id} ({company}) registered! Balance: ${balance:.2f} | Equity: ${equity:.2f}")
            self._auto_register_account(acc_id, company, server, balance, equity)
            self._save_radar_state()

        # 2. BAR / BAR_SYNC
        elif msg_type == "BAR":
            symbol = msg.get("symbol", "XAUUSD")
            data = msg.get("data", {})
            if self.on_bar_callback:
                self.on_bar_callback(symbol, data)

        # 3. BAR_SYNC (Bulk Historical Bars from MT5)
        elif msg_type == "BAR_SYNC":
            bars = msg.get("bars", [])
            batch = msg.get("batch", 1)
            total = msg.get("total", 1)
            symbol = msg.get("symbol", "XAUUSD")

            if batch == 1:
                self._pending_sync_bars = []

            self._pending_sync_bars.extend(bars)
            logger.info(f"📥 [BAR SYNC] Batch {batch}/{total} received ({len(bars)} M1 bars, total buffered: {len(self._pending_sync_bars)})")

            if batch >= total:
                self.history_m1.clear()
                for item in self._pending_sync_bars:
                    ts_sec = int(item["time"] / 1000)
                    self.history_m1.append({
                        "time": ts_sec,
                        "open": float(item["open"]),
                        "high": float(item["high"]),
                        "low": float(item["low"]),
                        "close": float(item["close"]),
                        "volume": int(item.get("volume", 1)),
                        "spread": float(item.get("spread", 0.20))
                    })
                self._pending_sync_bars.clear()
                last_c = self.history_m1[-1]["close"] if self.history_m1 else 0.0
                logger.info(f"✅ [BAR SYNC 100%] Ingested {len(self.history_m1)} REAL bars from MT5! Latest Close: ${last_c:.2f}")
                self._save_radar_state()

        # 4. CLOSED_TRADE (Real-time Closed Deal Telemetry from MT5)
        elif msg_type == "CLOSED_TRADE":
            trade_data = msg.get("data", {})
            if trade_data:
                # Ensure account number from message envelope is attached to trade data
                if "account_number" not in trade_data and "account_id" in msg:
                    trade_data["account_number"] = str(msg["account_id"])
                self._record_closed_trade(trade_data)

        # 5. TICK (Live High-Frequency Quotes)
        elif msg_type == "TICK":
            self.latest_tick = msg
            if "d1_trend" in msg:
                self.d1_trend = str(msg["d1_trend"])
            if "h1_trend" in msg:
                self.h1_trend = str(msg["h1_trend"])
            bid = float(msg.get("bid", 0.0))
            ask = float(msg.get("ask", 0.0))
            mid = round((bid + ask) / 2.0, 2)
            c = float(msg.get("last", mid))
            acc_id = str(msg.get("account_id") or (self.active_account_id if self.active_account_id else ""))
            norm_acc = self._normalize_account_id(acc_id)
            if norm_acc:
                self.account_writers[norm_acc].add(writer)
            if acc_id:
                self.active_account_id = acc_id
            self.equity = float(msg.get("equity", self.equity))
            self.balance = float(msg.get("balance", self.balance))
            self.unrealized_pnl = float(msg.get("unrealized", 0.0))

            # Store per-account positions & orders into multi-account map
            if acc_id:
                if "positions" in msg and isinstance(msg["positions"], list):
                    for p in msg["positions"]:
                        p["account_number"] = acc_id
                    self.accounts_open_positions[acc_id] = msg["positions"]
                if "orders" in msg and isinstance(msg["orders"], list):
                    for o in msg["orders"]:
                        o["account_number"] = acc_id
                    self.accounts_pending_orders[acc_id] = msg["orders"]
                self.synced_accounts.add(acc_id)

                # Ingest Daily & Weekly Performance Metrics from Broker Telemetry (DEC-040)
                try:
                    from src.analytics.performance_ledger import get_performance_ledger
                    get_performance_ledger().update_live_telemetry(acc_id, msg)
                except Exception as e:
                    logger.debug(f"Performance ledger tick update error: {e}")

                if "daily_start_balance" in msg and float(msg["daily_start_balance"]) > 0:
                    d_start = float(msg["daily_start_balance"])
                    acc_daily = self.account_daily_guard.setdefault(acc_id, {
                        "daily_start_equity": d_start,
                        "peak_daily_pnl": 0.0,
                        "daily_halted": False,
                        "reason": ""
                    })
                    acc_daily["daily_start_equity"] = d_start
                    if "daily_pnl" in msg:
                        acc_daily["daily_pnl"] = float(msg["daily_pnl"])
                    if "daily_pnl_pct" in msg:
                        acc_daily["daily_pnl_pct"] = float(msg["daily_pnl_pct"])
                    if "weekly_start_balance" in msg:
                        acc_daily["weekly_start_balance"] = float(msg["weekly_start_balance"])
                    if "weekly_pnl" in msg:
                        acc_daily["weekly_pnl"] = float(msg["weekly_pnl"])
                    if "weekly_pnl_pct" in msg:
                        acc_daily["weekly_pnl_pct"] = float(msg["weekly_pnl_pct"])

            # Flatten all active accounts positions & orders for global evaluation
            all_open = []
            for plist in self.accounts_open_positions.values():
                all_open.extend(plist)
            self.live_open_positions = all_open

            all_orders = []
            for olist in self.accounts_pending_orders.values():
                all_orders.extend(olist)
            self.live_pending_orders = all_orders

            # Active ForceClose Guardian Monitoring on each tick
            if self.live_open_positions:
                self._evaluate_force_close_guardian(mid)

            # Dynamically persist updated Live Equity and Balance to accounts.yaml every 5 seconds
            now_t = time.time()
            if now_t - self._last_account_persist >= 5.0:
                self._last_account_persist = now_t
                self._update_account_equity(acc_id, self.balance, self.equity)

            # Maintain active candle in history_m1
            t_sec = int(msg.get("time", time.time() * 1000) / 1000)
            if self.history_m1:
                # If within current minute, update bar close/high/low
                last_b = self.history_m1[-1]
                if t_sec - last_b["time"] < 60:
                    last_b["close"] = c
                    last_b["high"] = max(last_b["high"], c)
                    last_b["low"] = min(last_b["low"], c)
                else:
                    # New minute candle
                    self.history_m1.append({
                        "time": t_sec,
                        "open": c,
                        "high": c,
                        "low": c,
                        "close": c,
                        "volume": 1,
                        "spread": round(ask - bid, 2)
                    })
                    if len(self.history_m1) > 450:
                        self.history_m1.pop(0)

            # Persist radar state at most twice a second
            now = time.time()
            if now - self._last_radar_save >= 0.5:
                self._save_radar_state()

    def _save_radar_state(self):
        if not self.history_m1 and not self.latest_tick:
            return

        last_c = self.history_m1[-1]["close"] if self.history_m1 else 4296.0
        bid = float(self.latest_tick.get("bid", last_c - 0.15)) if self.latest_tick else (last_c - 0.15)
        ask = float(self.latest_tick.get("ask", last_c + 0.15)) if self.latest_tick else (last_c + 0.15)
        mid = round((bid + ask) / 2.0, 2)

        if self.latest_tick:
            if "d1_trend" in self.latest_tick:
                self.d1_trend = str(self.latest_tick["d1_trend"])
            if "h4_trend" in self.latest_tick:
                self.h4_trend = str(self.latest_tick["h4_trend"])
            if "h1_trend" in self.latest_tick:
                self.h1_trend = str(self.latest_tick["h1_trend"])

        # Multi-timeframe bar aggregation & PAC calculation
        tf_dict = {}
        tf_candles = {}

        for tf, mult in [("M1", 1), ("M2", 2), ("M3", 3), ("M4", 4), ("M5", 5), ("M15", 15), ("M30", 30)]:
            # Aggregate M1 bars into TF bars
            aggregated = []
            m1_len = len(self.history_m1)
            # Take bars in multiples of mult from newest to oldest
            for i in range(0, m1_len, mult):
                group = self.history_m1[i:i + mult]
                if not group:
                    continue
                o = group[0]["open"]
                h = max(x["high"] for x in group)
                l = min(x["low"] for x in group)
                c = group[-1]["close"]
                t = group[-1]["time"]
                aggregated.append({
                    "time": t,
                    "open": round(o, 2),
                    "high": round(h, 2),
                    "low": round(l, 2),
                    "close": round(c, 2)
                })

            # Calculate dynamic swings & PAC channel for this TF
            lookback_sw = aggregated[-20:] if len(aggregated) >= 20 else aggregated
            sw_high = round(max(x["high"] for x in lookback_sw), 2) if lookback_sw else round(mid + 5.0, 2)
            sw_low = round(min(x["low"] for x in lookback_sw), 2) if lookback_sw else round(mid - 5.0, 2)
            total_range = max(1.0, sw_high - sw_low)
            equilibrium = round((sw_high + sw_low) / 2.0, 2)

            # Institutional PAC Quadrants
            buy_zone_top = round(sw_low + (total_range * 0.25), 2)
            buy_zone_bottom = sw_low
            sell_zone_bottom = round(sw_low + (total_range * 0.75), 2)
            sell_zone_top = sw_high

            in_discount = mid <= buy_zone_top
            in_premium = mid >= sell_zone_bottom

            # Format candles with PAC bands for this TF
            tf_bar_list = []
            for idx, b in enumerate(aggregated):
                sub = aggregated[max(0, idx - 15):idx + 1]
                pu = round(max(x["high"] for x in sub), 2)
                pl = round(min(x["low"] for x in sub), 2)
                tf_bar_list.append({
                    "time": b["time"],
                    "open": b["open"],
                    "high": b["high"],
                    "low": b["low"],
                    "close": b["close"],
                    "pac_upper": pu,
                    "pac_lower": pl,
                    "midpoint": round((pu + pl) / 2.0, 2)
                })

            tf_candles[tf] = tf_bar_list

            # 4. Institutional POI Databank & Prioritizer Integration (DEC-032: RBR/DBD Prioritization)
            # Detect all active FVGs, Confluences, and OrderBlocks (RBR, DBD, DBR, RBD)
            c_highs = np.array([x["high"] for x in aggregated], dtype=float)
            c_lows = np.array([x["low"] for x in aggregated], dtype=float)
            c_closes = np.array([x["close"] for x in aggregated], dtype=float)
            c_opens = np.array([x["open"] for x in aggregated], dtype=float)
            c_times = [datetime.fromtimestamp(x["time"], tz=timezone.utc) for x in aggregated]

            active_fvgs = detect_fvgs(c_highs, c_lows, c_times)
            active_obs = detect_order_blocks(c_opens, c_highs, c_lows, c_closes, c_times, active_fvgs)
            active_confluences = detect_fvg_confluences(active_fvgs, [])

            prioritizer = POIPrioritizer(proximity_threshold_points=12.0)
            selected_roof = prioritizer.rank_and_select_roof(mid, active_obs, active_fvgs, active_confluences, sw_high)
            selected_floor = prioritizer.rank_and_select_floor(mid, active_obs, active_fvgs, active_confluences, sw_low)

            # If prioritizer selected a fresh RBR or DBD, prioritize its anchor and boundaries over generic swing!
            roof_is_dbd = (selected_roof.poi_type == "DBD")
            floor_is_rbr = (selected_floor.poi_type == "RBR")

            if roof_is_dbd:
                sw_high = selected_roof.top
                sell_zone_bottom = selected_roof.bottom
                sell_zone_top = selected_roof.top

            if floor_is_rbr:
                sw_low = selected_floor.bottom
                buy_zone_top = selected_floor.top
                buy_zone_bottom = selected_floor.bottom

            total_range = max(1.0, sw_high - sw_low)
            equilibrium = round((sw_high + sw_low) / 2.0, 2)

            # Institutional PAC Quadrants
            buy_zone_top = round(sw_low + (total_range * 0.25), 2)
            buy_zone_bottom = sw_low
            sell_zone_bottom = round(sw_low + (total_range * 0.75), 2)
            sell_zone_top = sw_high

            in_discount = mid <= buy_zone_top
            in_premium = mid >= sell_zone_bottom

            # Calculate Untouched / Fresh Depth Boundary for Visual Chart (>50% Penetration)
            untouched_buy_top = round(sw_low + (total_range * 0.125), 2)
            untouched_sell_bottom = round(sw_low + (total_range * 0.875), 2)

            # 4-Layer Judas Grid Target Levels for this TF (DEC-043 Champion: Judas Catch at -27.2%)
            buy_grid_levels = [
                round(buy_zone_top, 2),                   # L1: 25% Lantai Atas Buy
                round(sw_low + (total_range * 0.125), 2), # L2: 12.5% Kedalaman Murni
                round(sw_low, 2),                          # L3: 0% Dasar Lantai
                round(sw_low - (total_range * 0.272), 2)  # L4: -27.2% Judas Catch
            ]
            sell_grid_levels = [
                round(sell_zone_bottom, 2),               # L1: 75% Lantai Bawah Sell
                round(sw_low + (total_range * 0.875), 2), # L2: 87.5% Kedalaman Murni
                round(sw_high, 2),                         # L3: 100% Pucuk Atap
                round(sw_high + (total_range * 0.272), 2) # L4: +27.2% Judas Catch
            ]

            # Smart Judas Fortress SL (DEC-043: Hierarki OR_1 Unmitigated OB -> Fibo Judas -13%)
            valid_bull_ob = [ob for ob in active_obs if ob.ob_type in ("DBR", "RBR") and ob.bottom < sw_low and (sw_low - ob.bottom) <= (0.50 * total_range)]
            valid_bear_ob = [ob for ob in active_obs if ob.ob_type in ("RBD", "DBD") and ob.top > sw_high and (ob.top - sw_high) <= (0.50 * total_range)]

            if in_discount:
                dir_label = "BUY"
                status_label = "IN_BUY_ZONE"
                quad_label = "0% - 25% (Buy Discount)"
                if valid_bull_ob:
                    ob_bot = max(ob.bottom for ob in valid_bull_ob)
                    hard_sl = round(ob_bot - 0.25, 2)
                else:
                    hard_sl = round(sw_low - (total_range * 0.130) - 0.25, 2)
                soft_sl = round(sw_low - 0.5, 2)
                is_active = True
                score = 9.2
            elif in_premium:
                dir_label = "SELL"
                status_label = "IN_SELL_ZONE"
                quad_label = "75% - 100% (Sell Premium)"
                if valid_bear_ob:
                    ob_top = min(ob.top for ob in valid_bear_ob)
                    hard_sl = round(ob_top + 0.25, 2)
                else:
                    hard_sl = round(sw_high + (total_range * 0.130) + 0.25, 2)
                soft_sl = round(sw_high + 0.5, 2)
                is_active = True
                score = 9.0
            else:
                dir_label = "NEUTRAL"
                status_label = "EQUILIBRIUM_WAIT"
                quad_label = "40% - 60% (Equilibrium)"
                hard_sl = 0.0
                soft_sl = 0.0
                is_active = False
                score = 5.4

            # Find specific anchor/base candles for Roof (Swing High) and Floor (Swing Low)
            roof_idx = max(range(len(lookback_sw)), key=lambda i: lookback_sw[i]["high"]) if lookback_sw else None
            floor_idx = min(range(len(lookback_sw)), key=lambda i: lookback_sw[i]["low"]) if lookback_sw else None

            roof_anchor = lookback_sw[roof_idx] if roof_idx is not None else None
            floor_anchor = lookback_sw[floor_idx] if floor_idx is not None else None

            # Extract Leg-In & Leg-Out Structural Window (3 bars before, anchor bar, up to 3 bars after)
            roof_leg_bars = []
            if roof_idx is not None:
                start_r = max(0, roof_idx - 3)
                end_r = min(len(lookback_sw), roof_idx + 4)
                roof_leg_bars = [{
                    "time": b["time"],
                    "open": b["open"],
                    "high": b["high"],
                    "low": b["low"],
                    "close": b["close"],
                    "is_anchor": (i == roof_idx),
                    "role": "LEG_IN" if i < roof_idx else ("ANCHOR" if i == roof_idx else "LEG_OUT")
                } for i, b in enumerate(lookback_sw) if start_r <= i < end_r]

            floor_leg_bars = []
            if floor_idx is not None:
                start_f = max(0, floor_idx - 3)
                end_f = min(len(lookback_sw), floor_idx + 4)
                floor_leg_bars = [{
                    "time": b["time"],
                    "open": b["open"],
                    "high": b["high"],
                    "low": b["low"],
                    "close": b["close"],
                    "is_anchor": (i == floor_idx),
                    "role": "LEG_IN" if i < floor_idx else ("ANCHOR" if i == floor_idx else "LEG_OUT")
                } for i, b in enumerate(lookback_sw) if start_f <= i < end_f]

            roof_time_val = roof_anchor["time"] if roof_anchor else 0
            floor_time_val = floor_anchor["time"] if floor_anchor else 0

            roof_time_str = datetime.fromtimestamp(roof_time_val, tz=timezone.utc).strftime("%H:%M UTC") if roof_anchor else "Recent"
            floor_time_str = datetime.fromtimestamp(floor_time_val, tz=timezone.utc).strftime("%H:%M UTC") if floor_anchor else "Recent"

            poi_reasoning = {
                "roof": {
                    "price_high": sw_high,
                    "zone_range": f"${sell_zone_bottom:.2f} - ${sw_high:.2f}",
                    "structure_context": selected_roof.merged_description if roof_is_dbd else ("Rally-Base-Drop (RBD) Sweep Leg" if roof_leg_bars else "Swing High Pivot"),
                    "base_candle": {
                        "time": roof_time_str,
                        "timestamp": roof_time_val,
                        "open": roof_anchor["open"] if roof_anchor else sw_high,
                        "high": roof_anchor["high"] if roof_anchor else sw_high,
                        "low": roof_anchor["low"] if roof_anchor else sw_high,
                        "close": roof_anchor["close"] if roof_anchor else sw_high,
                    },
                    "leg_candles": roof_leg_bars,
                    "reasons": [
                        f"{'★ PRIORITIZED DBD SUPPLY BASE' if roof_is_dbd else 'Liquidity Sweep Peak'} at ${sw_high:.2f} ({roof_time_str})",
                        f"Touch Lifecycle: {'✨ 100% VIRGIN BASE (Untouched)' if selected_roof.is_virgin else f'Retested ({selected_roof.touch_count} touches)'}",
                        f"Consolidated Zone: ${sell_zone_bottom:.2f} - ${sw_high:.2f}",
                        f"4-Layer Sell Grid: L1=${sell_grid_levels[0]:.2f}, L2=${sell_grid_levels[1]:.2f}, L3=${sell_grid_levels[2]:.2f}, L4=${sell_grid_levels[3]:.2f}",
                        f"Virgin Depth >50% Untouched above ${untouched_sell_bottom:.2f}"
                    ]
                },
                "floor": {
                    "price_low": sw_low,
                    "zone_range": f"${sw_low:.2f} - ${buy_zone_top:.2f}",
                    "structure_context": selected_floor.merged_description if floor_is_rbr else ("Drop-Base-Rally (DBR) Demand Leg" if floor_leg_bars else "Swing Low Pivot"),
                    "base_candle": {
                        "time": floor_time_str,
                        "timestamp": floor_time_val,
                        "open": floor_anchor["open"] if floor_anchor else sw_low,
                        "high": floor_anchor["high"] if floor_anchor else sw_low,
                        "low": floor_anchor["low"] if floor_anchor else sw_low,
                        "close": floor_anchor["close"] if floor_anchor else sw_low,
                    },
                    "leg_candles": floor_leg_bars,
                    "reasons": [
                        f"{'★ PRIORITIZED RBR DEMAND BASE' if floor_is_rbr else 'Demand Absorption Low'} at ${sw_low:.2f} ({floor_time_str})",
                        f"Touch Lifecycle: {'✨ 100% VIRGIN BASE (Untouched)' if selected_floor.is_virgin else f'Retested ({selected_floor.touch_count} touches)'}",
                        f"Consolidated Zone: ${sw_low:.2f} - ${buy_zone_top:.2f}",
                        f"4-Layer Buy Grid: L1=${buy_grid_levels[0]:.2f}, L2=${buy_grid_levels[1]:.2f}, L3=${buy_grid_levels[2]:.2f}, L4=${buy_grid_levels[3]:.2f}",
                        f"Virgin Depth >50% Untouched below ${untouched_buy_top:.2f}"
                    ]
                }
            }

            # Deterministic Fractal Market Structure Detection (HH, HL, LH, LL, BOS, CHoCH)
            market_structure_points = []
            struct_state = None
            if len(aggregated) >= 9:
                try:
                    c_highs = np.array([x["high"] for x in aggregated], dtype=float)
                    c_lows = np.array([x["low"] for x in aggregated], dtype=float)
                    c_closes = np.array([x["close"] for x in aggregated], dtype=float)
                    c_times = [datetime.fromtimestamp(x["time"], tz=timezone.utc) for x in aggregated]

                    sh_list, sl_list = detect_swing_points(c_highs, c_lows, c_times, window=2)
                    struct_state = evaluate_market_structure(c_closes, sh_list, sl_list, c_times)

                    # Merge & sort swing points sequentially by candle index
                    combined_swings = []
                    for sh in sh_list:
                        combined_swings.append({
                            "type": "HIGH",
                            "index": sh.index,
                            "price": round(sh.price, 2),
                            "label": sh.label,  # HH, LH, SH, EQH
                            "time": aggregated[sh.index]["time"] if sh.index < len(aggregated) else 0
                        })
                    for sl in sl_list:
                        combined_swings.append({
                            "type": "LOW",
                            "index": sl.index,
                            "price": round(sl.price, 2),
                            "label": sl.label,  # HL, LL, SL, EQL
                            "time": aggregated[sl.index]["time"] if sl.index < len(aggregated) else 0
                        })

                    combined_swings.sort(key=lambda x: x["index"])
                    market_structure_points = combined_swings
                except Exception as e:
                    logger.debug(f"Market structure calc warning: {e}")

            tf_dict[tf] = {
                "timeframe": tf,
                "active_setup": is_active,
                "direction": dir_label,
                "status": status_label,
                "quadrant": quad_label,
                "structure": "BULLISH_BOS" if dir_label == "BUY" else ("BEARISH_BOS" if dir_label == "SELL" else "CONSOLIDATION"),
                "structure_event": struct_state.last_event.value if (struct_state and struct_state.last_event) else "NONE",
                "swing_high": sw_high,
                "swing_low": sw_low,
                "equilibrium": equilibrium,
                "poi_reasoning": poi_reasoning,
                "market_structure": market_structure_points,
                "grid_levels": buy_grid_levels if dir_label == "BUY" else sell_grid_levels,
                "buy_zone": {
                    "bottom": buy_zone_bottom,
                    "top": buy_zone_top,
                    "untouched_top": untouched_buy_top,
                    "active": in_discount
                },
                "sell_zone": {
                    "bottom": sell_zone_bottom,
                    "top": sell_zone_top,
                    "untouched_bottom": untouched_sell_bottom,
                    "active": in_premium
                },
                "current_price": mid,
                "sl_hard": hard_sl,
                "sl_soft": soft_sl,
                "tp_midpoint": equilibrium,
                "retest_mode": "MULTI_RETEST_DEEPER",
                "checklist_score": score,
                "checklist": [
                    {"label": f"Valid PAC Zone ({'0-25% Buy' if dir_label == 'BUY' else ('75-100% Sell' if dir_label == 'SELL' else 'Equilibrium')})", "ok": is_active, "val": f"Live Price ${mid:.2f}"},
                    {"label": "Structural Alignment (BOS / CHoCH)", "ok": is_active, "val": f"{tf} Fractal Structure Tracked"},
                    {"label": "Retest Quality (Deeper Penetration)", "ok": is_active, "val": "Depth liquidity monitored"},
                    {"label": "Midpoint Hard TP Target", "ok": True, "val": f"50% Eq at ${equilibrium:.2f}"},
                    {"label": "Protective SL Boundaries", "ok": True, "val": f"Hard SL: ${hard_sl:.2f} | Soft SL: ${soft_sl:.2f}" if is_active else "Standby"}
                ]
            }

        # Auto-trigger Limit Order Dispatch when M1/M3 setup is Active
        now_time = time.time()
        now_utc = datetime.now(timezone.utc)
        curr_min_day = now_utc.hour * 60 + now_utc.minute
        today_str = now_utc.strftime("%Y-%m-%d")

        # 1. Klasifikasi 3 Sesi Mandiri (DEC-028 Champion CLONE-08)
        # Asia: 00:00 - 07:00 UTC (0 - 420 min)
        # London: 07:00 - 13:30 UTC (420 - 810 min)
        # NY Overlap: 13:30 - 21:00 UTC (810 - 1260 min)
        if 0 <= curr_min_day < 420:
            active_sess = "ASIAN"
        elif 420 <= curr_min_day < 810:
            active_sess = "LONDON"
        elif 810 <= curr_min_day < 1260:
            active_sess = "NY_OVERLAP"
        else:
            active_sess = "OFF_HOURS"

        # Hitung Total Ekuitas Gabungan Seluruh Akun Aktif (Fleet Multi-Account)
        total_fleet_equity = 0.0
        if ACCOUNTS_CONFIG_PATH.exists():
            try:
                import yaml
                with open(ACCOUNTS_CONFIG_PATH, "r", encoding="utf-8") as f:
                    cfg = yaml.safe_load(f) or {}
                for acc_k, acc_v in cfg.get("accounts", {}).items():
                    if acc_v.get("active", False):
                        total_fleet_equity += float(acc_v.get("equity", 0.0))
            except Exception:
                pass
        if total_fleet_equity <= 0:
            total_fleet_equity = self.equity

        # Cek Transisi Hari & Sesi
        if today_str != self.current_session_day:
            self.current_session_day = today_str
            self.prior_session_pnl = 0.0
            # Reset Daily Account Guard at 00:00 UTC day boundary
            self.account_daily_guard.clear()
            logger.info(f"🌅 [DAILY DAY BOUNDARY] New trading day {today_str} initialized. Daily profit/loss guards reset!")

        if active_sess != self.current_session_name:
            if self.current_session_name != "" and self.current_session_name != "OFF_HOURS":
                self.prior_session_pnl = total_fleet_equity - self.session_start_equity
                logger.info(f"🏁 [SESSION TRANSITION] {self.current_session_name} ended with PnL: ${self.prior_session_pnl:+.2f}")

            self.current_session_name = active_sess
            self.session_start_equity = max(100.0, total_fleet_equity)
            self.session_peak_pnl = 0.0
            self.session_halted = (active_sess == "OFF_HOURS")
            self.session_status_desc = f"{active_sess} Active" if not self.session_halted else "Off-Hours Standby"

            # Reset per-account session tracking on session boundary
            self.account_sessions.clear()

        # 2. Multi-Session Equity Budgeting & Dynamic Greed Trailing
        # Budget loss dasar per-sesi: -0.50% dari ekuitas total fleet
        # House Money (CLONE-08): Jika sesi sebelumnya profit >= +1.0%, tambahkan 25% profit ke budget risiko sesi ini!
        base_sess_loss = self.session_start_equity * 0.005 # 0.5%
        if self.prior_session_pnl > (self.session_start_equity * 0.01):
            base_sess_loss += (self.prior_session_pnl * 0.25)

        curr_sess_pnl = total_fleet_equity - self.session_start_equity
        if curr_sess_pnl > self.session_peak_pnl:
            self.session_peak_pnl = curr_sess_pnl

        # Floor PnL Berundak: Capai +1.0% lock +0.5%, capai +1.5% lock +1.0%, dst. (Pullback 0.5% -> Halted)
        sess_floor_pnl = -base_sess_loss
        target_1pct = self.session_start_equity * 0.010
        step_05pct = self.session_start_equity * 0.005

        if self.session_peak_pnl >= target_1pct:
            steps = int((self.session_peak_pnl - target_1pct) / step_05pct)
            sess_floor_pnl = (target_1pct * 0.50) + (steps * step_05pct)
            self.session_status_desc = f"Locked +${sess_floor_pnl:.2f} (+{(sess_floor_pnl/self.session_start_equity)*100:.1f}%)"

        if curr_sess_pnl <= sess_floor_pnl and not self.session_halted and active_sess != "OFF_HOURS":
            self.session_halted = True
            is_win_lock = sess_floor_pnl > 0
            reason_str = "Greed Trailing Lock Triggered" if is_win_lock else "Session Loss Budget Reached"
            self.session_status_desc = f"{active_sess} HALTED ({reason_str}: PnL ${curr_sess_pnl:+.2f})"
            logger.info(f"🛑 [SESSION CIRCUIT BREAKER] {self.session_status_desc}. Purging pending orders for safety.")
            asyncio.create_task(self.broadcast({"action": "CANCEL_PENDING", "symbol": "XAUUSD", "magic": 1001}))

        # Multi-Timeframe Entry Scanning & Handover Engine (Pilar 1, 2, 3)
        if self.active_writers:
            if self.session_halted and not self.account_sessions:
                return

            cb_status = self.sasuke_overseer.check_daily_circuit_breaker(account_equity=self.equity, starting_equity=self.balance)
            if getattr(cb_status, "is_tripped", False):
                if not hasattr(self, "_last_cb_warn") or (now_time - getattr(self, "_last_cb_warn", 0) > 300.0):
                    self._last_cb_warn = now_time
                    logger.error(f"🚫 [SASUKE CIRCUIT BREAKER ACTIVE] Daily Drawdown limit (-1.0%) tripped: {getattr(cb_status, 'reason', '')}. Trading HALTED!")
                return

            # Load active accounts and profiles from accounts.yaml
            target_accounts = {}
            if ACCOUNTS_CONFIG_PATH.exists():
                try:
                    import yaml
                    with open(ACCOUNTS_CONFIG_PATH, "r", encoding="utf-8") as f:
                        cfg = yaml.safe_load(f) or {}
                    profiles_cfg = cfg.get("risk_profiles", {})
                    for acc_k, acc_v in cfg.get("accounts", {}).items():
                        p_name = acc_v.get("risk_profile", "none")
                        is_active = acc_v.get("active", False)
                        if is_active and p_name in profiles_cfg:
                            r_pct = float(profiles_cfg[p_name].get("risk_per_trade_pct", 0.50))
                            broker_name_str = str(acc_v.get("broker_name", "")).lower()
                            target_accounts[acc_k] = {
                                "account_number": str(acc_v.get("account_number")),
                                "profile": p_name,
                                "broker_name": acc_v.get("broker_name", "MetaQuotes"),
                                "is_cent": "cent" in broker_name_str or "pu" in broker_name_str or acc_v.get("account_number") == "33848251",
                                "equity": float(acc_v.get("equity", self.equity)),
                                "risk_pct": r_pct,
                                "assigned_timeframes": acc_v.get("assigned_timeframes", ["M1", "M2", "M3", "M5", "M15"])
                            }
                except Exception as e:
                    logger.error(f"Error loading accounts for dispatch: {e}")

            # DEC-043 Reflex Active Guard: Velocity Gate & Volatility Ratio
            is_freight_train = False
            is_volatile_spike = False
            current_atr14 = 0.50
            last_bar_range = 0.0
            base_atr100 = 0.50
            atr_ratio = 1.0

            if len(self.history_m1) >= 15:
                recent_tr = [
                    max(
                        self.history_m1[k]["high"] - self.history_m1[k]["low"],
                        abs(self.history_m1[k]["high"] - self.history_m1[k-1]["close"]),
                        abs(self.history_m1[k]["low"] - self.history_m1[k-1]["close"])
                    )
                    for k in range(len(self.history_m1) - 14, len(self.history_m1))
                ]
                current_atr14 = float(np.mean(recent_tr)) if recent_tr else 0.50
                last_bar_range = abs(self.history_m1[-1]["high"] - self.history_m1[-1]["low"])
                if last_bar_range > (1.80 * current_atr14):
                    is_freight_train = True

            if len(self.history_m1) >= 100:
                long_tr = [
                    max(
                        self.history_m1[k]["high"] - self.history_m1[k]["low"],
                        abs(self.history_m1[k]["high"] - self.history_m1[k-1]["close"]),
                        abs(self.history_m1[k]["low"] - self.history_m1[k-1]["close"])
                    )
                    for k in range(len(self.history_m1) - 100, len(self.history_m1))
                ]
                base_atr100 = float(np.mean(long_tr)) if long_tr else current_atr14
                atr_ratio = float(current_atr14 / max(base_atr100, 0.20))
                if atr_ratio >= 1.30:
                    is_volatile_spike = True

            reflex_status = "FREIGHT_TRAIN" if is_freight_train else ("VOLATILE_STAND_ASIDE" if is_volatile_spike else "NOMINAL")
            self.latest_reflex_guard = {
                "status": reflex_status,
                "is_freight_train": is_freight_train,
                "is_volatile_spike": is_volatile_spike,
                "current_atr14": round(current_atr14, 2),
                "last_bar_range": round(last_bar_range, 2),
                "base_atr100": round(base_atr100, 2),
                "atr_ratio": round(atr_ratio, 2),
                "velocity_threshold": round(1.80 * current_atr14, 2)
            }

            if target_accounts and is_freight_train:
                if not hasattr(self, "_last_train_warn") or (now_time - getattr(self, "_last_train_warn", 0) > 60.0):
                    self._last_train_warn = now_time
                    logger.warning(f"⚡ [ANTI-FREIGHT-TRAIN GATE] Suppressing limit order dispatch! Recent bar range ${last_bar_range:.2f} > 1.8x ATR14 (${current_atr14:.2f}). Standing clear of runaway news/breakout!")

            if target_accounts and not is_freight_train:
                dispatched_orders_summary = []
                pyramid_weights = [0.15, 0.25, 0.30, 0.30]
                spread_val = max(0.20, round(ask - bid, 2)) if (ask > bid > 0) else 0.35
                d1_bias = getattr(self, "d1_trend", "NEUTRAL")

                for acc_k, acc_info in target_accounts.items():
                    acc_num = acc_info["account_number"]
                    acc_prof = acc_info["profile"]
                    acc_eq = max(100.0, acc_info["equity"])
                    acc_risk_tot = acc_info["risk_pct"]

                    # 1. PER-ACCOUNT DAILY TARGET & MAX LOSS GUARD (DEC-034 Master Daily Circuit Breaker)
                    acc_daily = self.account_daily_guard.setdefault(acc_num, {
                        "daily_start_equity": acc_eq,
                        "peak_daily_pnl": 0.0,
                        "daily_halted": False,
                        "reason": ""
                    })

                    daily_pnl = acc_eq - acc_daily["daily_start_equity"]
                    if daily_pnl > acc_daily["peak_daily_pnl"]:
                        acc_daily["peak_daily_pnl"] = daily_pnl

                    p_cfg = profiles_cfg.get(acc_prof, {})
                    daily_target_pct = float(p_cfg.get("daily_target_pct", 2.5))
                    max_daily_loss_pct = float(p_cfg.get("max_daily_loss_pct", 2.0))
                    pullback_lock_pct = float(p_cfg.get("daily_lock_pullback_pct", 0.5))

                    max_loss_dollar = max(5.0, acc_daily["daily_start_equity"] * (max_daily_loss_pct / 100.0))
                    daily_target_dollar = max(10.0, acc_daily["daily_start_equity"] * (daily_target_pct / 100.0))

                    # A. Cek Hard Daily Max Loss Cut-off
                    if daily_pnl <= -max_loss_dollar:
                        if not acc_daily["daily_halted"]:
                            acc_daily["daily_halted"] = True
                            acc_daily["reason"] = f"Daily Max Loss Hit: ${daily_pnl:+.2f} (Batas -{max_daily_loss_pct}%)"
                            logger.error(f"🛑 [DAILY HARD LOCKOUT] Account #{acc_num} ({acc_prof}) hit Daily Max Loss limit (-${max_loss_dollar:.2f}). Halted until 00:00 UTC!")
                            asyncio.create_task(self.broadcast({"action": "CANCEL_PENDING", "symbol": "XAUUSD", "account_number": acc_num, "magic": 1001}))

                    # B. Cek Daily Profit Target & Pullback Lock
                    if acc_daily["peak_daily_pnl"] >= daily_target_dollar:
                        pullback_dollar = acc_daily["daily_start_equity"] * (pullback_lock_pct / 100.0)
                        daily_floor_lock = daily_target_dollar * 0.60
                        if daily_pnl <= (acc_daily["peak_daily_pnl"] - pullback_dollar) or daily_pnl <= daily_floor_lock:
                            if not acc_daily["daily_halted"]:
                                acc_daily["daily_halted"] = True
                                acc_daily["reason"] = f"Daily Profit Locked: PnL ${daily_pnl:+.2f} (Target +{daily_target_pct}% secured)"
                                logger.info(f"🏆 [DAILY TARGET SECURED] Account #{acc_num} ({acc_prof}) secured daily profit (+${daily_pnl:.2f}). Trading finished for today!")
                                asyncio.create_task(self.broadcast({"action": "CANCEL_PENDING", "symbol": "XAUUSD", "account_number": acc_num, "magic": 1001}))

                    if acc_daily["daily_halted"]:
                        continue

                    # 2. Per-Account Dynamic Session Risk & Greed Trailing Evaluation (DEC-030)
                    acc_sess = self.account_sessions.setdefault(acc_num, {
                        "start_equity": acc_eq,
                        "peak_pnl": 0.0,
                        "halted": False,
                        "reason": ""
                    })

                    acc_pnl = acc_eq - acc_sess["start_equity"]
                    if acc_pnl > acc_sess["peak_pnl"]:
                        acc_sess["peak_pnl"] = acc_pnl

                    acc_loss_budget = max(5.0, acc_sess["start_equity"] * (acc_risk_tot / 100.0))
                    acc_floor_pnl = -acc_loss_budget
                    acc_target_1pct = max(10.0, acc_sess["start_equity"] * 0.010)
                    acc_step_05pct = max(5.0, acc_sess["start_equity"] * 0.005)

                    if acc_sess["peak_pnl"] >= acc_target_1pct:
                        steps = int((acc_sess["peak_pnl"] - acc_target_1pct) / acc_step_05pct)
                        acc_floor_pnl = (acc_target_1pct * 0.50) + (steps * acc_step_05pct)

                    if acc_pnl <= acc_floor_pnl and active_sess != "OFF_HOURS":
                        if not acc_sess["halted"]:
                            acc_sess["halted"] = True
                            acc_sess["reason"] = f"Account Session Threshold Hit (PnL: ${acc_pnl:+.2f})"
                            logger.info(f"🛑 [ACCOUNT SESSION HALT] Account #{acc_num} ({acc_prof}) reached threshold: PnL ${acc_pnl:+.2f}. Trading halted for this account.")
                            asyncio.create_task(self.broadcast({
                                "action": "CANCEL_PENDING",
                                "symbol": "XAUUSD",
                                "account_number": acc_num,
                                "magic": 1001
                            }))

                    if acc_sess["halted"]:
                        continue

                    # 0. Cold-Start Telemetry Sync Gate: Wait for first TICK telemetry from MT5
                    if acc_num not in self.synced_accounts:
                        continue

                    acc_pending = [o for o in self.live_pending_orders if str(o.get("account_number")) == acc_num]
                    acc_open = [p for p in self.live_open_positions if str(p.get("account_number")) == acc_num]

                    # 1. Auto-Reconciliation: If account somehow accumulated excess pending orders (> 4),
                    # purge outdated ones to prevent over-exposure
                    if len(acc_pending) > 4:
                        logger.warning(f"⚠️ [ORDER RECONCILIATION] Account #{acc_num} has {len(acc_pending)} pending orders (max 4). Purging excess stale pending orders.")
                        asyncio.create_task(self.broadcast({
                            "action": "CANCEL_PENDING",
                            "symbol": "XAUUSD",
                            "account_number": acc_num,
                            "magic": 1001
                        }))
                        self.accounts_pending_orders[acc_num] = []
                        continue

                    # 1B. Pending Order Lifespan (TTL 30m Auto-Purge DEC-043)
                    for o in list(acc_pending):
                        t_key = f"{acc_num}_{o.get('ticket')}"
                        b_time = self.pending_order_birth_times.setdefault(t_key, now_time)
                        if (now_time - b_time) > 1800.0:
                            logger.info(f"⌛ [ORDER TTL EXPIRED] Canceling stale pending order #{o.get('ticket')} on #{acc_num} (> 30m idle).")
                            asyncio.create_task(self.broadcast({
                                "action": "CANCEL_PENDING",
                                "symbol": "XAUUSD",
                                "account_number": acc_num,
                                "magic": 1001
                            }))
                            self.pending_order_birth_times.pop(t_key, None)
                            break

                    # 2. In-Flight Order Throttle: Min 5.0s between new LIMIT order batches for this specific account
                    # (Prevents duplicate order dispatch during MT5 network round-trip; zero effect on Sasuke trailing)
                    if now_time - self.account_last_order_dispatch.get(acc_num, 0.0) < 5.0:
                        continue

                    # 3. Multi-Timeframe Setup Scanning (Priority: M15 -> M5 -> M3 -> M1)
                    user_tfs = acc_info.get("assigned_timeframes", ["M1", "M2", "M3", "M5", "M15"])
                    chosen_setup = None
                    chosen_tf = None
                    cand_is_counter = False
                    cand_tp_mode = "NORMAL"

                    for scan_tf in ["M15", "M5", "M3", "M2", "M1"]:
                        if scan_tf not in user_tfs:
                            continue
                        cand_setup = tf_dict.get(scan_tf, {})
                        if not cand_setup or not cand_setup.get("active_setup"):
                            continue

                        c_dir = cand_setup["direction"]

                        # A. Pilar 1: Top 2 HTF Bias Gatekeeper (Empirical Permissive OR)
                        # M1, M2, M3, M4, M5 -> Guarded by D1 & H4 (PF 1.52 / DD 5.6%)
                        # M15 -> Guarded by H1 & H4 (PF 1.20 / DD 9.26%)
                        if scan_tf in ("M1", "M2", "M3", "M4", "M5"):
                            bias1 = getattr(self, "d1_trend", "NEUTRAL")
                            bias2 = getattr(self, "h4_trend", "NEUTRAL")
                        else:  # M15
                            bias1 = getattr(self, "h1_trend", "NEUTRAL")
                            bias2 = getattr(self, "h4_trend", "NEUTRAL")

                        b1_bear = bias1 in ("STRONG_BEARISH", "WEAK_BEARISH")
                        b1_bull = bias1 in ("STRONG_BULLISH", "WEAK_BULLISH")
                        b2_bear = bias2 in ("STRONG_BEARISH", "WEAK_BEARISH")
                        b2_bull = bias2 in ("STRONG_BULLISH", "WEAK_BULLISH")

                        both_bear = (b1_bear and b2_bear)
                        both_bull = (b1_bull and b2_bull)
                        is_counter = (c_dir == "BUY" and both_bear) or (c_dir == "SELL" and both_bull)
                        tp_mode = "NORMAL"

                        if is_counter:
                            # Objective-Aware Adaptive Unlock (HYBRID_4 Champion: Opsi A OR Opsi B)
                            # 0. Volatility Stand-Aside (DEC-043: Stand clear during volatility expansion)
                            if is_volatile_spike:
                                logger.info(f"🛡️ [VOLATILITY STAND-ASIDE] Counter-trend suppressed for #{acc_num} due to high volatility expansion (ATR ratio >= 1.30).")
                                continue

                            # 1. Check Daily Goal / Protective Cut
                            daily_pnl_pct = (daily_pnl / max(100.0, acc_daily["daily_start_equity"])) * 100.0
                            if daily_pnl_pct >= 1.0 or daily_pnl_pct <= -0.5:
                                # Target harian 1% aman atau batas rugi harian tercapai -> Gembok rapat!
                                continue

                            # 2. Opsi A: M1 + M5 Confluence
                            m1_s = tf_dict.get("M1", {})
                            m5_s = tf_dict.get("M5", {})
                            if c_dir == "BUY":
                                m1_ok = m1_s.get("direction") == "BUY" or m1_s.get("buy_zone", {}).get("active", False) or m1_s.get("quadrant") == "DISCOUNT"
                                m5_ok = m5_s.get("direction") == "BUY" or m5_s.get("buy_zone", {}).get("active", False) or m5_s.get("quadrant") == "DISCOUNT"
                            else:
                                m1_ok = m1_s.get("direction") == "SELL" or m1_s.get("sell_zone", {}).get("active", False) or m1_s.get("quadrant") == "PREMIUM"
                                m5_ok = m5_s.get("direction") == "SELL" or m5_s.get("sell_zone", {}).get("active", False) or m5_s.get("quadrant") == "PREMIUM"
                            opsi_a = bool(m1_ok and m5_ok)

                            # 3. Opsi B: Micro (M1..M3) + Inter (M5/M15) Confluence OR M15/M30 BOS
                            micro_tfs = ["M1", "M2", "M3"]
                            inter_tfs = ["M5", "M15"]
                            if c_dir == "BUY":
                                micro_ok = any(
                                    tf_dict.get(t, {}).get("direction") == "BUY" or
                                    tf_dict.get(t, {}).get("buy_zone", {}).get("active", False) or
                                    tf_dict.get(t, {}).get("quadrant") == "DISCOUNT"
                                    for t in micro_tfs
                                )
                                inter_ok = any(
                                    tf_dict.get(t, {}).get("direction") == "BUY" or
                                    tf_dict.get(t, {}).get("buy_zone", {}).get("active", False) or
                                    tf_dict.get(t, {}).get("quadrant") == "DISCOUNT"
                                    for t in inter_tfs
                                )
                                m15_event = str(tf_dict.get("M15", {}).get("structure_event", ""))
                                m30_event = str(tf_dict.get("M30", {}).get("structure_event", ""))
                                bos_ok = "BULLISH" in m15_event or "BULLISH" in m30_event
                            else:
                                micro_ok = any(
                                    tf_dict.get(t, {}).get("direction") == "SELL" or
                                    tf_dict.get(t, {}).get("sell_zone", {}).get("active", False) or
                                    tf_dict.get(t, {}).get("quadrant") == "PREMIUM"
                                    for t in micro_tfs
                                )
                                inter_ok = any(
                                    tf_dict.get(t, {}).get("direction") == "SELL" or
                                    tf_dict.get(t, {}).get("sell_zone", {}).get("active", False) or
                                    tf_dict.get(t, {}).get("quadrant") == "PREMIUM"
                                    for t in inter_tfs
                                )
                                m15_event = str(tf_dict.get("M15", {}).get("structure_event", ""))
                                m30_event = str(tf_dict.get("M30", {}).get("structure_event", ""))
                                bos_ok = "BEARISH" in m15_event or "BEARISH" in m30_event

                            opsi_b = bool((micro_ok and inter_ok) or bos_ok)

                            # FORMULA HYBRID_4: Opsi A OR Opsi B
                            if not (opsi_a or opsi_b):
                                continue

                            tp_mode = "EQ" if opsi_a else "SHALLOW"
                            logger.info(f"🔓 [HTF COUNTER UNLOCK] Account #{acc_num} unlocked {c_dir} on {scan_tf}! OpsiA={opsi_a}, OpsiB={opsi_b}, TP={tp_mode}, DayPnL={daily_pnl_pct:+.2f}%")

                        # B. Directional Cooldown (Anti-Falling-Knife DEC-031)
                        if c_dir == "BUY" and now_time < self.buy_cooldown_until:
                            continue
                        if c_dir == "SELL" and now_time < self.sell_cooldown_until:
                            continue

                        # C. Pilar 3: Micro Level Depletion Check
                        dep_info = self.tf_depletion.setdefault(scan_tf, {
                            "spent_layers": set(),
                            "roof": cand_setup["swing_high"],
                            "floor": cand_setup["swing_low"],
                            "direction": c_dir
                        })
                        # Reset if structure shifted >= 1.0 pt or direction flipped
                        if abs(cand_setup["swing_high"] - dep_info["roof"]) >= 1.0 or abs(cand_setup["swing_low"] - dep_info["floor"]) >= 1.0 or c_dir != dep_info["direction"]:
                            dep_info["spent_layers"].clear()
                            dep_info["roof"] = cand_setup["swing_high"]
                            dep_info["floor"] = cand_setup["swing_low"]
                            dep_info["direction"] = c_dir
                            logger.info(f"🔄 [{scan_tf} NEW STRUCTURE] Reset micro-depletion! New Zone: ${cand_setup['swing_low']:.2f} - ${cand_setup['swing_high']:.2f}")

                        if len(dep_info["spent_layers"]) >= 4:
                            continue

                        chosen_setup = cand_setup
                        chosen_tf = scan_tf
                        cand_is_counter = is_counter
                        cand_tp_mode = tp_mode
                        break

                    if not chosen_setup or not chosen_tf:
                        continue

                    dir_cmd = chosen_setup["direction"]
                    side = "BUY_LIMIT" if dir_cmd == "BUY" else "SELL_LIMIT"
                    sw_low = chosen_setup["swing_low"]
                    sw_high = chosen_setup["swing_high"]
                    span = max(sw_high - sw_low, 1.0)
                    sl_buffer = max(0.50, round(span * 0.0375, 2))

                    # Direction flip: Cancel outdated opposite pending orders
                    opp_side = "BUY_LIMIT" if dir_cmd == "SELL" else "SELL_LIMIT"
                    if any(o.get("type") == opp_side for o in acc_pending):
                        asyncio.create_task(self.broadcast({
                            "action": "CANCEL_PENDING",
                            "symbol": "XAUUSD",
                            "account_number": acc_num,
                            "magic": 1001
                        }))

                    # If account already has active open positions in this direction, let them run!
                    if any(p.get("type") == dir_cmd for p in acc_open):
                        continue

                    acc_matching_pending = [o for o in acc_pending if o.get("type") == side]
                    tf_rank_map = {"M1": 1, "M2": 2, "M3": 3, "M4": 4, "M5": 5, "M15": 15}
                    cur_rank = tf_rank_map.get(chosen_tf, 1)

                    # Handover Pending: Upgrade lower TF pending orders to higher TF
                    if acc_matching_pending and cur_rank > 1:
                        has_lower_tf = any(not str(o.get("comment", "")).startswith(f"{chosen_tf}_") and f"_{chosen_tf}_" not in str(o.get("comment", "")) for o in acc_matching_pending)
                        if has_lower_tf:
                            logger.info(f"🔄 [PENDING HANDOVER] Account #{acc_num} upgrading pending limits from lower TF to {chosen_tf}!")
                            asyncio.create_task(self.broadcast({
                                "action": "CANCEL_PENDING",
                                "symbol": "XAUUSD",
                                "account_number": acc_num,
                                "magic": 1001
                            }))
                            acc_matching_pending = []

                    # If account already has 4 pending orders matching current TF/direction, skip
                    if len(acc_matching_pending) >= 4:
                        continue

                    # Pure Geometric S&D Levels (DEC-043 4-Layer Judas Grid)
                    if dir_cmd == "BUY":
                        raw_levels = [
                            round(sw_low + span * 0.25, 2),  # L1: 25% Bibir
                            round(sw_low + span * 0.125, 2), # L2: 12.5% Tengah
                            round(sw_low, 2),                 # L3: 0% Dasar
                            round(sw_low - (span * 0.272), 2) # L4: -27.2% Judas Catch
                        ]
                        base_sl = chosen_setup["sl_hard"]
                        sl = round(base_sl - spread_val, 2)
                        
                        # Asymmetric TP Assignment (HYBRID_4 Champion)
                        if cand_is_counter and cand_tp_mode == "SHALLOW":
                            tp = round(sw_low + (span * 0.382), 2)
                        else:
                            # Handover TP: check if nested in M15
                            m15_s = tf_dict.get("M15", {})
                            if m15_s.get("active_setup") and m15_s.get("direction") == "BUY":
                                tp = round(max(chosen_setup["tp_midpoint"] + 2.0, m15_s["tp_midpoint"]), 2)
                            else:
                                tp = round(chosen_setup["tp_midpoint"], 2)
                    else:
                        raw_levels = [
                            round(sw_low + span * 0.75, 2),  # L1: 75% Bibir
                            round(sw_low + span * 0.875, 2), # L2: 87.5% Tengah
                            round(sw_high, 2),                # L3: 100% Pucuk
                            round(sw_high + (span * 0.272), 2) # L4: +27.2% Judas Catch
                        ]
                        base_sl = chosen_setup["sl_hard"]
                        sl = round(base_sl + spread_val, 2)
                        
                        # Asymmetric TP Assignment (HYBRID_4 Champion)
                        if cand_is_counter and cand_tp_mode == "SHALLOW":
                            tp = round(sw_low + (span * 0.618) + spread_val, 2)
                        else:
                            m15_s = tf_dict.get("M15", {})
                            if m15_s.get("active_setup") and m15_s.get("direction") == "SELL":
                                tp = round(min(chosen_setup["tp_midpoint"] - 2.0, m15_s["tp_midpoint"]) + spread_val, 2)
                            else:
                                tp = round(chosen_setup["tp_midpoint"] + spread_val, 2)

                    # Filter valid layers:
                    # 1. Micro level depletion (skip spent layers)
                    # 2. Broker limit price check (BUY_LIMIT < bid, SELL_LIMIT > ask)
                    # 3. Proximity coalescing (no duplicate within 1.5 pts of existing pending order)
                    spent_set = self.tf_depletion.get(chosen_tf, {}).get("spent_layers", set())
                    existing_p_prices = [float(o.get("price", 0.0)) for o in acc_matching_pending]

                    valid_layers = []
                    for lay_i, limit_p in enumerate(raw_levels):
                        if lay_i in spent_set:
                            continue
                        if dir_cmd == "BUY" and limit_p >= (bid - 0.10):
                            continue # Already penetrated below this level
                        if dir_cmd == "SELL" and limit_p <= (ask + 0.10):
                            continue # Already penetrated above this level
                        if any(abs(limit_p - ep) <= 1.50 for ep in existing_p_prices):
                            continue # Proximity collision prevented

                        if len(acc_matching_pending) + len(valid_layers) >= 4:
                            break

                        valid_layers.append((lay_i, limit_p))

                    if not valid_layers:
                        continue

                    self.account_last_order_dispatch[acc_num] = now_time
                    active_adapter = self.cent_adapter if acc_info.get("is_cent") else self.adapter

                    # Asymmetric Counter-Trend Risk Sizing (0.50x Risk scaling)
                    effective_risk_pct = acc_risk_tot * (0.50 if cand_is_counter else 1.0)

                    for lay_idx, limit_p in valid_layers:
                        layer_weight = pyramid_weights[lay_idx] if lay_idx < len(pyramid_weights) else 0.25
                        risk_per_layer = effective_risk_pct * layer_weight

                        sl_dist = max(1.0, abs(limit_p - sl))
                        sl_dist_points = sl_dist / active_adapter.spec.point

                        calc_lot = active_adapter.calculate_lot(
                            equity=acc_eq,
                            risk_pct=risk_per_layer,
                            sl_distance_points=sl_dist_points
                        )
                        layer_lot = active_adapter.normalize_lot(calc_lot)
                        if layer_lot <= 0.0:
                            layer_lot = active_adapter.spec.min_lot

                        ct_suffix = f"_CT_{'A' if cand_tp_mode=='EQ' else 'B'}" if cand_is_counter else ""
                        order_cmd = {
                            "action": "ORDER",
                            "account_number": acc_num,
                            "symbol": active_adapter.spec.broker_symbol if acc_info.get("is_cent") else "XAUUSD",
                            "side": side,
                            "lots": layer_lot,
                            "price": limit_p,
                            "sl": sl,
                            "tp": tp,
                            "magic": 1001,
                            "comment": f"{chosen_tf}{ct_suffix}_L{lay_idx+1}_{acc_prof.upper()[:3]}"
                        }

                        asyncio.create_task(self.broadcast(order_cmd))
                        # Optimistic in-flight record to immediately block double-dispatch in same sub-second loop
                        self.live_pending_orders.append({
                            "account_number": acc_num,
                            "type": side,
                            "price": limit_p,
                            "sl": sl,
                            "tp": tp,
                            "ticket": int(now_time * 1000) + lay_idx,
                            "magic": 1001,
                            "comment": order_cmd["comment"]
                        })
                        dispatched_orders_summary.append(f"{acc_prof}_{chosen_tf}({layer_lot:.2f}L)")

                if dispatched_orders_summary:
                    summary_str = ", ".join(list(set(dispatched_orders_summary)))
                    notif = {
                        "id": int(now_time * 1000),
                        "timestamp": datetime.now().strftime("%H:%M:%S"),
                        "title": f"🚀 MULTI-TF GRID DISPATCHED!",
                        "message": f"Accounts: {summary_str}",
                        "type": "BUY" if dir_cmd == "BUY" else "SELL",
                        "price": mid
                    }
                    self.pending_notifications.append(notif)
                    if len(self.pending_notifications) > 10:
                        self.pending_notifications.pop(0)
                    logger.info(f"⚡ [MULTI-TF GRID DISPATCH] Sent orders to {len(target_accounts)} active accounts: {summary_str}")

        now_utc = datetime.now(timezone.utc)
        curr_h = now_utc.hour
        session_label = "Asian Session" if 0 <= curr_h < 8 else ("London Open" if 8 <= curr_h < 13 else ("NY Session" if 13 <= curr_h < 21 else "Off-Hours"))

        # Global Counter-Trend Unlock evaluation for Radar UI (HYBRID_4)
        d1_b = getattr(self, "d1_trend", "NEUTRAL")
        h4_b = getattr(self, "h4_trend", "NEUTRAL")
        both_bear = d1_b in ("STRONG_BEARISH", "WEAK_BEARISH") and h4_b in ("STRONG_BEARISH", "WEAK_BEARISH")
        both_bull = d1_b in ("STRONG_BULLISH", "WEAK_BULLISH") and h4_b in ("STRONG_BULLISH", "WEAK_BULLISH")

        ct_bias_active = both_bear or both_bull
        ct_direction = "BUY" if both_bear else ("SELL" if both_bull else "NONE")

        ct_opsi_a = False
        ct_opsi_b = False
        ct_status = "STANDBY"

        if ct_bias_active:
            m1_dir = tf_dict.get("M1", {}).get("direction")
            m5_dir = tf_dict.get("M5", {}).get("direction")
            if ct_direction == "BUY":
                ct_opsi_a = bool(m1_dir == "BUY" and m5_dir == "BUY")
                micro_ok = any(tf_dict.get(t, {}).get("direction") == "BUY" for t in ["M1", "M2", "M3"])
                inter_ok = any(tf_dict.get(t, {}).get("direction") == "BUY" for t in ["M5", "M15"])
                m15_ev = str(tf_dict.get("M15", {}).get("structure_event", ""))
                m30_ev = str(tf_dict.get("M30", {}).get("structure_event", ""))
                bos_ok = "BULLISH" in m15_ev or "BULLISH" in m30_ev
                ct_opsi_b = bool((micro_ok and inter_ok) or bos_ok)
            else:
                ct_opsi_a = bool(m1_dir == "SELL" and m5_dir == "SELL")
                micro_ok = any(tf_dict.get(t, {}).get("direction") == "SELL" for t in ["M1", "M2", "M3"])
                inter_ok = any(tf_dict.get(t, {}).get("direction") == "SELL" for t in ["M5", "M15"])
                m15_ev = str(tf_dict.get("M15", {}).get("structure_event", ""))
                m30_ev = str(tf_dict.get("M30", {}).get("structure_event", ""))
                bos_ok = "BEARISH" in m15_ev or "BEARISH" in m30_ev
                ct_opsi_b = bool((micro_ok and inter_ok) or bos_ok)

            if ct_opsi_a:
                ct_status = "UNLOCKED (Option A: M1+M5)"
            elif ct_opsi_b:
                ct_status = "UNLOCKED (Option B: BOS/Micro)"
            else:
                ct_status = "HUNTING (Waiting Confluence)"

        # Check if any active account reached goal or is halted
        daily_guard_snapshot = {}
        for acc_id_k, g_info in self.account_daily_guard.items():
            daily_guard_snapshot[acc_id_k] = {
                "daily_start_equity": g_info.get("daily_start_equity", 0.0),
                "daily_start_balance": g_info.get("daily_start_equity", 0.0),
                "peak_daily_pnl": g_info.get("peak_daily_pnl", 0.0),
                "daily_pnl": g_info.get("daily_pnl", 0.0),
                "daily_pnl_pct": g_info.get("daily_pnl_pct", 0.0),
                "weekly_start_balance": g_info.get("weekly_start_balance", 0.0),
                "weekly_pnl": g_info.get("weekly_pnl", 0.0),
                "weekly_pnl_pct": g_info.get("weekly_pnl_pct", 0.0),
                "daily_halted": g_info.get("daily_halted", False),
                "reason": g_info.get("reason", "")
            }

        payload = {
            "source": "LIVE_MT5_TERMINAL",
            "symbol": "XAUUSD",
            "current_price": mid,
            "bid": bid,
            "ask": ask,
            "session": f"{session_label} (LIVE MT5: {bid:.2f}/{ask:.2f})",
            "updated_at": now_utc.isoformat(),
            "session_budget": {
                "active_session": self.current_session_name,
                "session_start_equity": self.session_start_equity,
                "session_pnl": round(curr_sess_pnl, 2),
                "session_peak_pnl": round(self.session_peak_pnl, 2),
                "session_halted": self.session_halted,
                "status_desc": self.session_status_desc,
                "prior_session_pnl": round(self.prior_session_pnl, 2)
            },
            "notifications": list(self.pending_notifications),
            "account": {
                "id": self.active_account_id,
                "company": self.account_company,
                "balance": self.balance,
                "equity": self.equity,
                "unrealized_pnl": self.unrealized_pnl,
                "open_positions": list(self.live_open_positions),
                "pending_orders": list(self.live_pending_orders)
            },
            "htf_bias": {
                "D1": getattr(self, "d1_trend", "NEUTRAL"),
                "H4": getattr(self, "h4_trend", "NEUTRAL"),
                "H1": getattr(self, "h1_trend", "NEUTRAL")
            },
            "counter_trend_unlock": {
                "active_bias": ct_bias_active,
                "counter_direction": ct_direction,
                "status": ct_status,
                "option_a": ct_opsi_a,
                "option_b": ct_opsi_b,
                "mode": "HYBRID_4"
            },
            "reflex_guard": getattr(self, "latest_reflex_guard", {
                "status": "NOMINAL",
                "is_freight_train": False,
                "is_volatile_spike": False,
                "current_atr14": 0.50,
                "last_bar_range": 0.0,
                "base_atr100": 0.50,
                "atr_ratio": 1.0,
                "velocity_threshold": 0.90
            }),
            "account_daily_guard": daily_guard_snapshot,
            "d1_trend": getattr(self, "d1_trend", "NEUTRAL"),
            "h4_trend": getattr(self, "h4_trend", "NEUTRAL"),
            "h1_trend": getattr(self, "h1_trend", "NEUTRAL"),
            "bars": tf_candles.get("M1", []),
            "timeframe_bars": tf_candles,
            "timeframes": tf_dict
        }

        try:
            REPORTS_DIR.mkdir(parents=True, exist_ok=True)
            tmp_path = RADAR_STATE_PATH.with_suffix(".tmp")
            tmp_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
            tmp_path.replace(RADAR_STATE_PATH)
            self._last_radar_save = time.time()
        except Exception as e:
            logger.debug(f"Failed to persist radar state: {e}")

    async def broadcast(self, message: Any):
        """
        Transmits message to MT5 EA clients.
        If message specifies 'account_number', routes via Targeted Unicast Routing (DEC-042)
        specifically to the socket writer(s) of that account, saving MT5 CPU and network bandwidth.
        If no specific account is targeted, or if the targeted account writer is not found,
        safely broadcasts to all active writers.
        """
        payload = message.model_dump_json() if hasattr(message, "model_dump_json") else json.dumps(message)
        payload_bytes = (payload + "\n").encode("utf-8")

        target_acc = None
        if isinstance(message, dict):
            target_acc = message.get("account_number")
        elif hasattr(message, "data") and isinstance(message.data, dict):
            target_acc = message.data.get("account_number")
        elif hasattr(message, "account_number"):
            target_acc = getattr(message, "account_number")

        norm_acc = self._normalize_account_id(target_acc)

        if norm_acc and norm_acc in self.account_writers:
            target_writers = [w for w in self.account_writers[norm_acc] if w in self.active_writers]
            if target_writers:
                for writer in target_writers:
                    try:
                        writer.write(payload_bytes)
                        await writer.drain()
                    except Exception as e:
                        logger.debug(f"Targeted write error to account #{norm_acc}: {e}")
                return

        # Broadcast fallback: when no specific account is targeted or account writer is not yet mapped
        for writer in list(self.active_writers):
            try:
                writer.write(payload_bytes)
                await writer.drain()
            except Exception as e:
                logger.debug(f"Broadcast write error: {e}")

    async def start(self):
        self.server = await asyncio.start_server(self._handle_client, self.host, self.port)
        logger.info("============================================================")
        logger.info(f"🚀 LIVE MT5 BRIDGE CORE RUNNING ON {self.host}:{self.port}")
        logger.info(f"Waiting for MT5 EA (LLMTradingBridge.mq5) to connect...")
        logger.info("============================================================")

    async def stop(self):
        for writer in list(self.active_writers):
            try:
                writer.close()
                await writer.wait_closed()
            except Exception:
                pass
        self.active_writers.clear()
        self.account_writers.clear()
        if self.server:
            self.server.close()
            await self.server.wait_closed()


MT5BridgeServer = LiveMT5BridgeCore


class BridgeMessageType:
    HANDSHAKE = "HANDSHAKE"
    BAR = "BAR"
    TICK = "TICK"
    ORDER_REQUEST = "ORDER_REQUEST"
    ORDER_STATUS = "ORDER_STATUS"
    HEARTBEAT = "HEARTBEAT"
    ERROR = "ERROR"


class BridgeMessage:
    def __init__(self, type=None, symbol=None, data=None):
        self.type = type
        self.symbol = symbol
        self.data = data or {}

    def model_dump_json(self):
        return json.dumps({"type": self.type, "symbol": self.symbol, "data": self.data})


async def main():
    bridge = LiveMT5BridgeCore()
    await bridge.start()
    try:
        await asyncio.Event().wait()
    finally:
        await bridge.stop()


if __name__ == "__main__":
    asyncio.run(main())
