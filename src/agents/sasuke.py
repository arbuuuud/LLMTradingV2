"""
Sasuke Uchiha (Sharingan Overseer Agent) - Core Logic & Specification.

Lore & Philosophy:
- Pasangan abadi Naruto: Naruto eksploratif, agresif, dan kreatif mencari entry (Kage Bunshin).
- Sasuke dingin, rasional, penuh perhitungan, dan memiliki Mata Pengawas (Sharingan & Rinnegan).
- Peran Utama: The Ultimate Risk, Structure & Force-Close Overseer.
- Memantau trade yang sedang berjalan (running positions) dan mengevaluasi sinyal pembalikan arah
  (Reversal Cognition: Evening/Morning Star, Counter-Marubozu, S&D Flip).
- Memotong trade tanpa ampun (Force TP / Partial Exit / Breakeven Lock) jika struktur pasar berbalik,
  serta mengeksekusi Greed Trailing Bertingkat & Daily Circuit Breaker 1%.
"""

from enum import Enum
from typing import List, Dict, Any, Optional
from datetime import datetime
from pydantic import BaseModel, Field

from src.core.types import Direction


class SharinganPerceptionLevel(str, Enum):
    """Tingkat ketajaman mata Sharingan Sasuke dalam membaca pasar."""
    ONE_TOMOE = "ONE_TOMOE"       # Basic: Membaca momentum lawan (Opposite Marubozu)
    TWO_TOMOE = "TWO_TOMOE"       # Intermediate: Membaca pola lilin pembalikan (Star / Pin Bar di M1)
    THREE_TOMOE = "THREE_TOMOE"   # Advanced: Membaca S&D / Liquidity Flip & OTE Rejection
    MANGEKYO = "MANGEKYO"         # Master: Reversal Cognition penuh + Greed Trailing Bertingkat


class SasukeAction(str, Enum):
    """Keputusan eksekusi taktis yang dikeluarkan Sasuke."""
    HOLD = "HOLD"                             # Biarkan posisi bernapas (struktur masih sehat)
    GREED_TRAILING_STEP = "GREED_TRAILING"    # Kunci profit bertingkat (+0.5% pada 1.0%, +1.0% pada 1.5%)
    FORCE_TP_REVERSAL = "FORCE_TP_REVERSAL"   # Ambil profit saat ini juga karena terdeteksi pembalikan arah
    EMERGENCY_CUT = "EMERGENCY_CUT"           # Potong rugi dini jika struktur terinvalisir total
    DAILY_LOCKOUT = "DAILY_LOCKOUT"           # Kunci bot (Hard Daily Stop -1.0% tercapai)


class ReversalSignalCandidate(BaseModel):
    """Kandidat titik pembalikan yang dibaca oleh mata Sharingan."""
    timestamp: datetime
    price: float
    pattern: str  # e.g., "EVENING_STAR", "MORNING_STAR", "COUNTER_MARUBOZU", "SUPPLY_FLIP"
    direction_against: Direction
    potential_new_roof_floor: bool = True
    confidence: float = Field(ge=0.0, le=1.0)


class SasukeVerdict(BaseModel):
    """Hasil penalaran rasional Sasuke untuk posisi yang dipantau."""
    ticket: int
    action: SasukeAction
    target_sl: Optional[float] = None
    target_tp: Optional[float] = None
    reversal_signal: Optional[ReversalSignalCandidate] = None
    saved_r_impact: float = 0.0
    rationale: str


