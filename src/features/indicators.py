"""
Deterministic Quantitative Feature Pillars: ADX, VWAP, RVOL (Subtask 5-3G / DEC-001).
Strictly 100% deterministic calculations using Polars & NumPy (Never ask an LLM to calculate math).
"""

from typing import Optional, Union, Dict, Any
import numpy as np
import polars as pl


def calculate_adx(
    df: pl.DataFrame,
    period: int = 14,
    high_col: str = "high",
    low_col: str = "low",
    close_col: str = "close"
) -> pl.DataFrame:
    """
    Calculates Average Directional Index (ADX), +DI, and -DI using Wilder's Smoothing.
    
    Args:
        df: Polars DataFrame with high, low, close columns.
        period: Lookback period (default 14).
    
    Returns:
        DataFrame with adx_{period}, plus_di_{period}, minus_di_{period}.
    """
    if len(df) < period * 2:
        return df.with_columns([
            pl.lit(0.0).alias(f"adx_{period}"),
            pl.lit(0.0).alias(f"plus_di_{period}"),
            pl.lit(0.0).alias(f"minus_di_{period}")
        ])

    high = df[high_col].to_numpy()
    low = df[low_col].to_numpy()
    close = df[close_col].to_numpy()
    n = len(df)

    prev_close = np.roll(close, 1)
    prev_close[0] = close[0]

    prev_high = np.roll(high, 1)
    prev_high[0] = high[0]

    prev_low = np.roll(low, 1)
    prev_low[0] = low[0]

    # True Range (TR)
    tr1 = high - low
    tr2 = np.abs(high - prev_close)
    tr3 = np.abs(low - prev_close)
    tr = np.maximum(tr1, np.maximum(tr2, tr3))

    # Directional Movement (+DM and -DM)
    up_move = high - prev_high
    down_move = prev_low - low

    plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0.0)
    minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0.0)

    # Wilder's Smoothing
    tr_smooth = np.zeros(n)
    plus_dm_smooth = np.zeros(n)
    minus_dm_smooth = np.zeros(n)

    # Initial simple sum for period
    tr_smooth[period] = np.sum(tr[1:period + 1])
    plus_dm_smooth[period] = np.sum(plus_dm[1:period + 1])
    minus_dm_smooth[period] = np.sum(minus_dm[1:period + 1])

    alpha = 1.0 / period
    for i in range(period + 1, n):
        tr_smooth[i] = tr_smooth[i - 1] - (tr_smooth[i - 1] * alpha) + tr[i]
        plus_dm_smooth[i] = plus_dm_smooth[i - 1] - (plus_dm_smooth[i - 1] * alpha) + plus_dm[i]
        minus_dm_smooth[i] = minus_dm_smooth[i - 1] - (minus_dm_smooth[i - 1] * alpha) + minus_dm[i]

    # Calculate +DI and -DI
    with np.errstate(divide='ignore', invalid='ignore'):
        plus_di = 100.0 * (plus_dm_smooth / np.where(tr_smooth == 0, 1e-9, tr_smooth))
        minus_di = 100.0 * (minus_dm_smooth / np.where(tr_smooth == 0, 1e-9, tr_smooth))
        dx = 100.0 * (np.abs(plus_di - minus_di) / np.where((plus_di + minus_di) == 0, 1e-9, plus_di + minus_di))

    dx = np.nan_to_num(dx, nan=0.0)

    # Calculate ADX (Smoothed DX)
    adx = np.zeros(n)
    start_adx = period * 2
    if n > start_adx:
        adx[start_adx] = np.mean(dx[period + 1:start_adx + 1])
        for i in range(start_adx + 1, n):
            adx[i] = (adx[i - 1] * (period - 1) + dx[i]) / period

    return df.with_columns([
        pl.Series(f"adx_{period}", np.round(adx, 2)),
        pl.Series(f"plus_di_{period}", np.round(plus_di, 2)),
        pl.Series(f"minus_di_{period}", np.round(minus_di, 2))
    ])


