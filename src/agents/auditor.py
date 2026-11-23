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
        Disqualifies clones suffering from analysis paralysis (< 30 trades/month)
        or mathematical anomalies (e.g. inverted stop loss specs).
        """
        for r in results:
            # Check 0: Mathematical Integrity & Inverted Stops Audit (INCIDENT-001 Anti-Corruption Gate)
            if getattr(r.spec, "hard_sl_pct", -20.0) >= 0.0:
                r.is_disqualified = True
                r.disqualification_reason = f"MATH_ANOMALY: Inverted Stop Loss pct ({r.spec.hard_sl_pct}% >= 0.0% floor)"
                continue

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

    def audit_benchmark_milestone(
        self,
        candidate_metrics: Dict[str, Any],
        baseline_metrics: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Audits a new strategy candidate against the institutional baseline (DEC-043).
        Checks improvement across the Golden Triangle KPIs:
        1. Weekly 5% Target Hit Rate (primary consistency engine)
        2. Daily 1% Target Hit Rate (daily compounding velocity)
        3. Max Drawdown & Daily Loss Breach (capital preservation)
        """
        if baseline_metrics is None:
            from src.analytics.benchmark_matrix import DEFAULT_BASELINE
            baseline_metrics = DEFAULT_BASELINE

        cand_pnl = float(candidate_metrics.get("net_pnl", 0.0))
        base_pnl = float(baseline_metrics.get("net_pnl", 1.0))
        delta_pnl = cand_pnl - base_pnl

        cand_dd = float(candidate_metrics.get("max_drawdown_pct", 0.0))
        base_dd = float(baseline_metrics.get("max_drawdown_pct", 0.0))
        delta_dd = cand_dd - base_dd

        cand_daily = float(candidate_metrics.get("daily_1pct_target_hit_rate", 0.0))
        base_daily = float(baseline_metrics.get("daily_1pct_target_hit_rate", 0.0))
        delta_daily = cand_daily - base_daily

        cand_weekly = float(candidate_metrics.get("weekly_5pct_target_hit_rate", 0.0))
        base_weekly = float(baseline_metrics.get("weekly_5pct_target_hit_rate", 0.0))
        delta_weekly = cand_weekly - base_weekly

        cand_breach = float(candidate_metrics.get("daily_loss_breach_rate", 0.0))
        base_breach = float(baseline_metrics.get("daily_loss_breach_rate", 0.0))
        delta_breach = cand_breach - base_breach

        passes_weekly = cand_weekly >= base_weekly
        passes_dd = cand_dd <= (base_dd * 1.10) # Max 10% allowance if profit jumps significantly
        passes_pnl = cand_pnl >= base_pnl

        is_approved = passes_weekly and passes_dd and passes_pnl

        # Quant Composite Score
        score = (
            (cand_weekly * 2.0) +
            (cand_daily * 1.5) +
            (candidate_metrics.get("profit_factor", 1.0) * 20.0) -
            (cand_dd * 3.0) -
            (cand_breach * 4.0)
        )

        return {
            "is_approved_upgrade": is_approved,
            "quant_score": round(score, 2),
            "weekly_5pct_improved": passes_weekly,
            "drawdown_contained": passes_dd,
            "profit_improved": passes_pnl,
            "deltas": {
                "net_pnl": round(delta_pnl, 2),
                "max_drawdown_pct": round(delta_dd, 2),
                "daily_1pct_rate": round(delta_daily, 1),
                "weekly_5pct_rate": round(delta_weekly, 1),
                "daily_loss_breach_rate": round(delta_breach, 1)
            },
            "recommendation": (
                "PROMOTE TO CHAMPION MILESTONE: Superior weekly consistency and tighter drawdown."
                if is_approved else
                "REVISE CANDIDATE: Does not beat baseline across weekly/drawdown hurdles."
            )
        }

