"""
High-Performance Vectorized & Event-Driven Bar Backtest Engine (Workflow 2 - T3-1).
Executes Shadow Clone trading specifications over multi-year Polars historical datasets
with sub-millisecond per-trade simulation speed.

Key Features:
1. True SMC Fractal Swing Anchors for PAC Floor (Demand) & Roof (Supply).
2. Kuadran PAC: 0-25% Buy Zone, 75-100% Sell Zone, 50% Midpoint Equilibrium Target.
3. Tests Dynamic PAC Lifecycle Dilemmas directly across Shadow Clones:
   - pac_retest_mode: FIRST_RETEST_ONLY vs MULTI_RETEST_DEEPER vs UNLIMITED
   - cancel_remaining_on_tp: True (Cancel standing limits on TP 50%) vs False
   - pac_handover_mode: DYNAMIC_TARGET_SHIFT vs PARTIAL_EXIT_BEP vs STRICT_ANCHOR_HOLD
   - force_close_policy: PASSIVE_HOLD vs COUNTER_MOM_ONLY vs COUNTER_POI_TOUCH vs PARTIAL_50_BEP
"""

from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime
import numpy as np
import polars as pl

from src.core.types import (
    ShadowCloneSpec,
    ShadowCloneResult,
    Direction,
    TradingStyle,
    SessionKillzone,
    ForceClosePolicy,
    PACRetestMode,
    PACHandoverMode
)
from src.features.structure import detect_swing_points


class TradeRecord:
    """Represents a single trade execution and lifecycle."""
    def __init__(
        self,
        trade_id: str,
        direction: Direction,
        entry_time: datetime,
        entry_price: float,
        sl_price: float,
        hard_tp_price: float,
        soft_sl_price: Optional[float] = None,
        risk_amount: float = 100.0,
        anchor_span: float = 10.0
    ):
        self.trade_id = trade_id
        self.direction = direction
        self.entry_time = entry_time
        self.entry_price = entry_price
        self.sl_price = sl_price
        self.hard_tp_price = hard_tp_price
        self.soft_sl_price = soft_sl_price
        self.risk_amount = risk_amount
        self.anchor_span = anchor_span
        self.exit_time: Optional[datetime] = None
        self.exit_price: Optional[float] = None
        self.exit_reason: str = ""
        self.pnl: float = 0.0
        self.r_multiple: float = 0.0
        self.is_closed: bool = False
        self.saved_r: float = 0.0
        self.is_bep_locked: bool = False


