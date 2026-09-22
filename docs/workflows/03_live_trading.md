# Workflow 3: Live Trading Workflow (Execution Pipeline)

## 1. Tujuan
Mengeksekusi strategi yang telah teruji (*graduated strategies*) di pasar riil secara mandiri dengan kedisiplinan eksekusi tanpa emosi dan proteksi risiko bertingkat.

---

## 2. Pipeline Eksekusi Berlapis

```text
[W1: MarketStateSnapshot]
          │
          ▼
[Step 1: Tactician Agent (Checklist Evaluator)]
   - Mengevaluasi snapshot terhadap checklist strategi aktif
   - Menghitung total skor (contoh threshold: >= 8.0/10)
   - Jika pass -> Buat CandidateSignal (Symbol, Direction, Entry, SL, TP)
          │
          ▼
[Step 2: Risk Governor (The Law & Circuit Breaker)]
   - Validasi saldo & floating drawdown saat ini
   - Cek Max Daily Drawdown (< 3%)
   - Cek kalender berita (News Blackout Window: 5 menit pre/post high-impact)
   - Hitung ukuran lot berbasis Fixed Fractional Risk (misal: 0.5% balance per trade)
   - Keputusan: APPROVE atau VETO REJECT
          │
          ▼
[Step 3: Execution Bridge (MT5 Order Router)]
   - Kirim Limit Order / Market Order ke terminal MT5
   - Validasi slippage & order execution status
          │
          ▼
[Step 4: ForceClose Guardian (Active Position Sentinel)]
   - Begitu posisi terbuka, Guardian berjalan pada loop interval cepat (M1 close / tick)
   - Memonitor tanda-tanda structural invalidation
   - Menjalankan aksi: HOLD / MOVE_SL_BE / PARTIAL / FORCE_CLOSE_MARKET
```

---

## 3. Fitur Keamanan: Handbrake & Circuit Breaker
- **Manual Handbrake**: File flag `configs/handbrake.lock`. Jika file ini ada atau diaktifkan oleh operator, seluruh engine seketika menghentikan pembukaan posisi baru.
- **Hardware/Connection Watchdog**: Jika heartbeat bridge MT5 terputus lebih dari 10 detik, sistem otomatis masuk mode failsafe.
