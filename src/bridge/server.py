import asyncio
import json
import logging
from enum import Enum
from typing import Callable, Optional, Dict, Any, List
from pydantic import BaseModel, Field

logger = logging.getLogger("MT5BridgeServer")


class BridgeMessageType(str, Enum):
    HANDSHAKE = "HANDSHAKE"
    BAR = "BAR"
    TICK = "TICK"
    ORDER_REQUEST = "ORDER_REQUEST"
    ORDER_STATUS = "ORDER_STATUS"
    HEARTBEAT = "HEARTBEAT"
    ERROR = "ERROR"


class BridgeMessage(BaseModel):
    type: BridgeMessageType
    symbol: Optional[str] = None
    data: Dict[str, Any] = Field(default_factory=dict)
    timestamp: Optional[str] = None


class MT5BridgeServer:
    """
    High-speed, non-blocking TCP Socket Server bridging MetaTrader 5 EA and Python.
    Uses newline-delimited JSON for protocol simplicity and resilience across Wine/macOS/Linux/Windows.
    """

    def __init__(self, host: str = "127.0.0.1", port: int = 5555):
        self.host = host
        self.port = port
        self.server: Optional[asyncio.Server] = None
        self.active_writers: List[asyncio.StreamWriter] = []
        self._is_running = False

        # Callbacks
        self.on_handshake_callback: Optional[Callable[[Dict[str, Any]], None]] = None
        self.on_bar_callback: Optional[Callable[[str, Dict[str, Any]], None]] = None
        self.on_tick_callback: Optional[Callable[[str, Dict[str, Any]], None]] = None
        self.on_order_status_callback: Optional[Callable[[Dict[str, Any]], None]] = None

    async def start(self):
        """Starts the TCP Server."""
        self.server = await asyncio.start_server(self._handle_client, self.host, self.port)
        self._is_running = True
        logger.info(f"MT5 Bridge Server running on {self.host}:{self.port}")

    async def stop(self):
        """Stops the TCP Server and closes active connections."""
        self._is_running = False
        for writer in self.active_writers:
            try:
                writer.close()
                await writer.wait_closed()
            except Exception:
                pass
        self.active_writers.clear()

        if self.server:
            self.server.close()
            await self.server.wait_closed()
            logger.info("MT5 Bridge Server stopped.")

    async def broadcast(self, message: BridgeMessage):
        """Sends a JSON message to all connected MT5 EAs."""
        payload = (message.model_dump_json() + "\n").encode("utf-8")
        for writer in list(self.active_writers):
            try:
                writer.write(payload)
                await writer.drain()
            except Exception as e:
                logger.warning(f"Failed to send to client: {e}")
                self._remove_writer(writer)

    def _remove_writer(self, writer: asyncio.StreamWriter):
        if writer in self.active_writers:
            self.active_writers.remove(writer)
            try:
                writer.close()
            except Exception:
                pass

    async def _handle_client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        client_addr = writer.get_extra_info("peername")
        logger.info(f"MT5 Client connected from {client_addr}")
        self.active_writers.append(writer)

        buffer = ""
        try:
            while self._is_running:
                data = await reader.read(4096)
                if not data:
                    break

                buffer += data.decode("utf-8", errors="replace")
                while "\n" in buffer:
                    line, buffer = buffer.split("\n", 1)
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        raw_json = json.loads(line)
                        msg = BridgeMessage.model_validate(raw_json)
                        self._process_message(msg, writer)
                    except Exception as err:
                        logger.error(f"Error parsing incoming MT5 message: {err} | Raw: {line}")
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"Client connection error: {e}")
        finally:
            logger.info(f"MT5 Client disconnected: {client_addr}")
            self._remove_writer(writer)

    def _process_message(self, msg: BridgeMessage, writer: asyncio.StreamWriter):
        if msg.type == BridgeMessageType.HANDSHAKE:
            if self.on_handshake_callback:
                self.on_handshake_callback(msg.data)
        elif msg.type == BridgeMessageType.BAR:
            if self.on_bar_callback and msg.symbol:
                self.on_bar_callback(msg.symbol, msg.data)
        elif msg.type == BridgeMessageType.TICK:
            if self.on_tick_callback and msg.symbol:
                self.on_tick_callback(msg.symbol, msg.data)
        elif msg.type == BridgeMessageType.ORDER_STATUS:
            if self.on_order_status_callback:
                self.on_order_status_callback(msg.data)
        elif msg.type == BridgeMessageType.HEARTBEAT:
            pass  # Keep-alive acknowledged
