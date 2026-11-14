const LANGS = [
  ["auto", "Auto / bahasa asli"],
  ["en", "English"],
  ["id", "Bahasa Indonesia"],
  ["es", "Español"],
  ["pt", "Português"],
  ["fr", "Français"],
  ["de", "Deutsch"],
  ["it", "Italiano"],
  ["nl", "Nederlands"],
  ["pl", "Polski"],
  ["ru", "Русский"],
  ["tr", "Türkçe"],
  ["ar", "العربية"],
  ["hi", "हिन्दी"],
  ["th", "ไทย"],
  ["vi", "Tiếng Việt"],
  ["ja", "日本語"],
  ["ko", "한국어"],
  ["zh", "中文"],
];

const BASE_URLS = {
  google: "https://generativelanguage.googleapis.com/v1beta/openai",
  openai: "https://api.openai.com/v1",
  groq: "https://api.groq.com/openai/v1",
  openrouter: "https://openrouter.ai/api/v1",
  local: "http://localhost:8000/v1",
};

let watermarkPreview = "";

const state = {
  config: null,
  cookies: null,
  assets: null,
  sessions: [],
  highlights: [],
  sessionId: null,
  selected: new Set(),
  jobTimer: null,
  detail: null,
  toastTimer: null,
};

const $ = (id) => document.getElementById(id);
const esc = (value) =>
  String(value ?? "").replace(/[&<>"']/g, (char) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#39;",
  }[char]));

const fmtTime = (seconds) => {
  const total = Math.max(0, Math.floor(Number(seconds) || 0));
  const minutes = Math.floor(total / 60);
  return `${minutes}:${String(total % 60).padStart(2, "0")}`;
};

const fmtDate = (timestamp) =>
  timestamp
    ? new Date(timestamp * 1000).toLocaleString("id-ID", { dateStyle: "medium", timeStyle: "short" })
    : "";

async function api(path, method = "GET", body) {
  const options = { method, headers: {} };
  if (body !== undefined) {
    options.headers["Content-Type"] = "application/json";
    options.body = JSON.stringify(body);
  }
  const response = await fetch(path, options);
  let data;
  try {
    data = await response.json();
  } catch {
    throw new Error(`Server mengembalikan respons tidak valid (HTTP ${response.status})`);
  }
  if (!response.ok || data.ok === false) {
    throw new Error(data.error || `HTTP ${response.status}`);
  }
  return data;
}

function toast(message, isError = false) {
  const node = $("toast");
  node.textContent = message;
  node.classList.toggle("error", isError);
  node.classList.add("show");
  clearTimeout(state.toastTimer);
  state.toastTimer = setTimeout(() => node.classList.remove("show"), isError ? 6500 : 3800);
}

function setBusy(button, busy, text) {
  if (!button) return;
  button.disabled = busy;
  const label = button.querySelector("span");
  if (!label) return;
  if (!button.dataset.label) button.dataset.label = label.textContent;
  label.textContent = busy ? text : button.dataset.label;
}

function populateLanguages() {
  const options = LANGS.map(([value, label]) => `<option value="${value}">${label}</option>`).join("");
  ["subtitleLanguage", "outputLanguage", "settingsOutputLanguage"].forEach((id) => {
    const select = $(id);
    if (select) select.innerHTML = options;
  });
}

function updateAssetStatus() {
  const pill = $("assetStatus");
  const { ffmpeg, deno } = state.assets || {};
  pill.classList.remove("ok", "bad");
  if (ffmpeg) {
    pill.classList.add("ok");
    pill.title = `ffmpeg: ${ffmpeg}${deno ? `\ndeno: ${deno}` : "\ndeno: tidak ditemukan"}`;
    pill.querySelector("span:last-child").textContent = deno ? "ffmpeg + deno siap" : "ffmpeg siap";
  } else {
    pill.classList.add("bad");
    pill.title = "ffmpeg tidak ditemukan";
    pill.querySelector("span:last-child").textContent = "ffmpeg belum ada";
  }

  const setEngine = (name, ok, text) => {
    const node = $(`engine${name}`);
    const dot = $(`engine${name}Dot`);
    if (node) {
      node.textContent = text;
      node.className = ok ? "ok" : "";
    }
    if (dot) dot.className = `dot ${ok ? "ok" : ""}`;
  };
  setEngine("Ffmpeg", Boolean(ffmpeg), ffmpeg ? "siap" : "belum");
  setEngine("Deno", Boolean(deno), deno ? "siap" : "belum");
  setEngine("Ai", Boolean(state.config?.ai?.hasKey), state.config?.ai?.hasKey ? "aktif" : "belum");

  $("assetHint").textContent = `ffmpeg: ${ffmpeg || "tidak ditemukan"} · deno: ${deno || "tidak ditemukan"}`;
}

