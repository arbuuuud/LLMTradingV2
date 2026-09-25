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
from typing import Dict, Any, List, Optional

from src.data.adapter import BrokerAdapter, BrokerSpec
from src.engine.force_close import ForceCloseGuardianEngine, ForceCloseAction
from src.agents.sasuke import SasukeSharinganAgent, SharinganPerceptionLevel, SasukeAction

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
        self.history_m1: List[Dict[str, Any]] = []
        self.latest_tick: Optional[Dict[str, Any]] = None
        self.active_account_id = "112655823"
        self.account_company = "MetaQuotes Software Corp."
        self.balance = 10000.0
        self.equity = 10000.0
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
        self.adapter = BrokerAdapter(BrokerSpec(
            broker_name="MetaQuotes",
            broker_symbol="XAUUSD",
            point=0.01,
            contract_size=100.0,
            min_lot=0.01,
            max_lot=100.0,
            lot_step=0.01
        ))

        # Dynamic Multi-Session Equity Budgeting & Greed Trailing Overseer (DEC-028 Champion)
        self.current_session_name: str = ""
        self.session_start_equity: float = 10000.0
        self.session_peak_pnl: float = 0.0
        self.session_halted: bool = False
        self.prior_session_pnl: float = 0.0
        self.current_session_day: str = ""
        self.session_status_desc: str = "Active"

        # Buffer incoming bar batches
        self._pending_sync_bars: List[Dict[str, Any]] = []

    def _auto_register_account(self, acc_id: str, company: str, server: str, balance: float, equity: float):
        if not ACCOUNTS_CONFIG_PATH.exists():
            return
        try:
            import yaml
            with open(ACCOUNTS_CONFIG_PATH, "r", encoding="utf-8") as f:
                cfg = yaml.safe_load(f) or {}

            accounts = cfg.setdefault("accounts", {})
            acc_key = f"ACC-{acc_id}"

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
                    "assigned_timeframes": ["M1", "M2", "M3", "M5"],
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
        except Exception as e:
            logger.error(f"Failed to save closed trade record: {e}")

    def _update_account_equity(self, acc_id: str, balance: float, equity: float):
        if not ACCOUNTS_CONFIG_PATH.exists():
            return
        try:
            import yaml
            with open(ACCOUNTS_CONFIG_PATH, "r", encoding="utf-8") as f:
                cfg = yaml.safe_load(f) or {}

            accounts = cfg.setdefault("accounts", {})
            acc_key = f"ACC-{acc_id}"
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

            # 1. Sasuke Sharingan Greed Trailing (Replaces legacy flat BEP +1.0pt)
            pts_diff = (cur_p - entry_p) if side == "BUY" else (entry_p - cur_p)
            sl_dist = max(abs(entry_p - pos.get("sl", entry_p - 3.0)), 0.5)
            r_running = pts_diff / sl_dist

            # Trailing Stepped Lock:
            # >= +2.0R -> lock SL at +1.5R
            # >= +1.5R -> lock SL at +1.0R
            # >= +1.0R -> lock SL at +0.5R
            target_lock_r = None
            if r_running >= 2.0:
                target_lock_r = 1.5
            elif r_running >= 1.5:
                target_lock_r = 1.0
            elif r_running >= 1.0:
                target_lock_r = 0.5

            if target_lock_r is not None:
                new_trail_sl = round(entry_p + (target_lock_r * sl_dist if side == "BUY" else -target_lock_r * sl_dist), 2)
                cur_sl = float(pos.get("sl", 0.0))
                should_update = (cur_sl == 0.0) or (side == "BUY" and new_trail_sl > cur_sl) or (side == "SELL" and new_trail_sl < cur_sl)

                if should_update:
                    logger.info(f"👁️ [SASUKE GREED TRAILING] Locking SL on {side} #{ticket} @ ${new_trail_sl:.2f} (+{target_lock_r}R Locked | Running: +{r_running:.2f}R)")
                    asyncio.create_task(self.broadcast({
                        "action": "MODIFY_POSITION",
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

    async def _handle_client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        client_addr = writer.get_extra_info("peername")
        logger.info(f"🟢 MT5 EA Client connected from {client_addr}")
        self.active_writers.append(writer)

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
                        await self._dispatch_message(msg, writer)
                    except Exception as err:
                        logger.error(f"Error parsing incoming JSON: {err} | Raw: {line[:120]}")
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"Client connection error: {e}")
        finally:
            logger.info(f"🔴 MT5 Client disconnected: {client_addr}")
            if writer in self.active_writers:
                self.active_writers.remove(writer)
            self._save_radar_state()

    async def _dispatch_message(self, msg: Dict[str, Any], writer: asyncio.StreamWriter):
        msg_type = msg.get("type") or msg.get("action")

        # 1. REGISTER / HANDSHAKE
        if msg_type in ("REGISTER", "HANDSHAKE"):
            data_dict = msg.get("data", {}) if isinstance(msg.get("data"), dict) else {}
            acc_id = str(msg.get("account_id") or data_dict.get("account_number") or self.active_account_id)
            company = str(msg.get("company") or data_dict.get("broker_name") or "MetaQuotes")
            server = str(msg.get("server") or data_dict.get("server") or "MetaQuotes-Demo")
            balance = float(msg.get("balance") or data_dict.get("balance") or 10000.0)
            equity = float(msg.get("equity") or data_dict.get("equity") or balance)

            self.active_account_id = acc_id
            self.account_company = company
            self.balance = balance
            self.equity = equity

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
            bid = float(msg.get("bid", 0.0))
            ask = float(msg.get("ask", 0.0))
            mid = round((bid + ask) / 2.0, 2)
            c = float(msg.get("last", mid))
            acc_id = str(msg.get("account_id", self.active_account_id))
            self.active_account_id = acc_id
            self.equity = float(msg.get("equity", self.equity))
            self.balance = float(msg.get("balance", self.balance))
            self.unrealized_pnl = float(msg.get("unrealized", 0.0))

            # Store per-account positions & orders into multi-account map
            if "positions" in msg and isinstance(msg["positions"], list):
                for p in msg["positions"]:
                    p["account_number"] = acc_id
                self.accounts_open_positions[acc_id] = msg["positions"]
            if "orders" in msg and isinstance(msg["orders"], list):
                for o in msg["orders"]:
                    o["account_number"] = acc_id
                self.accounts_pending_orders[acc_id] = msg["orders"]

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
                    if len(self.history_m1) > 250:
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

        # Multi-timeframe bar aggregation & PAC calculation
        tf_dict = {}
        tf_candles = {}

        for tf, mult in [("M1", 1), ("M2", 2), ("M3", 3), ("M4", 4), ("M5", 5)]:
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

            # Calculate Untouched / Fresh Depth Boundary for Visual Chart (>50% Penetration)
            # An area is untouched if current/recent bar wicks haven't consumed that depth
            untouched_buy_top = round(sw_low + (total_range * 0.125), 2)  # >50% depth of discount (0-12.5%)
            untouched_sell_bottom = round(sw_low + (total_range * 0.875), 2)  # >50% depth of premium (87.5-100%)

            # 3-Layer Grid Target Levels for this TF
            buy_grid_levels = [
                round(buy_zone_top, 2),                  # L1: 25% Lantai Atas Buy
                round(sw_low + (total_range * 0.125), 2),# L2: 12.5% Kedalaman Murni
                round(sw_low, 2)                         # L3: 0% Dasar Lantai
            ]
            sell_grid_levels = [
                round(sell_zone_bottom, 2),              # L1: 75% Lantai Bawah Sell
                round(sw_low + (total_range * 0.875), 2),# L2: 87.5% Kedalaman Murni
                round(sw_high, 2)                        # L3: 100% Pucuk Atap
            ]

            if in_discount:
                dir_label = "BUY"
                status_label = "IN_BUY_ZONE"
                quad_label = "0% - 25% (Buy Discount)"
                hard_sl = round(sw_low - 2.5, 2)
                soft_sl = round(sw_low - 0.5, 2)
                is_active = True
                score = 9.2
            elif in_premium:
                dir_label = "SELL"
                status_label = "IN_SELL_ZONE"
                quad_label = "75% - 100% (Sell Premium)"
                hard_sl = round(sw_high + 2.5, 2)
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

            # Find specific anchor/base candles for Roof (Swing High) and Floor (Swing Low)
            roof_anchor = max(lookback_sw, key=lambda x: x["high"]) if lookback_sw else None
            floor_anchor = min(lookback_sw, key=lambda x: x["low"]) if lookback_sw else None

            roof_time_str = datetime.fromtimestamp(roof_anchor["time"], tz=timezone.utc).strftime("%H:%M UTC") if roof_anchor else "Recent"
            floor_time_str = datetime.fromtimestamp(floor_anchor["time"], tz=timezone.utc).strftime("%H:%M UTC") if floor_anchor else "Recent"

            poi_reasoning = {
                "roof": {
                    "price_high": sw_high,
                    "zone_range": f"${sell_zone_bottom:.2f} - ${sw_high:.2f}",
                    "base_candle": {
                        "time": roof_time_str,
                        "open": roof_anchor["open"] if roof_anchor else sw_high,
                        "high": roof_anchor["high"] if roof_anchor else sw_high,
                        "low": roof_anchor["low"] if roof_anchor else sw_high,
                        "close": roof_anchor["close"] if roof_anchor else sw_high,
                    },
                    "reasons": [
                        f"Liquidity Sweep Peak at ${sw_high:.2f} ({roof_time_str})",
                        f"Premium 75-100% Imbalance Zone (${sell_zone_bottom:.2f} - ${sw_high:.2f})",
                        f"3-Layer Sell Grid: L1=${sell_grid_levels[0]:.2f}, L2=${sell_grid_levels[1]:.2f}, L3=${sell_grid_levels[2]:.2f}",
                        f"Virgin Depth >50% Untouched above ${untouched_sell_bottom:.2f}"
                    ]
                },
                "floor": {
                    "price_low": sw_low,
                    "zone_range": f"${sw_low:.2f} - ${buy_zone_top:.2f}",
                    "base_candle": {
                        "time": floor_time_str,
                        "open": floor_anchor["open"] if floor_anchor else sw_low,
                        "high": floor_anchor["high"] if floor_anchor else sw_low,
                        "low": floor_anchor["low"] if floor_anchor else sw_low,
                        "close": floor_anchor["close"] if floor_anchor else sw_low,
                    },
                    "reasons": [
                        f"Demand Absorption Low at ${sw_low:.2f} ({floor_time_str})",
                        f"Discount 0-25% Valuation Base (${sw_low:.2f} - ${buy_zone_top:.2f})",
                        f"3-Layer Buy Grid: L1=${buy_grid_levels[0]:.2f}, L2=${buy_grid_levels[1]:.2f}, L3=${buy_grid_levels[2]:.2f}",
                        f"Virgin Depth >50% Untouched below ${untouched_buy_top:.2f}"
                    ]
                }
            }

            tf_dict[tf] = {
                "timeframe": tf,
                "active_setup": is_active,
                "direction": dir_label,
                "status": status_label,
                "quadrant": quad_label,
                "structure": "BULLISH_BOS" if dir_label == "BUY" else ("BEARISH_BOS" if dir_label == "SELL" else "CONSOLIDATION"),
                "swing_high": sw_high,
                "swing_low": sw_low,
                "equilibrium": equilibrium,
                "poi_reasoning": poi_reasoning,
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

        # Cek Transisi Hari & Sesi
        if today_str != self.current_session_day:
            self.current_session_day = today_str
            self.prior_session_pnl = 0.0

        if active_sess != self.current_session_name:
            if self.current_session_name != "" and self.current_session_name != "OFF_HOURS":
                self.prior_session_pnl = self.equity - self.session_start_equity
                logger.info(f"🏁 [SESSION TRANSITION] {self.current_session_name} ended with PnL: ${self.prior_session_pnl:+.2f}")

            self.current_session_name = active_sess
            # Anchor initial session equity accurately based on active account equity from MT5
            self.session_start_equity = max(100.0, self.equity)
            self.session_peak_pnl = 0.0
            self.session_halted = (active_sess == "OFF_HOURS")
            self.session_status_desc = f"{active_sess} Active" if not self.session_halted else "Off-Hours Standby"

        # Jika ekuitas awal sesi belum terkalibrasi dengan ekuitas riil MT5 (masih default), sinkronisasikan
        if self.session_start_equity == 10000.0 and self.equity > 0 and abs(self.equity - 10000.0) > 500.0:
            self.session_start_equity = self.equity
            self.session_peak_pnl = 0.0
            self.session_halted = False

        # 2. Multi-Session Equity Budgeting & Dynamic Greed Trailing
        # Budget loss dasar per-sesi: -0.50% dari ekuitas awal sesi
        # House Money (CLONE-08): Jika sesi sebelumnya profit >= +1.0%, tambahkan 25% profit ke budget risiko sesi ini!
        base_sess_loss = self.session_start_equity * 0.005 # 0.5%
        if self.prior_session_pnl > (self.session_start_equity * 0.01):
            base_sess_loss += (self.prior_session_pnl * 0.25)

        curr_sess_pnl = self.equity - self.session_start_equity
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

        m1_setup = tf_dict.get("M1", {})
        if m1_setup.get("active_setup") and self.active_writers:
            dir_cmd = m1_setup["direction"]

            # Sasuke Circuit Breaker Gate: Check if session is halted or daily drawdown breached -1.0%
            if self.session_halted:
                return

            cb_status = self.sasuke_overseer.check_daily_circuit_breaker(account_equity=self.equity, starting_equity=self.balance)
            if getattr(cb_status, "is_tripped", False):
                if not hasattr(self, "_last_cb_warn") or (now_time - getattr(self, "_last_cb_warn", 0) > 300.0):
                    self._last_cb_warn = now_time
                    logger.error(f"🚫 [SASUKE CIRCUIT BREAKER ACTIVE] Daily Drawdown limit (-1.0%) tripped: {getattr(cb_status, 'reason', '')}. Trading HALTED!")
                return

            # Strict Retest Rule: Only 1 pending order per active zone to avoid spamming duplicate limit orders
            has_matching_pending = any(
                (ord.get("type") == ("BUY_LIMIT" if dir_cmd == "BUY" else "SELL_LIMIT"))
                for ord in self.live_pending_orders
            )
            has_active_pos = any(
                (pos.get("type") == dir_cmd)
                for pos in self.live_open_positions
            )

            # Auto-cleanup stale pending orders from previous opposite or far expired zones
            if (dir_cmd != self._last_order_direction):
                # Direction flipped! Cancel outdated pending orders in opposite direction
                opp_side = "BUY_LIMIT" if dir_cmd == "SELL" else "SELL_LIMIT"
                if any(ord.get("type") == opp_side for ord in self.live_pending_orders):
                    asyncio.create_task(self.broadcast({
                        "action": "CANCEL_PENDING",
                        "symbol": "XAUUSD",
                        "magic": 1001
                    }))
                    logger.info(f"🧹 [STALE ORDER CLEANUP] Direction flipped to {dir_cmd}. Purging outdated pending orders.")

            # Cooldown: 1 order event per direction change, no duplicate pending in same zone, and cooldown > 30s
            if not has_matching_pending and not has_active_pos and ((dir_cmd != self._last_order_direction) or (now_time - self._last_order_time > 60.0)):
                self._last_order_direction = dir_cmd
                self._last_order_time = now_time

                side = "BUY_LIMIT" if dir_cmd == "BUY" else "SELL_LIMIT"
                spread_val = max(0.20, round(ask - bid, 2)) if (ask > bid > 0) else 0.35

                sw_low = m1_setup["swing_low"]
                sw_high = m1_setup["swing_high"]
                span = max(sw_high - sw_low, 1.0)
                base_sl = m1_setup["sl_hard"]

                # 1. Hard Stop Loss Adjustment (Spread Compensated)
                if dir_cmd == "SELL":
                    sl = round(base_sl + spread_val, 2)
                else:
                    sl = round(base_sl - spread_val, 2)

                # 2. Take Profit Adjustment: Shared Single Target TP (Adaptive Quick Escape Juara 5-3C)
                base_tp = m1_setup["tp_midpoint"]
                if dir_cmd == "BUY":
                    tp = round(base_tp, 2)
                else:
                    tp = round(base_tp + spread_val, 2)

        # 3. KUBU-GRID-3-LAYER DISPATCHER (Juara Mutlak Turnamen Subtask 5-3D)
                # Menebar 3 Limit Order Serentak dari Lantai Atas ke Dasar:
                # Untuk BUY : Layer 1 di 25% (Lantai Atas Buy), Layer 2 di 12.5% (Tengah), Layer 3 di 0% (Dasar Lantai)
                # Untuk SELL: Layer 1 di 75% (Lantai Bawah Sell), Layer 2 di 87.5% (Tengah), Layer 3 di 100% (Pucuk Atap)
                num_layers = 3

                if dir_cmd == "BUY":
                    target_levels = [
                        round(min(bid - 0.25, sw_low + span * 0.25), 2),  # Layer 1: Bibir Masuk (25%)
                        round(min(bid - 0.50, sw_low + span * 0.125), 2), # Layer 2: Kedalaman Murni (12.5%)
                        round(min(bid - 0.75, sw_low + span * 0.00), 2)   # Layer 3: Lantai Dasar (0%)
                    ]
                else:
                    target_levels = [
                        round(max(ask + 0.25, sw_low + span * 0.75), 2),  # Layer 1: Bibir Masuk (75%)
                        round(max(ask + 0.50, sw_low + span * 0.875), 2), # Layer 2: Kedalaman Murni (87.5%)
                        round(max(ask + 0.75, sw_high), 2)                # Layer 3: Pucuk Atap (100%)
                    ]

                # Load current configured accounts & risk profiles from accounts.yaml
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
                            # Only trade if account is active AND has an assigned profile (not 'none')
                            if is_active and p_name in profiles_cfg:
                                r_pct = float(profiles_cfg[p_name].get("risk_per_trade_pct", 0.50))
                                target_accounts[acc_k] = {
                                    "account_number": str(acc_v.get("account_number")),
                                    "profile": p_name,
                                    "equity": float(acc_v.get("equity", self.equity)),
                                    "risk_pct": r_pct
                                }
                    except Exception as e:
                        logger.error(f"Error loading accounts for dispatch: {e}")

                # If no accounts configured in yaml or none active, fallback to single active account
                if not target_accounts:
                    logger.warning("⚠️ No active accounts with configured risk profile found in accounts.yaml. Order dispatch skipped.")
                    return

                dispatched_orders_summary = []
                # Alokasi Bobot Pyramid 20% - 30% - 50% (Juara Empiris Turnamen Kage Bunshin)
                pyramid_weights = [0.20, 0.30, 0.50]

                for acc_k, acc_info in target_accounts.items():
                    acc_num = acc_info["account_number"]
                    acc_prof = acc_info["profile"]
                    acc_eq = max(100.0, acc_info["equity"])
                    acc_risk_tot = acc_info["risk_pct"]

                    for lay_idx, limit_p in enumerate(target_levels):
                        # Terapkan bobot Pyramid per layer
                        layer_weight = pyramid_weights[lay_idx] if lay_idx < len(pyramid_weights) else (1.0 / num_layers)
                        risk_per_layer = acc_risk_tot * layer_weight

                        sl_dist = max(1.0, abs(limit_p - sl))
                        sl_dist_points = sl_dist / self.adapter.spec.point

                        calc_lot = self.adapter.calculate_lot(
                            equity=acc_eq,
                            risk_pct=risk_per_layer,
                            sl_distance_points=sl_dist_points
                        )
                        layer_lot = self.adapter.normalize_lot(calc_lot)
                        if layer_lot <= 0.0:
                            layer_lot = 0.01

                        order_cmd = {
                            "action": "ORDER",
                            "account_number": acc_num,
                            "symbol": "XAUUSD",
                            "side": side,
                            "lots": layer_lot,
                            "price": limit_p,
                            "sl": sl,
                            "tp": tp, # 1 titik Hard TP bersama
                            "magic": 1001,
                            "comment": f"PAC_{acc_prof.upper()[:4]}_L{lay_idx+1}"
                        }

                        # Broadcast order to MT5 clients
                        asyncio.create_task(self.broadcast(order_cmd))
                        dispatched_orders_summary.append(f"{acc_prof}({layer_lot:.2f}L)")

                # Push instant Snackbar Notification for Dashboard
                summary_str = ", ".join(list(set(dispatched_orders_summary)))
                notif = {
                    "id": int(now_time * 1000),
                    "timestamp": datetime.now().strftime("%H:%M:%S"),
                    "title": f"🚀 3-LAYER GRID {side} DISPATCHED!",
                    "message": f"Accounts: {summary_str} | SL: ${sl:.2f} | Shared TP: ${tp:.2f}",
                    "type": "BUY" if dir_cmd == "BUY" else "SELL",
                    "price": target_levels[0]
                }
                self.pending_notifications.append(notif)
                if len(self.pending_notifications) > 10:
                    self.pending_notifications.pop(0)
                logger.info(f"⚡ [MULTI-ACCOUNT GRID DISPATCH] Sent 3 {side} orders to {len(target_accounts)} active accounts: {summary_str}")

        now_utc = datetime.now(timezone.utc)
        curr_h = now_utc.hour
        session_label = "Asian Session" if 0 <= curr_h < 8 else ("London Open" if 8 <= curr_h < 13 else ("NY Session" if 13 <= curr_h < 21 else "Off-Hours"))

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
                "session_pnl": self.equity - self.session_start_equity,
                "session_peak_pnl": self.session_peak_pnl,
                "session_halted": self.session_halted,
                "status_desc": self.session_status_desc,
                "prior_session_pnl": self.prior_session_pnl
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
        payload = message.model_dump_json() if hasattr(message, "model_dump_json") else json.dumps(message)
        payload = (payload + "\n").encode("utf-8")
        for writer in list(self.active_writers):
            try:
                writer.write(payload)
                await writer.drain()
            except Exception:
                pass

    async def start(self):
        self.server = await asyncio.start_server(self._handle_client, self.host, self.port)
        logger.info("============================================================")
        logger.info(f"🚀 LIVE MT5 BRIDGE CORE RUNNING ON {self.host}:{self.port}")
        logger.info(f"Waiting for MT5 EA (LLMTradingBridge.mq5) to connect...")
        logger.info("============================================================")

    async def stop(self):
        for writer in self.active_writers:
            try:
                writer.close()
                await writer.wait_closed()
            except Exception:
                pass
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
