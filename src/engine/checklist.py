from typing import List, Dict
from src.core.types import (
    MarketStateSnapshot,
    ChecklistRule,
    ChecklistEvaluation,
    Direction,
    Trend
)


class ChecklistScoringEngine:
    """
    Deterministic scoring engine that tests a MarketStateSnapshot
    against configured strategy checklist rules.
    """

    def __init__(self, strategy_id: str, rules: List[ChecklistRule], min_score_threshold: float):
        self.strategy_id = strategy_id
        self.rules = rules
        self.min_score_threshold = min_score_threshold

    def evaluate(self, snapshot: MarketStateSnapshot, target_direction: Direction) -> ChecklistEvaluation:
        total_score = 0.0
        max_possible_score = sum(r.weight for r in self.rules)
        criteria_met: Dict[str, bool] = {}
        failed_mandatory = False

        for rule in self.rules:
            is_met = self._test_rule(rule.id, snapshot, target_direction)
            criteria_met[rule.id] = is_met

            if is_met:
                total_score += rule.weight
            elif rule.mandatory:
                failed_mandatory = True

        passed = (not failed_mandatory) and (total_score >= self.min_score_threshold)
        pct = (total_score / max_possible_score * 100.0) if max_possible_score > 0 else 0.0

        return ChecklistEvaluation(
            strategy_id=self.strategy_id,
            direction=target_direction if passed else Direction.WAIT,
            total_score=total_score,
            max_possible_score=max_possible_score,
            passed=passed,
            criteria_met=criteria_met,
            score_percentage=pct,
            rationale=(
                f"Evaluation passed with score {total_score:.1f}/{max_possible_score:.1f} ({pct:.1f}%)"
                if passed else
                f"Evaluation rejected (failed_mandatory={failed_mandatory}, score={total_score:.1f}/{self.min_score_threshold:.1f})"
            )
        )

    def _test_rule(self, rule_id: str, snapshot: MarketStateSnapshot, direction: Direction) -> bool:
        if rule_id == "HTF_TREND_ALIGNED":
            if direction == Direction.BUY:
                return snapshot.htf_trend == Trend.BULLISH
            elif direction == Direction.SELL:
                return snapshot.htf_trend == Trend.BEARISH

        elif rule_id == "LIQUIDITY_SWEPT":
            if direction == Direction.BUY:
                return snapshot.liquidity.sell_side_swept
            elif direction == Direction.SELL:
                return snapshot.liquidity.buy_side_swept

        elif rule_id == "IN_OTE_ZONE":
            return bool(snapshot.fibonacci and snapshot.fibonacci.in_ote_zone)

        elif rule_id == "ACTIVE_POI_PRESENT":
            if direction == Direction.BUY:
                has_bull_fvg = any(f.direction == Direction.BUY and not f.is_mitigated for f in snapshot.active_fvgs)
                has_bull_ob = any(o.direction == Direction.BUY and not o.is_mitigated for o in snapshot.active_obs)
                return has_bull_fvg or has_bull_ob
            elif direction == Direction.SELL:
                has_bear_fvg = any(f.direction == Direction.SELL and not f.is_mitigated for f in snapshot.active_fvgs)
                has_bear_ob = any(o.direction == Direction.SELL and not o.is_mitigated for o in snapshot.active_obs)
                return has_bear_fvg or has_bear_ob

        return False