function updateCookieStatus() {
  const box = state.cookies || {};
  const node = $("cookieStatus");
  if (!box.saved) {
    node.textContent = "Belum ada cookies. Video publik biasanya tetap bisa diproses.";
    return;
  }
  const login = box.hasAuth ? "login terdeteksi" : "tanpa cookie login";
  node.textContent = `${box.count} cookie YouTube · ${login} · diperbarui ${box.ageHours ?? "?"} jam lalu`;
}

function syncBaseUrlPreset() {
  const current = $("baseUrl").value.trim();
  const match = Object.entries(BASE_URLS).find(([, url]) => url === current);
  $("baseUrlPreset").value = match ? match[0] : "custom";
}

function toggleCustomModel() {
  const custom = $("model").value === "__custom__";
  $("modelCustom").classList.toggle("hidden", !custom);
  if (custom) $("modelCustom").focus();
}

function selectedModel() {
  return $("model").value === "__custom__" ? $("modelCustom").value.trim() : $("model").value;
}

function modelChoices() {
  return [...$("model").options]
    .map((option) => option.value)
    .filter((value) => value && value !== "__custom__");
}

function fillModelOptions(models, selected) {
  const select = $("model");
  const values = [...new Set(models.filter((value) => value && value !== "__custom__"))];
  if (selected && selected !== "__custom__" && !values.includes(selected)) values.unshift(selected);
  select.innerHTML = "";
  if (!values.length) select.add(new Option("Belum ada model — klik Muat model", ""));
  for (const value of values) select.add(new Option(value, value));
  select.add(new Option("Custom / ketik manual…", "__custom__"));
  if (selected === "__custom__") select.value = "__custom__";
  else if (selected && values.includes(selected)) select.value = selected;
  else if (values.length) select.value = values[0];
  toggleCustomModel();
}

function ensureModelOption(model) {
  const known = modelChoices();
  if (!known.length) {
    fillModelOptions(model ? [model] : [], model);
    return;
  }
  if (model && !known.includes(model)) {
    fillModelOptions([model, ...known], model);
    return;
  }
  $("model").value = model || known[0];
  toggleCustomModel();
}

function applySettings() {
  const config = state.config;
  if (!config) return;
  $("baseUrl").value = config.ai?.baseUrl || "";
  syncBaseUrlPreset();
  ensureModelOption(config.ai?.model || "");
  $("apiKey").value = "";
  $("apiKey").placeholder = config.ai?.hasKey
    ? "Tersimpan aman — isi hanya untuk mengganti"
    : "Belum ada key — tempel API key di sini";
  $("settingsOutputLanguage").value = config.outputLanguage || "auto";
  $("minSeconds").value = config.clip?.minSeconds ?? 20;
  $("maxSeconds").value = config.clip?.maxSeconds ?? 120;
  $("padding").value = config.clip?.padding ?? 0.25;
  $("portrait").checked = config.render?.portrait !== false;
  $("background").value = config.render?.background || "black";
  $("captions").checked = config.render?.captions !== false;
  $("captionColor").value = /^#[0-9a-f]{6}$/i.test(config.render?.captionColor || "")
    ? config.render.captionColor
    : "#ffd700";
  $("captionStyle").value = config.render?.captionStyle || "highlight";
  $("hook").checked = config.render?.hook !== false;
  $("hookSeconds").value = config.render?.hookSeconds ?? 3;
  $("watermark").value = config.render?.watermark || "";
  $("credit").value = config.render?.credit || "";
  setGridValue("watermarkPosition", config.render?.watermarkPosition || "top-right");
  setGridValue("creditPosition", config.render?.creditPosition || "bottom-center");
  watermarkPreview = "";
  updateBrandPreview();
  $("ffmpegPath").value = config.paths?.ffmpeg || "";
  $("denoPath").value = config.paths?.deno || "";
  updateAssetStatus();
}

