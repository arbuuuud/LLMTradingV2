"""
Naruto Agent - Master Kage Bunshin Orchestrator.
Receives user methodology input (e.g. PAC) and autonomously generates a massive,
multi-dimensional Shadow Clone search space (hundreds to thousands of independent clones).

Includes the NEW Dynamic PAC Lifecycle Dilemmas as core search dimensions:
1. pac_retest_mode: FIRST_RETEST_ONLY vs MULTI_RETEST_DEEPER vs UNLIMITED
2. cancel_remaining_on_tp: True (Job Done) vs False (Keep Orders Active)
3. pac_handover_mode: DYNAMIC_TARGET_SHIFT vs PARTIAL_EXIT_BEP vs STRICT_ANCHOR_HOLD
4. force_close_policy: PASSIVE_HOLD vs COUNTER_POI_TOUCH vs COUNTER_MOM_ONLY vs PARTIAL_50_BEP
"""

from typing import List, Dict, Any, Optional
from src.core.types import (
    MethodologyInput,
    ShadowCloneSpec,
    TradingStyle,
    SessionKillzone,
    ForceClosePolicy,
    PACRetestMode,
    PACHandoverMode
)


class NarutoAgent:
    """Master Orchestrator Agent capable of mass Shadow Clone replication (Ratusan / Ribuan Klon)."""

    def __init__(self, agent_name: str = "NarutoMasterBrain"):
        self.agent_name = agent_name

    def spawn_clones(
        self,
        methodology: MethodologyInput,
        intensity: str = "MASSIVE"  # FAST (~100 clones), MASSIVE (~1,000 - 3,000+ clones)
    ) -> List[ShadowCloneSpec]:
        """
        Takes a core methodology (e.g. PAC) and autonomously splits into hundreds or thousands
        of diverse Shadow Clones exploring the complete multi-dimensional hypothesis space.
        """
        clones: List[ShadowCloneSpec] = []
        name = methodology.name.upper()

        # Dimension 1: Wave & Structure States
        structure_variations = [
            {"wave_regime": "ALL", "bos_choch": False, "fibo_ote": False, "tag": "StructureAll"},
            {"wave_regime": "IMPULSIVE", "bos_choch": True, "fibo_ote": False, "tag": "ImpulseBOS"},
            {"wave_regime": "SIDEWAY", "bos_choch": False, "fibo_ote": False, "tag": "SidewayRange"},
            {"wave_regime": "PULLBACK", "bos_choch": False, "fibo_ote": True, "tag": "PullbackFiboOTE"},
            {"wave_regime": "ALL", "bos_choch": True, "fibo_ote": True, "tag": "BOSPlusFibo"},
        ]

        # Dimension 2: POI Types, Freshness & Liquidity
        poi_variations = [
            {"types": ["OB", "CONTINUATION_SD", "CONFLUENCE"], "swept": False, "touches": 2, "tag": "AllPOIs"},
            {"types": ["CONFLUENCE"], "swept": True, "touches": 1, "tag": "HighConvictionCluster"},
            {"types": ["OB"], "swept": True, "touches": 0, "tag": "ReversalOBSweptVirgin"},
            {"types": ["OB"], "swept": False, "touches": 2, "tag": "ReversalOBTested"},
            {"types": ["CONTINUATION_SD"], "swept": False, "touches": 1, "tag": "ContinuationSDOnly"},
            {"types": ["FVG"], "swept": False, "touches": 1, "tag": "FVGGapsOnly"},
        ]

        # Dimension 3: Execution, Layering, SL/TP & Naruto-2 Guardian Force Close
        exec_variations = [
            # Grid 5 Layers with diverse SL and Force Close
            {"mode": "LIMIT_GRID", "layers": 5, "hard_sl": -15.0, "soft_sl": -5.0, "tp": 50.0, "fc": ForceClosePolicy.PARTIAL_50_BEP, "tag": "Grid5L_SL15_PartialBEP"},
            {"mode": "LIMIT_GRID", "layers": 5, "hard_sl": -20.0, "soft_sl": -5.0, "tp": 50.0, "fc": ForceClosePolicy.COUNTER_MOM_ONLY, "tag": "Grid5L_SL20_MomKill"},
            {"mode": "LIMIT_GRID", "layers": 5, "hard_sl": -25.0, "soft_sl": 0.0, "tp": 50.0, "fc": ForceClosePolicy.COUNTER_POI_TOUCH, "tag": "Grid5L_SL25_CounterPoi"},
            {"mode": "LIMIT_GRID", "layers": 5, "hard_sl": -20.0, "soft_sl": None, "tp": 50.0, "fc": ForceClosePolicy.PASSIVE_HOLD, "tag": "Grid5L_SL20_PassiveHold"},
            # Grid 3 Layers (Tighter, higher frequency)
            {"mode": "LIMIT_GRID", "layers": 3, "hard_sl": -10.0, "soft_sl": 0.0, "tp": 50.0, "fc": ForceClosePolicy.PARTIAL_50_BEP, "tag": "Grid3L_SL10_PartialBEP"},
            {"mode": "LIMIT_GRID", "layers": 3, "hard_sl": -15.0, "soft_sl": -5.0, "tp": 50.0, "fc": ForceClosePolicy.COUNTER_MOM_ONLY, "tag": "Grid3L_SL15_MomKill"},
            # Grid 10 Layers (Deep accumulation scalping)
            {"mode": "LIMIT_GRID", "layers": 10, "hard_sl": -25.0, "soft_sl": -10.0, "tp": 50.0, "fc": ForceClosePolicy.PARTIAL_50_BEP, "tag": "Grid10L_SL25_PartialBEP"},
            # Confirmed Candlestick Reaction (Zero grid, single sniper entry on [Reac])
            {"mode": "CONFIRMED_REACTION", "layers": 1, "hard_sl": -15.0, "soft_sl": -5.0, "tp": 50.0, "fc": ForceClosePolicy.PARTIAL_50_BEP, "tag": "ReacEntry_SL15_PartialBEP"},
        ]

        # Dimension 3B: NEW - PAC Lifecycle Dilemmas (User Question Tasks)
        pac_lifecycle_variations = [
            {"retest": PACRetestMode.FIRST_RETEST_ONLY, "cancel_on_tp": True, "handover": PACHandoverMode.DYNAMIC_TARGET_SHIFT, "tag": "1stRetest_CancelTP_DynShift"},
            {"retest": PACRetestMode.MULTI_RETEST_DEEPER, "cancel_on_tp": True, "handover": PACHandoverMode.PARTIAL_EXIT_BEP, "tag": "DeeperRetest_CancelTP_PartialBEP"},
            {"retest": PACRetestMode.FIRST_RETEST_ONLY, "cancel_on_tp": False, "handover": PACHandoverMode.STRICT_ANCHOR_HOLD, "tag": "1stRetest_KeepOrders_StrictHold"},
            {"retest": PACRetestMode.UNLIMITED_UNTIL_BREACH, "cancel_on_tp": False, "handover": PACHandoverMode.DYNAMIC_TARGET_SHIFT, "tag": "Unlimited_KeepOrders_DynShift"}
        ]

        # Dimension 4: Time Sessions & Killzones
        session_variations = [
            {"session": SessionKillzone.ALL_DAY, "tag": "AllDay"},
            {"session": SessionKillzone.ASIAN, "tag": "Asian"},
            {"session": SessionKillzone.LONDON_OPEN, "tag": "LondonOpen"},
            {"session": SessionKillzone.NY_OVERLAP, "tag": "NYOverlap"},
        ]

        # Target Timeframes for Scalping
        if methodology.trading_style == TradingStyle.SCALPING:
            timeframes = ["M1", "M2", "M3", "M5"]
        elif methodology.trading_style == TradingStyle.INTRADAY:
            timeframes = ["M5", "M15", "M30", "H1"]
        else:
            timeframes = ["H1", "H4", "D1"]

        # Selection based on requested intensity
        if intensity == "FAST":
            s_list = structure_variations[:2]
            p_list = poi_variations[:2]
            e_list = exec_variations[:2]
            lc_list = pac_lifecycle_variations[:2]
            sess_list = session_variations[:2]
            tfs = timeframes[:2]
        else:
            s_list = structure_variations
            p_list = poi_variations
            e_list = exec_variations
            lc_list = pac_lifecycle_variations
            sess_list = session_variations
            tfs = timeframes

        idx = 1
        for tf in tfs:
            for s_var in s_list:
                for p_var in p_list:
                    for e_var in e_list:
                        for lc_var in lc_list:
                            for sess_var in sess_list:
                                clone_id = f"CLONE-{name}-{tf}-{idx:04d}-{s_var['tag']}-{p_var['tag']}-{e_var['tag']}-{lc_var['tag']}-{sess_var['tag']}"
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
                                    hard_tp_pct=e_var["tp"],
                                    force_close_policy=e_var["fc"],
                                    pac_retest_mode=lc_var["retest"],
                                    cancel_remaining_on_tp=lc_var["cancel_on_tp"],
                                    pac_handover_mode=lc_var["handover"],
                                    session=sess_var["session"],
                                    min_trades_per_month=30
                                )
                                clones.append(spec)
                                idx += 1

        return clones
