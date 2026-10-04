"""
Institutional POI Prioritizer & Anchor Selector Engine.
Implements the 3 Core User Mandates:
1. Track all active RBR (Rally-Base-Rally) and DBD (Drop-Base-Drop) bases that are not fully used (virgin or tested).
2. Track FVG, iFVG, FVG+iFVG confluences, and classic Reversal OBs (DBR/RBD).
3. Proximity Prioritization: When areas are close together (e.g. within threshold pts),
   strictly prioritize RBR/DBD as the primary Floor / Roof over classic OBs!
   (e.g., Bearish OB at 4000, DBD at 4010 -> DBD selected as primary Roof at 4010).
"""

from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime

from src.core.types import Direction, OrderBlock, OrderBlockType, FairValueGap
from src.features.smc import FVGConfluenceZone


@dataclass
class SelectedPOIAnchor:
    """Consolidated POI anchor selected by the prioritizer."""
    poi_type: str                  # 'DBD', 'RBR', 'CONFLUENCE_CLUSTER', 'RBD_OB', 'DBR_OB', 'FVG', 'IFVG', 'SWING'
    direction: Direction
    top: float
    bottom: float
    anchor_price: float            # For Roof = top/high, for Floor = bottom/low
    mean_threshold: float
    is_virgin: bool
    touch_count: int
    proximity_merged: bool = False
    merged_description: str = ""
    original_sources: List[str] = field(default_factory=list)