async function loadState() {
  const data = await api("/api/state");
  state.config = data.config;
  state.cookies = data.cookies;
  state.assets = data.assets;
  applySettings();
  updateCookieStatus();
}

function route() {
  const requested = (location.hash || "#create").slice(1);
  const view = ["create", "library", "settings", "about"].includes(requested) ? requested : "create";
  document.querySelectorAll(".view").forEach((node) => node.classList.add("hidden"));
  $(`view-${view}`).classList.remove("hidden");
  document.querySelectorAll(".tab").forEach((tab) => {
    tab.classList.toggle("is-active", tab.dataset.view === view);
  });
  const crumbs = {
    create: ["WORKSPACE", "CLIP STUDIO"],
    library: ["WORKSPACE", "PUSTAKA"],
    settings: ["WORKSPACE", "PENGATURAN"],
    about: ["WORKSPACE", "TENTANG"],
  };
  const [top, bottom] = crumbs[view];
  $("crumb").innerHTML = `<span>${top}</span><i>/</i><b>${bottom}</b>`;
  document.title = view === "create" ? "AIKLIPYT — Clip Studio" : `AIKLIPYT — ${bottom.toLowerCase()}`;
  if (view === "library") loadSessions().catch((error) => toast(error.message, true));
}

function showJob(title) {
  $("jobTitle").textContent = title;
  $("jobEmpty").classList.add("hidden");
  $("jobBody").classList.remove("hidden");
  $("jobError").classList.add("hidden");
  $("jobProgress").style.width = "0%";
  $("jobPercent").textContent = "0%";
  $("jobLog").textContent = "";
  $("jobState").textContent = "jalan";
}

function updateJob(job) {
  $("jobMessage").textContent = job.message || "";
  const percent = Math.max(0, Math.min(100, Number(job.progress) || 0));
  $("jobProgress").style.width = `${percent}%`;
  $("jobPercent").textContent = `${Math.round(percent)}%`;
  $("jobLog").textContent = (job.log || []).join("\n");
  $("jobState").textContent = job.status === "running" ? "jalan" : job.status === "done" ? "selesai" : "gagal";
  if (job.error) {
    const node = $("jobError");
    node.textContent = job.error;
    node.classList.remove("hidden");
  }
}

function pollJob(jobId, onDone, onFail) {
  clearInterval(state.jobTimer);
  const tick = async () => {
    try {
      const { job } = await api(`/api/jobs/${jobId}`);
      updateJob(job);
      if (job.status !== "running") {
        clearInterval(state.jobTimer);
        state.jobTimer = null;
        if (job.status === "done") onDone(job);
        else {
          toast(job.error || "Proses gagal", true);
          if (onFail) onFail(job);
        }
      }
    } catch (error) {
      clearInterval(state.jobTimer);
      state.jobTimer = null;
      toast(error.message, true);
      if (onFail) onFail();
    }
  };
  tick();
  state.jobTimer = setInterval(tick, 1200);
}

