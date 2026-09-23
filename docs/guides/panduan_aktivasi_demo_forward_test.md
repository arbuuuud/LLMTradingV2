# Panduan Lengkap Mengaktifkan Forward Test di Akun Demo MT5 (Opsi B)
**LLMTradingV2 Institutional Architecture — Workflow 4: Incubation Staging**

Panduan ini memandu Anda langkah demi langkah untuk mengaktifkan bot forward test di terminal MetaTrader 5 (MT5) akun demo agar mulai mengumpulkan 50 closed trades nyata.

---

## 🏛️ Alur Kerja Sistem

```text
  [Terminal MT5 Akun Demo]                     [Python Daemon Server]
┌───────────────────────────┐                ┌────────────────────────────┐
│ LLMTradingBridge.mq5      │ ── (Socket) ── │ run_forward_demo.sh        │
│ Terpasang di chart XAUUSD │  Port: 5555    │ (src/workflows/            │
│ Mengirim Candle & Tik     │ ◄─ Limit Order │   forward_daemon.py)       │
└───────────────────────────┘                └──────────────┬─────────────┘
                                                            │
                                              Tiap trade selesai dicatat ke:
                                              data/forward_trades_live.json
                                                            │
                                                            ▼
                                              [IncubationStagingGate]
                                              Audit Degradasi <= 15% & Slippage
```

---

## 🚀 Langkah 1: Jalankan Python Forward Daemon di Mac

Buka terminal Mac Anda di folder project `LLMTradingV2`, lalu ketik:

```bash
./run_forward_demo.sh
```

**Output yang akan muncul:**
```text
============================================================
🚀 FORWARD DEMO DAEMON ACTIVE ON 127.0.0.1:5555
Target Trades: 50 | Output: data/forward_trades_live.json
Waiting for MT5 EA (LLMTradingBridge.mq5) to connect...
============================================================
```
*(Biarkan terminal ini tetap menyala selama trading demo berlangsung)*.

---

## 💻 Langkah 2: Konfigurasi di Terminal MT5 (Demo)

1. Buka aplikasi **MetaTrader 5** (akun Demo Anda).
2. **Aktifkan Izin Algo Trading & Socket**:
   - Klik menu **Tools** $\to$ **Options** (atau tekan `Ctrl + O`).
   - Pilih tab **Expert Advisors**.
   - Centang **"Allow Algo Trading"**.
   - Centang **"Allow WebRequest for listed URL"** (jika ada).
   - Klik **OK**.
3. **Buka Chart XAUUSD**:
   - Buka chart **XAUUSD** pada timeframe **M1** (atau M2/M3/M5 sesuai pilihan profil).
4. **Pasang EA Bridge ke Chart**:
   - Buka panel **Navigator** (`Ctrl + N`).
   - Cari di folder **Expert Advisors** $\to$ `LLMTradingBridge`.
   - Drag & drop `LLMTradingBridge` ke dalam chart XAUUSD.
5. **Periksa Parameter Input EA**:
   - `InpServerHost`: `127.0.0.1`
   - `InpServerPort`: `5555`
   - `InpCanonicalSymbol`: `XAUUSD`
   - Klik **OK**.

---

## ✅ Langkah 3: Verifikasi Koneksi Sukses

Begitu EA terpasang di chart MT5:
1. Di chart MT5, ikon topi EA di pojok kanan atas akan berubah menjadi **biru (aktif tersenyum)**.
2. Di terminal Python Mac (`run_forward_demo.sh`), akan seketika muncul log:
   ```text
   🤝 Handshake from MT5: Broker=ICMarkets Symbol=XAUUSD
   ✅ BrokerAdapter calibrated to live MT5 broker specs.
   📊 Bar arrived: XAUUSD @ 2026-04-03T... | Close: 2652.40 (Bid: 2652.30, Ask: 2652.50)
      Progress: 0 / 50 closed trades collected.
   ```

---

## 📈 Langkah 4: Memantau Progress & Kelulusan

- Sistem akan secara otomatis mengevaluasi sinyal PAC, memasang limit order di MT5, mengelola TP 50% / BEP, dan menyimpan setiap trade yang tertutup.
- Anda dapat melihat kemajuan pengumpulan trade secara berkala di file:
  `data/forward_trades_live.json`
- Begitu mencapai **50 trade**, `IncubationStagingGate` otomatis melakukan audit komparasi performa demo vs backtest untuk memberikan predikat resmi: **`GRADUATED_LIVE`**!

---

## 🛑 Cara Menghentikan / Pause Darurat

- **Matikan Sementara**: Tekan tombol `Algo Trading` di MT5 menjadi merah.
- **Emergency Handbrake Python**: Ketik perintah berikut di terminal:
  ```bash
  touch configs/handbrake.lock
  ```
  *(Sentinel Circuit Breaker seketika memblokir seluruh order baru tanpa mematikan program)*.
- **Hapus Handbrake**:
  ```bash
  rm configs/handbrake.lock
  ```