class POIPrioritizer:
    """
    Ranks and selects the highest-probability Roof (Supply) and Floor (Demand) anchors
    based on proximity clustering and strict structural hierarchy.
    """

    def __init__(self, proximity_threshold_points: float = 15.0):
        self.proximity_threshold = proximity_threshold_points

    def rank_and_select_roof(
        self,
        current_price: float,
        obs: List[OrderBlock],
        fvgs: List[FairValueGap],
        confluences: List[FVGConfluenceZone],
        fallback_swing_high: float
    ) -> SelectedPOIAnchor:
        """
        Selects the primary ROOF (Supply) anchor above current price.
        Prioritizes:
        1. Fresh DBD (Drop-Base-Drop) Continuation Bases
        2. FVG Confluence Clusters / Overlaps
        3. Classic RBD (Rally-Base-Drop) Reversal OBs
        4. Fresh Bearish FVGs
        5. Fallback Swing High
        """
        candidates: List[Dict[str, Any]] = []

        # 1. Harvest Active Bearish OBs (DBD and RBD)
        for ob in obs:
            if ob.direction == Direction.SELL and not ob.is_fully_used and ob.bottom >= current_price - 0.50:
                is_dbd = (ob.ob_type == OrderBlockType.CONTINUATION_DBD)
                # Hierarchy tier: DBD is Tier 1 (highest priority), RBD is Tier 3
                tier = 1 if is_dbd else 3
                score = 100.0 if is_dbd else 70.0
                if ob.touch_count == 0:
                    score += 15.0 # Virgin bonus
                candidates.append({
                    "tier": tier,
                    "score": score,
                    "type": "DBD" if is_dbd else "RBD_OB",
                    "top": ob.top,
                    "bottom": ob.bottom,
                    "anchor_price": ob.top,
                    "mt": ob.mean_threshold,
                    "virgin": (ob.touch_count == 0),
                    "touches": ob.touch_count,
                    "desc": f"{'Continuation DBD' if is_dbd else 'Reversal RBD OB'} (${ob.bottom:.2f} - ${ob.top:.2f})"
                })

        # 2. Harvest FVG Confluence Clusters
        for conf in confluences:
            if conf.overlap_bottom >= current_price - 0.50:
                candidates.append({
                    "tier": 2,
                    "score": 85.0 + (conf.probability_score or 0.0),
                    "type": "CONFLUENCE_CLUSTER",
                    "top": conf.overlap_top,
                    "bottom": conf.overlap_bottom,
                    "anchor_price": conf.overlap_top,
                    "mt": (conf.overlap_top + conf.overlap_bottom) / 2.0,
                    "virgin": True,
                    "touches": 0,
                    "desc": f"FVG+iFVG Cluster (${conf.overlap_bottom:.2f} - ${conf.overlap_top:.2f})"
                })

        # 3. Harvest Fresh Bearish FVGs
        for fvg in fvgs:
            if fvg.direction == Direction.SELL and not fvg.is_mitigated and fvg.bottom >= current_price - 0.50:
                candidates.append({
                    "tier": 4,
                    "score": 60.0,
                    "type": "FVG",
                    "top": fvg.top,
                    "bottom": fvg.bottom,
                    "anchor_price": fvg.top,
                    "mt": (fvg.top + fvg.bottom) / 2.0,
                    "virgin": True,
                    "touches": 0,
                    "desc": f"Bearish FVG (${fvg.bottom:.2f} - ${fvg.top:.2f})"
                })

        if not candidates:
            # Fallback to swing high
            top_p = max(current_price + 3.0, fallback_swing_high)
            btm_p = top_p - 2.5
            return SelectedPOIAnchor(
                poi_type="SWING_HIGH",
                direction=Direction.SELL,
                top=top_p,
                bottom=btm_p,
                anchor_price=top_p,
                mean_threshold=(top_p + btm_p) / 2.0,
                is_virgin=True,
                touch_count=0,
                proximity_merged=False,
                merged_description=f"Fallback Swing High Peak at ${top_p:.2f}"
            )

        # Apply Proximity Prioritization Rule:
        # Group candidates located within proximity_threshold of each other
        candidates.sort(key=lambda x: x["anchor_price"])
        best_candidate = self._resolve_proximity_group(candidates, is_roof=True)

        return SelectedPOIAnchor(
            poi_type=best_candidate["type"],
            direction=Direction.SELL,
            top=best_candidate["top"],
            bottom=best_candidate["bottom"],
            anchor_price=best_candidate["anchor_price"],
            mean_threshold=best_candidate["mt"],
            is_virgin=best_candidate["virgin"],
            touch_count=best_candidate["touches"],
            proximity_merged=best_candidate.get("merged", False),
            merged_description=best_candidate["desc"]
        )

    def rank_and_select_floor(
        self,
        current_price: float,
        obs: List[OrderBlock],
        fvgs: List[FairValueGap],
        confluences: List[FVGConfluenceZone],
        fallback_swing_low: float
    ) -> SelectedPOIAnchor:
        """
        Selects the primary FLOOR (Demand) anchor below current price.
        Prioritizes:
        1. Fresh RBR (Rally-Base-Rally) Continuation Bases
        2. FVG Confluence Clusters / Overlaps
        3. Classic DBR (Drop-Base-Rally) Reversal OBs
        4. Fresh Bullish FVGs
        5. Fallback Swing Low
        """
        candidates: List[Dict[str, Any]] = []

        # 1. Harvest Active Bullish OBs (RBR and DBR)
        for ob in obs:
            if ob.direction == Direction.BUY and not ob.is_fully_used and ob.top <= current_price + 0.50:
                is_rbr = (ob.ob_type == OrderBlockType.CONTINUATION_RBR)
                tier = 1 if is_rbr else 3
                score = 100.0 if is_rbr else 70.0
                if ob.touch_count == 0:
                    score += 15.0
                candidates.append({
                    "tier": tier,
                    "score": score,
                    "type": "RBR" if is_rbr else "DBR_OB",
                    "top": ob.top,
                    "bottom": ob.bottom,
                    "anchor_price": ob.bottom,
                    "mt": ob.mean_threshold,
                    "virgin": (ob.touch_count == 0),
                    "touches": ob.touch_count,
                    "desc": f"{'Continuation RBR' if is_rbr else 'Reversal DBR OB'} (${ob.bottom:.2f} - ${ob.top:.2f})"
                })

        # 2. Harvest FVG Confluence Clusters
        for conf in confluences:
            if conf.overlap_top <= current_price + 0.50:
                candidates.append({
                    "tier": 2,
                    "score": 85.0 + (conf.probability_score or 0.0),
                    "type": "CONFLUENCE_CLUSTER",
                    "top": conf.overlap_top,
                    "bottom": conf.overlap_bottom,
                    "anchor_price": conf.overlap_bottom,
                    "mt": (conf.overlap_top + conf.overlap_bottom) / 2.0,
                    "virgin": True,
                    "touches": 0,
                    "desc": f"FVG+iFVG Cluster (${conf.overlap_bottom:.2f} - ${conf.overlap_top:.2f})"
                })

        # 3. Harvest Fresh Bullish FVGs
        for fvg in fvgs:
            if fvg.direction == Direction.BUY and not fvg.is_mitigated and fvg.top <= current_price + 0.50:
                candidates.append({
                    "tier": 4,
                    "score": 60.0,
                    "type": "FVG",
                    "top": fvg.top,
                    "bottom": fvg.bottom,
                    "anchor_price": fvg.bottom,
                    "mt": (fvg.top + fvg.bottom) / 2.0,
                    "virgin": True,
                    "touches": 0,
                    "desc": f"Bullish FVG (${fvg.bottom:.2f} - ${fvg.top:.2f})"
                })

        if not candidates:
            # Fallback to swing low
            btm_p = min(current_price - 3.0, fallback_swing_low)
            top_p = btm_p + 2.5
            return SelectedPOIAnchor(
                poi_type="SWING_LOW",
                direction=Direction.BUY,
                top=top_p,
                bottom=btm_p,
                anchor_price=btm_p,
                mean_threshold=(top_p + btm_p) / 2.0,
                is_virgin=True,
                touch_count=0,
                proximity_merged=False,
                merged_description=f"Fallback Swing Low Base at ${btm_p:.2f}"
            )

        candidates.sort(key=lambda x: -x["anchor_price"]) # closest below current price first
        best_candidate = self._resolve_proximity_group(candidates, is_roof=False)

        return SelectedPOIAnchor(
            poi_type=best_candidate["type"],
            direction=Direction.BUY,
            top=best_candidate["top"],
            bottom=best_candidate["bottom"],
            anchor_price=best_candidate["anchor_price"],
            mean_threshold=best_candidate["mt"],
            is_virgin=best_candidate["virgin"],
            touch_count=best_candidate["touches"],
            proximity_merged=best_candidate.get("merged", False),
            merged_description=best_candidate["desc"]
        )

    def _resolve_proximity_group(self, candidates: List[Dict[str, Any]], is_roof: bool) -> Dict[str, Any]:
        """
        Groups candidates within proximity_threshold.
        If a higher priority Tier (Tier 1 RBR/DBD) exists near Tier 3 OB,
        Tier 1 RBR/DBD wins and anchors the Roof / Floor!
        """
        lead = candidates[0]
        nearby = [c for c in candidates if abs(c["anchor_price"] - lead["anchor_price"]) <= self.proximity_threshold]

        if len(nearby) == 1:
            return lead

        # Sort nearby by tier (1 is best: RBR/DBD), then by score
        nearby.sort(key=lambda x: (x["tier"], -x["score"]))
        winner = nearby[0]

        # Consolidate boundaries across the nearby cluster
        c_top = max(c["top"] for c in nearby)
        c_btm = min(c["bottom"] for c in nearby)
        merged_desc = f"{winner['type']} Winner (merged with {len(nearby)-1} adjacent zones): ${c_btm:.2f} - ${c_top:.2f}"

        return {
            "tier": winner["tier"],
            "score": winner["score"],
            "type": winner["type"],
            "top": c_top,
            "bottom": c_btm,
            "anchor_price": c_top if is_roof else c_btm,
            "mt": (c_top + c_btm) / 2.0,
            "virgin": any(c["virgin"] for c in nearby),
            "touches": min(c["touches"] for c in nearby),
            "merged": True,
            "desc": merged_desc
        }