def calculate_vwap(
    df: pl.DataFrame,
    anchor: str = "D", # "D" for daily reset
    high_col: str = "high",
    low_col: str = "low",
    close_col: str = "close",
    volume_col: str = "volume",
    time_col: str = "timestamp"
) -> pl.DataFrame:
    """
    Calculates Volume-Weighted Average Price (VWAP) anchored to each calendar day/session.
    Also calculates upper and lower standard deviation bands (+1sigma, -1sigma, +2sigma, -2sigma).
    
    Args:
        df: Polars DataFrame with OHLCV and time.
        anchor: Anchor reset period ('D' for daily).
    
    Returns:
        DataFrame with vwap, vwap_upper_1, vwap_lower_1, vwap_upper_2, vwap_lower_2.
    """
    if len(df) == 0:
        return df

    # Resolve volume column name (support 'volume' or 'tick_volume')
    actual_vol_col = volume_col
    if actual_vol_col not in df.columns:
        if "tick_volume" in df.columns:
            actual_vol_col = "tick_volume"
        elif "real_volume" in df.columns:
            actual_vol_col = "real_volume"
        else:
            # Fallback to constant volume
            df = df.with_columns(pl.lit(1.0).alias("_synthetic_vol"))
            actual_vol_col = "_synthetic_vol"

    # Resolve time column name (support 'time' or 'timestamp')
    actual_time_col = time_col
    if actual_time_col not in df.columns:
        if "time" in df.columns:
            actual_time_col = "time"
        elif "timestamp" in df.columns:
            actual_time_col = "timestamp"

    # Typical Price (TP)
    typical_price = (df[high_col] + df[low_col] + df[close_col]) / 3.0
    vol = df[actual_vol_col].cast(pl.Float64)
    # Avoid zero volume division
    vol = pl.when(vol <= 0).then(1.0).otherwise(vol)

    tp_v = typical_price * vol

    # Extract date for grouping
    if df[actual_time_col].dtype in (pl.Datetime, pl.Date):
        date_expr = df[actual_time_col].dt.date()
    else:
        # Epoch seconds or milliseconds
        sample_val = df[actual_time_col][0]
        if sample_val > 1e11: # milliseconds
            date_expr = pl.from_epoch(df[actual_time_col], time_unit="ms").dt.date()
        else: # seconds
            date_expr = pl.from_epoch(df[actual_time_col], time_unit="s").dt.date()

    df_temp = df.with_columns([
        typical_price.alias("tp"),
        vol.alias("adj_vol"),
        tp_v.alias("tp_v"),
        date_expr.alias("anchor_date")
    ])

    # Cumulative sum per anchor group
    df_vwap = df_temp.with_columns([
        pl.col("tp_v").cum_sum().over("anchor_date").alias("cum_tp_v"),
        pl.col("adj_vol").cum_sum().over("anchor_date").alias("cum_vol")
    ])

    vwap_expr = pl.col("cum_tp_v") / pl.col("cum_vol")
    
    # Calculate VWAP variance & standard deviation
    # Variance = (Cum(Vol * (TP - VWAP)^2)) / Cum(Vol)
    df_vwap = df_vwap.with_columns(vwap_expr.alias("vwap"))

    diff_sq = (pl.col("tp") - pl.col("vwap")) ** 2 * pl.col("adj_vol")
    df_vwap = df_vwap.with_columns([
        diff_sq.cum_sum().over("anchor_date").alias("cum_diff_sq")
    ])

    stdev_expr = (pl.col("cum_diff_sq") / pl.col("cum_vol")).sqrt()

    df_result = df_vwap.with_columns([
        stdev_expr.alias("vwap_stdev"),
        (pl.col("vwap") + stdev_expr).alias("vwap_upper_1"),
        (pl.col("vwap") - stdev_expr).alias("vwap_lower_1"),
        (pl.col("vwap") + (stdev_expr * 2.0)).alias("vwap_upper_2"),
        (pl.col("vwap") - (stdev_expr * 2.0)).alias("vwap_lower_2")
    ]).drop(["tp", "adj_vol", "tp_v", "anchor_date", "cum_tp_v", "cum_vol", "cum_diff_sq", "vwap_stdev"])

    return df_result


def calculate_rvol(
    df: pl.DataFrame,
    lookback: int = 20,
    volume_col: str = "volume"
) -> pl.DataFrame:
    """
    Calculates Relative Volume (RVOL) = current_volume / SMA(volume, lookback).
    
    RVOL > 2.0 indicates institutional burst / volume anomaly.
    RVOL < 0.8 indicates low participation / exhaustion / fakeout wick.
    """
    if len(df) == 0:
        return df

    actual_vol_col = volume_col
    if actual_vol_col not in df.columns:
        if "tick_volume" in df.columns:
            actual_vol_col = "tick_volume"
        elif "real_volume" in df.columns:
            actual_vol_col = "real_volume"
        else:
            df = df.with_columns(pl.lit(1.0).alias("_synthetic_vol"))
            actual_vol_col = "_synthetic_vol"

    vol = df[actual_vol_col].cast(pl.Float64)
    vol_safe = pl.when(vol <= 0).then(1.0).otherwise(vol)
    vol_sma = vol_safe.rolling_mean(window_size=lookback).fill_null(vol_safe)
    
    rvol_expr = pl.when(vol_sma <= 0).then(1.0).otherwise(vol_safe / vol_sma)

    return df.with_columns([
        rvol_expr.round(2).alias(f"rvol_{lookback}")
    ])