class SasukeSharinganAgent:
    """
    Sasuke Uchiha — The Ultimate Risk & Logic Overseer.
    Belajar berdampingan dengan ribuan kloningan Naruto di Kage Bunshin Tournament.
    """

    def __init__(
        self,
        perception_level: SharinganPerceptionLevel = SharinganPerceptionLevel.MANGEKYO,
        daily_max_loss_pct: float = -1.0,
        daily_profit_target_pct: float = 2.0,
        greed_trailing_enabled: bool = True,
        reversal_cognition_enabled: bool = True
    ):
        self.perception_level = perception_level
        self.daily_max_loss_pct = daily_max_loss_pct
        self.daily_profit_target_pct = daily_profit_target_pct
        self.greed_trailing_enabled = greed_trailing_enabled
        self.reversal_cognition_enabled = reversal_cognition_enabled

        # Track daily equity state for Circuit Breaker
        self.daily_realized_pnl: float = 0.0
        self.daily_lockout_active: bool = False

    def check_daily_circuit_breaker(self, account_equity: float, starting_equity: float) -> bool:
        """
        Mata Sharingan memantau batas harian (-1.0% max loss).
        Jika tembus, seluruh trading hari itu dikunci mutlak.
        """
        if starting_equity <= 0:
            return False

        drawdown_pct = ((account_equity - starting_equity) / starting_equity) * 100.0
        if drawdown_pct <= self.daily_max_loss_pct:
            self.daily_lockout_active = True
            return True
        return False

    def evaluate_position_with_sharingan(
        self,
        pos: Dict[str, Any],
        current_candle: Dict[str, Any],
        recent_m1_candles: List[Dict[str, Any]],
        account_equity: float,
        initial_balance: float
    ) -> SasukeVerdict:
        """
        Memeriksa posisi running secara rasional dan objektif:
        1. Greed Trailing Bertingkat
        2. Reversal Cognition (Deteksi Pembalikan Arah)
        3. Structural Break
        """
        ticket = int(pos.get("ticket", 0))
        side = pos.get("type") or pos.get("direction")  # "BUY" / "SELL"
        entry_p = float(pos.get("entry_price", 0.0))
        current_p = float(current_candle.get("close", entry_p))
        sl = float(pos.get("sl", 0.0))
        tp = float(pos.get("tp", 0.0))

        # Hitung floating R / PnL
        point = 0.01  # XAUUSD 2 digits
        sl_dist = max(1.0, abs(entry_p - sl)) if sl > 0 else 3.5

        if side in ("BUY", Direction.BUY):
            profit_pts = current_p - entry_p
            r_multiple = profit_pts / sl_dist
        else:
            profit_pts = entry_p - current_p
            r_multiple = profit_pts / sl_dist

        # Poin 2: Greed Trailing Bertingkat (Equity-Based atau R-Based)
        # +1.0% profit -> kunci +0.5%
        # +1.5% profit -> kunci +1.0%
        # +2.0% profit -> kunci +1.5%
        if self.greed_trailing_enabled and r_multiple >= 1.5:
            # Trailing target
            if r_multiple >= 2.5:
                locked_pts = sl_dist * 1.5
            elif r_multiple >= 2.0:
                locked_pts = sl_dist * 1.0
            else:
                locked_pts = sl_dist * 0.5

            if side in ("BUY", Direction.BUY):
                new_sl = round(entry_p + locked_pts, 2)
                if new_sl > sl:
                    return SasukeVerdict(
                        ticket=ticket,
                        action=SasukeAction.GREED_TRAILING_STEP,
                        target_sl=new_sl,
                        rationale=f"Sharingan Greed Trailing: Running {r_multiple:.2f}R. SL dinaikkan ke +{locked_pts:.2f} pts (${new_sl:.2f}) mengunci profit tebal."
                    )
            else:
                new_sl = round(entry_p - locked_pts, 2)
                if sl == 0.0 or new_sl < sl:
                    return SasukeVerdict(
                        ticket=ticket,
                        action=SasukeAction.GREED_TRAILING_STEP,
                        target_sl=new_sl,
                        rationale=f"Sharingan Greed Trailing: Running {r_multiple:.2f}R. SL diturunkan ke -{locked_pts:.2f} pts (${new_sl:.2f}) mengunci profit tebal."
                    )

        # Poin 1: Reversal Cognition (Deteksi Pembalikan Arah)
        # Aktif jika posisi sudah profit (>= 0.5R) dan terdeteksi pola pembalikan di M1
        if self.reversal_cognition_enabled and r_multiple >= 0.5 and len(recent_m1_candles) >= 3:
            reversal = self._detect_reversal_pattern(side, recent_m1_candles)
            if reversal:
                return SasukeVerdict(
                    ticket=ticket,
                    action=SasukeAction.FORCE_TP_REVERSAL,
                    reversal_signal=reversal,
                    rationale=f"Sharingan Reversal Cognition: Terdeteksi pola pembalikan {reversal.pattern} saat posisi running +{r_multiple:.2f}R. Force TP dieksekusi sebelum profit terpangkas. Level ${reversal.price:.2f} ditandai sebagai cikal bakal Roof/Floor baru."
                )

        return SasukeVerdict(
            ticket=ticket,
            action=SasukeAction.HOLD,
            rationale="Struktur pasar masih sehat searah posisi. Posisi diizinkan bernapas menuju target utama."
        )

    def _detect_reversal_pattern(
        self,
        pos_side: str,
        candles: List[Dict[str, Any]]
    ) -> Optional[ReversalSignalCandidate]:
        """
        Sharingan Pattern Detector:
        - Jika BUY: Deteksi Evening Star, Shooting Star Wick, atau Bearish Marubozu
        - Jika SELL: Deteksi Morning Star, Hammer Wick, atau Bullish Marubozu
        """
        c1, c2, c3 = candles[-3], candles[-2], candles[-1]
        t = datetime.fromtimestamp(c3.get("time", 0))
        rng3 = max(c3["high"] - c3["low"], 0.01)

        if pos_side in ("BUY", Direction.BUY):
            # 1. Evening Star (Bullish candle -> Small Doji/Star -> Bearish Drop)
            if c1["close"] > c1["open"] and abs(c2["close"] - c2["open"]) <= (rng3 * 0.35) and c3["close"] < (c1["open"] + c1["close"]) / 2:
                return ReversalSignalCandidate(
                    timestamp=t,
                    price=max(c1["high"], c2["high"], c3["high"]),
                    pattern="EVENING_STAR",
                    direction_against=Direction.SELL,
                    confidence=0.92
                )

            # 2. Bearish Engulfing / Opposite Momentum Marubozu
            body3 = c3["open"] - c3["close"]
            rng3 = max(c3["high"] - c3["low"], 0.01)
            if body3 > 0 and (body3 / rng3) >= 0.70 and c3["close"] < c2["low"]:
                return ReversalSignalCandidate(
                    timestamp=t,
                    price=c3["high"],
                    pattern="BEARISH_MOMENTUM_MARUBOZU",
                    direction_against=Direction.SELL,
                    confidence=0.88
                )

        else:  # pos_side SELL
            # 1. Morning Star (Bearish candle -> Small Doji/Star -> Bullish Rise)
            if c1["close"] < c1["open"] and abs(c2["close"] - c2["open"]) <= (rng3 * 0.35) and c3["close"] > (c1["open"] + c1["close"]) / 2:
                return ReversalSignalCandidate(
                    timestamp=t,
                    price=min(c1["low"], c2["low"], c3["low"]),
                    pattern="MORNING_STAR",
                    direction_against=Direction.BUY,
                    confidence=0.92
                )

            # 2. Bullish Engulfing / Opposite Momentum Marubozu
            body3 = c3["close"] - c3["open"]
            rng3 = max(c3["high"] - c3["low"], 0.01)
            if body3 > 0 and (body3 / rng3) >= 0.70 and c3["close"] > c2["high"]:
                return ReversalSignalCandidate(
                    timestamp=t,
                    price=c3["low"],
                    pattern="BULLISH_MOMENTUM_MARUBOZU",
                    direction_against=Direction.BUY,
                    confidence=0.88
                )

        return None
