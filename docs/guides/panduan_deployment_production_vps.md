# Panduan Deployment Production (24/7 Cloud VPS / Dedicated Server)
**LLMTradingV2 Institutional Architecture**

Karena laptop tidak bisa menyala 24/7, sistem trading otomatis harus dijalankan di **VPS (Virtual Private Server)** atau **Cloud Server**. 

Terdapat dua opsi deployment standar industri:
- **Opsi 1 (Paling Mudah & Populer)**: **Windows VPS** (Sangat disukai trader retail/prop firm karena MT5 berjalan native tanpa Wine).
- **Opsi 2 (Hemat Biaya & Modern)**: **Linux VPS (Ubuntu 22.04 LTS)** dengan Docker / Wine Headless & Systemd Daemon.

---

## 🖥️ PILIHAN 1: Windows VPS (Rekomendasi Paling Praktis & Cepat)

Jika Anda menyewa Windows Server di provider seperti **Contabo, Kamatera, OVH, ForexVPS, atau Vultr** (Spesifikasi minimal: 2-4 vCPU, 4-8 GB RAM):

### Langkah-langkah:
1. **Remote Desktop (RDP)**:
   - Login ke VPS menggunakan **Remote Desktop Connection** dari Mac (gunakan aplikasi *Microsoft Remote Desktop* dari App Store).
2. **Download & Pasang Python**:
   - Download Python 3.11 atau 3.12 dari `python.org` (Centang *"Add Python to PATH"* saat install).
3. **Download & Pasang Git**:
   - Install Git for Windows dari `git-scm.com`.
4. **Clone Repository Project**:
   Buka Command Prompt (CMD) atau PowerShell:
   ```cmd
   git clone https://github.com/arbuuuud/LLMTradingV2.git
   cd LLMTradingV2
   python -m venv .venv
   .venv\Scripts\activate
   pip install -r requirements.txt
   ```
5. **Install MetaTrader 5 Broker Anda**:
   - Download MT5 dari broker Anda (misal ICMarkets/Exness).
   - Copy folder EA `bridge/mt5/` dari project ke folder `MQL5/Experts/` terminal MT5 di Windows VPS.
   - Copy file databank `xauusd_m1_poi_databank.bin` ke folder:
     `%APPDATA%\MetaQuotes\Terminal\Common\Files\`
6. **Compile EA & Pasang ke Chart**:
   - Buka MetaEditor di MT5, compile `LLMTradingBridge.mq5`.
   - Pasang EA ke chart XAUUSD M1.
7. **Jalankan Python Daemon 24/7**:
   ```cmd
   python src/workflows/forward_daemon.py
   ```
   *(Tips: Buat file `.bat` di folder Windows Startup agar bot otomatis nyala jika VPS restart otomatis)*.

---

## 🐧 PILIHAN 2: Linux VPS (Ubuntu 22.04 LTS) via Systemd Service

Jika menggunakan server Linux Ubuntu (Contabo, DigitalOcean, Hetzner, AWS EC2):

### 1. Persiapan Server Linux
Buka terminal SSH ke VPS Anda:
```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y git python3 python3-venv python3-pip wine64 xvfb
```

### 2. Setup Project & Virtual Environment
```bash
git clone https://github.com/arbuuuud/LLMTradingV2.git /home/ubuntu/LLMTradingV2
cd /home/ubuntu/LLMTradingV2
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 3. Mengatur Background Service 24/7 (Systemd)
Agar daemon otomatis berjalan terus menerus di latar belakang, auto-restart jika crash, dan otomatis nyala saat server reboot:

File template systemd service telah tersedia di: `configs/systemd/llm-trading.service`.

Pasang service ke system:
```bash
sudo cp configs/systemd/llm-trading.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable llm-trading
sudo systemctl start llm-trading
```

### 4. Perintah Monitoring di Linux
- **Cek status bot**:
  ```bash
  sudo systemctl status llm-trading
  ```
- **Lihat log transaksi real-time**:
  ```bash
  journalctl -u llm-trading -f
  ```
- **Hentikan sementara (Stop)**:
  ```bash
  sudo systemctl stop llm-trading
  ```

---

## 🛡️ Monitoring & Kontrol Jarak Jauh dari HP / Laptop

Setelah bot berjalan 24/7 di VPS, Anda tidak perlu lagi membuka terminal setiap saat:

1. **Dashboard Web Interaktif**:
   - Di VPS, jalankan `./run_dashboard.sh`.
   - Akses dashboard melalui browser: `http://IP_VPS_ANDA:8000`.
   - Menampilkan status checklist, trade yang sudah terkumpul, dan kurva ekuitas secara live.
2. **Mobile MT5 App**:
   - Login akun demo/live Anda di aplikasi **MetaTrader 5 di smartphone Android/iPhone**.
   - Setiap kali bot mengeksekusi order dari VPS, notifikasi langsung muncul di HP Anda.
3. **Emergency Kill-Switch Jarak Jauh**:
   - Jika ingin mematikan eksekusi tanpa membuka server, cukup klik tombol `Algo Trading` menjadi **OFF** melalui MT5 di VPS, atau buat file rem darurat:
     ```bash
     touch configs/handbrake.lock
     ```

---

## 💰 Rekomendasi Provider VPS Teruji:
1. **Contabo (Cloud VPS 1 / 2)**: Harga sangat hemat (~$6 - $12 / bulan), 4-6 vCPU, 8 GB RAM. Tersedia pilihan OS Windows Server atau Ubuntu.
2. **ForexVPS.net / Chocoping**: Khusus trading forex dengan latensi ultra-rendah (< 2ms ke broker ICMarkets/Exness di London/NY).
3. **Hetzner Cloud (CPX21 / CPX31)**: Performa CPU AMD EPYC kencang, sangat stabil untuk Linux daemon.
