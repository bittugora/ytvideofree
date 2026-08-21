const state = {
  mode: "video",
  info: null,
  transcript: null,
};

const elements = {
  form: document.querySelector("#lookup-form"),
  url: document.querySelector("#youtube-url"),
  pasteButton: document.querySelector("#paste-button"),
  status: document.querySelector("#status-pill"),
  message: document.querySelector("#message-area"),
  empty: document.querySelector("#empty-state"),
  videoResult: document.querySelector("#video-result"),
  transcriptResult: document.querySelector("#transcript-result"),
  thumbnail: document.querySelector("#thumbnail"),
  title: document.querySelector("#video-title"),
  channel: document.querySelector("#channel-name"),
  duration: document.querySelector("#duration-label"),
  uploadDate: document.querySelector("#upload-date"),
  views: document.querySelector("#view-count"),
  videoQuality: document.querySelector("#video-quality"),
  audioQuality: document.querySelector("#audio-quality"),
  languageList: document.querySelector("#language-list"),
  translateTo: document.querySelector("#translate-to"),
  transcriptText: document.querySelector("#transcript-text"),
  transcriptLanguage: document.querySelector("#transcript-language"),
};

if ("serviceWorker" in navigator) {
  window.addEventListener("load", () => {
    navigator.serviceWorker.register("/sw.js").catch(() => {});
  });
}

// --- PWA install prompt ---------------------------------------------------

const installBanner = document.querySelector("#install-banner");
const installAppButton = document.querySelector("#install-app");
const installDismissButton = document.querySelector("#install-dismiss");
const installHint = document.querySelector("#install-hint");
let deferredPrompt = null;

function isInstallDismissed() {
  try {
    return localStorage.getItem("ytvideofree-install-dismissed") === "1";
  } catch {
    return false;
  }
}

function showInstallBanner() {
  if (!installBanner || isInstallDismissed()) return;
  installBanner.classList.remove("is-hidden");
}

function hideInstallBanner() {
  if (installBanner) installBanner.classList.add("is-hidden");
}

window.addEventListener("beforeinstallprompt", (event) => {
  event.preventDefault();
  deferredPrompt = event;
  showInstallBanner();
});

if (installAppButton) {
  installAppButton.addEventListener("click", async () => {
    if (!deferredPrompt) return;
    deferredPrompt.prompt();
    try {
      await deferredPrompt.userChoice;
    } catch {
      // The native prompt was dismissed; nothing else to do.
    }
    deferredPrompt = null;
    hideInstallBanner();
  });
}

if (installDismissButton) {
  installDismissButton.addEventListener("click", () => {
    hideInstallBanner();
    try {
      localStorage.setItem("ytvideofree-install-dismissed", "1");
    } catch {
      // Storage may be unavailable (private mode); ignore.
    }
  });
}

window.addEventListener("appinstalled", () => {
  deferredPrompt = null;
  hideInstallBanner();
});

// iOS Safari has no beforeinstallprompt; guide users to Add to Home Screen.
const isIos = /iphone|ipad|ipod/i.test(navigator.userAgent) && !window.MSStream;
if (isIos && installBanner) {
  if (installHint) installHint.textContent = "Tap Share, then \u201cAdd to Home Screen\u201d.";
  if (installAppButton) installAppButton.classList.add("is-hidden");
  setTimeout(showInstallBanner, 2500);
}

// --- Dark mode -------------------------------------------------------------

const themeToggle = document.querySelector("#theme-toggle");
const rootElement = document.documentElement;

function applyTheme(theme) {
  rootElement.dataset.theme = theme;
  try {
    localStorage.setItem("ytvideofree-theme", theme);
  } catch {
    // Storage may be unavailable; the toggle still works for this visit.
  }
  const themeMeta = document.querySelector('meta[name="theme-color"]');
  if (themeMeta) {
    themeMeta.content = theme === "dark" ? "#0b1220" : "#0f766e";
  }
  if (themeToggle) {
    themeToggle.setAttribute("aria-label", theme === "dark" ? "Switch to light mode" : "Switch to dark mode");
  }
}

if (themeToggle) {
  themeToggle.addEventListener("click", () => {
    applyTheme(rootElement.dataset.theme === "dark" ? "light" : "dark");
  });
}

// Follow OS theme changes unless the user has chosen a theme explicitly.
if (window.matchMedia) {
  const colorSchemeQuery = window.matchMedia("(prefers-color-scheme: dark)");
  const onSchemeChange = (event) => {
    let saved = null;
    try {
      saved = localStorage.getItem("ytvideofree-theme");
    } catch {
      // Ignore.
    }
    if (!saved) applyTheme(event.matches ? "dark" : "light");
  };
  if (colorSchemeQuery.addEventListener) {
    colorSchemeQuery.addEventListener("change", onSchemeChange);
  } else if (colorSchemeQuery.addListener) {
    colorSchemeQuery.addListener(onSchemeChange);
  }
}

