import polars as pl
from src.workflows.backtest import BacktestEngine
from src.agents.naruto import NarutoAgent
from src.core.types import MethodologyInput, TradingStyle

def main():
    df_m1 = pl.read_parquet("data/parquet/XAUUSD/M1/XAUUSD_M1.parquet")
    base_bars = 20000
    df_m1_slice = df_m1.tail(base_bars)

    timeframes = ["M1", "M2", "M3", "M4", "M5"]
    tf_dfs = {"M1": df_m1_slice}

    for tf in ["M2", "M3", "M4", "M5"]:
        mins = int(tf[1:])
        df_res = (
            df_m1_slice.sort("timestamp")
            .group_by_dynamic("timestamp", every=f"{mins}m")
            .agg([
                pl.first("open").alias("open"),
                pl.max("high").alias("high"),
                pl.min("low").alias("low"),
                pl.last("close").alias("close"),
                pl.sum("tick_volume").alias("tick_volume")
            ])
        )
        tf_dfs[tf] = df_res

    naruto = NarutoAgent()
    clones = naruto.spawn_clones(MethodologyInput(name="PAC", trading_style=TradingStyle.SCALPING), intensity="FAST")
    champ_spec = clones[3]  # Asian session, deeper retest, cancel on TP, partial exit BEP

    print("=" * 95)
    print("COMPREHENSIVE MULTI-TIMEFRAME SHOWDOWN: M1 vs M2 vs M3 vs M4 vs M5")
    print("Methodology: PAC Scalping | Data: 20,000 M1 Equivalent Bars (Identical Market Period)")
    print("=" * 95)

    engine = BacktestEngine(initial_capital=10000.0, base_risk_pct=0.50)

    results = []
    for tf in timeframes:
        df_cur = tf_dfs[tf]
        spec_tf = champ_spec.model_copy(update={"timeframe": tf, "clone_id": f"CHAMP-{tf}"})
        res = engine.run_simulation(spec_tf, df_cur)
        results.append((tf, len(df_cur), res))

    header = f"{'TF':<4} | {'Bars':<6} | {'Trades':<8} | {'Trades/Day':<10} | {'WinRate':<8} | {'ProfitFactor':<12} | {'MaxDD':<7} | {'Net PnL ($)':<12} | {'ROI (%)':<8}"
    print(header)
    print("-" * 95)
    for tf, bars, r in results:
        row = f"{tf:<4} | {bars:<6} | {r.total_trades:<8} | {r.avg_trades_per_day:<10.1f} | {r.win_rate_pct:<7.1f}% | {r.profit_factor:<12.2f} | {r.max_drawdown_pct:<6.1f}% | ${r.net_pnl:<11.2f} | +{r.roi_pct:<7.1f}%"
        print(row)
    print("=" * 95)

if __name__ == "__main__":
    main()