async function findHighlights() {
  const url = $("url").value.trim();
  if (!/^https?:\/\//i.test(url)) {
    toast("Tempel URL YouTube yang valid", true);
    return;
  }
  const button = $("findBtn");
  setBusy(button, true, "Mencari…");
  $("resultsPanel").classList.add("hidden");
  state.highlights = [];
  state.selected = new Set();
  $("previewHook").textContent = "Ini yang tidak dibicarakan.";
  $("previewMeta").textContent = "AI PICK · —:—";
  showJob("Mencari highlight");
  const requested = Math.max(1, Math.min(20, Number($("numClips").value) || 5));
  try {
    const { jobId } = await api("/api/highlights", "POST", {
      url,
      numClips: requested,
      subtitleLanguage: $("subtitleLanguage").value,
      outputLanguage: $("outputLanguage").value,
      direction: $("direction").value.trim(),
    });
    pollJob(jobId, (job) => {
      setBusy(button, false);
      state.sessionId = job.result.sessionId;
      state.highlights = job.result.highlights || [];
      const recommended = state.highlights
        .map((clip, index) => ({ clip, index }))
        .filter(({ clip }) => scoreOf(clip) >= 7)
        .map(({ index }) => index);
      state.selected = new Set(
        recommended.length ? recommended : state.highlights.map((_, index) => index),
      );
      renderHighlights();
      $("resultsPanel").classList.remove("hidden");
      $("resultsPanel").scrollIntoView({ behavior: "smooth", block: "start" });
      const wanted = Number(job.result?.requested) || requested;
      const short = state.highlights.length < wanted;
      toast(
        short
          ? `AI hanya menemukan ${state.highlights.length} dari ${wanted} momen`
          : `${state.highlights.length} highlight — ${state.selected.size} direkomendasikan untuk dirender`,
        short,
      );
    }, () => setBusy(button, false));
  } catch (error) {
    setBusy(button, false);
    toast(error.message, true);
  }
}

function scoreOf(clip) {
  return Number(clip?.virality_score) || 0;
}

function scoreGrade(score) {
  if (score >= 8.5) return { label: "Sangat kuat", cls: "score-strong" };
  if (score >= 7) return { label: "Kuat", cls: "score-good" };
  if (score >= 5.5) return { label: "Cukup", cls: "score-mid" };
  return { label: "Lemah", cls: "score-weak" };
}

function orderedHighlights() {
  return state.highlights
    .map((clip, index) => ({ clip, index }))
    .sort((a, b) => scoreOf(b.clip) - scoreOf(a.clip) || a.index - b.index);
}

function renderHighlights() {
  const { sessionId, highlights, selected } = state;
  const ordered = orderedHighlights();
  $("resultTitle").textContent = "Highlight";
  $("resultMeta").textContent = `${highlights.length} momen · diurutkan dari skor tertinggi · sesi ${sessionId}`;
  const first = ordered[0]?.clip;
  if (first) {
    $("previewHook").textContent = first.hook_text || first.title || "Momen terbaik.";
    $("previewMeta").textContent = `AI PICK · ${fmtTime(first.start)}–${fmtTime(first.end)}`;
  }
  $("highlightList").innerHTML = ordered
    .map(({ clip, index }, position) => {
      const active = selected.has(index);
      const score = scoreOf(clip);
      const grade = scoreGrade(score);
      const breakdown = clip.score_breakdown || {};
      const dims = [
        ["hook_score", "Hook"],
        ["emotion_score", "Emosi"],
        ["clarity_score", "Jelas"],
        ["loop_score", "Loop"],
      ]
        .filter(([key]) => Number.isFinite(Number(breakdown[key])))
        .map(([key, label]) => `${label} ${Math.round(Number(breakdown[key]))}`)
        .join(" · ");
      return `
        <label class="highlight ${active ? "" : "is-off"}" data-index="${index}">
          <input type="checkbox" data-index="${index}" ${active ? "checked" : ""} aria-label="Pilih klip ${index + 1}">
          <div>
            <h3><span class="rank">#${position + 1}</span> ${esc(clip.title || `Klip ${index + 1}`)}</h3>
            <div class="meta">
              <span>${fmtTime(clip.start)} – ${fmtTime(clip.end)}</span>
              <span>${Math.round(clip.duration || 0)} detik</span>
              <span>klip ${index + 1}</span>
            </div>
            ${clip.hook_text ? `<p class="hook">"${esc(clip.hook_text)}"</p>` : ""}
            ${clip.description ? `<p class="desc">${esc(clip.description)}</p>` : ""}
            ${dims ? `<p class="score-breakdown">${dims}</p>` : ""}
            ${clip.score_reason ? `<p class="score-reason">${esc(clip.score_reason)}</p>` : ""}
          </div>
          <div class="score ${grade.cls}">${score.toFixed(1)}<small>${grade.label}</small></div>
        </label>`;
    })
    .join("");
  updateRenderButton();
}

