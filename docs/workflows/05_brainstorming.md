# Workflow 5: Brainstorming & Research Registry Workflow

## 1. Tujuan
Menjaga proses inovasi dan penyempurnaan sistem agar **100% terdokumentasi, terstruktur, dan tidak mengalami regresi (*anti-forgetting*)**. Setiap ide perbaikan, eksperimen, dan kegagalan dicatat rapi ke dalam git history dan registry dokumen.

---

## 2. Struktur Dokumen Riset

Semua riset disimpan dalam dua folder utama:
- `registry/strategies/`: Spesifikasi formal checklist strategi dalam format YAML.
- `registry/experiments/`: Catatan eksperimen dan hasil komparasi uji matriks dalam format Markdown.

### A. Template Strategi YAML (`registry/strategies/template.yaml`)
```yaml
id: "STRAT-001"
name: "Trend Pullback iFVG Scalper"
version: "1.0.0"
status: "DRAFT" # DRAFT | BACKTESTED | FORWARD_STAGING | LIVE_APPROVED | ARCHIVED
author: "Researcher Agent & Human Operator"
created_at: "2025-09-22"

target_assets:
  - "XAUUSD"
timeframes:
  htf: "M15"
  ltf: "M1"

checklist_rules:
  - id: "HTF_TREND"
    description: "Trend M15 harus searah dengan setup (Bullish/Bearish)"
    weight: 2.0
    mandatory: true

  - id: "LIQUIDITY_SWEEP"
    description: "Telah terjadi sweep Asian High/Low atau recent Swing Point"
    weight: 2.0
    mandatory: true

  - id: "IFVG_DISPLACEMENT"
    description: "Muncul Inversion FVG dengan candle body displacement kuat"
    weight: 3.0
    mandatory: true

  - id: "FIBO_OTE"
    description: "Harga pullback ke zona discount/premium (0.618 - 0.786)"
    weight: 1.5
    mandatory: false

  - id: "RISK_REWARD"
    description: "Minimum Risk to Reward ratio >= 1:2.0"
    weight: 1.5
    mandatory: true

score_threshold: 8.0 # Total skor minimal untuk trigger trade
```

### B. Template Catatan Eksperimen (`registry/experiments/EXP-XXX.md`)
1. **Latar Belakang & Masalah**: Mengapa eksperimen ini dijalankan (contoh: *banyak trade kena SL karena fakeout Asian session*).
2. **Hipotesis**: Apa yang ingin dibuktikan (contoh: *menambahkan filter Asian Range Liquidity Sweep akan meningkatkan winrate sebesar 10%*).
3. **Konfigurasi Kage Bunshin**: Varian checklist yang diuji.
4. **Hasil Kuantitatif**: Tabel komparasi Sharpe, Winrate, Max DD, dan Saved R.
5. **Kesimpulan & Keputusan**: Apakah strategi diadopsi atau ditolak.
