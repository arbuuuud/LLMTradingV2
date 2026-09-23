from pathlib import Path
from typing import List, Dict, Any, Optional, Union
from datetime import datetime
import json
import logging
import numpy as np

from src.core.types import (
    MarketStateSnapshot,
    PriceQuote,
    Trend,
    StructureState,
    LiquidityState,
    Direction,
    FairValueGap,
    InversionFVG,
    FVGConfluenceZone,
    OrderBlock,
    FibonacciOTE
)
from src.features.structure import detect_swing_points, evaluate_market_structure
from src.features.smc import (
    detect_fvgs,
    update_fvg_mitigation,
    detect_order_blocks,
    process_order_block_lifecycle,
    cluster_order_blocks,
    process_fvg_inversions,
    detect_fvg_confluences
)
from src.features.candles import detect_candle_patterns
from src.features.fibonacci import calculate_fibonacci_ote
from src.data.adapter import BrokerAdapter


class LiveDataFeedGenerator:
    """
    Real-time Feature Generation Engine (Workflow 1).
    Processes incoming bar & tick events from MT5, calculates deterministic SMC features,
    and produces an enriched MarketStateSnapshot atomically saved to disk cache.
    """

    def __init__(
        self,
        canonical_symbol: str = "XAUUSD",
        timeframe: str = "M1",
        adapter: Optional[BrokerAdapter] = None,
        cache_dir: str = "data/cache",
        swing_window: int = 3,
        max_buffer_size: int = 300
    ):
        self.canonical_symbol = canonical_symbol
        self.timeframe = timeframe
        self.adapter = adapter
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.swing_window = swing_window
        self.max_buffer_size = max_buffer_size
        self.logger = logging.getLogger("LiveDataFeedGenerator")

        # In-memory bar rolling buffers
        self.timestamps: List[datetime] = []
        self.opens: List[float] = []
        self.highs: List[float] = []
        self.lows: List[float] = []
        self.closes: List[float] = []
        self.volumes: List[float] = []

        # State tracking
        self.active_fvgs: List[FairValueGap] = []
        self.active_ifvgs: List[InversionFVG] = []
        self.fvg_confluences: List[FVGConfluenceZone] = []
        self.active_obs: List[OrderBlock] = []
        self.active_breakers: List[OrderBlock] = []
        self.current_trend: Trend = Trend.RANGING
        self.last_snapshot: Optional[MarketStateSnapshot] = None

    def seed_historical_bars(self, bars: List[Dict[str, Any]]):
        """Initializes generator with historical bars so initial swings and POIs are ready."""
        for bar in bars:
            self._append_bar_to_buffer(bar)
        if len(self.closes) >= self.swing_window * 2 + 1:
            self._compute_snapshot(self.closes[-1], self.closes[-1], 0.1)

    def load_from_data_lake(
        self,
        parquet_path: Optional[Union[str, Path]] = None,
        max_bars: int = 3000
    ) -> bool:
        """
        Loads Priority 0 base cold historical data from Two-Tier Data Lake (parquet)
        to initialize the rolling buffer, structure, and POIs.
        """
        path = Path(parquet_path) if parquet_path else Path("data/parquet/XAUUSD/M1/XAUUSD_M1.parquet")
        if not path.exists():
            return False

        try:
            import polars as pl
            df = pl.read_parquet(path)
            if df.is_empty():
                return False
            df_subset = df.tail(max_bars)
            bars = []
            for row in df_subset.iter_rows(named=True):
                bars.append({
                    "timestamp": row["timestamp"].isoformat() if hasattr(row["timestamp"], "isoformat") else str(row["timestamp"]),
                    "open": float(row["open"]),
                    "high": float(row["high"]),
                    "low": float(row["low"]),
                    "close": float(row["close"]),
                    "volume": float(row.get("tick_volume", 0.0))
                })
            self.seed_historical_bars(bars)
            if self.last_snapshot:
                self._save_snapshot_to_cache(self.last_snapshot)
            return True
        except Exception as e:
            self.logger.error(f"Failed to load base historical data from {path}: {e}")
            return False

    def _append_bar_to_buffer(self, bar: Dict[str, Any]):
        t = bar["timestamp"]
        if isinstance(t, str):
            t = datetime.fromisoformat(t)

        self.timestamps.append(t)
        self.opens.append(float(bar["open"]))
        self.highs.append(float(bar["high"]))
        self.lows.append(float(bar["low"]))
        self.closes.append(float(bar["close"]))
        self.volumes.append(float(bar.get("volume", 0.0)))

        # Prune old bars if exceeding buffer
        if len(self.timestamps) > self.max_buffer_size:
            self.timestamps.pop(0)
            self.opens.pop(0)
            self.highs.pop(0)
            self.lows.pop(0)
            self.closes.pop(0)
            self.volumes.pop(0)

    def on_new_bar(self, bar: Dict[str, Any], bid: float, ask: float) -> MarketStateSnapshot:
        """Called when a new candle closes. Generates and caches MarketStateSnapshot."""
        self._append_bar_to_buffer(bar)
        spread = round(ask - bid, 4)
        snapshot = self._compute_snapshot(bid=bid, ask=ask, spread=spread)
        self._save_snapshot_to_cache(snapshot)
        return snapshot

    def _compute_snapshot(self, bid: float, ask: float, spread: float) -> MarketStateSnapshot:
        np_highs = np.array(self.highs)
        np_lows = np.array(self.lows)
        np_opens = np.array(self.opens)
        np_closes = np.array(self.closes)
        now = self.timestamps[-1]

        # 1. Structure (Swings, BOS, CHoCH)
        shs, sls = detect_swing_points(np_highs, np_lows, self.timestamps, window=self.swing_window)
        struct_state = evaluate_market_structure(
            np_closes, shs, sls, self.timestamps, current_trend=self.current_trend
        )

        # Update trend heuristic
        if struct_state.last_event.name.endswith("BULLISH"):
            self.current_trend = Trend.BULLISH
        elif struct_state.last_event.name.endswith("BEARISH"):
            self.current_trend = Trend.BEARISH

        # 2. SMC: FVGs and Order Blocks
        new_fvgs = detect_fvgs(np_highs, np_lows, self.timestamps)
        # Merge newly discovered FVGs with existing ones (avoid duplicates)
        existing_ids = {f.id for f in self.active_fvgs}
        for fvg in new_fvgs:
            if fvg.id not in existing_ids:
                self.active_fvgs.append(fvg)

        # Update mitigation & inversion against current candle
        self.active_fvgs = update_fvg_mitigation(
            self.active_fvgs,
            latest_high=float(self.highs[-1]),
            latest_low=float(self.lows[-1]),
            latest_close=float(self.closes[-1])
        )

        # Process Inversions and Confluences
        active_regs, updated_ifvgs = process_fvg_inversions(
            self.active_fvgs,
            latest_high=float(self.highs[-1]),
            latest_low=float(self.lows[-1]),
            latest_close=float(self.closes[-1]),
            current_time=now,
            existing_ifvgs=self.active_ifvgs
        )
        self.active_fvgs = active_regs
        self.active_ifvgs = updated_ifvgs
        self.fvg_confluences = detect_fvg_confluences(self.active_fvgs, self.active_ifvgs)

        # Order Blocks & Breakers
        new_obs = detect_order_blocks(np_opens, np_highs, np_lows, np_closes, self.timestamps, self.active_fvgs)
        existing_ob_ids = {ob.id for ob in self.active_obs} | {bb.id for bb in self.active_breakers}
        for ob in new_obs:
            if ob.id not in existing_ob_ids:
                self.active_obs.append(ob)

        active_obs, new_breakers = process_order_block_lifecycle(
            self.active_obs,
            latest_high=float(self.highs[-1]),
            latest_low=float(self.lows[-1]),
            latest_close=float(self.closes[-1]),
            current_time=now
        )
        self.active_obs = active_obs
        for bb in new_breakers:
            if not any(item.id == bb.id for item in self.active_breakers):
                self.active_breakers.append(bb)

        # 3. Fibonacci OTE & Equilibrium
        fibo_ote: Optional[FibonacciOTE] = None
        if struct_state.last_swing_high and struct_state.last_swing_low:
            trade_dir = Direction.BUY if self.current_trend == Trend.BULLISH else Direction.SELL
            fibo_ote = calculate_fibonacci_ote(
                high_anchor=struct_state.last_swing_high.price,
                low_anchor=struct_state.last_swing_low.price,
                current_price=float(self.closes[-1]),
                direction=trade_dir
            )

        # 4. Liquidity Sweep Detection
        liq_state = LiquidityState()
        if struct_state.last_swing_high and struct_state.last_swing_low:
            latest_h = self.highs[-1]
            latest_l = self.lows[-1]
            latest_c = self.closes[-1]

            # Buy-side sweep: Wick above swing high, but close back below it
            if latest_h > struct_state.last_swing_high.price and latest_c <= struct_state.last_swing_high.price:
                liq_state.buy_side_swept = True
            # Sell-side sweep: Wick below swing low, but close back above it
            if latest_l < struct_state.last_swing_low.price and latest_c >= struct_state.last_swing_low.price:
                liq_state.sell_side_swept = True

        # 5. Candlestick Confirmation Patterns (At Active POIs)
        candle_patterns = detect_candle_patterns(
            opens=np_opens,
            highs=np_highs,
            lows=np_lows,
            closes=np_closes,
            timestamps=self.timestamps,
            active_obs=self.active_obs,
            active_fvgs=self.active_fvgs,
            fibonacci_ote=fibo_ote,
            require_poi_confluence=True
        )

        quote = PriceQuote(bid=bid, ask=ask, spread=spread, timestamp=now)

        snapshot = MarketStateSnapshot(
            symbol=self.canonical_symbol,
            timestamp=now,
            timeframe=self.timeframe,
            current_price=quote,
            htf_trend=self.current_trend,
            structure=struct_state,
            active_fvgs=self.active_fvgs[-10:],  # Retain top 10 most recent
            active_ifvgs=self.active_ifvgs[-10:],
            fvg_confluences=self.fvg_confluences[-5:],
            active_obs=cluster_order_blocks(self.active_obs)[-5:],     # Retain top 5 most recent consolidated clusters
            active_breakers=self.active_breakers[-5:],
            active_candle_patterns=candle_patterns[-10:],             # Retain top 10 recent confirmation patterns
            fibonacci=fibo_ote,
            liquidity=liq_state
        )

        self.last_snapshot = snapshot
        return snapshot

    def _save_snapshot_to_cache(self, snapshot: MarketStateSnapshot):
        """Atomically saves snapshot to JSON to prevent race conditions during reads."""
        cache_file = self.cache_dir / f"live_snapshot_{self.canonical_symbol.lower()}.json"
        temp_file = self.cache_dir / f".tmp_{self.canonical_symbol.lower()}_{int(datetime.now().timestamp())}.json"

        with open(temp_file, "w") as f:
            f.write(snapshot.model_dump_json(indent=2))

        temp_file.replace(cache_file)
