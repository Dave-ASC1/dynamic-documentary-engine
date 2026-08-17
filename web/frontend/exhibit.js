/*
 * exhibit.js — gallery/kiosk view
 * ---------------------------------------------------------------------------
 * Drives the public-facing screen. The console (app.js) is unchanged and
 * still lives at "/"; this is a separate page at "/exhibit" because it
 * serves a different person. Staff configure it once, then it shows one
 * button for the rest of the day.
 *
 * Design rules this file follows:
 *   - The screen is never blank and never dead. Every failure lands on a
 *     panel with a way forward, because nobody will be watching it.
 *   - Nothing needs a keyboard, a mouse, or a second click.
 *   - Settings survive a reload, so a power cut doesn't need staff.
 */

const setupEl = document.getElementById("setup");
const stageEl = document.getElementById("stage");

const setupCollection = document.getElementById("setup-collection");
const setupCollectionHint = document.getElementById("setup-collection-hint");
const setupDuration = document.getElementById("setup-duration");
const setupUnit = document.getElementById("setup-unit");
const setupDurationHint = document.getElementById("setup-duration-hint");
const setupStart = document.getElementById("setup-start");

const panels = {
  attract: document.getElementById("attract"),
  working: document.getElementById("working"),
  screening: document.getElementById("screening"),
  failure: document.getElementById("failure"),
};

const makeBtn = document.getElementById("make-btn");
const workingDetail = document.getElementById("working-detail");
const progressBar = document.getElementById("progress-bar");
const progressFill = document.getElementById("progress-fill");
const workingCancel = document.getElementById("working-cancel");
const player = document.getElementById("exhibit-player");
const screeningOverlay = document.getElementById("screening-overlay");
const replayBtn = document.getElementById("replay-btn");
const anotherBtn = document.getElementById("another-btn");
const failureDetail = document.getElementById("failure-detail");
const retryBtn = document.getElementById("retry-btn");
const escapeHatch = document.getElementById("escape-hatch");

const SETTINGS_KEY = "dde-exhibit-settings";

let settings = null;      // {collection, seconds, mode}
let activeJobId = null;
let progressTimer = null;
let collections = [];

/* ---------------------------------------------------------------------------
 * Small helpers
 * ------------------------------------------------------------------------ */

function formatSeconds(s) {
  if (s == null) return "?";
  const total = Math.round(s);
  if (total < 60) return `${total}s`;
  const h = Math.floor(total / 3600);
  const m = Math.floor((total % 3600) / 60);
  const sec = total % 60;
  const parts = [];
  if (h) parts.push(`${h}h`);
  if (m) parts.push(`${m}m`);
  if (sec) parts.push(`${sec}s`);
  return parts.join(" ");
}