function updateRenderButton() {
  const count = state.selected.size;
  const button = $("renderBtn");
  button.textContent = count ? `Render ${count} klip` : "Pilih klip";
  button.disabled = count === 0;
  const all = state.highlights.length > 0 && count === state.highlights.length;
  $("selectAll").textContent = all ? "Batalkan semua" : "Pilih semua";
}

async function renderSelected() {
  if (!state.sessionId || state.selected.size === 0) return;
  const button = $("renderBtn");
  setBusy(button, true, "Merender…");
  showJob("Merender klip");
  try {
    const { jobId } = await api("/api/render", "POST", {
      sessionId: state.sessionId,
      indices: [...state.selected].sort((a, b) => a - b),
    });
    pollJob(jobId, (job) => {
      const errors = job.result?.errors || [];
      toast(errors.length ? `Selesai dengan ${errors.length} error` : "Klip selesai dirender", errors.length > 0);
      state.selected = new Set();
      setBusy(button, false);
      location.hash = "#library";
      loadSessions().catch((error) => toast(error.message, true));
    }, () => setBusy(button, false));
  } catch (error) {
    setBusy(button, false);
    toast(error.message, true);
  }
}

async function loadSessions() {
  const { sessions } = await api("/api/sessions");
  state.sessions = sessions;
  renderLibrary();
}

function renderLibrary() {
  const list = $("libraryList");
  if (!state.sessions.length) {
    list.innerHTML = `<div class="empty-line">Belum ada sesi. Buat klip pertamamu di tab Buat.</div>`;
    return;
  }
  list.innerHTML = state.sessions
    .map((session) => {
      const thumb = session.thumbnail
        ? `<img class="thumb" src="${esc(session.thumbnail)}" alt="" loading="lazy" onerror="this.outerHTML='<div class=&quot;thumb-fallback&quot;>▦</div>'">`
        : `<div class="thumb-fallback">▦</div>`;
      return `
        <article class="session-card" data-id="${esc(session.id)}">
          ${thumb}
          <div>
            <h3>${esc(session.title || "Tanpa judul")}</h3>
            <div class="meta">
              <span>${esc(session.channel || "—")}</span>
              <span>${fmtDate(session.createdAt)}</span>
              <span>${session.clipCount} klip</span>
              <span>${session.highlightCount} highlight</span>
            </div>
          </div>
          <div class="actions">
            <button class="btn ghost small" data-action="view">Lihat klip</button>
            <button class="btn ghost small" data-action="open">Folder</button>
            <button class="btn danger small" data-action="delete">Hapus</button>
          </div>
        </article>`;
    })
    .join("");
}

async function openSession(sessionId) {
  const { session } = await api(`/api/sessions/${encodeURIComponent(sessionId)}`);
  state.detail = session;
  $("libraryDetail").classList.remove("hidden");
  $("detailTitle").textContent = session.title || "Sesi";
  $("detailMeta").textContent = `${session.channel || "—"} · ${session.highlights?.length || 0} highlight · ${session.clips?.length || 0} klip dirender`;
  const clips = session.clips || [];
  $("clipGrid").innerHTML = clips.length
    ? clips
        .map(
          (clip) => `
        <article class="clip-card">
          <video controls preload="metadata" src="/api/media/${encodeURIComponent(sessionId)}/${encodeURIComponent(clip.file)}"></video>
          <div class="clip-info">
            <h4>${esc(clip.title || clip.file)}</h4>
            <div class="meta">${fmtTime(clip.start)} → ${fmtTime(clip.end)} · ${Math.round(clip.duration || 0)} dtk</div>
          </div>
        </article>`
        )
        .join("")
    : `<div class="empty-line">Belum ada klip dirender untuk sesi ini.</div>`;
  $("libraryDetail").scrollIntoView({ behavior: "smooth", block: "start" });
}

