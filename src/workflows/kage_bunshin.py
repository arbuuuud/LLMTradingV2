"""
Kage Bunshin Parallel Matrix Runner (Workflow 2 - T3-2).
Fans out hundreds to thousands of Shadow Clones across multi-core CPU workers,
executes backtesting in parallel over the Two-Tier Data Lake, and returns a unified leaderboard.
"""

from typing import List, Optional, Dict, Any
from concurrent.futures import ProcessPoolExecutor, as_completed
import time
import polars as pl
from pathlib import Path

from src.core.types import (
    MethodologyInput,
    ShadowCloneSpec,
    ShadowCloneResult,
    FourRiskProfilesReport
)
from src.agents.naruto import NarutoAgent
from src.agents.auditor import AuditorAgent
from src.workflows.backtest import BacktestEngine


def _simulate_single_clone_worker(args: Tuple[ShadowCloneSpec, str]) -> ShadowCloneResult:
    """Worker function executed across parallel CPU cores."""
    spec, parquet_path = args
    df = pl.read_parquet(parquet_path)
    engine = BacktestEngine(initial_capital=10000.0, base_risk_pct=0.50)
    return engine.run_simulation(spec, df)


# Need Tuple for typing in worker
from typing import Tuple


class KageBunshinRunner:
    """Parallel multi-core matrix runner for Shadow Clones."""

    def __init__(
        self,
        parquet_path: str = "data/parquet/XAUUSD/M1/XAUUSD_M1.parquet",
        max_workers: Optional[int] = None
    ):
        self.parquet_path = parquet_path
        self.max_workers = max_workers
        self.naruto = NarutoAgent()
        self.auditor = AuditorAgent()

    def run_tournament(
        self,
        methodology: MethodologyInput,
        intensity: str = "FAST",
        slice_bars: Optional[int] = 10000
    ) -> Tuple[List[ShadowCloneResult], Optional[FourRiskProfilesReport]]:
        """
        Executes a complete Kage Bunshin Tournament:
        1. Naruto spawns hundreds of Shadow Clones.
        2. Clones run in parallel across CPU cores.
        3. Auditor audits, eliminates dormant/fragile clones, and crowns the Champion.
        4. Champion is mapped into the 4 Standard Risk Profiles.
        """
        clones = self.naruto.spawn_clones(methodology, intensity=intensity)
        total_clones = len(clones)
        print(f"[Kage Bunshin] Naruto spawned {total_clones:,} Shadow Clones for '{methodology.name}'...")

        # If slicing for fast evaluation
        target_parquet = self.parquet_path
        temp_slice_path = None
        if slice_bars is not None:
            df = pl.read_parquet(self.parquet_path).tail(slice_bars)
            temp_slice_path = Path(f"data/cache/.tmp_tournament_{int(time.time())}.parquet")
            temp_slice_path.parent.mkdir(parents=True, exist_ok=True)
            df.write_parquet(temp_slice_path)
            target_parquet = str(temp_slice_path)

        t0 = time.time()
        results: List[ShadowCloneResult] = []

        try:
            worker_args = [(spec, target_parquet) for spec in clones]
            with ProcessPoolExecutor(max_workers=self.max_workers) as executor:
                futures = [executor.submit(_simulate_single_clone_worker, arg) for arg in worker_args]
                for fut in as_completed(futures):
                    try:
                        res = fut.result()
                        results.append(res)
                    except Exception as e:
                        pass
        finally:
            if temp_slice_path and temp_slice_path.exists():
                temp_slice_path.unlink()

        elapsed = time.time() - t0
        print(f"[Kage Bunshin] Completed {len(results):,} clone simulations in {elapsed:.2f}s ({len(results)/max(elapsed, 0.1):.1f} clones/sec)")

        # Audit & Rank
        ranked = self.auditor.audit_and_rank_clones(results)
        champion = next((r for r in ranked if not r.is_disqualified), None)

        report = None
        if champion:
            report = self.auditor.generate_four_risk_profiles(champion, strategy_id=f"STRAT-{methodology.name}-001")

        return ranked, report
