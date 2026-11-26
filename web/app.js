let LANGS = [
  ["auto", "Auto / bahasa asli"],
  ["en", "English"],
  ["id", "Bahasa Indonesia"],
];

const BASE_URLS = {
  google: "https://generativelanguage.googleapis.com/v1beta/openai",
  openai: "https://api.openai.com/v1",
  groq: "https://api.groq.com/openai/v1",
  openrouter: "https://openrouter.ai/api/v1",
  local: "http://localhost:8000/v1",
};

let watermarkPreview = "";
let watermarkRev = 0;

const state = {
  config: null,
  cookies: null,
  assets: null,
  sessions: [],
  highlights: [],
  sessionId: null,
  selected: new Set(),
  overrides: {},
  jobTimer: null,
  activeJobId: null,
  busyJob: false,
  settingsDirty: false,
  currentView: "create",
  detail: null,
  toastTimer: null,
  autoOpenSessionId: null,
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
  const label = button.querySelector("span") || button;
  if (busy) {
    if (!button.dataset.label) button.dataset.label = label.textContent;
    label.textContent = text;
  } else {
    if (button.dataset.label) label.textContent = button.dataset.label;
    delete button.dataset.label;
  }
}

function populateLanguages() {
  const options = LANGS.map(([value, label]) => `<option value="${esc(value)}">${esc(label)}</option>`).join("");
  ["subtitleLanguage", "outputLanguage", "settingsOutputLanguage"].forEach((id) => {
    const select = $(id);
    if (!select) return;
    const prev = select.value;
    select.innerHTML = options;
    if (prev && [...select.options].some((opt) => opt.value === prev)) select.value = prev;
  });
}

function markSettingsDirty(dirty = true) {
  state.settingsDirty = Boolean(dirty);
  const btn = $("saveSettings");
  if (btn && !btn.disabled) {
    btn.textContent = state.settingsDirty ? "Simpan perubahan ●" : "Simpan";
  }
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
  $("apiKey").placeholder = config.ai?.keyUnreadable
    ? "Key lama tidak bisa dibaca di PC/user ini — masukkan ulang"
    : config.ai?.hasKey
      ? "Tersimpan aman — isi hanya untuk mengganti"
      : "Belum ada key — tempel API key di sini";
  if ($("clearApiKey")) $("clearApiKey").disabled = !config.ai?.hasKey;
  $("settingsOutputLanguage").value = config.outputLanguage || "auto";
  $("outputLanguage").value = config.outputLanguage || "auto";
  $("minSeconds").value = config.clip?.minSeconds ?? 20;
  $("maxSeconds").value = config.clip?.maxSeconds ?? 120;
  $("padding").value = config.clip?.padding ?? 0.25;
  $("portrait").checked = config.render?.portrait !== false;
  $("background").value = config.render?.background || "black";
  $("facecamCorner").value = config.render?.facecamCorner || "top-right";
  $("captions").checked = config.render?.captions !== false;
  $("captionColor").value = /^#[0-9a-f]{6}$/i.test(config.render?.captionColor || "")
    ? config.render.captionColor
    : "#ffd700";
  $("captionStyle").value = config.render?.captionStyle || "highlight";
  $("captionFont").value = config.render?.captionFont || "Arial Black";
  $("captionBold").checked = config.render?.captionBold !== false;
  $("captionUppercase").checked = Boolean(config.render?.captionUppercase);
  $("hook").checked = config.render?.hook !== false;
  $("hookSeconds").value = config.render?.hookSeconds ?? 3;
  $("hookStyle").value = config.render?.hookStyle || "classic";
  syncStylePickers();
  $("watermark").value = config.render?.watermark || "";
  $("credit").value = config.render?.credit || "";
  $("watermarkOpacity").value = Math.round((config.render?.watermarkOpacity ?? 0.9) * 100);
  $("creditOpacity").value = Math.round((config.render?.creditOpacity ?? 1) * 100);
  setGridValue("watermarkPosition", config.render?.watermarkPosition || "top-right");
  setGridValue("creditPosition", config.render?.creditPosition || "bottom-center");
  watermarkPreview = "";
  watermarkRev += 1;
  updateBrandPreview();
  $("ffmpegPath").value = config.paths?.ffmpeg || "";
  $("denoPath").value = config.paths?.deno || "";
  markSettingsDirty(false);
  updateAssetStatus();
  updateLivePreview();
}

function extractYoutubeId(raw) {
  const value = String(raw || "").trim();
  if (!value) return "";
  try {
    const parsed = new URL(value);
    const host = parsed.hostname.toLowerCase();
    let id = "";
    if (host === "youtu.be") id = parsed.pathname.split("/").filter(Boolean)[0] || "";
    else if (host === "youtube.com" || host.endsWith(".youtube.com")) {
      if (parsed.pathname === "/watch") id = parsed.searchParams.get("v") || "";
      else {
        const match = parsed.pathname.match(/^\/(?:shorts|live|embed)\/([A-Za-z0-9_-]{11})/);
        if (match) id = match[1];
      }
    }
    return /^[A-Za-z0-9_-]{11}$/.test(id) ? id : "";
  } catch {
    return "";
  }
}

function closeSampleEmbed() {
  const embed = $("previewEmbed");
  if (embed) {
    if (embed.getAttribute("src")) embed.src = "about:blank";
    embed.removeAttribute("src");
    embed.classList.add("hidden");
  }
  $("closeEmbedBtn")?.classList.add("hidden");
}

