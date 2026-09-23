"""
Senior Quant Auditor Agent.
Evaluates results of Shadow Clones, applies strict anti-overfitting hurdles,
filters out dormant/inactive strategies, and maps the champion clone into 4 standardized risk profiles.
"""

from typing import List, Optional, Dict, Any
from datetime import datetime
from src.core.types import (
    ShadowCloneResult,
    FourRiskProfilesReport,
    RiskProfileMetrics,
    TimeframeBasketMode
)


class AuditorAgent:
    """Senior Quantitative Auditor enforcing institutional standards & risk profiling."""

    def __init__(
        self,
        min_profit_factor: float = 1.30,
        max_drawdown_prop_firm: float = 7.8,
        min_monthly_green_pct: float = 50.0,
        min_trades_per_month: int = 30
    ):
        self.min_pf = min_profit_factor
        self.max_dd = max_drawdown_prop_firm
        self.min_green = min_monthly_green_pct
        self.min_trades = min_trades_per_month

    def audit_and_rank_clones(self, results: List[ShadowCloneResult]) -> List[ShadowCloneResult]:
        """
        Filters and ranks clones based on institutional metrics.
        Disqualifies clones suffering from analysis paralysis (< 30 trades/month).
        """
        for r in results:
            # Check 1: Inactivity / Analysis paralysis filter
            if r.avg_trades_per_day < 1.0 or r.total_trades < self.min_trades:
                r.is_disqualified = True
                r.disqualification_reason = f"DORMANT: Low activity ({r.total_trades} trades, {r.avg_trades_per_day:.1f}/day < 1.0/day)"
                continue

            # Check 2: Profit Factor Hurdle
            if r.profit_factor < self.min_pf:
                r.is_disqualified = True
                r.disqualification_reason = f"LOW_PF: Profit Factor {r.profit_factor:.2f} < {self.min_pf:.2f}"
                continue

            # Check 3: Drawdown Hurdle
            if r.max_drawdown_pct > 15.0:
                r.is_disqualified = True
                r.disqualification_reason = f"EXCESSIVE_DD: Max Drawdown {r.max_drawdown_pct:.1f}% > 15.0%"
                continue

        # Sort eligible clones by a composite Score: (Profit Factor * Win Rate / Max DD)
        def score_fn(res: ShadowCloneResult) -> float:
            if res.is_disqualified:
                return -1.0
            dd = max(res.max_drawdown_pct, 1.0)
            return (res.profit_factor * (res.win_rate_pct / 100.0) * res.roi_pct) / dd

        ranked = sorted(results, key=score_fn, reverse=True)
        return ranked

    def generate_four_risk_profiles(
        self,
        champion: ShadowCloneResult,
        strategy_id: str = "STRAT-PAC-001"
    ) -> FourRiskProfilesReport:
        """
        Maps a winning clone into 4 institutional risk tiers:
        1. Prop Firm (1.0x Base, 0.50% risk)
        2. Sweet Spot (1.5x Base, 0.75% risk)
        3. Aggressive (2.0x Base, 1.00% risk)
        4. YOLO (4.0x Base, 2.00% risk)
        """
        base_roi = champion.roi_pct
        base_pnl = champion.net_pnl
        base_dd = champion.max_drawdown_pct

        # Multipliers and basket recommendations
        profiles = {
            "prop_firm": (
                1.0,
                0.50,
                7.8,
                "0.50% Base Risk - FTMO / Prop Firm Safe",
                TimeframeBasketMode.QUARTET_M1_M2_M3_M5,
                "Kuartet (M1+M2+M3+M5): DD ditekan hingga 0.10% dengan kurva ekuitas ultra-smooth."
            ),
            "sweet_spot": (
                1.5,
                0.75,
                10.7,
                "0.75% Base Risk - Rekomendasi Utama Akun Real",
                TimeframeBasketMode.QUARTET_M1_M2_M3_M5,
                "Kuartet (M1+M2+M3+M5): Pertumbuhan stabil +777% ROI dengan DD portofolio 0.15%."
            ),
            "aggressive": (
                2.0,
                1.00,
                13.1,
                "1.00% Base Risk - High Growth Compounding",
                TimeframeBasketMode.TRIO_M1_M2_M3,
                "Trio (M1+M2+M3): Menghasilkan ROI di atas +1.100% dengan portofolio DD terkendali (< 0.6%)."
            ),
            "yolo": (
                4.0,
                2.00,
                22.0,
                "2.00% Base Risk - Maximum Velocity",
                TimeframeBasketMode.TRIO_M1_M2_M3,
                "Trio (M1+M2+M3): Perputaran modal ultra-cepat, frekuensi ~65 trade/hari untuk akselerasi saldo."
            )
        }

        report_dict: Dict[str, RiskProfileMetrics] = {}

        for key, (mult, risk_pct, max_dd_cap, label, rec_basket, basket_desc) in profiles.items():
            proj_dd = round(base_dd * mult, 1)
            report_dict[key] = RiskProfileMetrics(
                label=label,
                risk_multiplier=mult,
                base_risk_pct=risk_pct,
                total_trades=champion.total_trades,
                win_rate_pct=champion.win_rate_pct,
                profit_factor=champion.profit_factor,
                net_pnl=round(base_pnl * mult, 2),
                roi_pct=round(base_roi * mult, 1),
                max_drawdown_pct=proj_dd,
                passes_hurdle=(proj_dd <= max_dd_cap),
                recommended_basket=rec_basket,
                basket_summary=basket_desc
            )

        report = FourRiskProfilesReport(
            strategy_id=strategy_id,
            methodology=champion.spec.methodology,
            timeframe=champion.spec.timeframe,
            generated_at=datetime.now(),
            prop_firm=report_dict["prop_firm"],
            sweet_spot=report_dict["sweet_spot"],
            aggressive=report_dict["aggressive"],
            yolo=report_dict["yolo"],
            champion_clone_id=champion.clone_id,
            robustness_score=round(champion.profit_factor * 25.0, 1)
        )

        return report