async function removeSession(sessionId) {
  if (!confirm("Hapus sesi ini beserta semua klipnya?")) return;
  try {
    await api("/api/delete", "POST", { sessionId });
    toast("Sesi dihapus");
    $("libraryDetail").classList.add("hidden");
    state.detail = null;
    await loadSessions();
  } catch (error) {
    toast(error.message, true);
  }
}

async function refreshModels() {
  const button = $("refreshModels");
  const status = $("modelsStatus");
  setBusy(button, true, "Memuat…");
  status.textContent = "Menghubungi provider…";
  try {
    const payload = { baseUrl: $("baseUrl").value.trim() };
    const key = $("apiKey").value.trim();
    if (key) payload.apiKey = key;
    const data = await api("/api/models", "POST", payload);
    fillModelOptions(data.models, selectedModel());
    status.textContent = `${data.models.length} model tersedia — pilih dari dropdown atau Custom.`;
    toast(`${data.models.length} model dimuat`);
  } catch (error) {
    status.textContent = "Gagal memuat model. Cek Base URL dan API key.";
    toast(error.message, true);
  } finally {
    setBusy(button, false);
  }
}

async function saveSettings() {
  const button = $("saveSettings");
  const model = selectedModel();
  if ($("model").value === "__custom__" && !model) {
    toast("Isi nama model custom dulu", true);
    $("modelCustom").focus();
    return;
  }
  setBusy(button, true, "Menyimpan…");
  try {
    const payload = {
      ai: {
        baseUrl: $("baseUrl").value.trim(),
        model,
      },
      outputLanguage: $("settingsOutputLanguage").value,
      clip: {
        minSeconds: Number($("minSeconds").value),
        maxSeconds: Number($("maxSeconds").value),
        padding: Number($("padding").value),
      },
      render: {
        portrait: $("portrait").checked,
        background: $("background").value,
        captions: $("captions").checked,
        captionColor: $("captionColor").value,
        captionStyle: $("captionStyle").value,
        hook: $("hook").checked,
        hookSeconds: Number($("hookSeconds").value),
        watermark: $("watermark").value.trim(),
        watermarkPosition: $("watermarkPosition").dataset.position || "top-right",
        credit: $("credit").value.trim(),
        creditPosition: $("creditPosition").dataset.position || "bottom-center",
      },
      paths: {
        ffmpeg: $("ffmpegPath").value.trim(),
        deno: $("denoPath").value.trim(),
      },
    };
    const key = $("apiKey").value.trim();
    if (key) payload.ai.apiKey = key;
    const data = await api("/api/settings", "POST", payload);
    state.config = data.config;
    state.cookies = data.cookies;
    state.assets = data.assets;
    applySettings();
    updateCookieStatus();
    toast("Pengaturan disimpan");
  } catch (error) {
    toast(error.message, true);
  } finally {
    setBusy(button, false);
  }
}

async function saveCookies() {
  const content = $("cookieText").value;
  if (!content.trim()) {
    toast("Tempel isi cookies dulu", true);
    return;
  }
  try {
    const data = await api("/api/cookies", "POST", { content });
    state.cookies = data.cookies;
    updateCookieStatus();
    $("cookieText").value = "";
    const skipped = data.filtered?.skipped || 0;
    toast(`${data.filtered?.kept || 0} cookie YouTube disimpan${skipped ? `, ${skipped} cookie domain lain dibuang` : ""}`);
  } catch (error) {
    toast(error.message, true);
  }
}