function openSampleEmbed(index) {
  const clip = state.highlights[index];
  if (!clip) return;
  const videoId = extractYoutubeId($("url")?.value) || extractYoutubeId(state.detail?.url);
  if (!videoId) {
    toast("URL YouTube tidak ditemukan untuk memutar sampel.", true);
    return;
  }
  const start = Math.max(0, Math.floor(Number(clip.start) || 0));
  const end = Math.max(start + 1, Math.ceil(Number(clip.end) || start + 1));
  const embed = $("previewEmbed");
  if (!embed) return;
  embed.src = `https://www.youtube-nocookie.com/embed/${encodeURIComponent(videoId)}?start=${start}&end=${end}&autoplay=1&rel=0`;
  embed.classList.remove("hidden");
  $("closeEmbedBtn")?.classList.remove("hidden");
  $("previewHook").textContent = clip.hook_text || clip.title || "Momen terbaik.";
  $("previewMeta").textContent = `AI PICK · ${fmtTime(clip.start)}–${fmtTime(clip.end)}`;
  $("previewPhone")?.scrollIntoView({ behavior: "smooth", block: "nearest" });
}

function updateLivePreview(overrideThumb) {
  const phone = $("previewPhone");
  if (!phone) return;
  const render = state.config?.render || {};
  const portrait = render.portrait !== false;
  const background = render.background || "black";
  const facecamCorner = render.facecamCorner || "top-right";
  const showCaptions = render.captions !== false;
  const showHook = render.hook !== false;
  const accent = /^#[0-9a-f]{6}$/i.test(render.captionColor || "") ? render.captionColor : "#FFD700";
  const style = render.captionStyle || "highlight";
  const hookStyle = render.hookStyle || "classic";
  const font = render.captionFont || "Arial Black";
  const bold = render.captionBold !== false;
  const upper = Boolean(render.captionUppercase);
  const isStacked = portrait && (background === "split" || background === "facecam-top");

  const videoId = extractYoutubeId($("url")?.value);
  const thumbUrl = overrideThumb || (videoId ? `https://i.ytimg.com/vi/${videoId}/hqdefault.jpg` : "");
  const thumb = $("previewThumb");
  const thumbTop = $("previewThumbTop");
  const bg = $("previewBg");
  if (thumbUrl) {
    if (thumb.getAttribute("src") !== thumbUrl) thumb.src = thumbUrl;
    thumb.classList.remove("hidden");
    phone.classList.add("has-thumb");
    if (thumbTop) {
      if (isStacked) {
        if (thumbTop.getAttribute("src") !== thumbUrl) thumbTop.src = thumbUrl;
        thumbTop.classList.remove("hidden");
      } else {
        thumbTop.removeAttribute("src");
        thumbTop.classList.add("hidden");
      }
    }
    if (portrait && background === "blurred") {
      if (bg.getAttribute("src") !== thumbUrl) bg.src = thumbUrl;
      bg.classList.remove("hidden");
    } else {
      bg.classList.add("hidden");
    }
  } else {
    thumb.removeAttribute("src");
    thumb.classList.add("hidden");
    if (thumbTop) {
      thumbTop.removeAttribute("src");
      thumbTop.classList.add("hidden");
    }
    bg.removeAttribute("src");
    bg.classList.add("hidden");
    phone.classList.remove("has-thumb");
  }

  phone.classList.toggle("is-landscape", !portrait);
  phone.dataset.mode = portrait ? background : "landscape";
  phone.dataset.facecam = facecamCorner;
  phone.classList.toggle("has-retro-hook", showHook && hookStyle === "retro-card");
  phone.style.setProperty("--preview-accent", accent);
  phone.style.setProperty("--preview-font", style === "gadzhi" && font === "Arial Black" ? "Arial" : font);
  phone.style.setProperty("--preview-weight", style === "gadzhi" ? "400" : bold ? "800" : "400");
  phone.style.setProperty("--preview-transform", upper ? "uppercase" : "none");

  $("previewRatio").textContent = portrait ? "9:16" : "16:9";
  $("previewFormat").textContent = portrait ? "● 9:16" : "● 16:9";
  if ($("statFormat")) $("statFormat").textContent = portrait ? "9:16" : "16:9";
  if ($("brandPreviewFrame")) $("brandPreviewFrame").textContent = portrait ? "PREVIEW 9:16" : "PREVIEW 16:9";
  $("previewStyleTag").textContent = style;
  const hookNode = $("previewHook");
  hookNode.className = `phone-hook hook-${hookStyle}${showHook ? "" : " hidden"}`;
  $("previewCaptionsWrap").classList.toggle("hidden", !showCaptions);
  $("previewCaptionAlt").classList.toggle("hidden", style !== "bilingual");
  $("previewCaptions").className = `phone-captions style-${style}`;
  const note = $("previewCaptionNote");
  if (note) {
    const dims = portrait ? "1080 × 1920" : "1920 × 1080";
    const bgLabel = portrait ? (BG_LABELS[background] || "latar hitam") : "layar penuh";
    const caseLabel = upper && bold ? " KAPITAL tebal" : upper ? " KAPITAL" : bold ? " tebal" : "";
    note.textContent = thumbUrl
      ? `Preview ${dims} (${bgLabel}) · gaya ${style} · font ${font}${caseLabel}.`
      : "Tempel URL YouTube untuk melihat preview thumbnail, hook, dan gaya subtitle dari Pengaturan.";
  }
}

function applyVersion(version) {
  if (!version) return;
  document.querySelectorAll("[data-version]").forEach((node) => { node.textContent = version; });
  document.querySelectorAll("[data-version-tag]").forEach((node) => { node.textContent = `v${version}`; });
  document.querySelectorAll("[data-release-link]").forEach((node) => {
    node.href = `https://github.com/nuellpr/AIKLIPYT/releases/tag/v${version}`;
    node.textContent = `Rilis v${version}`;
  });
}

