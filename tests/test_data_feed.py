from datetime import datetime, timedelta
from pathlib import Path
import json
from src.workflows.data_feed import LiveDataFeedGenerator
from src.core.types import MarketStateSnapshot, Direction, Trend


def test_live_data_feed_generator(tmp_path):
    generator = LiveDataFeedGenerator(
        canonical_symbol="XAUUSD",
        timeframe="M1",
        cache_dir=str(tmp_path),
        swing_window=2
    )

    base_time = datetime(2025, 1, 1, 10, 0)
    # Feed 6 bars with a strong upward displacement
    # Bar 0: 2600 - 2602
    # Bar 1: 2602 - 2610 (Displacement candle)
    # Bar 2: 2611 - 2615 (Leaves a gap between bar 0 high: 2602 and bar 2 low: 2611)
    bars = [
        {"timestamp": base_time + timedelta(minutes=0), "open": 2600.0, "high": 2602.0, "low": 2598.0, "close": 2601.0, "volume": 100},
        {"timestamp": base_time + timedelta(minutes=1), "open": 2601.0, "high": 2603.0, "low": 2600.0, "close": 2602.0, "volume": 110},
        {"timestamp": base_time + timedelta(minutes=2), "open": 2602.0, "high": 2610.0, "low": 2601.5, "close": 2609.5, "volume": 500},
        {"timestamp": base_time + timedelta(minutes=3), "open": 2609.5, "high": 2615.0, "low": 2611.0, "close": 2614.0, "volume": 350},
        {"timestamp": base_time + timedelta(minutes=4), "open": 2614.0, "high": 2616.0, "low": 2613.0, "close": 2615.0, "volume": 200},
    ]

    generator.seed_historical_bars(bars[:4])

    # Now add the 5th bar as live bar
    live_bar = bars[4]
    snapshot = generator.on_new_bar(live_bar, bid=2615.0, ask=2615.2)

    assert snapshot.symbol == "XAUUSD"
    assert snapshot.current_price.bid == 2615.0
    assert snapshot.current_price.spread == 0.2

    # Check that cache file exists and can be parsed
    cache_file = tmp_path / "live_snapshot_xauusd.json"
    assert cache_file.exists()

    with open(cache_file) as f:
        data = json.load(f)
    loaded_snapshot = MarketStateSnapshot.model_validate(data)
    assert loaded_snapshot.symbol == "XAUUSD"
    assert loaded_snapshot.timeframe == "M1"


def test_load_from_data_lake(tmp_path):
    generator = LiveDataFeedGenerator(
        canonical_symbol="XAUUSD",
        timeframe="M1",
        cache_dir=str(tmp_path),
        max_buffer_size=100
    )
    parquet_path = Path("data/parquet/XAUUSD/M1/XAUUSD_M1.parquet")
    if parquet_path.exists():
        success = generator.load_from_data_lake(parquet_path=parquet_path, max_bars=50)
        assert success is True
        assert len(generator.closes) == 50
        assert generator.last_snapshot is not None
        assert (tmp_path / "live_snapshot_xauusd.json").exists()
