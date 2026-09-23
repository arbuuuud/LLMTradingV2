# MT5 Visual Inspectors (Visual Verifier untuk POI & Market Structure)

Folder ini berisi Expert Advisors visual mandiri yang dirancang khusus untuk memverifikasi logika matematika deterministik (SMC, Structure, Fibonacci, dan Liquidity) langsung pada chart MetaTrader 5 sebelum digunakan oleh AI Trading Agent.

---

## 📂 Struktur Modul Inspector

```text
bridge/mt5/inspectors/
├── Structure_Inspector.mq5       # 1. Visualisasi Swing High/Low, BOS (Break of Structure), dan CHoCH
├── FVG_Inspector.mq5             # 2. Visualisasi Fair Value Gap (Bullish/Bearish), Mitigation, & Inversion (iFVG)
├── OrderBlock_Inspector.mq5      # 3. Visualisasi Order Blocks (+OB Bullish / -OB Bearish) & Mitigation
├── Fibonacci_OTE_Inspector.mq5   # 4. Visualisasi Equilibrium (50%) & Institutional OTE Golden Zone (0.618 - 0.786)
├── Liquidity_Inspector.mq5       # 5. Visualisasi Equal Highs/Lows ($$$ BSL / SSL) & Liquidity Sweeps
└── README.md                     # Panduan penggunaan
```

---

## 🚀 Cara Memasang & Menguji di MetaTrader 5

1. **Salin Folder ke Direktori MT5**:
   - Di MetaTrader 5, klik menu **File** $\to$ **Open Data Folder**.
   - Buka folder `MQL5/Experts/`.
   - Buat folder `LLMTradingV2/` dan salin seluruh file `.mq5` di folder `bridge/mt5/inspectors/` ke dalamnya.

2. **Kompilasi di MetaEditor**:
   - Tekan `F4` di MT5 untuk membuka MetaEditor.
   - Buka masing-masing file inspector di panel kiri (`Navigator`).
   - Tekan `F7` (Compile). Pastikan hasil kompilasi **0 errors, 0 warnings**.

3. **Uji Coba Satu Per Satu di Chart**:
   - Pasang inspector satu per satu ke chart XAUUSD (misal timeframe M1, M5, atau M15):
     - **Struktur**: Drag `Structure_Inspector` ke chart. Periksa label `SH`, `SL`, garis putus-putus `BOS`, dan garis solid `CHoCH`.
     - **FVG**: Drag `FVG_Inspector`. Periksa kotak hijau (Bull FVG), kotak merah (Bear FVG), garis putus-putus untuk gap yang sudah terisi (*Mitigated*), dan warna emas untuk Inversion FVG (`iFVG`).
     - **Order Block**: Drag `OrderBlock_Inspector`. Periksa kotak biru (+OB) dan ungu (-OB).
     - **Fibonacci OTE**: Drag `Fibonacci_OTE_Inspector`. Periksa zona hijau emerald 0.618 - 0.786 dan garis kuning 50% Equilibrium.
     - **Liquidity**: Drag `Liquidity_Inspector`. Periksa garis titik-titik merah/hijau `$$$ BSL / SSL` dan panah tanda `Swept`.

---

## ⚙️ Parameter Konfigurasi yang Tersedia

Setiap inspector memiliki input parameter yang dapat disesuaikan pada tab *Inputs*:
- `InpSwingWindow`: Lebar fractal window (default: 3 candle kiri-kanan).
- `InpMaxBars`: Jumlah bar candle yang dianalisis (default: 300 bar).
- `InpShowMitigated`: Menampilkan atau menyembunyikan POI yang sudah tersentuh harga.
- `InpExtendToCurrent`: Memperpanjang kotak POI aktif hingga candle berjalan.
