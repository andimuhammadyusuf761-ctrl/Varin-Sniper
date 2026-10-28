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
| **Generator** | **Rarest 3L** (skor kelangkaan: bobot huruf, struktur, bigram/trigram umum, pola berulang, urutan papan ketik) dengan mode *Rarest / Balanced / Legacy* + opsi *consonants only*, 3L/4L random, **3L FULL** (17.576 kombinasi terurut prioritas), pattern |
| **Versi Web** | UI web (`run_web.py`) dengan engine yang sama: antrian, checker multi-source, generator kelangkaan, riwayat SQLite, statistik, EN/ID, live log via SSE |
| **Auto Claim** | Claim otomatis saat AVAILABLE, round-robin multi-akun, skip akun cooldown/invalid, log ke `claimed.txt` |
| **Proxy** | HTTP/SOCKS4/SOCKS5, scoring, test all, auto-clean proxy mati, rotasi |
| **Notifikasi** | Toast in-app, modal claim, Discord webhook, sound opsional |
| **Data** | `available.txt`, `claimed.txt`, `failed.txt`, `claim_history.json`, `scan_history.db`, `ms_tokens.json` |
| **GUI** | Dark purple gradient, kartu bevel 3D, live wallpaper 3D (wireframe vault + partikel kedalaman), sidebar ikon vektor, sub-tab kapsul per halaman, toast, efek tekan 3D. Bahasa: **English (default)** & Indonesia, bisa diganti langsung dari GUI |
| **Performa** | Semua I/O di thread latar; wallpaper 3D punya frame-pacing adaptif (otomatis turun 20–30 FPS) dan pause saat jendela tidak fokus; font/gradient/ikon di-cache; tombol tidak pernah menggeser layout saat hover |
| **Ikon** | App icon `.png`/`.ico` multi-size + 53 ikon nav/tombol digambar prosedural oleh `tools/make_icons.py` (tanpa Pillow) |

---

## 🚀 Jalankan dari source

```bash
pip install -r requirements.txt
python varin_sniper.py
```

Cek cepat tanpa membuka GUI (dipakai juga di CI):

```bash
python tools/check_ui.py            # kunci i18n, ikon, matematika wallpaper
python tools/make_icons.py          # regenerasi assets/ (ikon app + ikon GUI)
python tools/smoke_gui.py --source  # buka GUI sungguhan: 7 halaman + ganti bahasa
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

Sebelum artifact diunggah, workflow menjalankan **smoke test** pada exe hasil build
(`tools/smoke_gui.py`): exe harus benar-benar membuka jendela, memuat aset ikon,
menggambar live wallpaper, dan berpindah bahasa EN → ID → EN. Kalau exe mati saat
dibuka, build jadi merah — jadi artifact tidak pernah berisi exe yang tidak jalan.
Kalau runner tidak punya display, langkah ini hanya memberi peringatan.

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
9. **Sidebar** — ganti bahasa (**English default / Indonesia**), nyalakan/matikan
   wallpaper 3D dan efek 3D, lihat status mesin + uptime + antrian.

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
| `varin_sniper.py` | Entry point: cek dependency, wire controller + UI, jalankan GUI |
| `controller.py` | Mesin sniper (antrian, worker, claim, notifikasi) — tanpa widget |
| `ui/theme.py` | Design system: palette dark purple gradient, gradient photo, font cache |
| `ui/i18n.py` | Terjemahan English (default) + Indonesia |
| `ui/icons.py` | Pemuat set ikon + ikon jendela (aman untuk exe) |
| `ui/wallpaper.py` | Live wallpaper 3D hemat CPU |
| `ui/widgets.py` | Kartu 3D, chip statistik, log, list, sub-tab segmented |
| `ui/app.py` | Layout, sidebar, navigasi, dan reaksi terhadap event mesin |
| `tools/make_icons.py` | Generator app icon + set ikon (stdlib, tanpa Pillow) |
| `tools/check_ui.py` | Verifikasi statis UI: kunci i18n, kelengkapan ikon, matematika wallpaper, helper tema |
| `tools/smoke_gui.py` | Smoke test GUI: jalankan app (source/exe) dalam mode laporan, tentukan exit code |
| `checker.py` | Checker multi-source zero-false-flag |
| `claimer.py` | Login Microsoft OAuth via Microsoft.com, refresh token, claim, smart queue |
| `scan_history.py` | Database SQLite riwayat pemindaian |
| `proxy.py` | Proxy model + manager (scoring, test, auto-clean) |
| `generator.py` | Generator 3L/4L, rarity scoring (`generate_rare`), priority scoring, pattern |
| `blocklist.py` | Daftar blokir bersama: nama dari `3name.xyz/list` + filter inappropriate (desktop & web) |
| `utils.py` | Config manager, stats, Discord webhook, logging |
| `assets/` | Ikon aplikasi + ikon GUI hasil `tools/make_icons.py` |
| `webapp/` | Server web stdlib (`server.py` + `static/`) untuk versi browser |
| `run_web.py` | Entry point versi web (`python run_web.py`) |
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

---

## 🌐 Versi Web

UI browser dengan engine yang sama seperti aplikasi desktop. Tanpa dependensi
baru — memakai `http.server` dari stdlib, jadi cukup Python yang sudah dipakai
untuk menjalankan `varin_sniper.py`.

```bash
python run_web.py                  # http://localhost:3000
python run_web.py --port 8080      # port lain
python run_web.py --open           # buka browser otomatis
```

Yang tersedia di versi web:

- **Checker** — cek satu nama, tempel banyak nama ke antrian, start/stop engine,
  log langsung via SSE, daftar AVAILABLE, ekspor `.txt`.
- **Generator** — mode *Rarest / Balanced / Legacy*, opsi *consonants only*,
  panjang 3L/4L, serta generator pola. Hasil langsung masuk antrian.
- **History** — tabel riwayat SQLite dengan pencarian, filter status, hapus
  entri, rescan nama error, dan hapus semua.
- **Stats** — penghitung mesin dan rincian status sepanjang waktu.
- **Settings** — threads, timeout, watch mode, stealth, bahasa (EN/ID), dan
  tautan ekspor. Semua tersimpan di `config.json` yang sama dengan desktop.

Batasan yang disengaja: login Microsoft/OAuth, refresh token, dan auto claim
masih hanya di aplikasi desktop. Versi web fokus ke pengecekan nama, antrian,
riwayat, dan generator. Jangan buka port-nya ke internet tanpa auth — ini alat
lokal, bukan layanan multi-user.
