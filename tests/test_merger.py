from datetime import datetime, timedelta
import polars as pl
from src.data.merger import HybridDataLake


def test_hybrid_data_lake_priority_merge():
    # Base historical data (T0, T1, T2)
    t0 = datetime(2025, 1, 1, 10, 0)
    t1 = datetime(2025, 1, 1, 10, 1)
    t2 = datetime(2025, 1, 1, 10, 2)
    t3 = datetime(2025, 1, 1, 10, 3)

    base_df = pl.DataFrame({
        "timestamp": [t0, t1, t2],
        "open": [100.0, 101.0, 102.0],
        "high": [102.0, 103.0, 104.0],
        "low": [99.0, 100.0, 101.0],
        "close": [101.0, 102.0, 103.0],
        "source": ["cold_base", "cold_base", "cold_base"]
    })

    # Live data stream (T2, T3) -> T2 is overlapping!
    live_df = pl.DataFrame({
        "timestamp": [t2, t3],
        "open": [102.5, 103.5], # Live broker has slightly different tick-based price
        "high": [104.5, 105.0],
        "low": [101.5, 102.0],
        "close": [103.5, 104.0],
        "source": ["live_broker", "live_broker"]
    })

    merged = HybridDataLake.merge_bars(base_df, live_df)

    assert len(merged) == 4
    # Timestamps are sorted
    assert merged["timestamp"].to_list() == [t0, t1, t2, t3]

    # At T0 and T1, base data is retained
    assert merged.filter(pl.col("timestamp") == t0)["source"][0] == "cold_base"
    assert merged.filter(pl.col("timestamp") == t1)["source"][0] == "cold_base"

    # At T2 (overlap), live data wins over base data
    t2_row = merged.filter(pl.col("timestamp") == t2)
    assert t2_row["source"][0] == "live_broker"
    assert t2_row["open"][0] == 102.5

    # At T3, live data is present
    assert merged.filter(pl.col("timestamp") == t3)["source"][0] == "live_broker"


def test_append_live_bar(tmp_path):
    t_now = datetime(2025, 3, 15, 14, 30)
    bar = {
        "timestamp": t_now,
        "open": 2600.0,
        "high": 2605.0,
        "low": 2598.0,
        "close": 2603.0,
        "volume": 150.0
    }

    file_path = HybridDataLake.append_live_bar(
        live_dir=tmp_path,
        broker_name="Exness_Raw",
        symbol="XAUUSD",
        timeframe="M1",
        bar=bar
    )

    assert file_path.exists()
    df = pl.read_parquet(file_path)
    assert len(df) == 1
    assert df["close"][0] == 2603.0
