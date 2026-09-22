# Support Workflows: Data Lake, Broker Normalization & Governance

## 1. W0: Hybrid Priority Data Lake (`src/data/merger.py`)

### Masalah yang Diselesaikan:
- Data historis download (Cold Data) berbeda broker/sumber dengan data live (Hot Data dari MT5 EA).
- Perlu penggabungan otomatis tanpa memodifikasi file besar hasil download.

### Mekanisme Waterfall Priority:
1. **Tier 1 (Base Cold Data, Priority = 0)**:
   - File historis jangka panjang di `data/parquet/base/`.
   - Menjadi *fallback* saat data live belum mencakup periode lampau.
2. **Tier 2 (Live Hot Data, Priority = 1)**:
   - Diterima langsung dari MT5 EA dan disimpan berpartisi per bulan di `data/parquet/live/{broker_name}/`.
   - Mengandung spread dan likuiditas broker riil (*ground truth*).
3. **Deterministic Merge Engine**:
   - Berbasis Polars vectorized sorting & deduplikasi.
   - Saat ada timestamp yang bertabrakan (*overlap*), data live secara mutlak menimpa (*overwrite*) data base.
   - Mengisi kekosongan data (*gap filling*) dari data historis secara instan dalam hitungan milidetik.

---

## 2. Multi-Broker Normalization (`src/data/adapter.py`)

### Masalah yang Diselesaikan:
- Simbol instrumen berbeda di tiap broker (`XAUUSD`, `XAUUSD.u`, `XAUUSD.sc`, `GOLD`).
- Resolusi lot dan step berbeda (Standard: min 0.01 step 0.01; Cent/Micro: min 0.1 step 0.1; Crypto: min 0.001).
- Presisi harga berbeda (2 desimal vs 3 desimal).

### Arsitektur Canonical Adapter:
- **Internal System** hanya mengenal simbol kanonikal mutlak: `"XAUUSD"`.
- Seluruh penyesuaian dilakukan di layer **Broker Boundary (`BrokerAdapter`)**:
  - `to_broker_symbol()` & `to_canonical_symbol()`
  - `normalize_price()` (sesuai `digits`)
  - `normalize_lot()` (quantization ke `lot_step`, pembatasan `min_lot` / `max_lot`)
  - `calculate_lot()` (Fixed Fractional Risk % to broker lots)