function newJobId() {
  if (window.crypto && typeof window.crypto.randomUUID === "function") {
    return window.crypto.randomUUID();
  }
  return `exhibit-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function showPanel(name) {
  for (const [key, el] of Object.entries(panels)) {
    el.classList.toggle("hidden", key !== name);
  }
}

/* ---------------------------------------------------------------------------
 * Setup screen
 * ------------------------------------------------------------------------ */

function setupSeconds() {
  const value = parseFloat(setupDuration.value);
  if (!Number.isFinite(value) || value <= 0) return null;
  return Math.max(1, Math.round(setupUnit.value === "minutes" ? value * 60 : value));
}

function updateSetupHint() {
  const seconds = setupSeconds();
  setupDurationHint.textContent =
    seconds === null ? "Enter a length greater than zero." : `Each film: ${formatSeconds(seconds)}`;
  refreshStartButton();
}

// A topic with no footage can't produce anything, so the exhibit must not
// be startable on it — that would put an error on the gallery wall.
function selectedCollection() {
  return collections.find((c) => c.id === setupCollection.value) || null;
}

function refreshStartButton() {
  const collection = selectedCollection();
  const empty = collection && (collection.artifact_counts?.total || 0) === 0;

  setupCollectionHint.classList.toggle("hidden", !empty);
  if (empty) {
    setupCollectionHint.textContent =
      `"${collection.name}" has no footage yet. Add clips to its assets folder first.`;
  }
  setupStart.disabled = !collection || empty || setupSeconds() === null;
}

async function loadCollections() {
  try {
    const res = await fetch("/api/collections");
    collections = await res.json();
  } catch (e) {
    collections = [];
  }

  setupCollection.innerHTML = "";
  for (const c of collections) {
    const opt = document.createElement("option");
    opt.value = c.id;
    const count = c.artifact_counts?.total || 0;
    opt.textContent = count ? `${c.name} (${count} clips)` : `${c.name} — no footage yet`;
    setupCollection.appendChild(opt);
  }

  const saved = loadSettings();
  if (saved && collections.some((c) => c.id === saved.collection)) {
    setupCollection.value = saved.collection;
    setupUnit.value = saved.seconds % 60 === 0 && saved.seconds >= 60 ? "minutes" : "seconds";
    setupDuration.value =
      setupUnit.value === "minutes" ? saved.seconds / 60 : saved.seconds;
    const radio = document.querySelector(`input[name="exhibit-mode"][value="${saved.mode}"]`);
    if (radio) radio.checked = true;
  }

  updateSetupHint();
}

function loadSettings() {
  try {
    const raw = localStorage.getItem(SETTINGS_KEY);
    return raw ? JSON.parse(raw) : null;
  } catch (e) {
    return null;
  }
}

function saveSettings(s) {
  try {
    localStorage.setItem(SETTINGS_KEY, JSON.stringify(s));
  } catch (e) {
    /* Private browsing or a full quota — the exhibit still runs. */
  }
}

function currentMode() {
  const checked = document.querySelector('input[name="exhibit-mode"]:checked');
  return checked ? checked.value : "visitor";
}

setupCollection.addEventListener("change", refreshStartButton);
setupDuration.addEventListener("input", updateSetupHint);
setupUnit.addEventListener("change", updateSetupHint);

setupStart.addEventListener("click", () => {
  const seconds = setupSeconds();
  if (seconds === null) return;
  settings = {
    collection: setupCollection.value,
    seconds,
    mode: currentMode(),
  };
  saveSettings(settings);
  enterExhibit();
});

/* ---------------------------------------------------------------------------
 * Entering and leaving the exhibit
 * ------------------------------------------------------------------------ */

function enterExhibit() {
  setupEl.classList.add("hidden");
  stageEl.classList.remove("hidden");

  // A wall-mounted screen should be showing the piece, not browser chrome.
  // Only works from a user gesture, which "Start exhibit" is; if the
  // browser refuses, the exhibit still runs windowed.
  if (document.documentElement.requestFullscreen) {
    document.documentElement.requestFullscreen().catch(() => {});
  }

  if (settings.mode === "continuous") {
    generate();                 // unattended: start immediately
  } else {
    showPanel("attract");
  }
}

function exitExhibit() {
  stopProgressPolling();
  if (activeJobId) cancelGeneration();
  player.pause();
  player.removeAttribute("src");
  player.load();
  stageEl.classList.add("hidden");
  setupEl.classList.remove("hidden");
  if (document.fullscreenElement && document.exitFullscreen) {
    document.exitFullscreen().catch(() => {});
  }
}

// Esc for staff with a keyboard; three taps in the corner for a bare
// touchscreen. Three, so one accidental brush doesn't expose settings.
document.addEventListener("keydown", (e) => {
  if (e.key === "Escape" && !stageEl.classList.contains("hidden")) exitExhibit();
});

let cornerTaps = 0;
let cornerTimer = null;
escapeHatch.addEventListener("click", () => {
  cornerTaps += 1;
  clearTimeout(cornerTimer);
  cornerTimer = setTimeout(() => { cornerTaps = 0; }, 1200);
  if (cornerTaps >= 3) {
    cornerTaps = 0;
    exitExhibit();
  }
});

/* ---------------------------------------------------------------------------
 * Generating
 * ------------------------------------------------------------------------ */

// Plain-language stage names. A visitor should never read "concat" or
// "X-roll"; staff can see the real trace in the console view.
const STAGE_TEXT = {
  starting: "Getting ready",
  sequencing: "Choosing the shots",
  clips: "Assembling the shots",
  joining: "Putting the film together",
  trimming: "Trimming to length",
  titles: "Adding the titles",
  done: "Ready",
};

function setProgress(stage, current, total) {
  let label = STAGE_TEXT[stage] || "Working";
  if (stage === "clips" && total) label = `${label} — ${current} of ${total}`;
  workingDetail.textContent = label;

  // Clip rendering is the bulk of the work, so it gets the bulk of the bar
  // rather than each stage counting equally.
  let pct;
  if (stage === "sequencing" || stage === "starting") pct = 4;
  else if (stage === "clips") pct = 8 + (total ? (current / total) * 62 : 0);
  else if (stage === "joining") pct = current ? 86 : 74;
  else if (stage === "trimming") pct = 90;
  else if (stage === "titles") pct = 95;
  else if (stage === "done") pct = 100;
  else pct = 50;

  progressFill.style.width = `${pct}%`;
  progressBar.setAttribute("aria-valuenow", Math.round(pct));
}

function startProgressPolling() {
  stopProgressPolling();
  progressTimer = setInterval(async () => {
    if (!activeJobId) return;
    try {
      const res = await fetch(`/api/generate/progress?job_id=${encodeURIComponent(activeJobId)}`);
      const p = await res.json();
      if (p.running) setProgress(p.stage, p.current, p.total);
    } catch (e) {
      /* A dropped poll is harmless — the next one will catch up. */
    }
  }, 1000);
}

function stopProgressPolling() {
  if (progressTimer) clearInterval(progressTimer);
  progressTimer = null;
}

async function generate() {
  activeJobId = newJobId();
  showPanel("working");
  setProgress("starting", 0, 1);
  startProgressPolling();

  try {
    const res = await fetch("/api/generate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        collection: settings.collection,
        target_duration: settings.seconds,
        job_id: activeJobId,
        // Baked in rather than exposed: diversity keeps a long run from
        // favouring the same clips, and whole clips are kinder than a hard
        // cut mid-shot on a gallery wall.
        diversity_mode: true,
        exact_duration: false,
      }),
    });
    const result = await res.json();

    if (res.status === 409 && result.cancelled) {
      showPanel(settings.mode === "continuous" ? "attract" : "attract");
      return;
    }
    if (!res.ok) throw new Error(result.error || `Server returned ${res.status}`);

    play(result.film_url);
  } catch (e) {
    fail(e.message);
  } finally {
    stopProgressPolling();
    activeJobId = null;
  }
}

async function cancelGeneration() {
  const jobId = activeJobId;
  if (!jobId) return;
  try {
    await fetch("/api/generate/cancel", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ job_id: jobId }),
    });
  } catch (e) {
    /* The generate request unwinds on its own regardless. */
  }
}

/* ---------------------------------------------------------------------------
 * Playing
 * ------------------------------------------------------------------------ */

function play(url) {
  showPanel("screening");
  player.src = url;
  player.muted = false;
  const attempt = player.play();
  if (attempt && attempt.catch) {
    attempt.catch(() => {
      // Some browsers block sound until the page has been interacted with.
      // A silent film is worse than a muted one, so fall back to muted
      // playback rather than leaving a still frame on the wall.
      player.muted = true;
      player.play().catch(() => fail("The film could not start playing."));
    });
  }
  revealOverlayBriefly();
}

// The controls appear on arrival and whenever the screen is touched, then
// fade so the film plays unobstructed.
let overlayTimer = null;
function revealOverlayBriefly() {
  screeningOverlay.classList.add("visible");
  clearTimeout(overlayTimer);
  overlayTimer = setTimeout(() => screeningOverlay.classList.remove("visible"), 4000);
}

panels.screening.addEventListener("pointerdown", revealOverlayBriefly);

player.addEventListener("ended", () => {
  if (settings && settings.mode === "continuous") {
    generate();                 // unattended: straight into the next film
  } else {
    showPanel("attract");       // visitor-triggered: back to the button
  }
});

player.addEventListener("error", () => fail("The film could not be played."));

replayBtn.addEventListener("click", () => {
  player.currentTime = 0;
  player.play().catch(() => {});
  revealOverlayBriefly();
});

anotherBtn.addEventListener("click", generate);

/* ---------------------------------------------------------------------------
 * Failure
 * ------------------------------------------------------------------------ */

// In continuous mode nobody is watching, so a failure retries on its own
// after a pause rather than leaving the wall stuck on an error.
function fail(message) {
  failureDetail.textContent = message || "Something went wrong.";
  showPanel("failure");
  if (settings && settings.mode === "continuous") {
    setTimeout(() => {
      if (!panels.failure.classList.contains("hidden")) generate();
    }, 12000);
  }
}

retryBtn.addEventListener("click", generate);
makeBtn.addEventListener("click", generate);
workingCancel.addEventListener("click", async () => {
  await cancelGeneration();
  showPanel("attract");
});

/* ------------------------------------------------------------------------ */

loadCollections();