function bindEvents() {
  document.querySelectorAll(".tab").forEach((tab) => {
    tab.addEventListener("click", () => {
      location.hash = `#${tab.dataset.view}`;
    });
  });
  window.addEventListener("hashchange", route);

  $("topCookies").addEventListener("click", () => {
    if (location.hash !== "#create") {
      location.hash = "#create";
      route();
    }
    $("cookieEditor").classList.remove("hidden");
    $("cookieEditor").scrollIntoView({ behavior: "smooth", block: "center" });
  });
  $("numClips").addEventListener("input", () => {
    const value = Math.max(1, Math.min(20, Number($("numClips").value) || 1));
    $("statClips").textContent = String(value).padStart(2, "0");
  });

  $("createForm").addEventListener("submit", (event) => {
    event.preventDefault();
    findHighlights();
  });

  $("toggleCookies").addEventListener("click", () => {
    $("cookieEditor").classList.toggle("hidden");
  });
  $("saveCookies").addEventListener("click", saveCookies);
  $("deleteCookies").addEventListener("click", async () => {
    if (!confirm("Hapus cookies tersimpan?")) return;
    try {
      const data = await api("/api/cookies/delete", "POST", {});
      state.cookies = data.cookies;
      updateCookieStatus();
      toast("Cookies dihapus");
    } catch (error) {
      toast(error.message, true);
    }
  });
  $("cookieFile").addEventListener("change", async (event) => {
    const file = event.target.files?.[0];
    if (file) $("cookieText").value = await file.text();
  });

  $("highlightList").addEventListener("change", (event) => {
    const input = event.target.closest('input[type="checkbox"]');
    if (!input) return;
    const index = Number(input.dataset.index);
    if (input.checked) state.selected.add(index);
    else state.selected.delete(index);
    input.closest(".highlight").classList.toggle("is-off", !input.checked);
    updateRenderButton();
  });

  $("selectAll").addEventListener("click", () => {
    const all = state.selected.size === state.highlights.length;
    state.selected = all ? new Set() : new Set(state.highlights.map((_, index) => index));
    renderHighlights();
  });
  $("selectGood").addEventListener("click", () => {
    state.selected = new Set(
      state.highlights
        .map((clip, index) => ({ clip, index }))
        .filter(({ clip }) => scoreOf(clip) >= 7)
        .map(({ index }) => index),
    );
    renderHighlights();
    if (!state.selected.size) toast("Belum ada klip dengan skor ≥ 7. Pilih manual.", true);
  });
  $("renderBtn").addEventListener("click", renderSelected);

  $("refreshLibrary").addEventListener("click", () => {
    loadSessions().catch((error) => toast(error.message, true));
  });
  $("libraryList").addEventListener("click", async (event) => {
    const action = event.target.closest("[data-action]")?.dataset.action;
    if (!action) return;
    const card = event.target.closest(".session-card");
    const sessionId = card?.dataset.id;
    if (!sessionId) return;
    try {
      if (action === "view") await openSession(sessionId);
      if (action === "open") await api("/api/open", "POST", { sessionId, kind: "output" });
      if (action === "delete") await removeSession(sessionId);
    } catch (error) {
      toast(error.message, true);
    }
  });
  $("openOutput").addEventListener("click", () => {
    if (state.detail) api("/api/open", "POST", { sessionId: state.detail.id, kind: "output" }).catch((error) => toast(error.message, true));
  });
  $("deleteSession").addEventListener("click", () => {
    if (state.detail) removeSession(state.detail.id);
  });

  $("saveSettings").addEventListener("click", saveSettings);
  $("refreshModels").addEventListener("click", refreshModels);
  $("model").addEventListener("change", toggleCustomModel);
  $("baseUrlPreset").addEventListener("change", () => {
    const url = BASE_URLS[$("baseUrlPreset").value];
    if (url) $("baseUrl").value = url;
    else $("baseUrl").focus();
  });
}

const POSITIONS = [
  ["top-left", "Kiri atas"],
  ["top-center", "Tengah atas"],
  ["top-right", "Kanan atas"],
  ["middle-left", "Kiri tengah"],
  ["center", "Tengah"],
  ["middle-right", "Kanan tengah"],
  ["bottom-left", "Kiri bawah"],
  ["bottom-center", "Tengah bawah"],
  ["bottom-right", "Kanan bawah"],
];

function setGridValue(id, value) {
  const grid = $(id);
  if (!grid) return;
  grid.dataset.position = value;
  for (const button of grid.querySelectorAll("button")) {
    button.classList.toggle("active", button.dataset.pos === value);
  }
  updateBrandPreview();
}

