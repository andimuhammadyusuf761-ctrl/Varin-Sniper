# 🌌 Varin Sniper — 3L/4L Minecraft Username Sniper (Premium GUI)

Tool sniper username Minecraft untuk nama **3 karakter (3L)** dan **4 karakter (4L)**.
GUI premium berbasis CustomTkinter dengan **tema dark purple gradient (galaksi ungu)**,
live galaxy wallpaper, sidebar, dashboard statistik, dan animasi. Checker
**multi-source zero-false-flag** (playerdb → minecraftservices → mojang → ashcon → namemc → mcchecker),
auto claim via **login Microsoft resmi OAuth melalui Microsoft.com**, proxy manager,
notifikasi Discord, dan **riwayat pemindaian SQLite** yang tersimpan setelah aplikasi ditutup.

![versi](https://img.shields.io/badge/versi-3.0%20Premium-b366ff)
![python](https://img.shields.io/badge/python-3.10%2B-8a2be2)

---

## ✨ Fitur

| Area | Kemampuan |
|---|---|
| **Rebranding** | Aplikasi dinamai **Varin Sniper** (logo, title, icon, metadata, file eksekutable) |
| **Checker** | Proxyless **multi-source**: `playerdb.co` → `api.minecraftservices.com` (lookup resmi) → `api.mojang.com` → `ashcon` → **NameMC** → **mcchecker.net**. Pacing per-sumber + cooldown otomatis = bypass 429 tanpa proxy. **Zero false flag**: AVAILABLE wajib dikonfirmasi sumber live |
| **Microsoft Login (OAuth)** | Login resmi lewat `login.microsoftonline.com` (OAuth2 authorization code flow + device code headless). Token & callback ditangani aman. Token yang valid tapi dianggap invalid (429/401) sekarang ditangani dengan benar |
| **Smart 3-Letter Scanner** | Cegah pemindaian nama yang sama berulang kali. Simpan semua nama & status scan dalam **SQLite** (`scan_history.db`) agar riwayat tetap tersimpan setelah ditutup. Daftar history, filter status, dan opsi rescan manual. Scan mulai dari 3L rare |
| **Generator** | 3L/4L random, **3L FULL** (17.576 kombinasi terurut prioritas), smart rare gen, pattern |
| **Auto Claim** | Claim otomatis saat AVAILABLE, round-robin multi-akun, skip akun cooldown/invalid, log ke `claimed.txt` |
| **Proxy** | HTTP/SOCKS4/SOCKS5, scoring, test all, auto-clean proxy mati, rotasi |
| **Notifikasi** | Toast in-app, modal claim, Discord webhook, sound opsional |
| **Data** | `available.txt`, `claimed.txt`, `failed.txt`, `claim_history.json`, `scan_history.db`, `ms_tokens.json` |
| **GUI** | Dark purple gradient galaksi, live galaxy wallpaper, sidebar, dashboard statistik, 7 tab, toast, animasi dinonaktifkan |
| **Stabilitas** | GUI tidak freeze (semua I/O di thread latar belakang), error ditangani, animasi bisa dinonaktifkan |

---

## 🚀 Jalankan dari source

```bash
pip install -r requirements.txt
python varin_sniper.py
```

Butuh Python 3.10+. Di Linux, tkinter harus tersedia (`sudo apt install python3-tk`).

---

## 🖥️ Build `.exe` lewat GitHub (tanpa install apa pun)

Repo ini sudah punya workflow: `.github/workflows/build-exe.yml`.

1. Push project ini ke repo GitHub kamu (branch `main`).
2. Buka tab **Actions** → pilih **Build Varin-Sniper.exe** → **Run workflow**
   (atau cukup push commit, workflow jalan otomatis).
3. Selesai (~3–5 menit) buka run tersebut → panel **Artifacts** →
   download **Varin-Sniper-windows** → isinya `Varin-Sniper.exe`.

Mau file `.exe` permanen di halaman Release? Buat tag:

```bash
git tag v3.0
git push origin v3.0
```

Workflow akan membuat Release dan menempelkan `Varin-Sniper.exe` di sana.

### Build lokal (Windows)

```
build.bat          → double-click, hasil dist\Varin-Sniper.exe
```

atau manual:

```bash
pip install -r requirements.txt pyinstaller
pyinstaller --clean --noconfirm Varin-Sniper.spec
```

`Varin-Sniper.spec` sudah mengumpulkan `customtkinter` (tema/aset) supaya GUI tidak
blank setelah dijadikan exe.

---

## 🧭 Alur pakai

1. **Checker tab** — ketik nama → **Check** (single) atau **＋ Add** (masuk queue).
   Bisa juga `Load .txt`, `3L FULL`, `Smart Gen (rare)`, atau pattern.
2. **START** di kanan atas. Log berwarna muncul real-time:
   hijau = available, cyan = claim, abu = taken, merah = error, kuning = rate limit.
3. **Accounts tab** — tambah akun via **Login Microsoft (OAuth)** atau tempel token.
   Status `VALID / EXPIRED` terlihat per akun.
4. **Sniper tab** — nyalakan **Auto Claim** dan **Watch mode**.
5. **Proxies tab** — `Load proxies.txt` → `Test All` → `Clean Dead`.
6. **Settings tab** — threads, delay, timeout, webhook Discord → **Save**.
7. **History tab** — riwayat pemindaian dari SQLite, filter status, **Rescan manual**.
8. **Stats tab** — total checked, available, claimed, taken, error, rate limited,
   success rate, uptime, checks/s, dan riwayat claim.

Shortcut: `Ctrl+Enter` = start, `Esc` = stop.

---

## 🔐 Login Microsoft (OAuth via Microsoft.com)

### A. Email + Password (OAuth resmi)
1. Tab **Accounts** → isi **Email** + **Password**.
2. Klik **Login Microsoft (OAuth)** — tool membuka browser ke
   `login.microsoftonline.com` (OAuth2 authorization code flow), lalu menukar
   code dengan access_token + refresh_token melalui callback
   `http://localhost:PORT/callback`.
3. Token Microsoft dikonversi ke Minecraft access token via XBL → XSTS →
   `api.minecraftservices.com`. Akun tersimpan di `ms_tokens.json`.

### B. Token-only (tanpa browser)
- `mc_token` (`eyJ…`) → diverifikasi ketat; token invalid = pesan jelas.
  Expiry dibaca dari claim `exp` di JWT.
- MS refresh token (`M.C…`) → di-refresh otomatis via Microsoft token endpoint.
- MS access token (`M.R…` / `eyJ…` non-MC) → dikonversi lewat rantai XBL.
- Pilih tipe **Auto-detect** agar sniper mendeteksi sendiri.

> ⚠️ File `ms_tokens.json` berisi kredensial — **jangan commit / dibagikan**.
> Sudah masuk `.gitignore`.

---

## 🗄️ Riwayat Pemindaian (SQLite)

Semua nama yang dipindai disimpan di `scan_history.db` beserta statusnya
(available/taken/error/unknown/rate_limited/claimed). Riwayat tetap ada setelah
aplikasi ditutup dan dibuka kembali.

- **History tab**: daftar lengkap, filter per status, dan tombol **Rescan manual**
  untuk memindai ulang nama yang error/unknown/rate-limited.
- Nama yang sudah tersimpan sebagai AVAILABLE atau TAKEN tidak akan dipindai
  ulang otomatis (mencegah pemindaian berulang).

---

## 📁 Struktur

| File | Isi |
|---|---|
| `varin_sniper.py` | GUI premium + engine (controller, worker, claim, SQLite history) |
| `checker.py` | Checker multi-source zero-false-flag |
| `claimer.py` | Login Microsoft OAuth via Microsoft.com, refresh token, claim, smart queue |
| `scan_history.py` | Database SQLite riwayat pemindaian |
| `proxy.py` | Proxy model + manager (scoring, test, auto-clean) |
| `generator.py` | Generator 3L/4L, priority scoring, pattern |
| `utils.py` | Config manager, stats, Discord webhook, logging |
| `Varin-Sniper.spec` / `build.bat` | Konfigurasi PyInstaller |
| `.github/workflows/build-exe.yml` | Build `.exe` otomatis di GitHub |

---

## ⚠️ Catatan

- Checker menghormati kontrak API setiap sumber (status code, bukan substring
  body). Saat satu sumber 429/challenge, sumber itu cooldown dan traffic pindah
  otomatis ke sumber sehat — tanpa proxy.
- `AVAILABLE` = nama tidak terdaftar di registry Minecraft. Nama yang baru
  dibebaskan lewat rename tetap kena cooldown 37 hari Mojang — itu divalidasi
  saat claim, bukan saat check.
- Auto claim hanya berhasil bila akun memenuhi syarat (cooldown ganti nama 30 hari,
  akun tidak dibatasi).
- Gunakan dengan tanggung jawab sendiri; ini tool bantu, bukan jaminan dapat nama.
