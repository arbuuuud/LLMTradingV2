# Development Lifecycle & Step-by-Step Review Protocol

## 1. Tujuan
Memastikan seluruh proses pengembangan sistem **LLMTradingV2** berjalan teratur, terverifikasi, transparan, dan tidak ada kesepakatan arsitektur yang terlewat atau terlupakan (*anti-forgetting*).

---

## 2. Siklus Pengembangan Per-Step (4 Langkah Wajib)

Setiap kali menyelesaikan sebuah fitur, modul, atau sub-task:

```text
┌─────────────────────────────────────────────────────────────┐
│ 1. IMPLEMENTASI & VERIFIKASI UNIT TEST                      │
│    - Kerjakan kode pada feature branch terpisah.            │
│    - Wajib lulus seluruh unit test: `pytest tests/`.        │
└──────────────────────────────┬──────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────┐
│ 2. UPDATE PROGRESS & CHECKLIST STATUS                       │
│    - Perbarui status task di `data/project_state.json`.     │
│    - Beri centang `[x]` pada task terkait di `PLAN.md`.     │
│    - Dashboard web otomatis merefleksikan persentase baru.  │
└──────────────────────────────┬──────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────┐
│ 3. REVIEW CATATAN & NOTULEN BERSAMA (SOP WAJIB)             │
│    - Tanyakan kepada pengguna:                              │
│      "Apakah ada catatan, batasan, atau penyesuaian untuk   │
│       step ini sebelum kita lanjutkan?"                     │
│    - Jika asisten memiliki temuan / usulan catatan:         │
│      Ajukan konfirmasi kepada pengguna.                     │
│    - Jika dikonfirmasi: simpan ke tabel Decision Log di     │
│      `PLAN.md` dan `data/project_state.json`.               │
└──────────────────────────────┬──────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────┐
│ 4. GIT PUSH & PULL REQUEST LINK                             │
│    - Commit perubahan ke branch `feat/nama-fitur`.          │
│    - Push ke GitHub repository.                             │
│    - Tampilkan tautan PR kepada pengguna untuk ditinjau.    │
└─────────────────────────────────────────────────────────────┘
```

---

## 3. Format Catatan Keputusan (Decision Log Schema)

Setiap catatan atau keputusan yang disetujui dicatat dengan struktur:
- **`ID`**: `DEC-XXX` (Auto-increment, misal `DEC-005`).
- **`Date`**: Tanggal kesepakatan (YYYY-MM-DD).
- **`Topic`**: Topik pembahasan (misal: *Dynamic SL Trailing Boundary*).
- **`Summary`**: Pernyataan aturan definitif (apa yang boleh dan tidak boleh dilakukan).
- **`Status`**: `CONFIRMED` | `PROPOSED` | `SUPERSEDED`.

---

## 4. Cara Menjalankan Live Dashboard

Dashboard lokal dapat dijalankan kapan saja untuk memonitor progress live, checklist, dan live market feed:
```bash
./run_dashboard.sh
# Buka di browser: http://127.0.0.1:8080
```
Fitur yang tersedia:
- **Roadmap & Checklist**: Menampilkan seluruh fase, status task, PR link, dan branch terkait.
- **Decision Log**: Menampilkan daftar notulen kesepakatan, lengkap dengan modal untuk menambahkan catatan baru secara interaktif.
- **Live Market Feed Viewer**: Menampilkan state data deterministik `MarketStateSnapshot` (bid, ask, spread, trend, BOS/CHoCH, active FVG, active OB, OTE zone) dari file cache.