function setPipeStep(doneCount) {
  [1, 2, 3].forEach((step) => {
    const node = $(`pipeStep${step}`);
    if (node) node.classList.toggle("is-done", step <= doneCount);
  });
}

async function loadState() {
  const data = await api("/api/state");
  if (Array.isArray(data.languages) && data.languages.length) {
    LANGS = data.languages;
    populateLanguages();
  }
  state.config = data.config;
  state.cookies = data.cookies;
  state.assets = data.assets;
  applyVersion(data.version);
  applySettings();
  updateCookieStatus();
  if (data.activeJob) resumeActiveJob(data.activeJob);
}

function route() {
  const requested = (location.hash || "#create").slice(1);
  const view = ["create", "library", "settings", "about"].includes(requested) ? requested : "create";
  if (state.currentView === "settings" && view !== "settings" && state.settingsDirty) {
    const oldBase = (state.config?.ai?.baseUrl || "").trim().replace(/\/+$/, "");
    const newBase = $("baseUrl").value.trim().replace(/\/+$/, "");
    const customEmpty = $("model").value === "__custom__" && !selectedModel();
    if (!customEmpty && (newBase === oldBase || Boolean($("apiKey").value.trim()))) {
      saveSettings({ silent: true });
    } else {
      toast("Klik Simpan di Pengaturan untuk menerapkan Base URL atau model baru.", true);
    }
  }
  if (view === "settings" && !state.settingsDirty && state.config) {
    applySettings();
  }
  if (view !== "create") {
    closeSampleEmbed();
  }
  state.currentView = view;
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
  $("cancelJobBtn")?.classList.remove("hidden");
}

function updateJob(job) {
  $("jobMessage").textContent = job.message || "";
  const percent = Math.max(0, Math.min(100, Number(job.progress) || 0));
  $("jobProgress").style.width = `${percent}%`;
  $("jobPercent").textContent = `${Math.round(percent)}%`;
  $("jobLog").textContent = (job.log || []).join("\n");
  $("jobState").textContent =
    job.status === "running"
      ? "jalan"
      : job.status === "done"
        ? "selesai"
        : job.status === "cancelled"
          ? "dibatalkan"
          : "gagal";
  $("cancelJobBtn")?.classList.toggle("hidden", job.status !== "running");
  if (job.error) {
    const node = $("jobError");
    node.textContent = job.error;
    node.classList.remove("hidden");
  }
}

function pollJob(jobId, onDone, onFail) {
  clearTimeout(state.jobTimer);
  state.jobTimer = null;
  state.activeJobId = jobId;
  $("cancelJobBtn")?.classList.remove("hidden");
  let finished = false;
  const tick = async () => {
    if (finished) return;
    try {
      const { job } = await api(`/api/jobs/${jobId}`);
      updateJob(job);
      if (job.kind === "highlights") {
        setPipeStep(job.status === "done" ? 2 : Number(job.progress) >= 30 ? 1 : 0);
      } else if (job.kind === "render") {
        setPipeStep(job.status === "done" ? 3 : 2);
      }
      if (job.status !== "running") {
        finished = true;
        state.jobTimer = null;
        state.activeJobId = null;
        $("cancelJobBtn")?.classList.add("hidden");
        if (job.status === "done") onDone(job);
        else {
          if (job.status === "cancelled") toast("Proses dibatalkan");
          else toast(job.error || "Proses gagal", true);
          if (onFail) onFail(job);
        }
        return;
      }
      state.jobTimer = setTimeout(tick, 1200);
    } catch (error) {
      finished = true;
      state.jobTimer = null;
      state.activeJobId = null;
      $("cancelJobBtn")?.classList.add("hidden");
      toast(error.message, true);
      if (onFail) onFail();
    }
  };
  tick();
}

async function cancelActiveJob() {
  if (!state.activeJobId) return;
  const button = $("cancelJobBtn");
  setBusy(button, true, "Batal…");
  try {
    const { job } = await api("/api/jobs/cancel", "POST", { jobId: state.activeJobId });
    updateJob(job);
  } catch (error) {
    toast(error.message, true);
  } finally {
    setBusy(button, false);
  }
}

function applyHighlightResult(job, fallbackRequested = 0) {
  state.busyJob = false;
  setBusy($("findBtn"), false);
  state.sessionId = job.result.sessionId;
  state.highlights = job.result.highlights || [];
  state.overrides = {};
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
  const wanted = Number(job.result?.requested) || fallbackRequested || state.highlights.length;
  const short = state.highlights.length < wanted;
  toast(
    short
      ? `AI hanya menemukan ${state.highlights.length} dari ${wanted} momen`
      : `${state.highlights.length} highlight — ${state.selected.size} direkomendasikan untuk dirender`,
    short,
  );
}

function finishRender(job) {
  const errors = job.result?.errors || [];
  toast(errors.length ? `Selesai dengan ${errors.length} error` : "Klip selesai dirender", errors.length > 0);
  state.busyJob = false;
  setBusy($("renderBtn"), false);
  state.selected = new Set();
  if (state.highlights.length) renderHighlights();
  const sid = job.result?.sessionId;
  state.autoOpenSessionId = sid || null;
  if (location.hash === "#library") {
    loadSessions().catch((error) => toast(error.message, true));
  } else {
    location.hash = "#library";
  }
}

