/* Varin Sniper Web — frontend tanpa framework, tanpa build step. */
(() => {
  "use strict";

  const BUILD = "4.5";

  /* ------------------------------------------------------------------ i18n */
  const I18N = {
    en: {
      "nav.checker": "Checker", "nav.history": "History", "nav.stats": "Stats",
      "nav.settings": "Settings",
      "nav.discord": "Discord",
      "page.discord.title": "Discord checker",
      "page.discord.sub": "Rare 3L/4L usernames across several sources — one 429 never stops the rest.",
      "dg.target": "Discord target queue",
      "dg.targetSub": "3L/4L usernames. One name per request, so pacing matters.",
      "dg.placeholder": "username (2–32 chars, a-z 0-9 . _)",
      "dg.check": "Check", "dg.add": "Add",
      "dg.hint": "Enter checks one name · Shift+Enter adds the list. Results are cached in SQLite, so Discord is never asked twice.",
      "dg.start": "Start checker", "dg.stop": "Stop", "dg.clear": "Clear queue",
      "dg.workers": "{n} workers · {q} in queue",
      "dg.statInvalid": "Invalid", "dg.statLimited": "Rate limited",
      "dg.genTitle": "Rare generator",
      "dg.genSub": "Rarest first — rare mode only, 3L and 4L.",
      "dg.genBtn": "Generate rare &amp; queue",
      "dg.genHint": "Discord allows a–z, 0–9, dot and underscore. Leading, trailing and double dots plus reserved words are filtered before queueing.",
      "dg.sourcesTitle": "Checker sources",
      "dg.sourcesSub": "Every source keeps its own rate-limit bucket — a 429 on one does not stop the others.",
      "dg.sourcesHint": "Direct endpoint answers 200 {taken:true|false}. Third-party APIs must return JSON with taken or available. Tokens and keys stay on this server and never reach the browser.",
      "dg.sourceMeta": "token {token} · api {api} · proxies {proxies}",
      "dg.on": "on", "dg.off": "off",
      "dg.pace": "Pace (s / request)",
      "dg.tokenLabel": "Account token",
      "dg.apiLabel": "3rd-party API URL",
      "dg.apiKeyLabel": "API key",
      "dg.saveSources": "Save sources",
      "dg.logTitle": "Discord log",
      "dg.logSub": "Live output from the Discord checker.",
      "dg.availTitle": "Free usernames",
      "dg.availSub": "Available right now, newest first.",
      "dg.sourceOk": "ready",
      "dg.sourceCooldown": "cooldown {s}s",
      "dg.sourceOff": "disabled",
      "toast.dgGenerated": "{n} rare names queued · {length}L",
      "toast.dgStarted": "Discord checker started",
      "toast.dgStopped": "Discord checker stopped",
      "toast.dgSaved": "Discord sources saved",
      "toast.dgInvalid": "Bad format: 2–32 chars, a-z, 0-9, dot or underscore",
      "toast.dgOne": "Check one username, or paste a list into Add",
      "page.checker.title": "Checker",
      "page.checker.sub": "Queue names, generate rare 3L targets, watch results live.",
      "page.history.title": "History",
      "page.history.sub": "Every scan is stored in SQLite, newest first.",
      "page.stats.title": "Stats",
      "page.stats.sub": "Engine counters and all-time breakdown.",
      "page.settings.title": "Settings",
      "page.settings.sub": "Threads, timeouts, notifications and data files.",
      "status.stopped": "Idle", "status.running": "Running", "status.stopping": "Stopping…",
      "label.inQueue": "in queue",
      "checker.target": "Target queue",
      "checker.targetSub": "Single check, or paste many names to fill the queue.",
      "checker.placeholder": "username (3–16 chars, a-z 0-9 _)",
      "checker.check": "Check", "checker.add": "Add",
      "checker.hint": "Enter checks one name · Shift+Enter adds the whole list.",
      "checker.start": "Start engine", "checker.stop": "Stop", "checker.clear": "Clear queue",
      "checker.threads": "{n} threads",
      "stat.checked": "Checked", "stat.available": "Available", "stat.taken": "Taken",
      "stat.errors": "Errors", "stat.speed": "Checks / s", "stat.uptime": "Uptime",
      "stat.totalScans": "Total scans", "stat.availableTotal": "Available found",
      "stat.takenTotal": "Taken", "stat.errorTotal": "Errors",
      "gen.title": "Generators",
      "gen.sub": "Rarest first, then more common — same rarity model as the desktop app.",
      "gen.rarity": "Rarity", "gen.rarest": "Rarest", "gen.balanced": "Balanced",
      "gen.legacy": "Legacy", "gen.random": "Random", "gen.consonants": "Consonants only",
      "gen.length": "Length", "gen.count": "Count", "gen.generate": "Generate & queue",
      "gen.pattern": "Pattern", "gen.patternPlaceholder": "x_x · aaa · _dd",
      "gen.patternRun": "Generate pattern",
      "gen.hint": "Rarest starts at consonant clusters like zbx / qkg. Balanced 3L always includes one _ (h_d, z_x). Random mixes letters, digits and _ (ig9, hg_, x7z).",
      "log.title": "Live log", "log.sub": "Streaming from the engine.", "log.clear": "Clear",
      "avail.title": "Available", "avail.sub": "Fresh hits, newest first.",
      "avail.export": "Export",
      "history.title": "Scan history", "history.sub": "Every result is stored in SQLite.",
      "history.rescan": "Rescan errors", "history.clear": "Clear all",
      "history.search": "Search name", "history.all": "All statuses",
      "history.name": "Name", "history.status": "Status", "history.source": "Source",
      "history.time": "Scanned", "history.empty": "No scans yet — start the engine or check a name.",
      "history.rows": "{n} of {total} rows",
      "stats.breakdown": "History breakdown", "stats.breakdownSub": "By status, all time.",
      "settings.engine": "Engine",
      "settings.engineSub": "Applied the next time the engine starts.",
      "settings.threads": "Threads", "settings.timeout": "Request timeout (s)",
      "settings.watch": "Watch mode (recheck taken names)",
      "settings.stealth": "Stealth pacing",
      "settings.autoClaim": "Auto claim (needs accounts, desktop only)",
      "settings.language": "Language", "settings.save": "Save settings",
      "settings.data": "Data & exports", "settings.dataSub": "Files live next to the app.",
      "settings.accounts": "Accounts loaded", "settings.proxies": "Proxies in proxies.txt",
      "settings.historyRows": "History rows", "settings.scanned": "Names scanned",
      "settings.availableTxt": "available.txt", "settings.claimedTxt": "claimed.txt",
      "settings.failedTxt": "failed.txt",
      "settings.desktopOnly": "Microsoft login, token refresh and automatic claiming stay in the desktop app. This web build checks names, queues targets, stores history and generates names.",
      "toast.generated": "{n} names added · {mode} {length}L",
      "toast.queue": "{n} waiting in queue",
      "toast.staleUi": "This page is an old build — press Ctrl+F5",
      "build.new": "A new version of the web UI is ready.",
      "build.reload": "Reload",
      "toast.pattern": "Pattern {pattern} — {n} names",
      "toast.added": "{n} names added",
      "toast.rechecked": "{n} rechecked",
      "toast.skipped": "{n} skipped (already queued or invalid)",
      "toast.exhausted": "only {n} fresh names left",
      "toast.nothing": "Nothing new was added (invalid, duplicate, or already scanned)",
      "toast.cleared": "Queue cleared ({n})",
      "toast.started": "Engine started",
      "toast.stopped": "Engine stopped",
      "toast.saved": "Settings saved",
      "toast.restart": "Threads changed — stop and start the engine to apply",
      "toast.deleted": "History entry removed",
      "toast.historyCleared": "History cleared ({n})",
      "toast.rescan": "{n} names queued for rescan",
      "toast.checking": "Checking {name}…",
      "toast.result": "{name}: {status}",
      "toast.invalid": "Use 3–16 chars: a-z, 0-9 or _",
      "toast.one": "Check one name at a time, or use Add for a list",
      "toast.error": "Error: {error}",
      "toast.lang": "Language set to English",
    },
    id: {
      "nav.checker": "Checker", "nav.history": "Riwayat", "nav.stats": "Statistik",
      "nav.settings": "Pengaturan",
      "nav.discord": "Discord",
      "page.discord.title": "Checker Discord",
      "page.discord.sub": "Username rare 3L/4L dari beberapa sumber — satu 429 tidak mematikan yang lain.",
      "dg.target": "Antrean target Discord",
      "dg.targetSub": "Username 3L/4L. Satu nama per request, jadi pacing menentukan.",
      "dg.placeholder": "username (2–32 karakter, a-z 0-9 . _)",
      "dg.check": "Cek", "dg.add": "Tambah",
      "dg.hint": "Enter mengecek satu nama · Shift+Enter menambah daftar. Hasil disimpan di SQLite, jadi Discord tidak pernah ditanya dua kali.",
      "dg.start": "Jalankan checker", "dg.stop": "Berhenti", "dg.clear": "Bersihkan antrean",
      "dg.workers": "{n} worker · {q} dalam antrean",
      "dg.statInvalid": "Tidak valid", "dg.statLimited": "Kena limit",
      "dg.genTitle": "Generator rare",
      "dg.genSub": "Dari yang paling langka — mode rare saja, 3L dan 4L.",
      "dg.genBtn": "Buat rare &amp; antrekan",
      "dg.genHint": "Discord mengizinkan a–z, 0–9, titik dan garis bawah. Titik di awal/akhir/bertumpuk dan kata terlarang difilter sebelum masuk antrean.",
      "dg.sourcesTitle": "Sumber checker",
      "dg.sourcesSub": "Tiap sumber punya bucket limit sendiri — 429 di satu sumber tidak menghentikan yang lain.",
      "dg.sourcesHint": "Endpoint langsung menjawab 200 {taken:true|false}. API pihak ketiga harus mengembalikan JSON dengan taken atau available. Token dan key tetap di server ini, tidak pernah sampai ke browser.",
      "dg.sourceMeta": "token {token} · api {api} · proxy {proxies}",
      "dg.on": "aktif", "dg.off": "nonaktif",
      "dg.pace": "Pace (detik / request)",
      "dg.tokenLabel": "Token akun",
      "dg.apiLabel": "URL API pihak ketiga",
      "dg.apiKeyLabel": "API key",
      "dg.saveSources": "Simpan sumber",
      "dg.logTitle": "Log Discord",
      "dg.logSub": "Keluaran live dari checker Discord.",
      "dg.availTitle": "Username bebas",
      "dg.availSub": "Bisa dipakai sekarang, terbaru di atas.",
      "dg.sourceOk": "siap",
      "dg.sourceCooldown": "cooldown {s} dtk",
      "dg.sourceOff": "nonaktif",
      "toast.dgGenerated": "{n} nama rare diantrikan · {length}L",
      "toast.dgStarted": "Checker Discord dijalankan",
      "toast.dgStopped": "Checker Discord dihentikan",
      "toast.dgSaved": "Sumber Discord disimpan",
      "toast.dgInvalid": "Format salah: 2–32 karakter, a-z, 0-9, titik atau garis bawah",
      "toast.dgOne": "Cek satu username, atau tempel daftar ke Tambah",
      "page.checker.title": "Checker",
      "page.checker.sub": "Isi antrian, buat target 3L langka, pantau hasil secara langsung.",
      "page.history.title": "Riwayat",
      "page.history.sub": "Setiap scan tersimpan di SQLite, terbaru dulu.",
      "page.stats.title": "Statistik",
      "page.stats.sub": "Penghitung mesin dan rincian sepanjang waktu.",
      "page.settings.title": "Pengaturan",
      "page.settings.sub": "Thread, timeout, notifikasi, dan file data.",
      "status.stopped": "Siaga", "status.running": "Berjalan", "status.stopping": "Berhenti…",
      "label.inQueue": "di antrian",
      "checker.target": "Antrian target",
      "checker.targetSub": "Cek satu nama, atau tempel banyak nama untuk mengisi antrian.",
      "checker.placeholder": "username (3–16 karakter, a-z 0-9 _)",
      "checker.check": "Cek", "checker.add": "Tambah",
      "checker.hint": "Enter untuk cek satu nama · Shift+Enter untuk menambah seluruh daftar.",
      "checker.start": "Mulai mesin", "checker.stop": "Berhenti",
      "checker.clear": "Kosongkan antrian",
      "checker.threads": "{n} thread",
      "stat.checked": "Diperiksa", "stat.available": "Tersedia", "stat.taken": "Terpakai",
      "stat.errors": "Error", "stat.speed": "Cek / detik", "stat.uptime": "Waktu aktif",
      "stat.totalScans": "Total scan", "stat.availableTotal": "Tersedia ditemukan",
      "stat.takenTotal": "Terpakai", "stat.errorTotal": "Error",
      "gen.title": "Generator",
      "gen.sub": "Dari yang paling langka lalu makin umum — model yang sama dengan aplikasi desktop.",
      "gen.rarity": "KELANGKAAN", "gen.rarest": "Terlangka", "gen.balanced": "Seimbang",
      "gen.legacy": "Legacy", "gen.random": "Acak", "gen.consonants": "Konsonan saja",
      "gen.length": "Panjang", "gen.count": "Jumlah", "gen.generate": "Buat & antrikan",
      "gen.pattern": "Pola", "gen.patternPlaceholder": "x_x · aaa · _dd",
      "gen.patternRun": "Buat pola",
      "gen.hint": "Terlangka mulai dari gugus konsonan seperti zbx / qkg. 3L Seimbang selalu memakai satu _ (h_d, z_x). Acak mencampur huruf, angka dan _ (ig9, hg_, x7z).",
      "log.title": "Log langsung", "log.sub": "Aliran dari mesin.", "log.clear": "Bersihkan",
      "avail.title": "Tersedia", "avail.sub": "Hasil baru, terbaru dulu.",
      "avail.export": "Ekspor",
      "history.title": "Riwayat scan", "history.sub": "Setiap hasil disimpan di SQLite.",
      "history.rescan": "Rescan error", "history.clear": "Hapus semua",
      "history.search": "Cari nama", "history.all": "Semua status",
      "history.name": "Nama", "history.status": "Status", "history.source": "Sumber",
      "history.time": "Waktu", "history.empty": "Belum ada scan — mulai mesin atau cek satu nama.",
      "history.rows": "{n} dari {total} baris",
      "stats.breakdown": "Rincian riwayat", "stats.breakdownSub": "Per status, sepanjang waktu.",
      "settings.engine": "Mesin",
      "settings.engineSub": "Diterapkan saat mesin dijalankan berikutnya.",
      "settings.threads": "Thread", "settings.timeout": "Timeout request (detik)",
      "settings.watch": "Watch mode (cek ulang nama terpakai)",
      "settings.stealth": "Stealth pacing",
      "settings.autoClaim": "Auto claim (butuh akun, hanya desktop)",
      "settings.language": "Bahasa", "settings.save": "Simpan pengaturan",
      "settings.data": "Data & ekspor", "settings.dataSub": "File disimpan di folder aplikasi.",
      "settings.accounts": "Akun dimuat", "settings.proxies": "Proxy di proxies.txt",
      "settings.historyRows": "Baris riwayat", "settings.scanned": "Nama dipindai",
      "settings.availableTxt": "available.txt", "settings.claimedTxt": "claimed.txt",
      "settings.failedTxt": "failed.txt",
      "settings.desktopOnly": "Login Microsoft, refresh token, dan auto claim tetap di aplikasi desktop. Versi web ini mengecek nama, mengisi antrian, menyimpan riwayat, dan membuat nama.",
      "toast.generated": "{n} nama ditambahkan · {mode} {length}L",
      "toast.queue": "{n} menunggu di antrean",
      "toast.staleUi": "Halaman ini versi lama — tekan Ctrl+F5",
      "build.new": "Versi baru web UI sudah siap.",
      "build.reload": "Muat ulang",
      "toast.pattern": "Pola {pattern} — {n} nama",
      "toast.added": "{n} nama ditambahkan",
      "toast.rechecked": "{n} dicek ulang",
      "toast.skipped": "{n} dilewati (sudah di antrian atau tidak valid)",
      "toast.exhausted": "sisa {n} nama baru",
      "toast.nothing": "Tidak ada yang baru (tidak valid, duplikat, atau sudah pernah dipindai)",
      "toast.cleared": "Antrian dikosongkan ({n})",
      "toast.started": "Mesin dijalankan",
      "toast.stopped": "Mesin dihentikan",
      "toast.saved": "Pengaturan disimpan",
      "toast.restart": "Thread berubah — hentikan lalu jalankan mesin lagi",
      "toast.deleted": "Entri riwayat dihapus",
      "toast.historyCleared": "Riwayat dihapus ({n})",
      "toast.rescan": "{n} nama masuk antrian untuk rescan",
      "toast.checking": "Memeriksa {name}…",
      "toast.result": "{name}: {status}",
      "toast.invalid": "Gunakan 3–16 karakter: a-z, 0-9 atau _",
      "toast.one": "Cek satu nama sekaligus, atau pakai Tambah untuk daftar",
      "toast.error": "Error: {error}",
      "toast.lang": "Bahasa diatur ke Indonesia",
    },
  };

  const PAGE_META = {
    checker: ["page.checker.title", "page.checker.sub"],
    discord: ["page.discord.title", "page.discord.sub"],
    history: ["page.history.title", "page.history.sub"],
    stats: ["page.stats.title", "page.stats.sub"],
    settings: ["page.settings.title", "page.settings.sub"],
  };

  const STATUS_TONE = {
    available: "#b366ff", taken: "#8c8ab0", claimed: "#2bf5a0",
    error: "#ff4d6d", unknown: "#ffd166", rate_limited: "#ffd166",
    scanned: "#7b68b0",
  };

  const $ = (sel, root = document) => root.querySelector(sel);
  const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));

  const state = {
    lang: localStorage.getItem("vs-lang") || "en",
    page: "checker",
    running: false,
    queue: 0,
    threads: 15,
    stats: {},
    history: { total: 0, by_status: {} },
    config: {},
    log: [],
    available: [],
    genMode: "rarest",
    genLength: 3,
    historyRows: [],
    autoScroll: true,
  };

  /* --------------------------------------------------------------- helpers */
  function t(key, vars) {
    const table = I18N[state.lang] || I18N.en;
    let text = table[key] ?? I18N.en[key] ?? key;
    if (vars) {
      for (const [name, value] of Object.entries(vars)) {
        text = text.split(`{${name}}`).join(String(value));
      }
    }
    return text;
  }

  function escapeHtml(value) {
    return String(value).replace(/[&<>"']/g, (ch) => ({
      "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
    }[ch]));
  }

  function num(value) {
    const n = Number(value || 0);
    return Number.isFinite(n) ? n.toLocaleString(state.lang === "id" ? "id-ID" : "en-US") : "0";
  }

  function toast(message, tone = "accent") {
    const box = $("#toasts");
    if (!box) return;
    const el = document.createElement("div");
    el.className = "toast";
    el.dataset.tone = tone;
    el.textContent = message;
    box.appendChild(el);
    setTimeout(() => {
      el.classList.add("is-hiding");
      setTimeout(() => el.remove(), 220);
    }, 3200);
  }

  async function api(path, options) {
    const response = await fetch(path, options);
    let data = {};
    try { data = await response.json(); } catch (_) { /* ignore */ }
    if (!response.ok) throw new Error(data.error || response.statusText || "request failed");
    return data;
  }

  const post = (path, body) => api(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body || {}),
  });

  function debounce(fn, wait) {
    let handle = null;
    return (...args) => {
      clearTimeout(handle);
      handle = setTimeout(() => fn(...args), wait);
    };
  }

  /* Satu elemen hilang tidak boleh mematikan seluruh wiring. */
  function on(target, event, handler) {
    const el = typeof target === "string" ? $(target) : target;
    if (el) el.addEventListener(event, handler);
    return el;
  }

  /* Baca pilihan langsung dari chip yang tampak aktif, bukan dari state
     yang bisa tertinggal kalau handler lama gagal terpasang. */
  function activeLength() {
    const chip = $("#lengthChips .chip.is-active");
    const value = Number(chip ? chip.dataset.length : state.genLength);
    return value === 4 ? 4 : 3;
  }

  function activeMode() {
    const chip = $("#modeChips .chip.is-active");
    let mode = (chip && chip.dataset.mode) || state.genMode;
    if (mode === "legacy") mode = "random";
    return ["rarest", "balanced", "random"].includes(mode) ? mode : "rarest";
  }

  function checkBuild(snapshot) {
    if (!snapshot || !snapshot.build || snapshot.build === BUILD) return;
    const banner = $("#buildBanner");
    if (banner) banner.hidden = false;
    pushLog({ tag: "warn", text: `UI ${BUILD} vs server ${snapshot.build} — reload` });
  }

  /* ------------------------------------------------------------------ i18n */
  function applyI18n() {
    $$("[data-i18n]").forEach((el) => { el.textContent = t(el.dataset.i18n); });
    $$("[data-i18n-placeholder]").forEach((el) => {
      el.placeholder = t(el.dataset.i18nPlaceholder);
    });
    const meta = PAGE_META[state.page] || PAGE_META.checker;
    $("#pageTitle").textContent = t(meta[0]);
    $("#pageSubtitle").textContent = t(meta[1]);
    $("#statusText").textContent = t(state.running ? "status.running" : "status.stopped");
    $("#threadsMeta").textContent = t("checker.threads", { n: state.threads });
    $("#historyMeta").textContent = t("history.rows", {
      n: state.historyRows.length, total: state.history.total ?? state.historyRows.length,
    });
    $$(".lang-btn").forEach((btn) => {
      btn.classList.toggle("is-active", btn.dataset.lang === state.lang);
    });
    renderBars();
  }

  function setLanguage(lang, persist = true) {
    if (!I18N[lang]) return;
    state.lang = lang;
    localStorage.setItem("vs-lang", lang);
    applyI18n();
    renderHistory();
    if (persist) {
      post("/api/settings", { language: lang }).catch(() => {});
      toast(t("toast.lang"), "accent");
    }
  }

  /* ---------------------------------------------------------------- pages */
  function setPage(page) {
    if (!PAGE_META[page]) page = "checker";
    state.page = page;
    $$(".page").forEach((el) => el.classList.toggle("is-active", el.id === `page-${page}`));
    $$(".nav-item").forEach((el) => el.classList.toggle("is-active", el.dataset.page === page));
    applyI18n();
    if (page === "history") loadHistory();
    if (page === "settings") fillSettings();
    if (page === "discord") dgRefresh();
    if (location.hash !== `#${page}`) history.replaceState(null, "", `#${page}`);
  }

  /* ---------------------------------------------------------------- state */
  function applyState(snapshot) {
    if (!snapshot) return;
    state.running = Boolean(snapshot.running);
    state.queue = Number(snapshot.queue?.size || 0);
    state.threads = Number(snapshot.config?.threads || state.threads);
    state.config = snapshot.config || state.config;
    state.history = snapshot.history || state.history;
    if (snapshot.stats) applyStats(snapshot.stats);

    $("#statusPill").dataset.state = state.running ? "running" : "stopped";
    $("#statusText").textContent = t(state.running ? "status.running" : "status.stopped");
    $("#queuePill").innerHTML = `${num(state.queue)} <span>${escapeHtml(t("label.inQueue"))}</span>`;
    $("#threadsMeta").textContent = t("checker.threads", { n: state.threads });
    $("#startBtn").disabled = state.running;
    $("#stopBtn").disabled = !state.running;

    if (state.config.gen_mode) {
      state.genMode = state.config.gen_mode === "legacy" ? "random" : state.config.gen_mode;
    }
    if (typeof state.config.gen_consonants_only === "boolean") {
      $("#consOnly").checked = state.config.gen_consonants_only;
    }
    syncChips();
    renderFacts(snapshot);
    if (state.page === "settings") fillSettings(false);
  }

  function applyStats(stats) {
    state.stats = stats || {};
    $("#statChecked").textContent = num(stats.total_checked);
    $("#statAvailable").textContent = num(stats.available);
    $("#statTaken").textContent = num(stats.taken);
    $("#statErrors").textContent = num(stats.errors);
    $("#statSpeed").textContent = Number(stats.checks_per_sec || 0).toFixed(1);
    $("#statUptime").textContent = stats.uptime || "00:00:00";
    if (state.history) {
      const counts = state.history.by_status || {};
      $("#bigTotal").textContent = num(state.history.total);
      $("#bigAvailable").textContent = num(counts.available);
      $("#bigTaken").textContent = num(counts.taken);
      $("#bigErrors").textContent = num((counts.error || 0) + (counts.unknown || 0) + (counts.rate_limited || 0));
    }
  }

  function renderFacts(snapshot) {
    $("#factAccounts").textContent = num(snapshot.accounts);
    $("#factProxies").textContent = num(snapshot.proxies);
    $("#factHistory").textContent = num(snapshot.history?.total);
    $("#factScanned").textContent = num(snapshot.history?.by_status ? Object.values(snapshot.history.by_status).reduce((a, b) => a + b, 0) : 0);
  }

  function renderBars() {
    const host = $("#statusBars");
    if (!host) return;
    const counts = state.history?.by_status || {};
    const entries = Object.entries(counts).sort((a, b) => b[1] - a[1]);
    const total = entries.reduce((sum, [, value]) => sum + value, 0);
    host.innerHTML = "";
    if (!entries.length) {
      host.innerHTML = `<li class="empty">${escapeHtml(t("history.empty"))}</li>`;
      return;
    }
    for (const [status, value] of entries) {
      const pct = total ? Math.max(2, Math.round((value / total) * 100)) : 0;
      const li = document.createElement("li");
      li.innerHTML = `
        <span class="bar-label">${escapeHtml(status.toUpperCase())}</span>
        <span class="bar-track"><i style="width:${pct}%;background:linear-gradient(90deg, ${STATUS_TONE[status] || "#b366ff"}, ${STATUS_TONE[status] || "#b366ff"}aa)"></i></span>
        <span class="bar-value">${num(value)}</span>`;
      host.appendChild(li);
    }
  }

  /* ------------------------------------------------------------------- log */
  function pushLog(entry) {
    if (!entry) return;
    state.log.push(entry);
    if (state.log.length > 400) state.log.splice(0, state.log.length - 400);
    const host = $("#log");
    if (!host) return;
    const line = document.createElement("div");
    line.className = "log-line";
    const stamp = document.createElement("span");
    stamp.className = "log-time";
    stamp.textContent = entry.stamp || new Date().toLocaleTimeString();
    const tag = document.createElement("span");
    tag.className = `log-tag tag-${entry.tag || "info"}`;
    tag.textContent = (entry.tag || "info").toUpperCase();
    const text = document.createElement("span");
    text.className = "log-text";
    text.textContent = entry.text || "";
    line.append(stamp, tag, text);
    host.appendChild(line);
    while (host.childElementCount > 400) host.removeChild(host.firstChild);
    if (state.autoScroll) host.scrollTop = host.scrollHeight;
  }

  function onResult(result) {
    const tone = ({ AVAILABLE: "avail", TAKEN: "taken", ERROR: "bad" })[result.status] || "info";
    pushLog({ tag: tone, text: `${result.name}  ${result.status}${result.reason ? "  ·  " + result.reason : ""}` });
    if (result.status === "AVAILABLE") onAvailable(result.name);
    if (state.page === "history") scheduleHistory();
  }

  function onAvailable(name) {
    if (!name || state.available.includes(name)) return;
    state.available.unshift(name);
    state.available = state.available.slice(0, 120);
    renderAvailable();
  }

  function renderAvailable() {
    const host = $("#available");
    if (!host) return;
    host.innerHTML = "";
    if (!state.available.length) {
      host.innerHTML = `<li class="list-empty">${escapeHtml(t("avail.sub"))}</li>`;
      return;
    }
    for (const name of state.available) {
      const li = document.createElement("li");
      const strong = document.createElement("strong");
      strong.textContent = name;
      const span = document.createElement("span");
      span.textContent = "available";
      li.append(strong, span);
      host.appendChild(li);
    }
  }

  /* --------------------------------------------------------------- discord */
  const dgState = {
    running: false, queue: 0, workers: 3, stats: {}, sources: [], available: [],
    settings: {}, length: 3, log: [],
  };

  const mcState = {
    running: false, queue: 0, workers: 3, stats: {}, sources: [], available: [],
    length: 3, log: [],
  };

  function dgRenderTop() {
    if ($("#dgStartBtn")) $("#dgStartBtn").disabled = dgState.running;
    if ($("#dgStopBtn")) $("#dgStopBtn").disabled = !dgState.running;
    const meta = $("#dgWorkersMeta");
    if (meta) meta.textContent = t("dg.workers", { n: dgState.workers, q: dgState.queue });
  }

  function dgRenderStats() {
    const s = dgState.stats || {};
    const set = (id, value) => { const el = $(id); if (el) el.textContent = num(value); };
    set("#dgStatChecked", s.checked);
    set("#dgStatAvailable", s.available);
    set("#dgStatTaken", s.taken);
    set("#dgStatInvalid", s.invalid);
    set("#dgStatLimited", s.rate_limited);
    set("#dgStatSpeed", s.per_sec);
  }

  function dgRenderSources() {
    const host = $("#dgSources");
    if (host) {
      host.innerHTML = (dgState.sources || []).map((source) => {
        const state = !source.enabled ? t("dg.sourceOff")
          : (source.healthy ? t("dg.sourceOk")
            : t("dg.sourceCooldown", { s: Math.ceil(source.cooldown || 0) }));
        const li = document.createElement("li");
        const strong = document.createElement("strong");
        strong.textContent = source.label || source.name;
        const span = document.createElement("span");
        span.textContent = `${state} · ${num(source.requests)} req · ${num(source.limited)} ×429`
          + (source.last_error ? ` · ${source.last_error}` : "");
        li.append(strong, span);
        return li;
      }).join("");
      if (!host.childElementCount) {
        host.innerHTML = `<li class="list-empty">${escapeHtml(t("dg.sourceOff"))}</li>`;
      }
    }
    const settings = dgState.settings || {};
    const meta = $("#dgSourceMeta");
    if (meta) {
      meta.textContent = t("dg.sourceMeta", {
        token: settings.token ? t("dg.on") : t("dg.off"),
        api: settings.api ? t("dg.on") : t("dg.off"),
        proxies: num(settings.proxies || 0),
      });
    }
    const pace = $("#dgPace");
    if (pace && document.activeElement !== pace && settings.pace) pace.value = settings.pace;
  }

  function dgRenderAvailable() {
    const host = $("#dgAvailable");
    if (!host) return;
    host.innerHTML = "";
    if (!dgState.available.length) {
      host.innerHTML = `<li class="list-empty">${escapeHtml(t("dg.availSub"))}</li>`;
      return;
    }
    for (const name of dgState.available) {
      const li = document.createElement("li");
      const strong = document.createElement("strong");
      strong.textContent = name;
      const span = document.createElement("span");
      span.textContent = "available";
      li.append(strong, span);
      host.appendChild(li);
    }
  }

  function pushDgLog(entry) {
    if (!entry) return;
    dgState.log.push(entry);
    if (dgState.log.length > 300) dgState.log.splice(0, dgState.log.length - 300);
    const host = $("#dgLog");
    if (!host) return;
    const line = document.createElement("div");
    line.className = "log-line";
    const stamp = document.createElement("span");
    stamp.className = "log-time";
    stamp.textContent = entry.stamp || new Date().toLocaleTimeString();
    const tag = document.createElement("span");
    tag.className = `log-tag tag-${entry.tag || "info"}`;
    tag.textContent = (entry.tag || "info").toUpperCase();
    const text = document.createElement("span");
    text.className = "log-text";
    text.textContent = entry.text || "";
    line.append(stamp, tag, text);
    host.appendChild(line);
    while (host.childElementCount > 300) host.removeChild(host.firstChild);
    host.scrollTop = host.scrollHeight;
  }

  function onDgResult(result) {
    const tone = ({ AVAILABLE: "avail", TAKEN: "taken", INVALID: "info",
                   RATE_LIMITED: "warn" })[result.status] || "info";
    pushDgLog({ tag: tone,
      text: `${result.name}  ${result.status}${result.reason ? "  ·  " + result.reason : ""}` });
    if (result.status === "AVAILABLE" && !dgState.available.includes(result.name)) {
      dgState.available.unshift(result.name);
      dgState.available = dgState.available.slice(0, 80);
      dgRenderAvailable();
    }
  }

  function applyDgState(snapshot) {
    if (!snapshot) return;
    dgState.running = Boolean(snapshot.running);
    dgState.queue = Number(snapshot.queue || 0);
    dgState.workers = Number(snapshot.workers || 3);
    dgState.stats = snapshot.stats || dgState.stats;
    dgState.sources = snapshot.sources || [];
    dgState.settings = snapshot.settings || dgState.settings;
    if (Array.isArray(snapshot.available)) {
      dgState.available = snapshot.available;
      dgRenderAvailable();
    }
    dgRenderStats();
    dgRenderSources();
    dgRenderTop();
  }

  async function dgRefresh() {
    try { applyDgState(await api("/api/dg/state")); } catch (_) { /* restarting */ }
  }

  async function dgGenerate() {
    try {
      const data = await post("/api/dg/generate",
        { length: dgState.length, count: Number($("#dgCount")?.value || 100) });
      toast(t("toast.dgGenerated", { n: data.generated, length: data.length }), "ok");
      pushDgLog({ tag: "ok", text: `generate ${data.length}L -> ${data.generated} nama, ${data.added} antre` });
      dgRefresh();
    } catch (error) {
      toast(t("toast.error", { error: error.message }), "bad");
    }
  }

  async function mcGenerate() {
    const length = Number($("#mcLength")?.value || 4);
    const count = Number($("#mcCount")?.value || 50);
    if (length !== 3 && length !== 4) {
      toast(t("toast.error", { error: "Panjang harus 3 atau 4" }), "bad");
      return;
    }
    $("#mcGenBtn").disabled = true;
    try {
      const data = await post("/api/mc/generate", {
        length, count, mode: dgState.mode, consonants_only: dgState.consonants_only,
        underscore: dgState.underscore
      });
      toast(t("toast.mcGenerated", { n: data.generated, length: data.length }), "ok");
      pushMcLog({ tag: "ok", text: `generate ${data.length}L -> ${data.generated} nama, ${data.added} antre` });
      mcRefresh();
      dgRefresh();
    } catch (error) {
      toast(t("toast.error", { error: error.message }), "bad");
    }
    $("#mcGenBtn").disabled = false;
  }

  async function mcCheck() {
    const name = ($("#mcNameInput")?.value || "").trim().toLowerCase();
    if (!name) { toast(t("toast.dgOne"), "accent"); return; }
    try {
      const result = await post("/api/mc/check", { name });
      toast(t("toast.result", { name: result.result.name, status: result.result.status }),
        result.result.status === "available" ? "ok" : "accent");
      onMcResult(result.result);
      mcRefresh();
    } catch (error) {
      toast(t("toast.error", { error: error.message }), "bad");
    }
  }

  async function mcAdd() {
    const raw = ($("#mcNameInput")?.value || "").trim();
    if (!raw) { toast(t("toast.dgOne"), "accent"); return; }
    try {
      const data = await post("/api/mc/queue/add", { text: raw });
      $("#mcNameInput").value = "";
      if (data.invalid) toast(t("toast.dgInvalid"), "bad");
      else toast(t("toast.queue", { n: data.added }), "ok");
      mcRefresh();
      dgRefresh();
    } catch (error) {
      toast(t("toast.error", { error: error.message }), "bad");
    }
  }

  async function mcSetRunning(run) {
    try {
      await post(run ? "/api/mc/start" : "/api/mc/stop", {});
      mcState.running = run;
      mcRenderTop();
      pushMcLog({ tag: run ? "ok" : "warn", text: run ? "engine started" : "engine stopped" });
      toast(t(run ? "toast.mcStarted" : "toast.mcStopped"), run ? "ok" : "warn");
      mcRefresh();
      dgRefresh();
    } catch (error) {
      toast(t("toast.error", { error: error.message }), "bad");
    }
  }

  async function dgAdd() {
    const raw = ($("#dgNameInput")?.value || "").trim();
    if (!raw) { toast(t("toast.dgOne"), "accent"); return; }
    try {
      const data = await post("/api/dg/queue/add", { text: raw });
      $("#dgNameInput").value = "";
      if (data.invalid) toast(t("toast.dgInvalid"), "bad");
      else toast(t("toast.queue", { n: data.added }), "ok");
      dgRefresh();
    } catch (error) {
      toast(t("toast.error", { error: error.message }), "bad");
    }
  }

  async function dgCheck() {
    const name = ($("#dgNameInput")?.value || "").trim().toLowerCase();
    if (!name) { toast(t("toast.dgOne"), "accent"); return; }
    try {
      const result = await post("/api/dg/check", { name, force: true });
      toast(t("toast.result", { name: result.name, status: result.status }),
        result.status === "AVAILABLE" ? "ok" : "accent");
      onDgResult(result);
      dgRefresh();
    } catch (error) {
      toast(t("toast.error", { error: error.message }), "bad");
    }
  }

  async function dgSetRunning(run) {
    try {
      await post(run ? "/api/dg/start" : "/api/dg/stop", {});
      dgState.running = run;
      dgRenderTop();
      pushDgLog({ tag: run ? "ok" : "warn", text: run ? "checker started" : "checker stopped" });
      toast(t(run ? "toast.dgStarted" : "toast.dgStopped"), run ? "ok" : "warn");
      dgRefresh();
    } catch (error) {
      toast(t("toast.error", { error: error.message }), "bad");
    }
  }

  async function dgSaveSources() {
    try {
      await post("/api/dg/settings", {
        pace: Number($("#dgPace")?.value || 1.5),
        dg_token: $("#dgToken")?.value || "",
        dg_api_url: $("#dgApiUrl")?.value || "",
        dg_api_key: $("#dgApiKey")?.value || "",
      });
      toast(t("toast.dgSaved"), "ok");
      dgRefresh();
    } catch (error) {
      toast(t("toast.error", { error: error.message }), "bad");
    }
  }

  /* --------------------------------------------------------------- minecraft */
  function mcRenderTop() {
    if ($("#mcStartBtn")) $("#mcStartBtn").disabled = mcState.running;
    if ($("#mcStopBtn")) $("#mcStopBtn").disabled = !mcState.running;
    const meta = $("#mcWorkersMeta");
    if (meta) meta.textContent = t("checker.threads", { n: mcState.workers, q: mcState.queue });
  }

  function mcRenderStats() {
    const s = mcState.stats || {};
    const set = (id, value) => { const el = $(id); if (el) el.textContent = num(value); };
    set("#mcStatChecked", s.checked);
    set("#mcStatAvailable", s.available);
    set("#mcStatTaken", s.taken);
    set("#mcStatErrors", s.errors);
    set("#mcStatSpeed", s.per_sec);
  }

  function mcRenderSources() {
    const host = $("#mcSources");
    if (host) {
      host.innerHTML = (mcState.sources || []).map((source) => {
        const healthy = source.healthy ? source.healthy() : false;
        const state = healthy ? t("label.inQueue") : t("dg.sourceOff");
        const li = document.createElement("li");
        const strong = document.createElement("strong");
        strong.textContent = source.name || "—";
        const span = document.createElement("span");
        span.textContent = `${state} · ${num(source.requests)} req · ${num(source.limited)} ×429`
          + (source.last_error ? ` · ${source.last_error}` : "");
        li.append(strong, span);
        return li;
      }).join("");
      if (!host.childElementCount) {
        host.innerHTML = `<li class="list-empty">${escapeHtml(t("dg.sourceOff"))}</li>`;
      }
    }
    const meta = $("#mcSourceMeta");
    if (meta) {
      meta.textContent = t("checker.targetSub");
    }
  }

  function mcRenderAvailable() {
    const host = $("#mcAvailable");
    if (!host) return;
    host.innerHTML = "";
    if (!mcState.available.length) {
      host.innerHTML = `<li class="list-empty">${escapeHtml(t("avail.sub"))}</li>`;
      return;
    }
    for (const name of mcState.available) {
      const li = document.createElement("li");
      const strong = document.createElement("strong");
      strong.textContent = name;
      const span = document.createElement("span");
      span.textContent = "available";
      li.append(strong, span);
      host.appendChild(li);
    }
  }

  function pushMcLog(entry) {
    if (!entry) return;
    mcState.log.push(entry);
    if (mcState.log.length > 300) mcState.log.splice(0, mcState.log.length - 300);
    const host = $("#mcLog");
    if (!host) return;
    const line = document.createElement("div");
    line.className = "log-line";
    const stamp = document.createElement("span");
    stamp.className = "log-time";
    stamp.textContent = entry.stamp || new Date().toLocaleTimeString();
    const tag = document.createElement("span");
    tag.className = `log-tag tag-${entry.tag || "info"}`;
    tag.textContent = (entry.tag || "info").toUpperCase();
    const text = document.createElement("span");
    text.className = "log-text";
    text.textContent = entry.text || "";
    line.append(stamp, tag, text);
    host.appendChild(line);
    while (host.childElementCount > 300) host.removeChild(host.firstChild);
    host.scrollTop = host.scrollHeight;
  }

  function onMcResult(result) {
    const tone = ({ AVAILABLE: "avail", TAKEN: "taken", ERROR: "bad" })[result.status] || "info";
    pushMcLog({ tag: tone, text: `${result.name}  ${result.status}${result.reason ? "  ·  " + result.reason : ""}` });
    if (result.status === "AVAILABLE" && !mcState.available.includes(result.name)) {
      mcState.available.unshift(result.name);
      mcState.available = mcState.available.slice(0, 80);
      mcRenderAvailable();
    }
    if (state.page === "history") scheduleHistory();
  }

  async function mcRefresh() {
    try { applyMcState(await api("/api/mc/state")); } catch (_) { /* restarting */ }
  }

  async function mcCheckOne(name) {
    try {
      const result = await post("/api/mc/check", { name });
      toast(t("toast.result", { name: result.name, status: result.status }),
        result.status === "AVAILABLE" ? "ok" : "accent");
      onMcResult(result);
      mcRefresh();
    } catch (error) {
      toast(t("toast.error", { error: error.message }), "bad");
    }
  }

  async function mcSetRunning(run) {
    try {
      await post(run ? "/api/scan/start" : "/api/scan/stop", {});
      mcState.running = run;
      mcRenderTop();
      pushMcLog({ tag: run ? "ok" : "warn", text: run ? "checker started" : "checker stopped" });
      toast(t(run ? "toast.started" : "toast.stopped"), run ? "ok" : "warn");
      mcRefresh();
    } catch (error) {
      toast(t("toast.error", { error: error.message }), "bad");
    }
  }

  async function mcGenerate() {
    const length = Number($("#mcLength").value) || 4;
    const count = Number($("#mcCount").value || 50);
    $("#mcGenBtn").disabled = true;
    try {
      const data = await post("/api/generate", {
        length,
        count,
        mode: "rarest",
        consonants_only: false,
      });
      let message = t("toast.generated", {
        n: data.added, mode: t("gen.rarest"), length: data.length,
      });
      if (typeof data.queue === "number") {
        message += " · " + t("toast.queue", { n: data.queue });
      }
      if (data.generated < data.requested) {
        message += " · " + t("toast.exhausted", { n: data.generated });
      }
      toast(message, data.added ? "ok" : "warn");
      if (data.sample?.length) pushLog({ tag: "info", text: `${data.mode} ${data.length}L → ${data.sample.join(" ")}` });
      refreshState();
    } catch (error) {
      toast(t("toast.error", { error: error.message }), "bad");
    }
    $("#mcGenBtn").disabled = false;
  }

  /* --------------------------------------------------------------- history */
  const scheduleHistory = debounce(() => loadHistory(), 400);

  async function loadHistory() {
    const query = $("#historySearch")?.value.trim() || "";
    const status = $("#historyStatus")?.value || "";
    const params = new URLSearchParams({ limit: "300" });
    if (query) params.set("q", query);
    if (status) params.set("status", status);
    try {
      const data = await api(`/api/history?${params}`);
      state.historyRows = data.rows || [];
      state.history.total = data.total ?? state.history.total;
      renderHistory();
      applyI18n();
    } catch (error) {
      toast(t("toast.error", { error: error.message }), "bad");
    }
  }

  function renderHistory() {
    const body = $("#historyBody");
    if (!body) return;
    body.innerHTML = "";
    $("#historyEmpty").hidden = state.historyRows.length > 0;
    for (const row of state.historyRows) {
      const tr = document.createElement("tr");
      const status = String(row.status || "unknown");
      tr.innerHTML = `
        <td class="mono">${escapeHtml(row.name)}</td>
        <td><span class="badge badge-${escapeHtml(status)}">${escapeHtml(status.toUpperCase())}</span></td>
        <td>${escapeHtml(row.source || "—")}</td>
        <td>${row.scanned_at ? new Date(row.scanned_at * 1000).toLocaleString(state.lang === "id" ? "id-ID" : "en-US") : "—"}</td>
        <td><button class="row-action" data-delete="${escapeHtml(row.name)}" type="button">✕</button></td>`;
      body.appendChild(tr);
    }
    $("#historyMeta").textContent = t("history.rows", {
      n: state.historyRows.length, total: state.history.total ?? state.historyRows.length,
    });
  }

  /* -------------------------------------------------------------- settings */
  function fillSettings(force = true) {
    const cfg = state.config || {};
    if (!force && document.activeElement && ["INPUT", "SELECT"].includes(document.activeElement.tagName)) return;
    if (document.activeElement && ["INPUT", "SELECT"].includes(document.activeElement.tagName)) return;
    $("#setThreads").value = cfg.threads ?? 15;
    $("#setTimeout").value = cfg.timeout ?? 10;
    $("#setWatch").checked = Boolean(cfg.watch_mode);
    $("#setStealth").checked = Boolean(cfg.stealth_mode);
    $("#setAutoClaim").checked = Boolean(cfg.auto_claim);
    $("#setLanguage").value = cfg.language || state.lang;
  }

  async function saveSettings() {
    try {
      const data = await post("/api/settings", {
        threads: Number($("#setThreads").value || 15),
        timeout: Number($("#setTimeout").value || 10),
        watch_mode: $("#setWatch").checked,
        stealth_mode: $("#setStealth").checked,
        auto_claim: $("#setAutoClaim").checked,
        language: $("#setLanguage").value,
      });
      state.config = data.config || state.config;
      if (data.config?.language && data.config.language !== state.lang) {
        setLanguage(data.config.language, false);
      }
      $("#settingsNote").textContent = data.restart_required ? t("toast.restart") : "";
      toast(t("toast.saved"), "ok");
      refreshState();
    } catch (error) {
      toast(t("toast.error", { error: error.message }), "bad");
    }
  }

  /* --------------------------------------------------------------- actions */
  async function addNames() {
    const input = $("#nameInput");
    const raw = input.value.trim();
    if (!raw) return;
    try {
      const data = await post("/api/queue/add", { text: raw });
      if (data.added > 0) {
        let message = t("toast.added", { n: data.added });
        if (data.already_scanned) message += " · " + t("toast.rechecked", { n: data.already_scanned });
        if (data.skipped) message += " · " + t("toast.skipped", { n: data.skipped });
        toast(message, "ok");
        input.value = "";
      } else {
        toast(t("toast.nothing"), "warn");
      }
      state.queue = data.queue ?? state.queue;
      refreshState();
    } catch (error) {
      toast(t("toast.error", { error: error.message }), "bad");
    }
  }

  async function checkOne() {
    const input = $("#nameInput");
    const parts = input.value.trim().split(/\s+/).filter(Boolean);
    if (!parts.length) return;
    if (parts.length > 1) { toast(t("toast.one"), "warn"); return; }
    const name = parts[0].toLowerCase();
    if (!/^[a-z0-9_]{3,16}$/.test(name)) { toast(t("toast.invalid"), "bad"); return; }
    $("#checkBtn").disabled = true;
    toast(t("toast.checking", { name }), "accent");
    try {
      const data = await post("/api/check", { name });
      if (!data.ok) throw new Error(data.error || "check failed");
      const status = data.result.status;
      toast(t("toast.result", { name, status }), status === "AVAILABLE" ? "ok" : status === "TAKEN" ? "warn" : "bad");
      if (state.page === "history") loadHistory();
      refreshState();
    } catch (error) {
      toast(t("toast.error", { error: error.message }), "bad");
    } finally {
      $("#checkBtn").disabled = false;
    }
  }

  async function startEngine() {
    try {
      await post("/api/scan/start");
      toast(t("toast.started"), "ok");
      refreshState();
    } catch (error) {
      toast(t("toast.error", { error: error.message }), "bad");
    }
  }

  async function stopEngine() {
    try {
      await post("/api/scan/stop");
      toast(t("toast.stopped"), "warn");
      refreshState();
    } catch (error) {
      toast(t("toast.error", { error: error.message }), "bad");
    }
  }

  async function clearQueue() {
    if (!confirm(t("toast.cleared", { n: state.queue }) + " — lanjut?")) return;
    try {
      const data = await post("/api/queue/clear");
      toast(t("toast.cleared", { n: data.cleared }), "warn");
      refreshState();
    } catch (error) {
      toast(t("toast.error", { error: error.message }), "bad");
    }
  }

  async function generate() {
    const length = activeLength();
    const mode = activeMode();
    $("#genBtn").disabled = true;
    try {
      const data = await post("/api/generate", {
        length,
        count: Number($("#genCount").value || 500),
        mode,
        consonants_only: $("#consOnly").checked,
      });
      let message = t("toast.generated", {
        n: data.added, mode: t(`gen.${mode}`), length: data.length,
      });
      if (typeof data.queue === "number") {
        message += " · " + t("toast.queue", { n: data.queue });
      }
      if (data.generated < data.requested) {
        message += " · " + t("toast.exhausted", { n: data.generated });
      }
      toast(message, data.added ? "ok" : "warn");
      if (data.received && data.received.length == null) {
        toast(t("toast.staleUi"), "bad");
      }
      if (data.sample?.length) pushLog({ tag: "info", text: `${data.mode} ${data.length}L → ${data.sample.join(" ")}` });
      refreshState();
    } catch (error) {
      toast(t("toast.error", { error: error.message }), "bad");
    } finally {
      $("#genBtn").disabled = false;
    }
  }

  async function generatePattern() {
    const pattern = $("#patternInput").value.trim();
    if (!pattern) { $("#patternInput").focus(); return; }
    try {
      const data = await post("/api/generate/pattern", {
        pattern, count: Number($("#genCount").value || 500),
      });
      toast(t("toast.pattern", { pattern, n: data.added }), data.added ? "ok" : "warn");
      pushLog({ tag: "info", text: `${pattern} → ${(data.sample || []).join(" ")}` });
      refreshState();
    } catch (error) {
      toast(t("toast.error", { error: error.message }), "bad");
    }
  }

  async function deleteHistory(name) {
    try {
      await post("/api/history/delete", { name });
      toast(t("toast.deleted"), "warn");
      loadHistory();
    } catch (error) {
      toast(t("toast.error", { error: error.message }), "bad");
    }
  }

  async function clearHistory() {
    if (!confirm(t("history.clear") + " — " + t("history.title") + "?")) return;
    try {
      const data = await post("/api/history/clear");
      toast(t("toast.historyCleared", { n: data.removed }), "warn");
      loadHistory();
      refreshState();
    } catch (error) {
      toast(t("toast.error", { error: error.message }), "bad");
    }
  }

  async function rescanFailed() {
    try {
      const data = await post("/api/history/rescan");
      toast(t("toast.rescan", { n: data.added }), "accent");
      refreshState();
    } catch (error) {
      toast(t("toast.error", { error: error.message }), "bad");
    }
  }

  /* ------------------------------------------------------------------ chips */
  function syncChips() {
    $$("#modeChips .chip").forEach((chip) => {
      chip.classList.toggle("is-active", chip.dataset.mode === state.genMode);
    });
    $$("#lengthChips .chip").forEach((chip) => {
      chip.classList.toggle("is-active", Number(chip.dataset.length) === state.genLength);
    });
  }

  /* --------------------------------------------------------------- realtime */
  function connect() {
    if (!window.EventSource) return;
    const source = new EventSource("/api/events");
    source.addEventListener("hello", (event) => {
      const snapshot = safeParse(event.data);
      applyState(snapshot);
      checkBuild(snapshot);
    });
    source.addEventListener("stats", (event) => {
      const stats = safeParse(event.data);
      if (stats) applyStats(stats);
    });
    source.addEventListener("log", (event) => pushLog(safeParse(event.data)));
    source.addEventListener("result", (event) => {
      const result = safeParse(event.data);
      if (result) onResult(result);
    });
    source.addEventListener("status", (event) => {
      const data = safeParse(event.data) || {};
      state.running = data.state === "running";
      $("#statusPill").dataset.state = state.running ? "running" : "stopped";
      $("#statusText").textContent = t(state.running ? "status.running" : "status.stopped");
      $("#startBtn").disabled = state.running;
      $("#stopBtn").disabled = !state.running;
    });
    source.addEventListener("available", (event) => onAvailable(safeParse(event.data)));
    source.addEventListener("dg_state", (event) => applyDgState(safeParse(event.data)));
    source.addEventListener("dg_status", (event) => {
      const data = safeParse(event.data) || {};
      dgState.running = data.state === "running";
      if (data.workers) dgState.workers = data.workers;
      dgRenderTop();
    });
    source.addEventListener("dg_log", (event) => pushDgLog(safeParse(event.data)));
    source.addEventListener("dg_result", (event) => {
      const result = safeParse(event.data);
      if (result) onDgResult(result);
    });
    source.addEventListener("claimed", (event) => {
      const data = safeParse(event.data) || {};
      pushLog({ tag: "claim", text: `claimed ${data.name} via ${data.account}` });
    });
  }

  function safeParse(raw) {
    try { return JSON.parse(raw); } catch (_) { return null; }
  }

  async function refreshState() {
    try {
      const snapshot = await api("/api/state");
      applyState(snapshot);
      checkBuild(snapshot);
    } catch (_) { /* server might be restarting */ }
  }

  /* ------------------------------------------------------------------ wiring */
  function wire() {
    const nav = $("#nav");
    if (nav) {
      nav.addEventListener("click", (e) => {
        const btn = e.target.closest(".nav-item");
        if (btn && btn.dataset.page) {
          e.preventDefault();
          setPage(btn.dataset.page);
        }
      });
    } else {
      $$(".nav-item").forEach((btn) => btn.addEventListener("click", () => setPage(btn.dataset.page)));
    }
    $$(".lang-btn").forEach((btn) => btn.addEventListener("click", () => setLanguage(btn.dataset.lang)));

    on("#addBtn", "click", addNames);
    on("#checkBtn", "click", checkOne);
    on("#startBtn", "click", startEngine);
    on("#stopBtn", "click", stopEngine);
    on("#clearBtn", "click", clearQueue);
    on("#genBtn", "click", generate);
    on("#patternBtn", "click", generatePattern);
    on("#buildReload", "click", () => location.reload());
    on("#logClear", "click", () => {
      state.log = [];
      const host = $("#log");
      if (host) host.innerHTML = "";
    });

    on("#nameInput", "keydown", (event) => {
      if (event.key !== "Enter") return;
      event.preventDefault();
      if (event.shiftKey) addNames(); else checkOne();
    });

    const logHost = $("#log");
    if (logHost) {
      logHost.addEventListener("scroll", () => {
        state.autoScroll = logHost.scrollTop + logHost.clientHeight >= logHost.scrollHeight - 24;
      });
    }

    $$("#modeChips .chip").forEach((chip) => chip.addEventListener("click", () => {
      state.genMode = chip.dataset.mode;
      syncChips();
      post("/api/settings", { gen_mode: state.genMode }).catch(() => {});
    }));
    $$("#lengthChips .chip").forEach((chip) => chip.addEventListener("click", () => {
      state.genLength = Number(chip.dataset.length);
      syncChips();
    }));
    on("#consOnly", "change", () => {
      post("/api/settings", { gen_consonants_only: $("#consOnly").checked }).catch(() => {});
    });

    on("#historySearch", "input", debounce(loadHistory, 300));
    on("#historyStatus", "change", loadHistory);
    on("#historyBody", "click", (event) => {
      const button = event.target.closest("[data-delete]");
      if (button) deleteHistory(button.dataset.delete);
    });
    on("#dgGenBtn", "click", dgGenerate);
    on("#dgAddBtn", "click", dgAdd);
    on("#dgCheckBtn", "click", dgCheck);
    on("#dgStartBtn", "click", () => dgSetRunning(true));
    on("#dgStopBtn", "click", () => dgSetRunning(false));
    on("#dgClearBtn", "click", async () => {
      try {
        const data = await post("/api/dg/queue/clear", {});
        pushDgLog({ tag: "warn", text: `queue cleared (${data.cleared})` });
        dgRefresh();
      } catch (error) {
        toast(t("toast.error", { error: error.message }), "bad");
      }
    });
    on("#dgSaveSources", "click", dgSaveSources);
    on("#dgLogClear", "click", () => {
      dgState.log = [];
      const host = $("#dgLog");
      if (host) host.innerHTML = "";
    });
    on("#dgNameInput", "keydown", (event) => {
      if (event.key !== "Enter") return;
      event.preventDefault();
      if (event.shiftKey) dgAdd(); else dgCheck();
    });
    $$("#dgLengthChips .chip").forEach((chip) => chip.addEventListener("click", () => {
      dgState.length = Number(chip.dataset.length) === 4 ? 4 : 3;
      $$("#dgLengthChips .chip").forEach((other) => {
        other.classList.toggle("is-active", other === chip);
      });
    }));

    $$("#mcLengthChips .chip").forEach((chip) => chip.addEventListener("click", () => {
      mcState.length = Number(chip.dataset.length) === 4 ? 4 : 3;
      $$("#mcLengthChips .chip").forEach((other) => {
        other.classList.toggle("is-active", other === chip);
      });
    }));

    on("#rescanBtn", "click", rescanFailed);
    on("#historyClear", "click", clearHistory);
    on("#saveSettings", "click", saveSettings);

    window.addEventListener("hashchange", () => setPage(location.hash.replace("#", "")));
  }

  window.setPage = setPage;
  window.switchPage = setPage;
  document.addEventListener("DOMContentLoaded", () => {
    state.lang = I18N[state.lang] ? state.lang : "en";
    wire();
    applyI18n();
    setPage(location.hash.replace("#", "") || "checker");
    applyStats({});
    renderAvailable();
    mcRefresh();
    refreshState();
    connect();
    setInterval(() => { if (!state.running) refreshState(); }, 15000);
  });
})();
