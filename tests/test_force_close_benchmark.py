from datetime import datetime, timedelta
import polars as pl
import pytest

from src.core.types import (
    ShadowCloneSpec,
    Direction,
    TradingStyle,
    SessionKillzone,
    ForceClosePolicy,
    PACRetestMode,
    PACHandoverMode
)
from src.workflows.force_close_benchmark import ForceCloseAnalyticsRunner


def test_force_close_benchmark_runner():
    runner = ForceCloseAnalyticsRunner()
    base_spec = ShadowCloneSpec(
        clone_id="BENCHMARK-PAC-M1",
        methodology="PAC",
        timeframe="M1",
        limit_layers=3,
        hard_sl_pct=-15.0,
        soft_sl_candle_close_pct=-5.0,
        hard_tp_pct=50.0,
        session=SessionKillzone.ALL_DAY
    )

    parquet_path = "data/parquet/XAUUSD/M1/XAUUSD_M1.parquet"
    df = pl.read_parquet(parquet_path).tail(3000)

    benchmark = runner.run_benchmark(base_spec, df)

    assert benchmark.methodology == "PAC"
    assert benchmark.total_samples == 3000
    assert benchmark.baseline_passive.clone_id.endswith("-PASSIVE")
    assert benchmark.guardian_mom_kill.clone_id.endswith("-MOM-KILL")
    assert benchmark.guardian_partial_bep.clone_id.endswith("-HANDOVER-BEP")
    assert benchmark.efficacy_conclusion != ""
