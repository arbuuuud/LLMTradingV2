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


@pytest.mark.asyncio
async def test_targeted_unicast_routing_multi_account():
    """Verify Targeted Unicast Socket Routing (DEC-042) isolates multi-account order dispatches."""
    server = MT5BridgeServer(host="127.0.0.1", port=5589)
    await server.start()

    try:
        # Simulate two MT5 EA terminal clients connecting
        reader_a, writer_a = await asyncio.open_connection("127.0.0.1", 5589)
        reader_b, writer_b = await asyncio.open_connection("127.0.0.1", 5589)

        # 1. Register Client A as Account 115745645
        reg_a = {"type": "REGISTER", "account_id": "115745645", "symbol": "XAUUSD", "balance": 10000.0, "equity": 10000.0}
        writer_a.write((json.dumps(reg_a) + "\n").encode("utf-8"))
        await writer_a.drain()

        # 2. Register Client B as Account 5058996231
        reg_b = {"type": "REGISTER", "account_id": "5058996231", "symbol": "XAUUSD", "balance": 100000.0, "equity": 100000.0}
        writer_b.write((json.dumps(reg_b) + "\n").encode("utf-8"))
        await writer_b.drain()

        await asyncio.sleep(0.05)

        assert "115745645" in server.account_writers
        assert "5058996231" in server.account_writers

        # 3. Dispatched order targeted ONLY to Account 115745645
        order_to_a = {
            "action": "ORDER",
            "account_number": "115745645",
            "side": "BUY_LIMIT",
            "lots": 0.05,
            "price": 2600.0
        }
        await server.broadcast(order_to_a)

        # Client A MUST receive the order
        line_a = await asyncio.wait_for(reader_a.readline(), timeout=0.5)
        parsed_a = json.loads(line_a.decode("utf-8").strip())
        assert parsed_a["action"] == "ORDER"
        assert parsed_a["account_number"] == "115745645"

        # Client B MUST NOT receive anything (timeout after 0.1s)
        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(reader_b.readline(), timeout=0.1)

        # 4. Dispatched order targeted to Account ACC-5058996231 (Testing prefix normalization)
        order_to_b = {
            "action": "ORDER",
            "account_number": "ACC-5058996231",
            "side": "SELL_LIMIT",
            "lots": 0.50,
            "price": 2650.0
        }
        await server.broadcast(order_to_b)

        # Client B MUST receive the order
        line_b = await asyncio.wait_for(reader_b.readline(), timeout=0.5)
        parsed_b = json.loads(line_b.decode("utf-8").strip())
        assert parsed_b["action"] == "ORDER"
        assert parsed_b["account_number"] == "ACC-5058996231"

        # Client A MUST NOT receive anything
        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(reader_a.readline(), timeout=0.1)

        # 5. Global command with no account_number (e.g. Session Halt CANCEL_PENDING) -> Both must receive
        global_cancel = {"action": "CANCEL_PENDING", "symbol": "XAUUSD", "magic": 1001}
        await server.broadcast(global_cancel)

        line_a2 = await asyncio.wait_for(reader_a.readline(), timeout=0.5)
        line_b2 = await asyncio.wait_for(reader_b.readline(), timeout=0.5)

        assert json.loads(line_a2.decode("utf-8").strip())["action"] == "CANCEL_PENDING"
        assert json.loads(line_b2.decode("utf-8").strip())["action"] == "CANCEL_PENDING"

        writer_a.close()
        writer_b.close()
        await writer_a.wait_closed()
        await writer_b.wait_closed()
    finally:
        await server.stop()

