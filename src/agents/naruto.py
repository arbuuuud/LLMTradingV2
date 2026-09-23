"""
Naruto Agent - Master Kage Bunshin Orchestrator.
Receives user methodology input (e.g. PAC) and autonomously generates a multi-dimensional
Shadow Clone search space based on the 4 Core Dimensions:
1. Market Structure & Wave State
2. POI Characteristics & Selection
3. Candlestick Role (Execution Trigger vs Guardian Force Close)
4. Trading Sessions & Killzones
"""

from typing import List, Dict, Any
from src.core.types import (
    MethodologyInput,
    ShadowCloneSpec,
    TradingStyle,
    SessionKillzone,
    ForceClosePolicy
)


class NarutoAgent:
    """Master Orchestrator Agent that divides itself into Shadow Clones."""

    def __init__(self, agent_name: str = "NarutoMasterBrain"):
        self.agent_name = agent_name

    def spawn_clones(self, methodology: MethodologyInput) -> List[ShadowCloneSpec]:
        """
        Takes a core methodology (e.g. PAC) and autonomously splits into a matrix
        of diverse Shadow Clones exploring all 4 dimensions.
        """
        clones: List[ShadowCloneSpec] = []
        name = methodology.name.upper()

        # Dimension 1: Wave & Structure States
        structure_variations = [
            {"wave_regime": "ALL", "bos_choch": False, "fibo_ote": False, "tag": "StructureAll"},
            {"wave_regime": "IMPULSIVE", "bos_choch": True, "fibo_ote": False, "tag": "ImpulseBOS"},
            {"wave_regime": "SIDEWAY", "bos_choch": False, "fibo_ote": False, "tag": "SidewayRange"},
            {"wave_regime": "ALL", "bos_choch": False, "fibo_ote": True, "tag": "FiboOTE"},
        ]

        # Dimension 2: POI Types & Freshness
        poi_variations = [
            {"types": ["OB", "CONTINUATION_SD", "CONFLUENCE"], "swept": False, "touches": 2, "tag": "AllPOIs"},
            {"types": ["CONFLUENCE"], "swept": True, "touches": 0, "tag": "HighConvictionCluster"},
            {"types": ["OB"], "swept": True, "touches": 1, "tag": "ReversalOBSwept"},
            {"types": ["FVG"], "swept": False, "touches": 1, "tag": "FVGGaps"},
        ]

        # Dimension 3: Execution, Layers & Force Close Policy
        exec_variations = [
            {
                "mode": "LIMIT_GRID",
                "layers": 5,
                "hard_sl": -20.0,
                "soft_sl": -5.0,
                "fc": ForceClosePolicy.PARTIAL_50_BEP,
                "tag": "Grid5L_PartialBEP"
            },
            {
                "mode": "LIMIT_GRID",
                "layers": 3,
                "hard_sl": -15.0,
                "soft_sl": 0.0,
                "fc": ForceClosePolicy.COUNTER_MOM_ONLY,
                "tag": "Grid3L_MomKill"
            },
            {
                "mode": "CONFIRMED_REACTION",
                "layers": 1,
                "hard_sl": -25.0,
                "soft_sl": -5.0,
                "fc": ForceClosePolicy.COUNTER_POI_TOUCH,
                "tag": "ReacEntry_CounterPoi"
            },
        ]

        # Dimension 4: Time Sessions
        session_variations = [
            {"session": SessionKillzone.ALL_DAY, "tag": "AllDay"},
            {"session": SessionKillzone.ASIAN, "tag": "Asian"},
            {"session": SessionKillzone.NY_OVERLAP, "tag": "NYOverlap"},
        ]

        # Target Timeframes for Scalping
        timeframes = ["M1", "M3", "M5"] if methodology.trading_style == TradingStyle.SCALPING else ["M15", "H1"]

        # Autonomous Matrix Permutation (Curated multi-dimensional grid)
        idx = 1
        for tf in timeframes:
            for s_var in structure_variations:
                for p_var in poi_variations[:2]:  # Top representative POIs
                    for e_var in exec_variations[:2]:  # Top representative execution setups
                        for sess_var in session_variations:  # All sessions (AllDay, Asian, NYOverlap)
                            clone_id = f"CLONE-{name}-{tf}-{idx:03d}-{s_var['tag']}-{p_var['tag']}-{e_var['tag']}-{sess_var['tag']}"
                            spec = ShadowCloneSpec(
                                clone_id=clone_id,
                                methodology=methodology.name,
                                timeframe=tf,
                                trading_style=methodology.trading_style,
                                wave_regime=s_var["wave_regime"],
                                require_bos_or_choch=s_var["bos_choch"],
                                require_fibo_ote=s_var["fibo_ote"],
                                poi_types=p_var["types"],
                                require_swept_liquidity=p_var["swept"],
                                max_touch_count=p_var["touches"],
                                execution_mode=e_var["mode"],
                                limit_layers=e_var["layers"],
                                hard_sl_pct=e_var["hard_sl"],
                                soft_sl_candle_close_pct=e_var["soft_sl"],
                                hard_tp_pct=50.0,
                                force_close_policy=e_var["fc"],
                                session=sess_var["session"],
                                min_trades_per_month=30
                            )
                            clones.append(spec)
                            idx += 1

        return clones
