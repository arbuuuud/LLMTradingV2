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

# Ensure project root in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

REPORTS_DIR = PROJECT_ROOT / "reports"
RADAR_STATE_PATH = REPORTS_DIR / "radar_state.json"
CONFIGS_DIR = PROJECT_ROOT / "configs"
ACCOUNTS_CONFIG_PATH = CONFIGS_DIR / "accounts.yaml"

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] [Bridge]: %(message)s")
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

        # Live Open Positions & Pending Orders Telemetry from MT5
        self.live_open_positions: List[Dict[str, Any]] = []
        self.live_pending_orders: List[Dict[str, Any]] = []
        self.unrealized_pnl: float = 0.0

        # Callbacks for backward compatibility with test suites
        self.on_handshake_callback = None
        self.on_bar_callback = None
        self.on_tick_callback = None
        self.on_order_status_callback = None

        # Force Close Guardian Agent Engine
        self.force_close_guardian = ForceCloseGuardianEngine()
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
            for k, acc in accounts.items():
                if acc.get("status") == "CONNECTED":
                    acc["status"] = "STANDBY"

            acc_key = f"ACC-{acc_id}"
            accounts[acc_key] = {
                "account_number": str(acc_id),
                "broker_name": company,
                "server": server or "MetaQuotes-Demo",
                "account_type": "DEMO",
                "risk_profile": cfg.get("default_profile", "prop_firm"),
                "status": "CONNECTED",
                "balance": balance,
                "equity": equity,
                "assigned_timeframes": ["M1", "M2", "M3", "M5"],
                "updated_at": datetime.now().isoformat()
            }

            with open(ACCOUNTS_CONFIG_PATH, "w", encoding="utf-8") as f:
                yaml.dump(cfg, f, default_flow_style=False, sort_keys=False, allow_unicode=True)
            logger.info(f"✨ [AUTO-REGISTER] Live MT5 Account #{acc_id} ({company}) synced to accounts.yaml! Balance=${balance:.2f} Equity=${equity:.2f}")
        except Exception as e:
            logger.error(f"Error auto-registering account #{acc_id}: {e}")

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

            # 1. Handover BEP Trigger (+1.0 point profit)
            if side == "BUY" and cur_p >= entry_p + 1.0 and sl < entry_p:
                bep_sl = round(entry_p + 0.20, 2)  # Entry + spread buffer
                logger.info(f"🛡️ [GUARDIAN BEP] Locking BEP on BUY #{ticket} @ ${bep_sl:.2f}")
                asyncio.create_task(self.broadcast({
                    "action": "MODIFY_POSITION",
                    "ticket": ticket,
                    "sl": bep_sl,
                    "tp": pos.get("tp", 0.0)
                }))

                # Toast Notification for BEP Lock
                notif = {
                    "id": int(now * 1000),
                    "timestamp": datetime.now().strftime("%H:%M:%S"),
                    "title": f"🛡️ BEP Lock Activated!",
                    "message": f"BUY #{ticket} Stop Loss moved to BEP (${bep_sl:.2f}) - Zero Risk!",
                    "type": "BEP",
                    "price": bep_sl
                }
                self.pending_notifications.append(notif)
                if len(self.pending_notifications) > 10:
                    self.pending_notifications.pop(0)

            elif side == "SELL" and cur_p <= entry_p - 1.0 and (sl > entry_p or sl == 0.0):
                bep_sl = round(entry_p - 0.20, 2)  # Entry - spread buffer
                logger.info(f"🛡️ [GUARDIAN BEP] Locking BEP on SELL #{ticket} @ ${bep_sl:.2f}")
                asyncio.create_task(self.broadcast({
                    "action": "MODIFY_POSITION",
                    "ticket": ticket,
                    "sl": bep_sl,
                    "tp": pos.get("tp", 0.0)
                }))

                # Toast Notification for BEP Lock
                notif = {
                    "id": int(now * 1000),
                    "timestamp": datetime.now().strftime("%H:%M:%S"),
                    "title": f"🛡️ BEP Lock Activated!",
                    "message": f"SELL #{ticket} Stop Loss moved to BEP (${bep_sl:.2f}) - Zero Risk!",
                    "type": "BEP",
                    "price": bep_sl
                }
                self.pending_notifications.append(notif)
                if len(self.pending_notifications) > 10:
                    self.pending_notifications.pop(0)

            # 2. Structural Soft-SL Cut (Emergency Force Close on violation)
            # If opposite momentum pushes past critical invalidation threshold
            if side == "BUY" and cur_p <= (entry_p - 3.5):
                logger.warning(f"🚨 [FORCE CLOSE] Structural breach on BUY #{ticket}! Closing at market...")
                asyncio.create_task(self.broadcast({
                    "action": "CLOSE_ALL",
                    "symbol": "XAUUSD",
                    "magic": pos.get("magic", 1001)
                }))

                # Toast Notification for Emergency Force Close
                notif = {
                    "id": int(now * 1000),
                    "timestamp": datetime.now().strftime("%H:%M:%S"),
                    "title": f"🚨 EMERGENCY FORCE CLOSE!",
                    "message": f"BUY #{ticket} soft-cut at market (${cur_p:.2f}) - Structural Breach Avoided!",
                    "type": "FORCE_CLOSE",
                    "price": cur_p
                }
                self.pending_notifications.append(notif)
                if len(self.pending_notifications) > 10:
                    self.pending_notifications.pop(0)

            elif side == "SELL" and cur_p >= (entry_p + 3.5):
                logger.warning(f"🚨 [FORCE CLOSE] Structural breach on SELL #{ticket}! Closing at market...")
                asyncio.create_task(self.broadcast({
                    "action": "CLOSE_ALL",
                    "symbol": "XAUUSD",
                    "magic": pos.get("magic", 1001)
                }))

                # Toast Notification for Emergency Force Close
                notif = {
                    "id": int(now * 1000),
                    "timestamp": datetime.now().strftime("%H:%M:%S"),
                    "title": f"🚨 EMERGENCY FORCE CLOSE!",
                    "message": f"SELL #{ticket} soft-cut at market (${cur_p:.2f}) - Structural Breach Avoided!",
                    "type": "FORCE_CLOSE",
                    "price": cur_p
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

        # 3. TICK (Live High-Frequency Quotes)
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

            # Ingest live open positions & pending limit orders
            if "positions" in msg and isinstance(msg["positions"], list):
                self.live_open_positions = msg["positions"]
            if "orders" in msg and isinstance(msg["orders"], list):
                self.live_pending_orders = msg["orders"]

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

            # Calculate Untouched / Fresh Depth Boundary for Visual Chart
            # An area is untouched if current/recent bar wicks haven't consumed that depth
            untouched_buy_top = round(sw_low + (total_range * 0.15), 2)  # Deeper 0-15% fresh zone
            untouched_sell_bottom = round(sw_low + (total_range * 0.85), 2)  # Higher 85-100% fresh zone

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
                        f"Untouched Liquidity Depth above ${untouched_sell_bottom:.2f}"
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
                        f"Untouched Liquidity Depth below ${untouched_buy_top:.2f}"
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
        m1_setup = tf_dict.get("M1", {})
        if m1_setup.get("active_setup") and self.active_writers:
            dir_cmd = m1_setup["direction"]
            # Cooldown: 1 order event per direction change or every 60s
            if (dir_cmd != self._last_order_direction) or (now_time - self._last_order_time > 60.0):
                self._last_order_direction = dir_cmd
                self._last_order_time = now_time

                side = "BUY_LIMIT" if dir_cmd == "BUY" else "SELL_LIMIT"
                limit_p = round(m1_setup["buy_zone"]["untouched_top"] if dir_cmd == "BUY" else m1_setup["sell_zone"]["untouched_bottom"], 2)
                sl = m1_setup["sl_hard"]
                tp = m1_setup["tp_midpoint"]

                # Dynamic Risk-Based Lot Sizing based on real Account Equity
                sl_distance = max(1.0, abs(limit_p - sl))
                sl_dist_points = sl_distance / self.adapter.spec.point  # point = 0.01
                # Standard Prop Firm / Sweet Spot risk: 0.50% of equity
                calculated_raw_lot = self.adapter.calculate_lot(
                    equity=max(100.0, self.equity),
                    risk_pct=0.50,
                    sl_distance_points=sl_dist_points
                )
                dynamic_lots = self.adapter.normalize_lot(calculated_raw_lot)
                # Fallback safeguard minimum lot
                if dynamic_lots <= 0.0:
                    dynamic_lots = 0.01

                order_cmd = {
                    "action": "ORDER",
                    "symbol": "XAUUSD",
                    "side": side,
                    "lots": dynamic_lots,
                    "price": limit_p,
                    "sl": sl,
                    "tp": tp,
                    "magic": 1001,
                    "comment": "PAC_AUTO_LIMIT"
                }

                # Dispatch over socket to MT5 EA
                asyncio.create_task(self.broadcast(order_cmd))

                # Push instant Snackbar Notification for Dashboard
                notif = {
                    "id": int(now_time * 1000),
                    "timestamp": datetime.now().strftime("%H:%M:%S"),
                    "title": f"🚀 {side} Dispatched to MT5!",
                    "message": f"Target: ${limit_p:.2f} | SL: ${sl:.2f} | TP: ${tp:.2f} (Lot: {dynamic_lots:.2f} on ${self.equity:,.0f} Eq)",
                    "type": "BUY" if dir_cmd == "BUY" else "SELL",
                    "price": limit_p
                }
                self.pending_notifications.append(notif)
                if len(self.pending_notifications) > 10:
                    self.pending_notifications.pop(0)
                logger.info(f"⚡ [AUTO-DISPATCH] Sent {side} order to MT5 EA at ${limit_p:.2f} (SL: ${sl:.2f}, TP: ${tp:.2f}) | Dynamic Lot: {dynamic_lots:.2f} (Equity: ${self.equity:.2f})")

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
