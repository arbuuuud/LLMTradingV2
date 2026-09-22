# Workflow 4: Forward Test Workflow (Incubation Staging)

## 1. Tujuan
Menjadi pintu gerbang validasi (*staging / sandbox*) sebelum suatu strategi hasil optimasi W2 (Backtest) diizinkan dieksekusi menggunakan modal riil di W3 (Live Trading). Mengeliminasi bias *overfitting* data historis.

---

## 2. Kriteria Inkubasi (Graduation Gate)

Setiap strategi yang dipromosikan dari Backtest wajib melewati pengujian di akun Demo / Paper Trading dengan kriteria:
1. **Durasi / Sampel Minimum**:
   - Berjalan aktif minimal **20 hari bursa** ATAU telah mengeksekusi minimal **50 closed trades**.
2. **Toleransi Degradasi Performa (Max 15%)**:
   - Realized Winrate $\ge 0.85 \times \text{Backtest Winrate}$.
   - Realized Profit Factor $\ge 0.85 \times \text{Backtest Profit Factor}$.
   - Max Drawdown Demo $\le 1.20 \times \text{Backtest Max Drawdown}$.
3. **Slippage & Spread Audit**:
   - Memastikan strategi tidak bergantung pada fill rate teoritis yang tidak realistis di kondisi spread riil.

---

## 3. Siklus Hidup Strategi (Strategy State Machine)

```text
[DRAFT / BRAINSTORM] (W5)
         │
         ▼
    [BACKTESTING] (W2)
         │ (Lolos Kage Bunshin Leaderboard)
         ▼
   [FORWARD_STAGING] (W4 - Demo/Paper)
         │
    ┌────┴────────────────────────┐
    ▼ (Lolos KPI Inkubasi)        ▼ (Gagal KPI)
[LIVE_APPROVED] (W3)          [REJECTED / ARCHIVED]
```
