from src.data.adapter import BrokerSpec, BrokerAdapter


def test_symbol_translation():
    spec = BrokerSpec(
        broker_name="Exness",
        canonical_symbol="XAUUSD",
        broker_symbol="XAUUSD.u",
        digits=3
    )
    adapter = BrokerAdapter(spec)

    assert adapter.to_broker_symbol("XAUUSD") == "XAUUSD.u"
    assert adapter.to_canonical_symbol("XAUUSD.u") == "XAUUSD"
    # Unknown symbols remain untouched
    assert adapter.to_broker_symbol("EURUSD") == "EURUSD"


def test_lot_normalization_standard():
    spec = BrokerSpec(
        broker_name="Standard",
        min_lot=0.01,
        max_lot=100.0,
        lot_step=0.01,
        lot_decimals=2
    )
    adapter = BrokerAdapter(spec)

    # Truncate / quantize downward to valid step
    assert adapter.normalize_lot(0.158) == 0.15
    # Clamp minimum
    assert adapter.normalize_lot(0.005) == 0.01
    # Clamp maximum
    assert adapter.normalize_lot(150.0) == 100.0


def test_lot_normalization_cent_step():
    spec = BrokerSpec(
        broker_name="Cent",
        min_lot=0.1,
        max_lot=500.0,
        lot_step=0.1,
        lot_decimals=1
    )
    adapter = BrokerAdapter(spec)

    assert adapter.normalize_lot(0.38) == 0.3
    assert adapter.normalize_lot(0.05) == 0.1


def test_calculate_lot_sizing():
    spec = BrokerSpec(
        broker_name="Standard",
        contract_size=100.0,
        point=0.01,
        tick_size=0.01,
        tick_value=1.0,  # $1 per point for 1.0 lot ($100 per $1 move in gold)
        min_lot=0.01,
        max_lot=50.0,
        lot_step=0.01,
        lot_decimals=2
    )
    adapter = BrokerAdapter(spec)

    equity = 10000.0  # $10,000
    risk_pct = 1.0    # 1% = $100 risk
    sl_distance_points = 200.0 # 200 points = $2.00 move in gold ($200 per lot)

    # Risk = $100. Cost per lot = 200 * $1 = $200. Expected lot = 100 / 200 = 0.50 lot.
    lot = adapter.calculate_lot(equity, risk_pct, sl_distance_points)
    assert lot == 0.50
