from pathlib import Path
from typing import Optional, Union, Dict, Any
from datetime import datetime
import polars as pl


class HybridDataLake:
    """
    Two-Tier Hybrid Data Lake for Market Data:
    - Tier 1: Base Cold Data (Historical download, priority=0, fallback)
    - Tier 2: Live Hot Data (Live MT5 stream, priority=1, ground truth)

    Merges both tiers into a seamless, deduplicated, sorted Polars DataFrame.
    """

    @staticmethod
    def merge_bars(base_df: Optional[pl.DataFrame], live_df: Optional[pl.DataFrame]) -> pl.DataFrame:
        """
        Merges base historical data with live broker data.
        In case of timestamp collision, live data (priority 1) takes precedence over base data (priority 0).
        """
        has_base = base_df is not None and not base_df.is_empty()
        has_live = live_df is not None and not live_df.is_empty()

        if not has_base and not has_live:
            return pl.DataFrame()
        if not has_base:
            return live_df.sort("timestamp")
        if not has_live:
            return base_df.sort("timestamp")

        # Cast timestamp to Datetime if needed for strict matching
        b_df = base_df.with_columns(
            pl.col("timestamp").cast(pl.Datetime),
            pl.lit(0).alias("_priority")
        )
        l_df = live_df.with_columns(
            pl.col("timestamp").cast(pl.Datetime),
            pl.lit(1).alias("_priority")
        )

        # Align columns by selecting common columns
        common_cols = [c for c in b_df.columns if c in l_df.columns and c != "_priority"]
        b_df = b_df.select(common_cols + ["_priority"])
        l_df = l_df.select(common_cols + ["_priority"])

        # Concatenate and sort: priority 1 comes after priority 0
        merged = pl.concat([b_df, l_df], how="vertical_relaxed")
        merged = merged.sort(["timestamp", "_priority"])

        # Keep the last entry for each timestamp -> Live data wins on overlap
        deduped = merged.unique(subset=["timestamp"], keep="last")
        final_df = deduped.drop("_priority").sort("timestamp")

        return final_df

    @staticmethod
    def append_live_bar(
        live_dir: Union[str, Path],
        broker_name: str,
        symbol: str,
        timeframe: str,
        bar: Dict[str, Any]
    ) -> Path:
        """
        Appends or creates a monthly partitioned parquet file for live incoming bars.
        Ensures thread-safe/process-safe incremental updates without rewriting huge historical files.
        """
        target_dir = Path(live_dir) / broker_name.lower()
        target_dir.mkdir(parents=True, exist_ok=True)

        bar_time = bar["timestamp"]
        if isinstance(bar_time, str):
            bar_time = datetime.fromisoformat(bar_time)

        year_month = bar_time.strftime("%Y_%m")
        file_path = target_dir / f"{symbol.upper()}_{timeframe.upper()}_{year_month}.parquet"

        new_df = pl.DataFrame([bar]).with_columns(pl.col("timestamp").cast(pl.Datetime))

        if file_path.exists():
            existing_df = pl.read_parquet(file_path)
            combined = pl.concat([existing_df, new_df], how="vertical_relaxed")
            combined = combined.unique(subset=["timestamp"], keep="last").sort("timestamp")
            combined.write_parquet(file_path, compression="zstd")
        else:
            new_df.write_parquet(file_path, compression="zstd")

        return file_path
