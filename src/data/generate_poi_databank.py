#!/usr/bin/env python3
"""
M1 POI Databank Generator for LLMTradingV2.
Pre-calculates all M1 Order Blocks, FVG origins, and lifecycle expiration timestamps
across the entire historical dataset and exports a compact binary and CSV format
directly accessible by MetaTrader 5 Strategy Tester.
"""

from pathlib import Path
import time
import struct
import numpy as np
import polars as pl

COMMON_FILES_DIR = Path("/Users/alami/mt5prefix/drive_c/users/alami/AppData/Roaming/MetaQuotes/Terminal/Common/Files")
OUTPUT_BIN = COMMON_FILES_DIR / "xauusd_m1_poi_databank.bin"
OUTPUT_CSV = COMMON_FILES_DIR / "xauusd_m1_poi_databank.csv"
LOCAL_CACHE_BIN = Path("data/cache/xauusd_m1_poi_databank.bin")
LOCAL_CACHE_CSV = Path("data/cache/xauusd_m1_poi_databank.csv")

PARQUET_FILE = Path("data/parquet/XAUUSD/M1/XAUUSD_M1.parquet")


def generate_poi_databank(parquet_path: Path = PARQUET_FILE):
    print(f"[1/4] Loading M1 dataset from {parquet_path}...")
    t0 = time.time()
    df = pl.read_parquet(parquet_path)
    n = len(df)
    print(f"      Loaded {n:,} M1 bars in {time.time() - t0:.2f}s")

    closes = df["close"].to_numpy()
    highs = df["high"].to_numpy()
    lows = df["low"].to_numpy()
    opens = df["open"].to_numpy()
    timestamps = (df["timestamp"].dt.epoch(time_unit="s")).to_numpy()

    # Block min/max for sub-millisecond search
    block_size = 500
    num_blocks = (n + block_size - 1) // block_size
    block_mins = np.array([np.min(closes[b * block_size : min((b + 1) * block_size, n)]) for b in range(num_blocks)])
    block_maxs = np.array([np.max(closes[b * block_size : min((b + 1) * block_size, n)]) for b in range(num_blocks)])

    def find_first_below(start_idx, threshold):
        first_block = start_idx // block_size
        first_end = min((first_block + 1) * block_size, n)
        sub = closes[start_idx:first_end]
        hits = np.where(sub < threshold)[0]
        if len(hits) > 0:
            return start_idx + hits[0]
        for blk in range(first_block + 1, num_blocks):
            if block_mins[blk] < threshold:
                b_start = blk * block_size
                b_end = min((blk + 1) * block_size, n)
                hits = np.where(closes[b_start:b_end] < threshold)[0]
                if len(hits) > 0:
                    return b_start + hits[0]
        return n

    def find_first_above(start_idx, threshold):
        first_block = start_idx // block_size
        first_end = min((first_block + 1) * block_size, n)
        sub = closes[start_idx:first_end]
        hits = np.where(sub > threshold)[0]
        if len(hits) > 0:
            return start_idx + hits[0]
        for blk in range(first_block + 1, num_blocks):
            if block_maxs[blk] > threshold:
                b_start = blk * block_size
                b_end = min((blk + 1) * block_size, n)
                hits = np.where(closes[b_start:b_end] > threshold)[0]
                if len(hits) > 0:
                    return b_start + hits[0]
        return n

    print("[2/4] Detecting all M1 Order Blocks and calculating lifecycle boundaries...")
    t_calc = time.time()
    obs_data = []

    for i in range(2, n - 1):
        # Bullish FVG -> Bullish OB Floor
        if lows[i] > highs[i - 2]:
            b = i - 2
            if closes[b] > opens[b]:
                if closes[b + 1] < opens[b + 1]:
                    b += 1
                elif b - 1 >= 0 and closes[b - 1] < opens[b - 1]:
                    b -= 1
            top = round(float(highs[b]), 3)
            btm = round(float(lows[b]), 3)
            t_base = int(timestamps[b])
            brk_idx = find_first_below(b + 1, btm)
            t_break = int(timestamps[brk_idx]) if brk_idx < n else 0
            obs_data.append((t_base, 1, top, btm, t_break))

        # Bearish FVG -> Bearish OB Roof
        elif lows[i - 2] > highs[i]:
            b = i - 2
            if closes[b] < opens[b]:
                if closes[b + 1] > opens[b + 1]:
                    b += 1
                elif b - 1 >= 0 and closes[b - 1] > opens[b - 1]:
                    b -= 1
            top = round(float(highs[b]), 3)
            btm = round(float(lows[b]), 3)
            t_base = int(timestamps[b])
            brk_idx = find_first_above(b + 1, top)
            t_break = int(timestamps[brk_idx]) if brk_idx < n else 0
            obs_data.append((t_base, 0, top, btm, t_break))

    # Sort strictly by time
    obs_data.sort(key=lambda x: x[0])
    print(f"      Calculated {len(obs_data):,} OB records in {time.time() - t_calc:.2f}s")

    print("[3/4] Exporting binary databank file for MetaTrader 5...")
    # Binary layout:
    # Header: Magic 4 bytes b'POIB', count (uint32)
    # Each record:
    #   t_base: int64 (8 bytes)
    #   is_bull: int32 (4 bytes)
    #   top: double (8 bytes)
    #   bottom: double (8 bytes)
    #   t_break: int64 (8 bytes)
    # Total per record = 36 bytes. (79,000 * 36 = ~2.8 MB, ultra-compact!)
    header = struct.pack("<4sI", b"POIB", len(obs_data))
    payload = bytearray(header)
    for row in obs_data:
        payload.extend(struct.pack("<qi dd q", row[0], row[1], row[2], row[3], row[4]))

    COMMON_FILES_DIR.mkdir(parents=True, exist_ok=True)
    LOCAL_CACHE_BIN.parent.mkdir(parents=True, exist_ok=True)

    with open(OUTPUT_BIN, "wb") as f:
        f.write(payload)
    with open(LOCAL_CACHE_BIN, "wb") as f:
        f.write(payload)

    print(f"      Wrote binary databank ({len(payload) / (1024 * 1024):.2f} MB) to:")
    print(f"      -> {OUTPUT_BIN}")

    # Also write a CSV version for human inspection & fallback
    print("[4/4] Writing CSV fallback...")
    lines = ["time,is_bull,top,bottom,break_time\n"]
    for row in obs_data:
        lines.append(f"{row[0]},{row[1]},{row[2]},{row[3]},{row[4]}\n")
    csv_text = "".join(lines)

    with open(OUTPUT_CSV, "w") as f:
        f.write(csv_text)
    with open(LOCAL_CACHE_CSV, "w") as f:
        f.write(csv_text)

    print(f"      Wrote CSV databank to {OUTPUT_CSV}")
    print("Done! POI Databank is ready for MT5 Backtest!")


if __name__ == "__main__":
    generate_poi_databank()