function resumeActiveJob(job) {
  if (!job || state.busyJob) return;
  state.busyJob = true;
  const isRender = job.kind === "render";
  showJob(isRender ? "Merender klip" : "Mencari highlight");
  updateJob(job);
  if (isRender) {
    setBusy($("renderBtn"), true, "Merender…");
    pollJob(job.id, finishRender, () => {
      state.busyJob = false;
      setBusy($("renderBtn"), false);
    });
  } else {
    setBusy($("findBtn"), true, "Mencari…");
    pollJob(job.id, (doneJob) => applyHighlightResult(doneJob), () => {
      state.busyJob = false;
      setBusy($("findBtn"), false);
    });
  }
}

async function findHighlights() {
  if (state.busyJob) {
    toast("Ada proses yang masih berjalan.", true);
    return;
  }
  const url = $("url").value.trim();
  if (!/^https?:\/\//i.test(url)) {
    toast("Tempel URL YouTube yang valid", true);
    return;
  }
  const button = $("findBtn");
  closeSampleEmbed();
  setBusy(button, true, "Mencari…");
  state.busyJob = true;
  $("resultsPanel").classList.add("hidden");
  state.highlights = [];
  state.selected = new Set();
  state.overrides = {};
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
    pollJob(jobId, (job) => applyHighlightResult(job, requested), () => {
      state.busyJob = false;
      setBusy(button, false);
    });
  } catch (error) {
    state.busyJob = false;
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
        <div class="highlight ${active ? "" : "is-off"}" data-index="${index}">
          <input type="checkbox" data-index="${index}" ${active ? "checked" : ""} aria-label="Pilih klip ${index + 1}">
          <div>
            <h3><span class="rank">#${position + 1}</span> ${esc(clip.title || `Klip ${index + 1}`)}</h3>
            <div class="hl-meta-row">
              <div class="meta" data-meta-index="${index}">
                <span>${fmtTime(clip.start)} – ${fmtTime(clip.end)}</span>
                <span>${Math.round(clip.duration || 0)} detik</span>
                <span>klip ${index + 1}</span>
              </div>
              <button type="button" class="btn ghost small hl-sample-btn" data-preview-clip="${index}">▶ Putar sampel</button>
            </div>
            ${clip.description ? `<p class="desc">${esc(clip.description)}</p>` : ""}
            ${dims ? `<p class="score-breakdown">${dims}</p>` : ""}
            ${clip.score_reason ? `<p class="score-reason">${esc(clip.score_reason)}</p>` : ""}
            <div class="hl-edit">
              <label><span>Mulai (dtk)</span><input type="number" step="0.1" min="0" data-edit="start" data-index="${index}" value="${Number(clip.start ?? 0)}"></label>
              <label><span>Selesai (dtk)</span><input type="number" step="0.1" min="1" data-edit="end" data-index="${index}" value="${Number(clip.end ?? 0)}"></label>
              <label class="hl-edit-wide"><span>Hook pembuka</span><input type="text" maxlength="120" data-edit="hook_text" data-index="${index}" value="${esc(clip.hook_text || "")}" placeholder="Teks hook di awal klip…"></label>
            </div>
          </div>
          <div class="score ${grade.cls}">${score.toFixed(1)}<small>${grade.label}</small></div>
        </div>`;
    })
    .join("");
  updateRenderButton();
}

function updateRenderButton() {
  const count = state.selected.size;
  const button = $("renderBtn");
  const all = state.highlights.length > 0 && count === state.highlights.length;
  $("selectAll").textContent = all ? "Batalkan semua" : "Pilih semua";
  if (state.busyJob) return;
  button.textContent = count ? `Render ${count} klip` : "Pilih klip";
  button.disabled = count === 0;
}

async function renderSelected() {
  if (state.busyJob) {
    toast("Ada proses yang masih berjalan.", true);
    return;
  }
  if (!state.sessionId || state.selected.size === 0) return;
  closeSampleEmbed();
  const button = $("renderBtn");
  setBusy(button, true, "Merender…");
  state.busyJob = true;
  showJob("Merender klip");
  try {
    const { jobId } = await api("/api/render", "POST", {
      sessionId: state.sessionId,
      indices: [...state.selected].sort((a, b) => a - b),
      overwrite: true,
      overrides: state.overrides,
    });
    pollJob(jobId, finishRender, () => {
      state.busyJob = false;
      setBusy(button, false);
    });
  } catch (error) {
    state.busyJob = false;
    setBusy(button, false);
    toast(error.message, true);
  }
}

async function loadSessions() {
  const { sessions } = await api("/api/sessions");
  state.sessions = sessions;
  renderLibrary();
  const pendingId = state.autoOpenSessionId;
  if (pendingId) {
    state.autoOpenSessionId = null;
    await openSession(pendingId);
  }
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
        ? `<img class="thumb" src="${esc(session.thumbnail)}" alt="" loading="lazy">`
        : `<div class="thumb-fallback">▦</div>`;
      return `
        <article class="session-card" data-id="${esc(session.id)}">
          ${thumb}
          <div>
            <h3>${esc(session.title || "Tanpa judul")}</h3>
            <div class="meta">
              <span>${esc(session.channel || "—")}</span>
              <span>${fmtDate(session.createdAt)}</span>
              <span>${esc(session.clipCount)} klip</span>
              <span>${esc(session.highlightCount)} highlight</span>
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
        (clip, idx) => `
        <article class="clip-card">
          <video controls preload="metadata" src="/api/media/${encodeURIComponent(sessionId)}/${encodeURIComponent(clip.file)}"></video>
          <div class="clip-info">
            <h4>${esc(clip.title || clip.file)}</h4>
            <div class="meta">${fmtTime(clip.start)} → ${fmtTime(clip.end)} · ${Math.round(clip.duration || 0)} dtk</div>
            ${clip.description ? `<p class="clip-desc">${esc(clip.description)}</p>` : ""}
            <div class="clip-actions">
              <button type="button" class="btn ghost small" data-copy-clip="${idx}">Salin caption</button>
              <a class="btn ghost small" href="/api/media/${encodeURIComponent(sessionId)}/${encodeURIComponent(clip.file)}" download="${esc(clip.file)}">Unduh MP4</a>
            </div>
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

async function saveSettings({ silent = false } = {}) {
  const button = $("saveSettings");
  const model = selectedModel();
  if ($("model").value === "__custom__" && !model) {
    if (!silent) {
      toast("Isi nama model custom dulu", true);
      $("modelCustom").focus();
    }
    return;
  }
  const hadKey = Boolean(state.config?.ai?.hasKey);
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
        facecamCorner: $("facecamCorner").value,
        captions: $("captions").checked,
        captionColor: $("captionColor").value,
        captionStyle: $("captionStyle").value,
        captionFont: $("captionFont").value,
        captionBold: $("captionBold").checked,
        captionUppercase: $("captionUppercase").checked,
        hook: $("hook").checked,
        hookSeconds: Number($("hookSeconds").value),
        hookStyle: $("hookStyle").value,
        watermark: $("watermark").value.trim(),
        watermarkPosition: $("watermarkPosition").dataset.position || "top-right",
        credit: $("credit").value.trim(),
        creditPosition: $("creditPosition").dataset.position || "bottom-center",
        watermarkOpacity: Number($("watermarkOpacity").value) / 100,
        creditOpacity: Number($("creditOpacity").value) / 100,
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
    if (!silent) {
      toast(
        hadKey && !key && !data.config?.ai?.hasKey
          ? "Pengaturan disimpan — isi API key baru untuk Base URL ini"
          : "Pengaturan disimpan",
      );
    }
  } catch (error) {
    toast(error.message, true);
  } finally {
    setBusy(button, false);
    markSettingsDirty(state.settingsDirty);
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
    }
    $("cookieEditor").classList.remove("hidden");
    $("cookieEditor").scrollIntoView({ behavior: "smooth", block: "center" });
  });
  $("url").addEventListener("input", () => {
    closeSampleEmbed();
    updateLivePreview();
  });
  $("closeEmbedBtn")?.addEventListener("click", closeSampleEmbed);
  $("previewThumb").addEventListener("error", () => {
    $("previewThumb").classList.add("hidden");
    $("previewThumbTop")?.classList.add("hidden");
    $("previewBg").classList.add("hidden");
    $("previewPhone").classList.remove("has-thumb");
  });
  $("highlightList").addEventListener("mouseover", (event) => {
    const card = event.target.closest(".highlight[data-index]");
    if (!card) return;
    const clip = state.highlights[Number(card.dataset.index)];
    if (!clip) return;
    $("previewHook").textContent = clip.hook_text || clip.title || "Momen terbaik.";
    $("previewMeta").textContent = `AI PICK · ${fmtTime(clip.start)}–${fmtTime(clip.end)}`;
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

  $("highlightList").addEventListener("click", (event) => {
    const previewBtn = event.target.closest("[data-preview-clip]");
    if (previewBtn) {
      openSampleEmbed(Number(previewBtn.dataset.previewClip));
      return;
    }
    if (event.target.closest("input, button, a, label")) return;
    const card = event.target.closest(".highlight[data-index]");
    const checkbox = card?.querySelector('input[type="checkbox"]');
    if (!checkbox) return;
    checkbox.checked = !checkbox.checked;
    checkbox.dispatchEvent(new Event("change", { bubbles: true }));
  });

  $("highlightList").addEventListener("input", (event) => {
    const field = event.target.dataset?.edit;
    if (!field) return;
    const idx = Number(event.target.dataset.index);
    const clip = state.highlights[idx];
    if (!clip) return;
    const patch = state.overrides[idx] || {};
    if (field === "hook_text") {
      clip.hook_text = event.target.value;
      patch.hook_text = event.target.value;
      $("previewHook").textContent = clip.hook_text || clip.title || "Momen terbaik.";
    } else if (field === "start" || field === "end") {
      const val = Number(event.target.value);
      if (Number.isFinite(val) && val >= 0) {
        clip[field] = val;
        patch[field] = val;
        if (clip.end > clip.start) clip.duration = Math.round((clip.end - clip.start) * 100) / 100;
        const meta = document.querySelector(`[data-meta-index="${idx}"]`);
        if (meta) {
          meta.innerHTML = `<span>${fmtTime(clip.start)} – ${fmtTime(clip.end)}</span><span>${Math.round(clip.duration || 0)} detik</span><span>klip ${idx + 1}</span>`;
        }
        $("previewMeta").textContent = `AI PICK · ${fmtTime(clip.start)}–${fmtTime(clip.end)}`;
      }
    }
    state.overrides[idx] = patch;
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
  $("libraryList").addEventListener(
    "error",
    (event) => {
      const img = event.target;
      if (!(img instanceof HTMLImageElement) || !img.classList.contains("thumb")) return;
      const fallback = document.createElement("div");
      fallback.className = "thumb-fallback";
      fallback.textContent = "▦";
      img.replaceWith(fallback);
    },
    true,
  );
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
  $("loadToCreate").addEventListener("click", () => {
    const session = state.detail;
    if (!session || !session.highlights?.length) {
      toast("Sesi ini belum punya daftar highlight.", true);
      return;
    }
    state.sessionId = session.id;
    state.highlights = session.highlights;
    state.overrides = {};
    if (session.url) $("url").value = session.url;
    const rendered = new Set((session.clips || []).map((clip) => Number(clip.index)));
    const remaining = state.highlights.map((_, index) => index).filter((index) => !rendered.has(index));
    state.selected = new Set(remaining.length ? remaining : state.highlights.map((_, index) => index));
    renderHighlights();
    updateLivePreview(session.thumbnail);
    setPipeStep(rendered.size ? 3 : 2);
    $("resultsPanel").classList.remove("hidden");
    location.hash = "#create";
    $("resultsPanel").scrollIntoView({ behavior: "smooth", block: "start" });
  });
  $("openOutput").addEventListener("click", () => {
    if (state.detail) api("/api/open", "POST", { sessionId: state.detail.id, kind: "output" }).catch((error) => toast(error.message, true));
  });
  $("deleteSession").addEventListener("click", () => {
    if (state.detail) removeSession(state.detail.id);
  });

  $("clipGrid").addEventListener("click", async (event) => {
    const copyBtn = event.target.closest("[data-copy-clip]");
    if (!copyBtn) return;
    const clip = state.detail?.clips?.[Number(copyBtn.dataset.copyClip)];
    if (!clip) return;
    const text = [clip.title, clip.description].filter(Boolean).join("\n\n");
    try {
      await navigator.clipboard.writeText(text || clip.file || "");
      toast("Judul & deskripsi disalin");
    } catch {
      toast("Gagal menyalin ke clipboard", true);
    }
  });
  $("cancelJobBtn")?.addEventListener("click", cancelActiveJob);
  $("saveSettings").addEventListener("click", () => saveSettings());
  $("settingsForm")?.addEventListener("input", () => markSettingsDirty(true));
  $("settingsForm")?.addEventListener("change", () => markSettingsDirty(true));
  $("clearApiKey")?.addEventListener("click", async () => {
    if (!confirm("Hapus API key tersimpan?")) return;
    try {
      const data = await api("/api/settings", "POST", { ai: { apiKey: "" } });
      state.config = data.config;
      applySettings();
      toast("API key dihapus");
    } catch (error) {
      toast(error.message, true);
    }
  });
  $("refreshModels").addEventListener("click", refreshModels);
  $("model").addEventListener("change", toggleCustomModel);
  $("baseUrl").addEventListener("input", syncBaseUrlPreset);
  $("baseUrlPreset").addEventListener("change", () => {
    const url = BASE_URLS[$("baseUrlPreset").value];
    if (url) $("baseUrl").value = url;
    else $("baseUrl").focus();
    markSettingsDirty(true);
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
      button.addEventListener("click", () => {
        setGridValue(id, value);
        markSettingsDirty(true);
      });
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
  const saved = state.config?.render?.watermark || "";
  const src = watermarkPreview || (path && path === saved ? `/api/watermark?v=${watermarkRev}` : "");
  const image = $("previewWatermark");
  if (path && src) {
    if (image.getAttribute("src") !== src) image.src = src;
    image.classList.remove("hidden");
  } else {
    image.removeAttribute("src");
    image.classList.add("hidden");
  }
  image.style.opacity = Number($("watermarkOpacity").value) / 100;
  $("watermarkOpacityValue").textContent = `${$("watermarkOpacity").value}%`;
  previewPos(image, $("watermarkPosition").dataset.position);
  const credit = $("credit").value.trim();
  const label = $("previewCredit");
  label.textContent = credit || "@channel";
  label.style.opacity = Number($("creditOpacity").value) / 100;
  $("creditOpacityValue").textContent = `${$("creditOpacity").value}%`;
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
      const mime = file.type === "image/jpeg" ? "image/jpeg" : "image/png";
      resolve(canvas.toDataURL(mime, 0.92));
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
      markSettingsDirty(true);
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
    markSettingsDirty(true);
    updateBrandPreview();
  });
  $("watermark").addEventListener("input", () => {
    watermarkPreview = "";
    updateBrandPreview();
  });
  $("credit").addEventListener("input", updateBrandPreview);
  for (const id of ["watermarkOpacity", "creditOpacity"]) {
    $(id).addEventListener("input", updateBrandPreview);
  }
  $("previewWatermark").addEventListener("error", () => $("previewWatermark").classList.add("hidden"));
}

const CAPTION_CARDS = [
  ["highlight", "Highlight kata", "Default"],
  ["hormozi", "Hormozi", "Populer"],
  ["karaoke", "Karaoke", ""],
  ["mrbeast", "MrBeast", ""],
  ["bilingual", "Bilingual (2 bahasa)", "AI"],
  ["box", "Kotak tebal", ""],
  ["pop", "Pop membesar", ""],
  ["smart-bg-focus", "Smart BG focus", ""],
  ["box-highlight", "Box 1 kata", ""],
  ["word-focus", "Word focus", ""],
  ["underline-focus", "Underline focus", ""],
  ["outline-focus", "Outline focus", ""],
  ["temp-0", "temp-0", ""],
  ["gadzhi", "Gadzhi", ""],
];

const BG_LABELS = {
  black: "latar hitam",
  blurred: "latar blur",
  fill: "layar penuh",
  split: "split podcast",
  "crop-left": "crop kiri",
  "crop-right": "crop kanan",
  "facecam-top": "facecam atas",
  cinema: "zoom 4:5",
};

const BACKGROUND_CARDS = [
  ["black", "Hitam", "", "Video 16:9 + bar hitam"],
  ["blurred", "Blur", "", "Video 16:9 + latar blur"],
  ["fill", "Layar Penuh", "", "Auto fokus wajah 9:16"],
  ["split", "Split Podcast", "Baru", "Atas kiri · bawah kanan"],
  ["crop-left", "Crop Kiri", "Baru", "Fokus sisi kiri 9:16"],
  ["crop-right", "Crop Kanan", "Baru", "Fokus sisi kanan 9:16"],
  ["facecam-top", "Gaming / Reaction", "Baru", "Facecam atas · layar bawah"],
  ["cinema", "Zoom 4:5", "Baru", "4:5 tengah + ruang hook"],
];

const HOOK_CARDS = [
  ["classic", "Klasik", "Default"],
  ["card", "Kartu", "Populer"],
  ["quote", "Kutipan", ""],
  ["accent-bar", "Bar Aksen", "Populer"],
  ["cinema", "Sinema", ""],
  ["neon", "Neon Glow", "Baru"],
  ["breaking", "Breaking News", "Baru"],
  ["impact", "Impact Slam", "Populer"],
  ["tape", "Stiker Miring", "Baru"],
  ["spotlight", "Sorot", "Baru"],
  ["retro-card", "Kartu Retro", "Baru"],
];

function captionSampleHtml(style) {
  if (style === "karaoke") {
    return `<div class="sc-sub sc-karaoke"><span class="sc-karaoke-text">satu kalimat penuh</span><span class="sc-karaoke-bar"><i></i></span></div>`;
  }
  if (style === "box-highlight") {
    return `<div class="sc-sub sc-box-highlight"><span class="w">RASA</span></div>`;
  }
  if (style === "bilingual") {
    return `<div class="sc-sub sc-bilingual"><span class="sc-bi-top">we all feel the same</span><span class="sc-bi-bot"><span class="w w1">kita</span><span class="w w2">punya</span><span class="w w3">rasa</span></span></div>`;
  }
  return `<div class="sc-sub sc-${style}"><span class="w w1">kita</span><span class="w w2">punya</span><span class="w w3">rasa</span></div>`;
}

function hookSampleHtml(style) {
  if (style === "card") return `<div class="sc-hook hk-card">Ternyata dia<br>nolak 1 miliar</div>`;
  if (style === "quote") return `<div class="sc-hook hk-quote"><i>“</i><span>Ternyata dia</span><span>nolak 1 miliar</span></div>`;
  if (style === "accent-bar") return `<div class="sc-hook hk-accent-bar"><b>Ternyata dia</b><span>nolak 1 miliar</span></div>`;
  if (style === "cinema") return `<div class="sc-hook hk-cinema">Ternyata dia<br>nolak 1 miliar</div>`;
  if (style === "neon") return `<div class="sc-hook hk-neon">Ternyata dia<br>nolak 1 miliar</div>`;
  if (style === "breaking") return `<div class="sc-hook hk-breaking"><i>● BREAKING</i><span>Nolak 1 Miliar</span></div>`;
  if (style === "impact") return `<div class="sc-hook hk-impact">NOLAK<br>1 MILIAR!</div>`;
  if (style === "tape") return `<div class="sc-hook hk-tape">Ternyata dia<br>nolak 1 miliar</div>`;
  if (style === "spotlight") return `<div class="sc-hook hk-spotlight"><em>1 MILIAR</em><br>DITOLAK MENTAH</div>`;
  if (style === "retro-card") return `<div class="sc-hook hk-retro-card">inilah satu-satunya<br>kelebihan dia</div>`;
  return `<div class="sc-hook hk-classic">Ternyata dia<br>nolak 1 miliar</div>`;
}

function captionCaseMode() {
  const bold = Boolean($("captionBold")?.checked);
  const upper = Boolean($("captionUppercase")?.checked);
  if (upper && bold) return "upper-bold";
  if (upper) return "upper";
  if (bold) return "bold";
  return "normal";
}

function setCaptionCaseMode(mode) {
  if ($("captionBold")) $("captionBold").checked = mode === "bold" || mode === "upper-bold";
  if ($("captionUppercase")) $("captionUppercase").checked = mode === "upper" || mode === "upper-bold";
}

function syncStylePickers() {
  const accent = /^#[0-9a-f]{6}$/i.test($("captionColor")?.value || "") ? $("captionColor").value : "#FFD700";
  const font = $("captionFont")?.value || "Arial Black";
  const bold = Boolean($("captionBold")?.checked);
  const upper = Boolean($("captionUppercase")?.checked);
  const weight = bold ? "800" : "400";

  const bgPicker = $("backgroundPicker");
  if (bgPicker) {
    bgPicker.classList.toggle("is-off", !$("portrait")?.checked);
    const activeBg = $("background")?.value || "black";
    for (const card of bgPicker.querySelectorAll(".mode-card")) {
      const selected = card.dataset.value === activeBg;
      card.classList.toggle("is-selected", selected);
      card.setAttribute("aria-checked", String(selected));
    }
    const facecamRow = $("facecamCornerRow");
    if (facecamRow) {
      facecamRow.classList.toggle("hidden", activeBg !== "facecam-top");
      const activeCorner = $("facecamCorner")?.value || "top-right";
      for (const btn of facecamRow.querySelectorAll(".seg-btn")) {
        const selected = btn.dataset.corner === activeCorner;
        btn.classList.toggle("is-selected", selected);
        btn.setAttribute("aria-checked", String(selected));
      }
    }
  }

  const caseGroup = $("captionCaseGroup");
  if (caseGroup) {
    const activeMode = captionCaseMode();
    for (const btn of caseGroup.querySelectorAll(".seg-btn")) {
      const selected = btn.dataset.mode === activeMode;
      btn.classList.toggle("is-selected", selected);
      btn.setAttribute("aria-checked", String(selected));
    }
  }

  const subPicker = $("subtitlePicker");
  const hookPicker = $("hookPicker");
  if (subPicker) {
    subPicker.style.setProperty("--picker-accent", accent);
    subPicker.style.setProperty("--picker-font", font);
    subPicker.style.setProperty("--picker-weight", weight);
    subPicker.style.setProperty("--picker-transform", upper ? "uppercase" : "none");
    subPicker.classList.toggle("is-off", !$("captions").checked);
    const active = $("captionStyle").value || "highlight";
    const strip = $("captionStyleStrip");
    for (const card of subPicker.querySelectorAll(".style-card")) {
      const selected = card.dataset.value === active;
      card.classList.toggle("is-selected", selected);
      card.setAttribute("aria-checked", String(selected));
      if (selected && strip && strip.clientWidth > 0) {
        const left = card.offsetLeft;
        if (left < strip.scrollLeft || left + card.offsetWidth > strip.scrollLeft + strip.clientWidth) {
          strip.scrollLeft = Math.max(0, left - 24);
        }
      }
    }
  }
  if (hookPicker) {
    hookPicker.style.setProperty("--picker-accent", accent);
    hookPicker.classList.toggle("is-off", !$("hook").checked);
    const active = $("hookStyle").value || "classic";
    for (const card of hookPicker.querySelectorAll(".style-card")) {
      const selected = card.dataset.value === active;
      card.classList.toggle("is-selected", selected);
      card.setAttribute("aria-checked", String(selected));
    }
  }
}

function buildStylePickers() {
  const bgStrip = $("backgroundStrip");
  if (bgStrip) {
    bgStrip.innerHTML = BACKGROUND_CARDS.map(([value, label, badge, desc]) => `
      <button type="button" class="mode-card" role="radio" aria-checked="false" data-value="${value}">
        <span class="mode-card-top">
          <strong>${label}</strong>
          ${badge ? `<span class="style-card-badge">${badge}</span>` : ""}
        </span>
        <span class="mode-stage"><span class="mode-mini-phone mode-${value}"></span></span>
        <span class="mode-desc">${desc}</span>
      </button>`).join("");
    bgStrip.addEventListener("click", (event) => {
      const card = event.target.closest(".mode-card");
      if (!card) return;
      $("background").value = card.dataset.value;
      markSettingsDirty(true);
      syncStylePickers();
    });
  }
  const facecamGroup = $("facecamCornerGroup");
  if (facecamGroup) {
    facecamGroup.addEventListener("click", (event) => {
      const btn = event.target.closest(".seg-btn");
      if (!btn) return;
      $("facecamCorner").value = btn.dataset.corner;
      markSettingsDirty(true);
      syncStylePickers();
    });
  }
  const caseGroup = $("captionCaseGroup");
  if (caseGroup) {
    caseGroup.addEventListener("click", (event) => {
      const btn = event.target.closest(".seg-btn");
      if (!btn) return;
      setCaptionCaseMode(btn.dataset.mode);
      markSettingsDirty(true);
      syncStylePickers();
    });
  }
  const subStrip = $("captionStyleStrip");
  if (subStrip) {
    subStrip.innerHTML = CAPTION_CARDS.map(([value, label, badge]) => `
      <button type="button" class="style-card" role="radio" aria-checked="false" data-value="${value}">
        <span class="style-card-box">${badge ? `<span class="style-card-badge">${badge}</span>` : ""}${captionSampleHtml(value)}</span>
        <span class="style-card-label">${label}</span>
      </button>`).join("");
    subStrip.addEventListener("click", (event) => {
      const card = event.target.closest(".style-card");
      if (!card) return;
      $("captionStyle").value = card.dataset.value;
      markSettingsDirty(true);
      syncStylePickers();
    });
  }
  const hookStrip = $("hookStyleStrip");
  if (hookStrip) {
    hookStrip.innerHTML = HOOK_CARDS.map(([value, label, badge]) => `
      <button type="button" class="style-card" role="radio" aria-checked="false" data-value="${value}">
        <span class="style-card-box">${badge ? `<span class="style-card-badge">${badge}</span>` : ""}${hookSampleHtml(value)}</span>
        <span class="style-card-label">${label}</span>
      </button>`).join("");
    hookStrip.addEventListener("click", (event) => {
      const card = event.target.closest(".style-card");
      if (!card) return;
      $("hookStyle").value = card.dataset.value;
      markSettingsDirty(true);
      syncStylePickers();
    });
  }
  document.querySelectorAll(".carousel-arrow").forEach((btn) => {
    btn.addEventListener("click", () => {
      const strip = $(btn.dataset.scroll);
      if (strip) strip.scrollBy({ left: Number(btn.dataset.dir) * 360, behavior: "smooth" });
    });
  });
  $("toggleCaptionTuning")?.addEventListener("click", () => $("captionTuning").classList.toggle("hidden"));
  $("toggleHookTuning")?.addEventListener("click", () => $("hookTuning").classList.toggle("hidden"));
  for (const id of ["portrait", "captions", "hook", "captionColor", "captionFont", "captionBold", "captionUppercase"]) {
    $(id)?.addEventListener("input", syncStylePickers);
    $(id)?.addEventListener("change", syncStylePickers);
  }
  syncStylePickers();
}

function startPhonePreviewLoop() {
  const words = [...document.querySelectorAll("#previewCaptions span")];
  if (!words.length) return;
  let step = 1;
  setInterval(() => {
    step = (step + 1) % words.length;
    words.forEach((node, idx) => node.classList.toggle("active", idx === step));
  }, 750);
}

async function init() {
  populateLanguages();
  buildStylePickers();
  startPhonePreviewLoop();
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