document.querySelectorAll("[data-mode]").forEach((button) => {
  button.addEventListener("click", () => setMode(button.dataset.mode));
});

elements.form.addEventListener("submit", async (event) => {
  event.preventDefault();
  await inspectCurrentUrl();
  if (state.mode === "transcript") {
    await loadTranscript();
  }
});

elements.pasteButton.addEventListener("click", pasteFromClipboard);

// Show the video thumbnail automatically as soon as a complete-looking
// YouTube link lands in the input field.
let inputTimer = null;
elements.url.addEventListener("input", () => {
  clearTimeout(inputTimer);
  const value = elements.url.value.trim();
  if (!value) {
    resetResult();
    return;
  }
  inputTimer = setTimeout(() => {
    if (looksLikeYouTubeUrl(value)) {
      inspectCurrentUrl();
    }
  }, 800);
});

document.querySelector("#download-video").addEventListener("click", () => {
  downloadMedia("video");
});

document.querySelector("#download-audio").addEventListener("click", () => {
  downloadMedia("audio");
});

document.querySelector("#download-thumbnail").addEventListener("click", downloadThumbnail);

document.querySelector("#load-transcript").addEventListener("click", loadTranscript);
document.querySelector("#copy-transcript").addEventListener("click", copyTranscript);
document.querySelector("#download-txt").addEventListener("click", () => downloadTranscript("txt"));
document.querySelector("#download-srt").addEventListener("click", () => downloadTranscript("srt"));

function setMode(mode) {
  state.mode = mode;
  document.querySelectorAll("[data-mode]").forEach((button) => {
    const active = button.dataset.mode === mode;
    button.classList.toggle("is-active", active);
    button.setAttribute("aria-selected", String(active));
  });

  document.querySelectorAll(".mode-panel").forEach((panel) => {
    panel.classList.toggle("is-active", panel.id === `${mode}-panel`);
  });
}

function looksLikeYouTubeUrl(value) {
  return /(youtube\.com|youtu\.be)/i.test(value);
}

async function pasteFromClipboard() {
  let text = "";
  try {
    text = await navigator.clipboard.readText();
  } catch {
    text = "";
  }

  if (!text.trim()) {
    elements.url.focus();
    setMessage("Could not read the clipboard — select the link, copy it, then press Ctrl+V to paste.", "error");
    return;
  }

  elements.url.value = text.trim();
  await inspectCurrentUrl();
}

function resetResult() {
  state.info = null;
  state.transcript = null;
  elements.videoResult.classList.add("is-hidden");
  elements.transcriptResult.classList.add("is-hidden");
  elements.empty.classList.remove("is-hidden");
  toggleButtons(false);
}

async function inspectCurrentUrl() {
  const url = elements.url.value.trim();
  if (!url) {
    setMessage("Paste a YouTube link first.", "error");
    return null;
  }

  setBusy("Analyzing");
  setMessage("Fetching video details...");

  try {
    const info = await postJson("/api/inspect", { url });
    // Ignore responses that arrive after the user changed the link, but
    // re-enable the controls so buttons never stay stuck disabled.
    if (elements.url.value.trim() !== url) {
      setDone("Ready");
      return null;
    }
    state.info = info;
    renderInfo(info);
    setDone("Ready");
    setMessage("Choose a format and download when ready.");
    return info;
  } catch (error) {
    setError(error.message);
    return null;
  }
}

function renderInfo(info) {
  elements.empty.classList.add("is-hidden");
  elements.transcriptResult.classList.add("is-hidden");
  elements.videoResult.classList.remove("is-hidden");

  elements.thumbnail.src = info.thumbnail || "";
  elements.thumbnail.alt = info.title ? `${info.title} thumbnail` : "";
  elements.title.textContent = info.title || "Untitled video";
  elements.channel.textContent = info.channel || "YouTube";
  elements.duration.textContent = info.duration_label || "0:00";
  elements.uploadDate.textContent = info.upload_date || "Unknown";
  elements.views.textContent = typeof info.view_count === "number" ? info.view_count.toLocaleString() : "Unknown";

  if (Array.isArray(info.video_qualities) && info.video_qualities.length) {
    const options = new Set(info.video_qualities);
    Array.from(elements.videoQuality.options).forEach((option) => {
      option.disabled = option.value !== "best" && !options.has(option.value);
    });
    if (elements.videoQuality.selectedOptions[0]?.disabled) {
      elements.videoQuality.value = "best";
    }
  }
}

