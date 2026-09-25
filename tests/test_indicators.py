"""
Unit tests for deterministic quantitative feature pillars: ADX, VWAP, RVOL (Subtask 5-3G).
"""

import pytest
import polars as pl
import numpy as np
from datetime import datetime, timedelta

from src.features.indicators import calculate_adx, calculate_vwap, calculate_rvol


def test_calculate_adx_basic():
    # Construct synthetic trending data
    n = 100
    base = 2650.0
    highs = [base + i * 0.5 + 1.0 for i in range(n)]
    lows = [base + i * 0.5 - 1.0 for i in range(n)]
    closes = [base + i * 0.5 for i in range(n)]
    times = [1700000000 + i * 60 for i in range(n)]

    df = pl.DataFrame({
        "time": times,
        "high": highs,
        "low": lows,
        "close": closes,
        "volume": [10.0] * n
    })

    res = calculate_adx(df, period=14)
    assert "adx_14" in res.columns
    assert "plus_di_14" in res.columns
    assert "minus_di_14" in res.columns
    assert len(res) == n
    # In a persistent uptrend, plus_di should be substantially higher than minus_di
    last_row = res.tail(1).to_dicts()[0]
    assert last_row["plus_di_14"] > last_row["minus_di_14"]
    assert last_row["adx_14"] > 0.0


def test_calculate_vwap_daily_anchor():
    # 2 days of data: Day 1 (50 bars), Day 2 (50 bars)
    t0 = datetime(2026, 9, 24, 0, 0)
    times = []
    highs = []
    lows = []
    closes = []
    volumes = []

    for i in range(100):
        t = t0 + timedelta(minutes=i * 30) # Crosses over to next day after 48 bars
        times.append(int(t.timestamp()))
        p = 2650.0 + (i % 48) * 0.2
        highs.append(p + 0.5)
        lows.append(p - 0.5)
        closes.append(p)
        volumes.append(100.0)

    df = pl.DataFrame({
        "time": times,
        "high": highs,
        "low": lows,
        "close": closes,
        "volume": volumes
    })

    res = calculate_vwap(df, anchor="D")
    assert "vwap" in res.columns
    assert "vwap_upper_1" in res.columns
    assert "vwap_lower_1" in res.columns
    assert "vwap_upper_2" in res.columns
    assert "vwap_lower_2" in res.columns

    # Upper band must be strictly greater than VWAP, and lower band strictly less
    last_row = res.tail(1).to_dicts()[0]
    assert last_row["vwap_upper_2"] > last_row["vwap_upper_1"] >= last_row["vwap"]
    assert last_row["vwap"] >= last_row["vwap_lower_1"] > last_row["vwap_lower_2"]


def test_calculate_rvol():
    volumes = [10.0] * 20 + [50.0] # 21st bar has 5x volume
    df = pl.DataFrame({
        "volume": volumes
    })

    res = calculate_rvol(df, lookback=20)
    assert "rvol_20" in res.columns
    vals = res["rvol_20"].to_list()
    # At bar 21, volume is 50, avg before was 10. RVOL should be ~4.16 - 5.0
    assert vals[-1] > 3.0
