# Workflow 1: Live Data Feed Generation (Deterministic Feature Engine)

## 1. Tujuan
Menyediakan data pasar yang diperkaya (*enriched feature state*) secara real-time dan terstandarisasi untuk menjadi landasan keputusan bagi seluruh Agent, tanpa ada ketergantungan kalkulasi matematika pada LLM.

---

## 2. Input & Output

### Input
- Live Bar Data (M1, M5, M15, H1) dari MT5 Bridge.
- Live Tick Stream (Bid, Ask, Spread, Volume).

### Output
- `MarketStateSnapshot` (JSON) yang diperbarui setiap candle M1 close atau per interval waktu tertentu.

---

## 3. Komponen Feature yang Dihitung

1. **Market Structure**:
   - Deteksi Swing High (SH) dan Swing Low (SL) menggunakan fractal window parametrik (misal: $N=3$ atau $N=5$ candle kiri-kanan).
   - Break of Structure (BOS): Penembusan swing point searah tren utama dengan candle body close.
   - Change of Character (CHoCH): Penembusan swing point berlawanan dengan arah tren sebelumnya (tanda potensi reversal).

2. **Smart Money Concepts (SMC) POI**:
   - **Fair Value Gap (FVG)**:
     - Bullish: `Low[i] > High[i-2]`.
     - Bearish: `High[i] < Low[i-2]`.
   - **Inversion FVG (iFVG)**:
     - FVG yang ditembus penuh oleh candle berikutnya dan fungsinya berbalik (support menjadi resistance atau sebaliknya).
   - **Order Block (OB)**:
     - Candle berlawanan terakhir sebelum terjadi displacement/impulsif yang menciptakan FVG dan menembus struktur (BOS).
   - **Mitigation Tracker**:
     - Status apakah harga saat ini sudah menyentuh / mengisi area POI tersebut.

3. **Fibonacci Retracement & OTE (Optimal Trade Entry)**:
   - Dihitung dari Swing Low ke Swing High terbaru (pada tren bullish), atau sebaliknya.
   - Menghitung zona OTE: Golden pocket 0.618, 0.705, dan 0.786.
   - Menentukan status posisi harga: **Premium Zone** (di atas 0.50 equilibrium) vs **Discount Zone** (di bawah 0.50).

4. **Liquidity & Sweep Tracker**:
   - Buy-Side Liquidity (BSL) / Equal Highs (EQH).
   - Sell-Side Liquidity (SSL) / Equal Lows (EQL).
   - Flag `sweep_detected`: Jika wick candle menembus liquidity level tetapi body close kembali di dalam range.

---

## 4. Alur Kerja (Execution Loop)

```text
[MT5 Bridge / Parquet Stream]
             │ (Bar M1 Close)
             ▼
[Feature Engine Processor]
 ├── 1. Update Fractal Swings
 ├── 2. Evaluate BOS / CHoCH
 ├── 3. Detect New FVG / OB & Update Mitigation Status
 ├── 4. Calculate OTE & Equilibrium
 └── 5. Check Liquidity Sweeps
             │
             ▼
[JSON Serialization: MarketStateSnapshot]
             │
             ├──► [Publish to Disk Cache: data/cache/live_snapshot.json]
             └──► [Broadcast Event to Registered Agents]
```
