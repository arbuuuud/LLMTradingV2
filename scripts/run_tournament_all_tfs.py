import polars as pl
from src.workflows.kage_bunshin import KageBunshinRunner
from src.core.types import MethodologyInput, TradingStyle

def main():
    df_m1 = pl.read_parquet("data/parquet/XAUUSD/M1/XAUUSD_M1.parquet")
    base_bars = 20000
    df_m1_slice = df_m1.tail(base_bars)

    runner = KageBunshinRunner()
    methodology = MethodologyInput(name="PAC", trading_style=TradingStyle.SCALPING)

    timeframes = ["M1", "M2", "M3", "M4", "M5"]

    print("=" * 105)
    print("AUDITED TOURNAMENT MATRIX: M1 vs M2 vs M3 vs M4 vs M5 (64 Clones per TF)")
    print("=" * 105)

    for tf in timeframes:
        if tf == "M1":
            df_cur = df_m1_slice
        else:
            mins = int(tf[1:])
            df_cur = (
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

        ranked, report = runner.run_tournament(methodology, intensity="FAST", slice_bars=len(df_cur))
        champ = ranked[0]
        prop = report.prop_firm if report else None

        print(f"\n[{tf}] BARS: {len(df_cur):<5} | CHAMPION: {champ.clone_id}")
        print(f"     Trades: {champ.total_trades} ({champ.avg_trades_per_day:.1f}/day) | WinRate: {champ.win_rate_pct:.1f}% | PF: {champ.profit_factor:.1f} | MaxDD: {champ.max_drawdown_pct:.1f}%")
        if prop:
            print(f"     🛡️ Prop Firm Hurdle (0.5% risk): MaxDD: {prop.max_drawdown_pct:.1f}% | Passed: {prop.passes_hurdle} (Max Limit <= 7.8%)")

if __name__ == "__main__":
    main()