function buildPositionGrids() {
  for (const [id, fallback] of [["watermarkPosition", "top-right"], ["creditPosition", "bottom-center"]]) {
    const grid = $(id);
    if (!grid) continue;
    grid.innerHTML = "";
    for (const [value, label] of POSITIONS) {
      const button = document.createElement("button");
      button.type = "button";
      button.dataset.pos = value;
      button.title = label;
      button.setAttribute("aria-label", label);
      button.addEventListener("click", () => setGridValue(id, value));
      grid.appendChild(button);
    }
    setGridValue(id, grid.dataset.position || fallback);
  }
}

function previewPos(element, position) {
  for (const [value] of POSITIONS) element.classList.remove(`pos-${value}`);
  element.classList.add(`pos-${position || "top-right"}`);
}

function updateBrandPreview() {
  if (!$("previewWatermark")) return;
  const path = $("watermark").value.trim();
  const image = $("previewWatermark");
  if (path) {
    image.src = watermarkPreview || `/api/watermark?v=${Date.now()}`;
    image.classList.remove("hidden");
  } else {
    image.removeAttribute("src");
    image.classList.add("hidden");
  }
  previewPos(image, $("watermarkPosition").dataset.position);
  const credit = $("credit").value.trim();
  const label = $("previewCredit");
  label.textContent = credit || "@channel";
  label.classList.toggle("hidden", !credit);
  previewPos(label, $("creditPosition").dataset.position);
}

function downscaleImage(file, max) {
  return new Promise((resolve, reject) => {
    const url = URL.createObjectURL(file);
    const image = new Image();
    image.onload = () => {
      URL.revokeObjectURL(url);
      const scale = Math.min(1, max / Math.max(image.width, image.height));
      const canvas = document.createElement("canvas");
      canvas.width = Math.max(1, Math.round(image.width * scale));
      canvas.height = Math.max(1, Math.round(image.height * scale));
      canvas.getContext("2d").drawImage(image, 0, 0, canvas.width, canvas.height);
      resolve(canvas.toDataURL("image/png"));
    };
    image.onerror = () => {
      URL.revokeObjectURL(url);
      reject(new Error(`Gambar ${file.name} tidak bisa dibaca (${file.type || "tipe tidak dikenal"}). Coba PNG atau JPG lain.`));
    };
    image.src = url;
  });
}

function bindBranding() {
  $("pickWatermark").addEventListener("click", () => $("watermarkFile").click());
  $("watermarkFile").addEventListener("change", async (event) => {
    const file = event.target.files?.[0];
    if (!file) return;
    if (!["image/png", "image/jpeg"].includes(file.type)) {
      toast("Gunakan PNG atau JPG", true);
      return;
    }
    const button = $("pickWatermark");
    setBusy(button, true, "Upload...");
    try {
      const dataUrl = await downscaleImage(file, 1200);
      const { path } = await api("/api/watermark", "POST", { name: file.name, data: dataUrl });
      $("watermark").value = path;
      watermarkPreview = dataUrl;
      updateBrandPreview();
      toast("Watermark diunggah. Klik Simpan untuk menyimpan setelan.");
    } catch (error) {
      toast(error.message, true);
    } finally {
      setBusy(button, false);
      event.target.value = "";
    }
  });
  $("clearWatermark").addEventListener("click", () => {
    $("watermark").value = "";
    watermarkPreview = "";
    updateBrandPreview();
  });
  $("watermark").addEventListener("input", () => {
    watermarkPreview = "";
    updateBrandPreview();
  });
  $("credit").addEventListener("input", updateBrandPreview);
  $("previewWatermark").addEventListener("error", () => $("previewWatermark").classList.add("hidden"));
}

async function init() {
  populateLanguages();
  buildPositionGrids();
  bindBranding();
  bindEvents();
  try {
    await loadState();
  } catch (error) {
    toast(`Gagal menghubungi server: ${error.message}`, true);
  }
  route();
}

document.addEventListener("DOMContentLoaded", init);
