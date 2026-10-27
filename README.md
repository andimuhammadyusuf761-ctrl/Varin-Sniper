# ⚡ MC Sniper — 3L/4L Username Sniper

Tool sniper username Minecraft untuk nama **3 karakter (3L)** dan **4 karakter (4L)**.
GUI premium berbasis CustomTkinter, checker **multi-source zero-false-flag**
(playerdb → minecraftservices → mojang → ashcon → namemc → mcchecker),
auto claim via **login Microsoft langsung (tanpa Azure / OAuth2)**, proxy manager,
dan notifikasi Discord.

![versi](https://img.shields.io/badge/versi-2.2%20Pro-00f0ff)
![python](https://img.shields.io/badge/python-3.10%2B-5b8bff)

---

## ✨ Fitur

| Area | Kemampuan |
|---|---|
| **Checker** | Proxyless **multi-source**: `playerdb.co` → `api.minecraftservices.com` (lookup resmi) → `api.mojang.com` → `ashcon` (backend mcchecker) → **NameMC** → **mcchecker.net**. Pacing per-sumber + cooldown otomatis = **bypass 429 tanpa proxy**. **Zero false flag**: AVAILABLE wajib dikonfirmasi sumber live; ambiguity = UNKNOWN + retry, tidak pernah menebak |
| **Generator** | 3L/4L random, **3L FULL** (17.576 kombinasi terurut prioritas), smart gen, pattern (`a_d`, `aab`) |
| **Auto Claim** | Claim otomatis saat AVAILABLE, round-robin multi-akun, skip akun cooldown/invalid, log ke `claimed.txt` |
| **Login** | **Email + Password Microsoft langsung** (alur launcher, client id bawaan — **tanpa Azure, tanpa device-code/OAuth2**) atau tempel `mc_token` (eyJ…) / MS token (`M.C…`, `M.R…`, eyJ MS) dengan auto-detect |
| **Proxy** | HTTP/SOCKS4/SOCKS5, scoring, test all, auto-clean proxy mati, rotasi (tab tersedia; checker berjalan proxyless) |
| **Notifikasi** | Toast in-app, modal claim, Discord webhook, sound opsional |
| **Data** | `available.txt`, `claimed.txt`, `failed.txt`, `claim_history.json` |
| **GUI** | Dark premium, sidebar ber-indikator, header live-stats, log berwarna + timestamp, 6 tab |

---

## 🚀 Jalankan dari source

```bash
pip install -r requirements.txt
python main.py
```

Butuh Python 3.10+. Di Linux, tkinter harus tersedia (`sudo apt install python3-tk`).

---

## 🖥️ Build `.exe` lewat GitHub (tanpa install apa pun)

Repo ini sudah punya workflow: `.github/workflows/build-exe.yml`.

1. Push project ini ke repo GitHub kamu (branch `main`).
2. Buka tab **Actions** → pilih **Build MC-Sniper.exe** → **Run workflow**
   (atau cukup push commit, workflow jalan otomatis).
3. Selesai (~3–5 menit) buka run tersebut → panel **Artifacts** →
   download **MC-Sniper-windows** → isinya `MC-Sniper.exe`.

Mau file `.exe` permanen di halaman Release? Buat tag:

```bash
git tag v2.1
git push origin v2.1
```

Workflow akan membuat Release dan menempelkan `MC-Sniper.exe` di sana.

### Build lokal (Windows)

```
build.bat          → double-click, hasil dist\MC-Sniper.exe
```

atau manual:

```bash
pip install -r requirements.txt pyinstaller
pyinstaller --clean --noconfirm MC-Sniper.spec
```

`MC-Sniper.spec` sudah mengumpulkan `customtkinter` (tema/aset) supaya GUI tidak
blank setelah dijadikan exe.

---

## 🧭 Alur pakai

1. **Checker tab** — ketik nama → **Check** (single) atau **＋ Add** (masuk queue).
   Bisa juga `Load .txt`, `3L FULL`, `Smart Gen`, atau pattern.
2. **START** di kanan atas. Log berwarna muncul real-time:
   hijau = available, cyan = claim, abu = taken, merah = error, kuning = rate limit.
3. **Accounts tab** — tambah akun (device-code atau token). Status `VALID / EXPIRED`
   terlihat per akun.
4. **Sniper tab** — nyalakan **Auto Claim** dan **Watch mode**.
5. **Proxies tab** — `Load proxies.txt` → `Test All` → `Clean Dead`.
6. **Settings tab** — threads, delay, timeout, retry, webhook Discord → **Save**.
7. **Stats tab** — total checked, available, claimed, taken, error, rate limited,
   success rate, uptime, checks/s, dan riwayat claim.

Shortcut: `Ctrl+Enter` = start, `Esc` = stop.

---

## 🔐 Login Microsoft

### A. Email + Password (langsung, tanpa Azure)
1. Tab **Accounts** → isi **Email** + **Password** (opsional: Label).
2. Klik **Login Microsoft** — tool login langsung ke `login.live.com`
   memakai client id bawaan Minecraft Launcher, jadi **tidak perlu registrasi
   Azure / OAuth2 / device code**.
3. Akun tersimpan di `ms_tokens.json` beserta refresh token (auto-refresh).

> Akun dengan **2FA** akan ditolak dengan pesan jelas (butuh persetujuan
> manual) — tool tidak pernah berpura-pura login sukses.

### B. Token-only (tanpa browser)
- `mc_token` (`eyJ…`) → diverifikasi ketat; token invalid = pesan jelas.
  Expiry dibaca dari claim `exp` di JWT (bukan dikira-kira).
- MS refresh token (`M.C…`) → di-refresh otomatis (client id bawaan).
- MS access token (`M.R…` / `eyJ…` non-MC) → dikonversi lewat rantai XBL.
- Pilih tipe **Auto-detect** agar sniper mendeteksi sendiri.

> ⚠️ File `ms_tokens.json` berisi kredensial — **jangan commit / dibagikan**.
> Sudah masuk `.gitignore`.

---

## 📁 Struktur

| File | Isi |
|---|---|
| `main.py` | GUI premium + engine (controller, worker, claim) |
| `checker.py` | Checker multi-source zero-false-flag (playerdb + mojang services + namemc + mcchecker + ashcon) |
| `Tool.bat` | Versi batch standalone (Windows, rantai playerdb → minecraftservices → mojang) |
| `claimer.py` | Login Microsoft langsung, refresh token, claim, smart queue |
| `proxy.py` | Proxy model + manager (scoring, test, auto-clean) |
| `generator.py` | Generator 3L/4L, priority scoring, pattern |
| `utils.py` | Config manager, stats, Discord webhook, logging |
| `MC-Sniper.spec` / `build.bat` | Konfigurasi PyInstaller |
| `.github/workflows/build-exe.yml` | Build `.exe` otomatis di GitHub |

---

## 🎨 Tema GUI

| Elemen | Warna |
|---|---|
| Background | `#0d0d12` |
| Sidebar | `#111118` |
| Card / panel | `#1a1a24` / `#1e1e2a` |
| Accent | `#00f0ff` (cyan) · `#5b8bff` (blue) |
| Success / Error / Warning | `#00ff9f` / `#ff4d6d` / `#ffd166` |

---

## ⚠️ Catatan

- Checker menghormati kontrak API setiap sumber (status code, bukan substring
  body — body 404 resmi mengandung kata "name" jadi jangan pernah di-guess).
  Saat satu sumber 429/challenge, sumber itu cooldown dan traffic pindah otomatis
  ke sumber sehat — tanpa proxy.
- `AVAILABLE` = nama tidak terdaftar di registry Minecraft. Nama yang baru
  dibebaskan lewat rename tetap kena cooldown 37 hari Mojang — itu divalidasi
  saat claim, bukan saat check.
- Auto claim hanya berhasil bila akun memenuhi syarat (cooldown ganti nama 30 hari,
  akun tidak dibatasi).
- Gunakan dengan tanggung jawab sendiri; ini tool bantu, bukan jaminan dapat nama.
