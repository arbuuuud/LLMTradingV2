import asyncio
import json
import pytest
from src.bridge.server import MT5BridgeServer, BridgeMessage, BridgeMessageType


@pytest.mark.asyncio
async def test_bridge_server_handshake_and_bar():
    server = MT5BridgeServer(host="127.0.0.1", port=5588)

    received_handshake = {}
    received_bar = {}

    def on_handshake(data):
        nonlocal received_handshake
        received_handshake = data

    def on_bar(symbol, data):
        nonlocal received_bar
        received_bar = data

    server.on_handshake_callback = on_handshake
    server.on_bar_callback = on_bar

    await server.start()

    try:
        # Simulate an MT5 EA client connecting
        reader, writer = await asyncio.open_connection("127.0.0.1", 5588)

        # 1. Send Handshake
        handshake_payload = {
            "type": "HANDSHAKE",
            "symbol": "XAUUSD",
            "data": {
                "broker_name": "TestBroker",
                "broker_symbol": "XAUUSD.u",
                "digits": 3,
                "point": 0.001
            }
        }
        writer.write((json.dumps(handshake_payload) + "\n").encode("utf-8"))
        await writer.drain()

        # 2. Send Bar event
        bar_payload = {
            "type": "BAR",
            "symbol": "XAUUSD",
            "data": {
                "timestamp": "2025-01-01T12:00:00",
                "open": 2600.0,
                "high": 2605.0,
                "low": 2599.0,
                "close": 2604.0,
                "volume": 120
            }
        }
        writer.write((json.dumps(bar_payload) + "\n").encode("utf-8"))
        await writer.drain()

        # Give small time for async server loop to process
        await asyncio.sleep(0.1)

        assert received_handshake.get("broker_name") == "TestBroker"
        assert received_handshake.get("broker_symbol") == "XAUUSD.u"
        assert received_bar.get("close") == 2604.0

        # 3. Test Broadcast from server to client
        order_cmd = BridgeMessage(
            type=BridgeMessageType.ORDER_REQUEST,
            symbol="XAUUSD",
            data={"action": "BUY", "lot": 0.50, "sl": 2595.0, "tp": 2620.0}
        )
        await server.broadcast(order_cmd)

        # Read line on client
        line = await reader.readline()
        client_received = json.loads(line.decode("utf-8").strip())
        assert client_received["type"] == "ORDER_REQUEST"
        assert client_received["data"]["action"] == "BUY"

        writer.close()
        await writer.wait_closed()
    finally:
        await server.stop()