async function downloadMedia(mode) {
  const url = elements.url.value.trim();
  if (!url) {
    setMessage("Paste a YouTube link first.", "error");
    return;
  }

  if (!state.info) {
    const info = await inspectCurrentUrl();
    if (!info) return;
  }

  setBusy(mode === "video" ? "Preparing MP4" : "Preparing MP3");
  setMessage("The file will download as soon as conversion finishes.");

  const payload = {
    url,
    mode,
    quality: elements.videoQuality.value,
    audio_quality: elements.audioQuality.value,
  };

  try {
    const response = await fetch("/api/download", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    await downloadBlobResponse(response, mode === "video" ? "video.mp4" : "audio.mp3");
    setDone("Downloaded");
    setMessage("Download started.");
  } catch (error) {
    setError(error.message);
  }
}

async function downloadThumbnail() {
  const url = elements.url.value.trim();
  if (!url) {
    setMessage("Paste a YouTube link first.", "error");
    return;
  }

  if (!state.info) {
    const info = await inspectCurrentUrl();
    if (!info) return;
  }

  setBusy("Thumbnail");
  setMessage("Preparing thumbnail...");

  try {
    const response = await fetch("/api/thumbnail", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url, title: state.info?.title || null }),
    });
    const thumbName = (state.info?.title || "thumbnail").replace(/[^A-Za-z0-9._ -]+/g, "").trim().slice(0, 120) || "thumbnail";
    await downloadBlobResponse(response, "thumbnail.jpg", thumbName + ".jpg");
    setDone("Downloaded");
    setMessage("Thumbnail download started.");
  } catch (error) {
    setError(error.message);
  }
}

async function loadTranscript() {
  const url = elements.url.value.trim();
  if (!url) {
    setMessage("Paste a YouTube link first.", "error");
    return;
  }

  setBusy("Transcript");
  setMessage("Looking for available captions...");

  try {
    const transcript = await postJson("/api/transcript", transcriptPayload("txt"));
    state.transcript = transcript;
    elements.transcriptText.value = transcript.text || "";
    elements.transcriptLanguage.textContent = `Transcript: ${transcript.language || transcript.language_code}`;
    elements.transcriptResult.classList.remove("is-hidden");
    setDone("Ready");
    setMessage("Transcript is ready to copy or download.");
  } catch (error) {
    setError(error.message);
  }
}

async function copyTranscript() {
  if (!elements.transcriptText.value.trim()) {
    setMessage("Load a transcript first.", "error");
    return;
  }

  try {
    await navigator.clipboard.writeText(elements.transcriptText.value);
  } catch {
    elements.transcriptText.select();
    document.execCommand("copy");
  }
  setDone("Copied");
  setMessage("Transcript copied.");
}

async function downloadTranscript(format) {
  const url = elements.url.value.trim();
  if (!url) {
    setMessage("Paste a YouTube link first.", "error");
    return;
  }

  if (!state.info) {
    const info = await inspectCurrentUrl();
    if (!info) return;
  }

  setBusy(format.toUpperCase());
  setMessage("Preparing transcript file...");

  try {
    const response = await fetch("/api/transcript/download", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(transcriptPayload(format, state.info?.title || null)),
    });
    await downloadBlobResponse(response, `transcript.${format}`);
    setDone("Downloaded");
    setMessage("Transcript download started.");
  } catch (error) {
    setError(error.message);
  }
}

function transcriptPayload(format, title = null) {
  return {
    url: elements.url.value.trim(),
    languages: elements.languageList.value
      .split(",")
      .map((language) => language.trim())
      .filter(Boolean),
    translate_to: elements.translateTo.value.trim() || null,
    format,
    title,
  };
}

async function postJson(url, payload) {
  const response = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });

  if (!response.ok) {
    throw new Error(await responseError(response));
  }

  return response.json();
}

async function downloadBlobResponse(response, fallbackName, overrideName) {
  if (!response.ok) {
    throw new Error(await responseError(response));
  }

  const blob = await response.blob();
  const objectUrl = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = objectUrl;
  link.download = overrideName || filenameFromDisposition(response.headers.get("Content-Disposition")) || fallbackName;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(objectUrl);
}

async function responseError(response) {
  try {
    const data = await response.json();
    return data.detail || "The request could not be completed.";
  } catch {
    return "The request could not be completed.";
  }
}

function filenameFromDisposition(header) {
  if (!header) return null;
  const match = header.match(/filename="?([^"]+)"?/i);
  return match ? match[1] : null;
}

function setBusy(label) {
  elements.status.textContent = label;
  elements.status.className = "status-pill is-busy";
  toggleButtons(true);
}

function setDone(label) {
  elements.status.textContent = label;
  elements.status.className = "status-pill is-done";
  toggleButtons(false);
}

function setError(message) {
  elements.status.textContent = "Needs attention";
  elements.status.className = "status-pill is-error";
  toggleButtons(false);
  setMessage(message, "error");
}

function setMessage(message, type = "") {
  elements.message.textContent = message;
  elements.message.classList.toggle("is-error", type === "error");
}

function toggleButtons(disabled) {
  document.querySelectorAll("button").forEach((button) => {
    if (button.id === "theme-toggle") return;
    button.disabled = disabled;
  });
}
