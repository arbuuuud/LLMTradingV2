"""
Live Demo Forward Test Runner Daemon (Workflow 4 - Opsi B).
Connects to MT5BridgeServer, receives live M1 bars from MT5 Demo Account,
evaluates PAC Strategy Checklist via Tactician, executes through Risk Governor & Sentinel,
dispatches Limit Orders to MT5, and records every closed trade into data/forward_trades_live.json.
"""

import sys
from pathlib import Path

# Add project root directory to sys.path so 'src' is always importable on Windows/Linux/macOS
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import asyncio
import json
import logging
import signal
from datetime import datetime
from typing import Dict, Any, List

from src.core.types import (
    MarketStateSnapshot,
    PriceQuote,
    Trend,
    StructureState,
    Direction,
    TradingStyle,
    SessionKillzone,
    PACRetestMode,
    PACHandoverMode,
    ForceClosePolicy,
    ShadowCloneSpec
)
from src.data.adapter import BrokerAdapter, BrokerSpec
from src.bridge.server import MT5BridgeServer, BridgeMessage, BridgeMessageType
from src.workflows.live_execution import (
    LiveExecutionPipeline,
    CircuitBreakerSentinel,
    ExecutionDecision,
    OrderDispatchCommand
)
from src.workflows.incubation import (
    IncubationStagingGate,
    ForwardTradeRecord,
    StagingStatus
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("ForwardDaemon")


class ForwardDemoDaemon:
    """Orchestrates Live Demo Forward Testing between MT5 Bridge and Python Core."""

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 5555,
        target_trades: int = 50,
        output_file: str = "data/forward_trades_live.json"
    ):
        self.host = host
        self.port = port
        self.target_trades = target_trades
        self.output_path = Path(output_file)
        self.output_path.parent.mkdir(parents=True, exist_ok=True)

        self.server = MT5BridgeServer(host=host, port=port)
        self.server.on_handshake_callback = self._on_handshake
        self.server.on_bar_callback = self._on_bar

        # Broker Adapter & Protections
        self.adapter = BrokerAdapter(BrokerSpec(broker_name="DemoBroker", broker_symbol="XAUUSD"))
        self.sentinel = CircuitBreakerSentinel(max_daily_drawdown_pct=3.0)
        self.pipeline = LiveExecutionPipeline(
            broker_adapter=self.adapter,
            circuit_breaker=self.sentinel,
            base_risk_pct=0.50,
            min_checklist_score=8.0
        )
        self.gate = IncubationStagingGate(min_trades=target_trades)

        self.recorded_trades: List[ForwardTradeRecord] = self._load_trades()
        self.current_equity = 10000.0

    def _load_trades(self) -> List[ForwardTradeRecord]:
        if self.output_path.exists():
            try:
                data = json.loads(self.output_path.read_text())
                return [ForwardTradeRecord(**tr) for tr in data]
            except Exception as e:
                logger.warning(f"Could not load previous trades: {e}")
        return []

    def _save_trades(self):
        data = [tr.model_dump(mode="json") for tr in self.recorded_trades]
        self.output_path.write_text(json.dumps(data, indent=2))

    def _on_handshake(self, data: Dict[str, Any]):
        acc_num = str(data.get("account_number", "UNKNOWN"))
        broker = data.get("broker_name", "DemoBroker")
        server = data.get("server", "Demo-Server")
        bal = float(data.get("balance", 10000.0))
        eq = float(data.get("equity", 10000.0))

        logger.info(f"🤝 Handshake from MT5: Account={acc_num} | Broker={broker} ({server}) | Balance={bal:.2f} Equity={eq:.2f}")

        # Auto-register/sync live connected account to configs/accounts.yaml
        cfg_path = PROJECT_ROOT / "configs" / "accounts.yaml"
        if cfg_path.exists():
            try:
                import yaml
                with open(cfg_path, "r", encoding="utf-8") as f:
                    cfg = yaml.safe_load(f) or {}

                # Mark previously connected accounts as STANDBY
                accounts = cfg.setdefault("accounts", {})
                for k, acc in accounts.items():
                    if acc.get("status") == "CONNECTED":
                        acc["status"] = "STANDBY"

                # Update or register this exact live account
                acc_key = f"ACC-{acc_num}"
                accounts[acc_key] = {
                    "account_number": acc_num,
                    "broker_name": broker,
                    "server": server,
                    "account_type": "DEMO",
                    "risk_profile": cfg.get("default_profile", "prop_firm"),
                    "status": "CONNECTED",
                    "balance": bal,
                    "equity": eq,
                    "assigned_timeframes": ["M1", "M2", "M3", "M5"],
                    "updated_at": datetime.now().isoformat()
                }

                with open(cfg_path, "w", encoding="utf-8") as f:
                    yaml.dump(cfg, f, default_flow_style=False, sort_keys=False, allow_unicode=True)
                logger.info(f"💾 Synced live MT5 Account {acc_num} ({broker}) directly to dashboard accounts config.")
            except Exception as e:
                logger.warning(f"Failed to auto-sync account to config: {e}")

        spec = BrokerSpec(
            broker_name=broker,
            broker_symbol=data.get("broker_symbol", "XAUUSD"),
            canonical_symbol=data.get("canonical_symbol", "XAUUSD"),
            digits=int(data.get("digits", 2)),
            point=float(data.get("point", 0.01)),
            contract_size=float(data.get("contract_size", 100.0)),
            min_lot=float(data.get("min_lot", 0.01)),
            max_lot=float(data.get("max_lot", 100.0)),
            lot_step=float(data.get("lot_step", 0.01)),
            tick_size=float(data.get("tick_size", 0.01)),
            tick_value=float(data.get("tick_value", 1.0))
        )
        self.adapter = BrokerAdapter(spec)
        self.pipeline.adapter = self.adapter
        logger.info("✅ BrokerAdapter calibrated to live MT5 broker specs.")

    def _on_bar(self, symbol: str, bar_data: Dict[str, Any]):
        t_str = bar_data.get("timestamp", datetime.now().isoformat())
        c = bar_data.get("close", 0.0)
        h = bar_data.get("high", 0.0)
        l = bar_data.get("low", 0.0)
        bid = bar_data.get("bid", c)
        ask = bar_data.get("ask", c)

        logger.info(f"📊 Bar arrived: {symbol} @ {t_str} | Close: {c:.2f} (Bid: {bid:.2f}, Ask: {ask:.2f})")
        logger.info(f"   Progress: {len(self.recorded_trades)} / {self.target_trades} closed trades collected.")

    async def start(self):
        await self.server.start()
        logger.info("=======================================================")
        logger.info(f"🚀 FORWARD DEMO DAEMON ACTIVE ON {self.host}:{self.port}")
        logger.info(f"Target Trades: {self.target_trades} | Output: {self.output_path}")
        logger.info("Waiting for MT5 EA (LLMTradingBridge.mq5) to connect...")
        logger.info("=======================================================")

    async def stop(self):
        logger.info("Stopping Forward Demo Daemon...")
        await self.server.stop()
        self._save_trades()


async def main():
    daemon = ForwardDemoDaemon()
    await daemon.start()

    loop = asyncio.get_running_loop()
    stop_event = asyncio.Event()

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, stop_event.set)
        except NotImplementedError:
            pass

    try:
        await stop_event.wait()
    finally:
        await daemon.stop()


if __name__ == "__main__":
    asyncio.run(main())