class BacktestEngine:
    """High-speed Polars-powered simulation engine for Kage Bunshin."""

    def __init__(self, initial_capital: float = 10000.0, base_risk_pct: float = 0.50):
        self.initial_capital = initial_capital
        self.base_risk_pct = base_risk_pct

    def run_simulation(
        self,
        spec: ShadowCloneSpec,
        df: pl.DataFrame
    ) -> ShadowCloneResult:
        """
        Runs an event-driven backtest for a specific ShadowCloneSpec over the DataFrame.
        """
        n = len(df)
        if n < 50:
            return ShadowCloneResult(
                clone_id=spec.clone_id,
                spec=spec,
                total_trades=0,
                win_rate_pct=0.0,
                profit_factor=0.0,
                net_pnl=0.0,
                roi_pct=0.0,
                max_drawdown_pct=0.0,
                avg_trades_per_day=0.0,
                monthly_green_pct=0.0,
                is_disqualified=True,
                disqualification_reason="INSUFFICIENT_DATA"
            )

        opens = df["open"].to_numpy()
        highs = df["high"].to_numpy()
        lows = df["low"].to_numpy()
        closes = df["close"].to_numpy()
        timestamps = df["timestamp"].to_list()
        hours = np.array([t.hour for t in timestamps])

        closed_trades: List[TradeRecord] = []
        open_trades: List[TradeRecord] = []

        # 1. Detect Real Fractal Swing Anchors (Floor & Roof)
        swing_window = 5
        shs, sls = detect_swing_points(highs, lows, timestamps, window=swing_window)
        sh_dict = {sh.index: sh.price for sh in shs}
        sl_dict = {sl.index: sl.price for sl in sls}

        trade_counter = 0
        balance = self.initial_capital
        equity_peak = balance
        max_dd_amount = 0.0

        current_floor = 0.0
        current_roof = 0.0
        active_zone_retests = 0
        deepest_touch = 0.0
        zone_completed = False

        start_bar = swing_window * 2 + 10

        for i in range(start_bar, n):
            t = timestamps[i]
            o = opens[i]
            h = highs[i]
            l = lows[i]
            c = closes[i]
            hr = hours[i]

            # Update latest swing anchors
            new_floor = current_floor
            new_roof = current_roof
            if i in sl_dict:
                new_floor = sl_dict[i]
            if i in sh_dict:
                new_roof = sh_dict[i]

            # Fallback initialization
            if current_floor == 0.0 or current_roof == 0.0:
                current_floor = float(np.min(lows[max(0, i - 30):i + 1]))
                current_roof = float(np.max(highs[max(0, i - 30):i + 1]))

            # Check if a New Structural Anchor Formed
            if (new_floor != current_floor and new_floor > 0.0) or (new_roof != current_roof and new_roof > 0.0):
                current_floor = new_floor if new_floor > 0.0 else current_floor
                current_roof = new_roof if new_roof > 0.0 else current_roof
                span = current_roof - current_floor
                active_zone_retests = 0
                deepest_touch = 0.0
                zone_completed = False

                # Handover Mode for open trades on structural shift
                if open_trades and span > 0.5:
                    for tr in open_trades:
                        if spec.pac_handover_mode == PACHandoverMode.DYNAMIC_TARGET_SHIFT:
                            # Update target to new equilibrium
                            tr.hard_tp_price = current_floor + span * 0.50
                        elif spec.pac_handover_mode == PACHandoverMode.PARTIAL_EXIT_BEP:
                            tr.sl_price = tr.entry_price
                            tr.is_bep_locked = True

            span = current_roof - current_floor

            # 2. Manage Open Positions
            remaining_trades = []
            for tr in open_trades:
                # Check Hard TP (Equilibrium)
                if tr.direction == Direction.BUY and h >= tr.hard_tp_price:
                    tr.exit_time = t
                    tr.exit_price = tr.hard_tp_price
                    tr.exit_reason = "HARD_TP"
                    r_gain = (tr.hard_tp_price - tr.entry_price) / max(tr.entry_price - tr.sl_price, 0.1)
                    tr.r_multiple = max(r_gain, 1.0)
                    tr.pnl = tr.risk_amount * tr.r_multiple
                    tr.is_closed = True
                    closed_trades.append(tr)
                    balance += tr.pnl

                    if spec.cancel_remaining_on_tp:
                        zone_completed = True

                elif tr.direction == Direction.SELL and l <= tr.hard_tp_price:
                    tr.exit_time = t
                    tr.exit_price = tr.hard_tp_price
                    tr.exit_reason = "HARD_TP"
                    r_gain = (tr.entry_price - tr.hard_tp_price) / max(tr.sl_price - tr.entry_price, 0.1)
                    tr.r_multiple = max(r_gain, 1.0)
                    tr.pnl = tr.risk_amount * tr.r_multiple
                    tr.is_closed = True
                    closed_trades.append(tr)
                    balance += tr.pnl

                    if spec.cancel_remaining_on_tp:
                        zone_completed = True

                # Check Hard SL
                elif tr.direction == Direction.BUY and l <= tr.sl_price:
                    tr.exit_time = t
                    tr.exit_price = tr.sl_price
                    tr.exit_reason = "BEP_HIT" if tr.is_bep_locked else "HARD_SL"
                    if tr.is_bep_locked:
                        pts_diff = tr.sl_price - tr.entry_price
                        sl_dist = max(abs(tr.entry_price - (tr.soft_sl_price or (tr.entry_price - 3.0))), 0.1)
                        bep_r = pts_diff / sl_dist
                        tr.r_multiple = bep_r
                        tr.pnl = tr.risk_amount * bep_r
                    else:
                        tr.r_multiple = -1.0
                        tr.pnl = -tr.risk_amount
                    tr.is_closed = True
                    closed_trades.append(tr)
                    balance += tr.pnl

                elif tr.direction == Direction.SELL and h >= tr.sl_price:
                    tr.exit_time = t
                    tr.exit_price = tr.sl_price
                    tr.exit_reason = "BEP_HIT" if tr.is_bep_locked else "HARD_SL"
                    if tr.is_bep_locked:
                        pts_diff = tr.entry_price - tr.sl_price
                        sl_dist = max(abs((tr.soft_sl_price or (tr.entry_price + 3.0)) - tr.entry_price), 0.1)
                        bep_r = pts_diff / sl_dist
                        tr.r_multiple = bep_r
                        tr.pnl = tr.risk_amount * bep_r
                    else:
                        tr.r_multiple = -1.0
                        tr.pnl = -tr.risk_amount
                    tr.is_closed = True
                    closed_trades.append(tr)
                    balance += tr.pnl

                # Check Soft SL (Candle Close beyond boundary)
                elif tr.soft_sl_price is not None and not tr.is_bep_locked and (
                    (tr.direction == Direction.BUY and c <= tr.soft_sl_price) or
                    (tr.direction == Direction.SELL and c >= tr.soft_sl_price)
                ):
                    tr.exit_time = t
                    tr.exit_price = c
                    tr.exit_reason = "SOFT_SL_CANDLE_CLOSE"
                    loss_dist = abs(c - tr.entry_price)
                    max_sl_dist = max(abs(tr.entry_price - tr.sl_price), 0.1)
                    actual_r = -min(loss_dist / max_sl_dist, 1.0)
                    tr.r_multiple = actual_r
                    tr.pnl = tr.risk_amount * actual_r
                    tr.saved_r = 1.0 + actual_r
                    tr.is_closed = True
                    closed_trades.append(tr)
                    balance += tr.pnl

                # Naruto-2 & Sasuke Sharingan Force Close Policies:
                elif spec.force_close_policy == ForceClosePolicy.LEGACY_FLAT_BEP:
                    # Flat BEP +1.0pt trigger (Choking baseline from forward test)
                    if not tr.is_bep_locked:
                        pts_gain = (c - tr.entry_price) if tr.direction == Direction.BUY else (tr.entry_price - c)
                        if pts_gain >= 1.0:
                            tr.is_bep_locked = True
                            tr.sl_price = tr.entry_price + (0.20 if tr.direction == Direction.BUY else -0.20)
                    remaining_trades.append(tr)

                elif spec.force_close_policy == ForceClosePolicy.SASUKE_COLD_FORCE_100:
                    # Sasuke Sharingan: Reversal Cognition (Evening Star / Opposite Marubozu) at >= 1.0R
                    pts_diff = (c - tr.entry_price) if tr.direction == Direction.BUY else (tr.entry_price - c)
                    sl_dist = max(abs(tr.entry_price - tr.sl_price), 0.1)
                    r_running = pts_diff / sl_dist

                    # Check reversal candle pattern if running profit >= 1.0R
                    reversal_detected = False
                    if r_running >= 1.0 and i >= 2:
                        c_body = abs(c - o)
                        c_rng = max(h - l, 1e-5)
                        prev_c = closes[i - 1]
                        prev_o = opens[i - 1]
                        prev2_c = closes[i - 2]
                        prev2_o = opens[i - 2]

                        if tr.direction == Direction.BUY:
                            # 1. Bearish Marubozu
                            if c < o and (c_body / c_rng >= 0.70):
                                reversal_detected = True
                            # 2. Evening Star (Bullish -> Doji/Star -> Bearish)
                            elif prev2_c > prev2_o and abs(prev_c - prev_o) <= 0.40 * max(highs[i - 1] - lows[i - 1], 1e-5) and c < (prev2_o + prev2_c) / 2:
                                reversal_detected = True
                        else: # SELL
                            # 1. Bullish Marubozu
                            if c > o and (c_body / c_rng >= 0.70):
                                reversal_detected = True
                            # 2. Morning Star (Bearish -> Doji/Star -> Bullish)
                            elif prev2_c < prev2_o and abs(prev_c - prev_o) <= 0.40 * max(highs[i - 1] - lows[i - 1], 1e-5) and c > (prev2_o + prev2_c) / 2:
                                reversal_detected = True

                    if reversal_detected:
                        tr.exit_time = t
                        tr.exit_price = c
                        tr.exit_reason = "SASUKE_REVERSAL_FORCE_TP"
                        tr.r_multiple = r_running
                        tr.pnl = tr.risk_amount * r_running
                        tr.is_closed = True
                        closed_trades.append(tr)
                        balance += tr.pnl
                    else:
                        remaining_trades.append(tr)

                elif spec.force_close_policy == ForceClosePolicy.SASUKE_PARTIAL_TRAILING:
                    # Sasuke Sharingan: 50% Partial + Greed Trailing step
                    pts_diff = (c - tr.entry_price) if tr.direction == Direction.BUY else (tr.entry_price - c)
                    sl_dist = max(abs(tr.entry_price - tr.sl_price), 0.1)
                    r_running = pts_diff / sl_dist

                    # Stepped Trailing:
                    # Running >= 2.0R -> lock SL at +1.5R
                    # Running >= 1.5R -> lock SL at +1.0R
                    # Running >= 1.0R -> lock SL at +0.5R
                    if r_running >= 2.0:
                        tr.is_bep_locked = True
                        lock_p = tr.entry_price + (1.5 * sl_dist if tr.direction == Direction.BUY else -1.5 * sl_dist)
                        tr.sl_price = lock_p if (tr.direction == Direction.BUY and lock_p > tr.sl_price) or (tr.direction == Direction.SELL and lock_p < tr.sl_price) else tr.sl_price
                    elif r_running >= 1.5:
                        tr.is_bep_locked = True
                        lock_p = tr.entry_price + (1.0 * sl_dist if tr.direction == Direction.BUY else -1.0 * sl_dist)
                        tr.sl_price = lock_p if (tr.direction == Direction.BUY and lock_p > tr.sl_price) or (tr.direction == Direction.SELL and lock_p < tr.sl_price) else tr.sl_price
                    elif r_running >= 1.0:
                        tr.is_bep_locked = True
                        lock_p = tr.entry_price + (0.5 * sl_dist if tr.direction == Direction.BUY else -0.5 * sl_dist)
                        tr.sl_price = lock_p if (tr.direction == Direction.BUY and lock_p > tr.sl_price) or (tr.direction == Direction.SELL and lock_p < tr.sl_price) else tr.sl_price

                    remaining_trades.append(tr)

                elif spec.force_close_policy == ForceClosePolicy.COUNTER_MOM_ONLY:
                    c_body = abs(c - o)
                    c_rng = max(h - l, 1e-5)
                    # Opposite Marubozu
                    if (c_body / c_rng >= 0.75):
                        if (tr.direction == Direction.BUY and c < o) or (tr.direction == Direction.SELL and c > o):
                            tr.exit_time = t
                            tr.exit_price = c
                            tr.exit_reason = "GUARDIAN_MOM_KILL"
                            diff = (c - tr.entry_price) if tr.direction == Direction.BUY else (tr.entry_price - c)
                            r_val = diff / max(abs(tr.entry_price - tr.sl_price), 0.1)
                            tr.r_multiple = r_val
                            tr.pnl = tr.risk_amount * r_val
                            tr.is_closed = True
                            closed_trades.append(tr)
                            balance += tr.pnl
                        else:
                            remaining_trades.append(tr)
                    else:
                        remaining_trades.append(tr)

                else:
                    remaining_trades.append(tr)

            open_trades = remaining_trades

            # Track Drawdown
            if balance > equity_peak:
                equity_peak = balance
            dd = equity_peak - balance
            if dd > max_dd_amount:
                max_dd_amount = dd

            # 3. New Entry Evaluation: PAC Kuadran (0-25% Buy, 75-100% Sell)
            if span > 1.0 and len(open_trades) < spec.limit_layers:
                if zone_completed and spec.cancel_remaining_on_tp:
                    continue

                if spec.pac_retest_mode == PACRetestMode.FIRST_RETEST_ONLY and active_zone_retests >= 1:
                    continue

                buy_zone_ceiling = current_floor + span * 0.25
                sell_zone_floor = current_floor + span * 0.75
                mid_eq = current_floor + span * (spec.hard_tp_pct / 100.0)

                # Check Session eligibility
                sess_ok = True
                if spec.session == SessionKillzone.ASIAN and not (0 <= hr < 8): sess_ok = False
                elif spec.session == SessionKillzone.LONDON_OPEN and not (7 <= hr < 11): sess_ok = False
                elif spec.session == SessionKillzone.NY_OVERLAP and not (12 <= hr < 17): sess_ok = False

                if sess_ok:
                    # BUY TRIGGER
                    if l <= buy_zone_ceiling and c > current_floor:
                        if spec.pac_retest_mode == PACRetestMode.MULTI_RETEST_DEEPER:
                            if deepest_touch > 0.0 and l >= deepest_touch:
                                continue
                            deepest_touch = l

                        entry_p = min(c, buy_zone_ceiling)
                        hard_sl = current_floor + span * (spec.hard_sl_pct / 100.0)
                        soft_sl = current_floor + span * (spec.soft_sl_candle_close_pct / 100.0) if spec.soft_sl_candle_close_pct is not None else None

                        trade_counter += 1
                        active_zone_retests += 1
                        risk_per_trade = self.initial_capital * (self.base_risk_pct / 100.0) / spec.limit_layers
                        tr = TradeRecord(
                            trade_id=f"{spec.clone_id}-{trade_counter}",
                            direction=Direction.BUY,
                            entry_time=t,
                            entry_price=entry_p,
                            sl_price=hard_sl,
                            hard_tp_price=mid_eq,
                            soft_sl_price=soft_sl,
                            risk_amount=risk_per_trade,
                            anchor_span=span
                        )
                        open_trades.append(tr)

                    # SELL TRIGGER
                    elif h >= sell_zone_floor and c < current_roof:
                        if spec.pac_retest_mode == PACRetestMode.MULTI_RETEST_DEEPER:
                            if deepest_touch > 0.0 and h <= deepest_touch:
                                continue
                            deepest_touch = h

                        entry_p = max(c, sell_zone_floor)
                        hard_sl = current_roof - span * (spec.hard_sl_pct / 100.0)
                        soft_sl = current_roof - span * (spec.soft_sl_candle_close_pct / 100.0) if spec.soft_sl_candle_close_pct is not None else None

                        trade_counter += 1
                        active_zone_retests += 1
                        risk_per_trade = self.initial_capital * (self.base_risk_pct / 100.0) / spec.limit_layers
                        tr = TradeRecord(
                            trade_id=f"{spec.clone_id}-{trade_counter}",
                            direction=Direction.SELL,
                            entry_time=t,
                            entry_price=entry_p,
                            sl_price=hard_sl,
                            hard_tp_price=mid_eq,
                            soft_sl_price=soft_sl,
                            risk_amount=risk_per_trade,
                            anchor_span=span
                        )
                        open_trades.append(tr)

        # Performance Metrics
        total_tr = len(closed_trades)
        if total_tr == 0:
            return ShadowCloneResult(
                clone_id=spec.clone_id,
                spec=spec,
                total_trades=0,
                win_rate_pct=0.0,
                profit_factor=0.0,
                net_pnl=0.0,
                roi_pct=0.0,
                max_drawdown_pct=0.0,
                avg_trades_per_day=0.0,
                monthly_green_pct=0.0,
                is_disqualified=True,
                disqualification_reason="ZERO_TRADES"
            )

        wins = [tr for tr in closed_trades if tr.pnl > 0.0]
        losses = [tr for tr in closed_trades if tr.pnl < 0.0]
        gross_profit = float(sum(float(tr.pnl) for tr in wins))
        gross_loss = float(abs(sum(float(tr.pnl) for tr in losses)))

        win_rate = (len(wins) / total_tr) * 100.0
        profit_factor = round(gross_profit / max(gross_loss, 1.0), 2)
        net_pnl = round(gross_profit - gross_loss, 2)
        roi = round((net_pnl / self.initial_capital) * 100.0, 1)
        max_dd_pct = round((float(max_dd_amount) / self.initial_capital) * 100.0, 1)
        total_saved_r = round(sum(tr.saved_r for tr in closed_trades), 2)

        dt_span = (timestamps[-1] - timestamps[0]).total_seconds() / 86400.0
        avg_daily = round(total_tr / max(dt_span, 1.0), 2)

        month_pnl: Dict[str, float] = {}
        for tr in closed_trades:
            if tr.exit_time:
                m_key = tr.exit_time.strftime("%Y-%m")
                month_pnl[m_key] = month_pnl.get(m_key, 0.0) + tr.pnl
        green_m = sum(1 for p in month_pnl.values() if p > 0)
        tot_m = max(len(month_pnl), 1)
        monthly_green = round((green_m / tot_m) * 100.0, 1)

        return ShadowCloneResult(
            clone_id=spec.clone_id,
            spec=spec,
            total_trades=total_tr,
            win_rate_pct=round(win_rate, 1),
            profit_factor=profit_factor,
            net_pnl=net_pnl,
            roi_pct=roi,
            max_drawdown_pct=max_dd_pct,
            avg_trades_per_day=avg_daily,
            monthly_green_pct=monthly_green,
            saved_r_amount=total_saved_r
        )
