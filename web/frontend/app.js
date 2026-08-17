const generateBtn = document.getElementById("generate-btn");
const collectionSelect = document.getElementById("collection-select");
const collectionHint = document.getElementById("collection-hint");
const durationInput = document.getElementById("duration");
const diversityToggle = document.getElementById("diversity-toggle");
const exactDurationToggle = document.getElementById("exact-duration-toggle");
const cancelBtn = document.getElementById("cancel-btn");
const durationUnit = document.getElementById("duration-unit");
const durationHint = document.getElementById("duration-hint");
const statusEl = document.getElementById("status");
const statusText = statusEl.querySelector(".status-text");
const playerSection = document.getElementById("player-section");
const player = document.getElementById("player");
const metaEl = document.getElementById("meta");
const traceSection = document.getElementById("trace-section");
const traceList = document.getElementById("trace-list");
const historyList = document.getElementById("history-list");
const syncNotice = document.getElementById("sync-notice");
const themeToggle = document.getElementById("theme-toggle");

function currentTheme() {
  return document.documentElement.getAttribute("data-theme") === "dark" ? "dark" : "light";
}

function applyTheme(theme) {
  document.documentElement.setAttribute("data-theme", theme);
  localStorage.setItem("dde-theme", theme);
  themeToggle.setAttribute(
    "aria-label",
    theme === "dark" ? "Switch to light mode" : "Switch to dark mode"
  );
}

themeToggle.addEventListener("click", () => {
  applyTheme(currentTheme() === "dark" ? "light" : "dark");
});

applyTheme(currentTheme());

function setStatus(text, state) {
  // state: "active" | "done" | "error" | undefined
  statusText.textContent = text;
  statusEl.classList.remove("active", "done", "error");
  if (state) statusEl.classList.add(state);
}

// Films can run from seconds to feature length, so a bare second count
// stops being readable quickly ("5400s" tells you nothing). Anything over
// a minute is broken into h/m/s.
function formatSeconds(s) {
  if (s == null) return "?";
  const total = Math.round(s);
  if (total < 60) return `${total}s`;

  const hours = Math.floor(total / 3600);
  const minutes = Math.floor((total % 3600) / 60);
  const seconds = total % 60;

  const parts = [];
  if (hours) parts.push(`${hours}h`);
  if (minutes) parts.push(`${minutes}m`);
  if (seconds) parts.push(`${seconds}s`);
  return parts.join(" ");
}

// Labels come back from the engine as "Title [artifact_type]" — pull the
// type out so we can color-code it (A-roll / B-roll / X-roll).
function parseLabel(label) {
  const m = /^(.*)\s\[([^\]]+)\]$/.exec(label || "");
  if (!m) return { title: label || "(none)", type: null };
  return { title: m[1], type: m[2].toLowerCase() };
}

function typeClass(type) {
  if (!type) return "";
  if (type.includes("a-roll")) return "type-a";
  if (type.includes("b-roll")) return "type-b";
  if (type.includes("x-roll")) return "type-x";
  return "";
}

function badgeText(type) {
  if (!type) return "";
  if (type.includes("a-roll")) return "A-roll";
  if (type.includes("b-roll")) return "B-roll";
  if (type.includes("x-roll")) return "X-roll";
  return type;
}

function buildCutCard(markerClass, badgeClass, badgeLabel, title, contrast) {
  const li = document.createElement("li");

  const marker = document.createElement("span");
  marker.className = `marker ${markerClass}`;
  li.appendChild(marker);

  const card = document.createElement("div");
  card.className = "cut-card";

  const badge = document.createElement("span");
  badge.className = `cut-badge ${badgeClass}`;
  badge.textContent = badgeLabel;
  card.appendChild(badge);

  const titleEl = document.createElement("span");
  titleEl.className = "cut-title";
  titleEl.textContent = title;
  card.appendChild(titleEl);

  if (contrast && contrast.length) {
    const contrastEl = document.createElement("div");
    contrastEl.className = "cut-contrast";
    if (contrast.length === 1 && /—| — /.test(contrast[0])) {
      const sentence = document.createElement("span");
      sentence.className = "sentence";
      sentence.textContent = contrast[0];
      contrastEl.appendChild(sentence);
    } else {
      for (const dim of contrast) {
        const tag = document.createElement("span");
        tag.className = "tag";
        tag.textContent = dim;
        contrastEl.appendChild(tag);
      }
    }
    card.appendChild(contrastEl);
  }

  li.appendChild(card);
  return li;
}

function renderTrace(result) {
  traceList.innerHTML = "";

  const open = parseLabel(result.opening);
  traceList.appendChild(
    buildCutCard("type-open", "type-open", "Open", open.title, null)
  );

  let step = 0;
  for (const ev of result.trace) {
    step += 1;
    const parsed = parseLabel(ev.chosen);
    const isPairing = ev.kind === "pairing";
    const marker = isPairing ? "type-x" : typeClass(parsed.type) || "type-a";
    const badgeCls = isPairing ? "type-x" : typeClass(parsed.type) || "type-a";
    const badgeLabel = isPairing ? "Audio pairing" : `Cut ${step} · ${badgeText(parsed.type)}`;
    traceList.appendChild(
      buildCutCard(marker, badgeCls, badgeLabel, parsed.title, ev.contrast)
    );
  }

  const close = parseLabel(result.closing);
  traceList.appendChild(
    buildCutCard("type-close", "type-close", "Close", close.title, null)
  );

  traceSection.classList.remove("hidden");
}

function chip(label, value) {
  const span = document.createElement("span");
  span.className = "chip";
  span.innerHTML = `${label} <strong>${value}</strong>`;
  return span;
}

function renderSyncNotice(sync) {
  if (!sync || (!sync.added.length && !sync.removed.length)) {
    syncNotice.classList.add("hidden");
    syncNotice.textContent = "";
    return;
  }
  const parts = [];
  if (sync.added.length) {
    parts.push(`+${sync.added.length} new clip${sync.added.length === 1 ? "" : "s"} detected in the media library`);
  }
  if (sync.removed.length) {
    parts.push(`${sync.removed.length} clip${sync.removed.length === 1 ? "" : "s"} retired (source file no longer found)`);
  }
  syncNotice.textContent = parts.join(" — ");
  syncNotice.classList.remove("hidden");
}

function renderMeta(result) {
  metaEl.innerHTML = "";
  metaEl.appendChild(chip("Collection", result.collection_name));
  metaEl.appendChild(chip("Requested", formatSeconds(result.target_duration)));
  metaEl.appendChild(chip("Actual", formatSeconds(result.actual_duration)));
  metaEl.appendChild(chip("Slots", result.slots.length));
  if (result.diversity_mode) metaEl.appendChild(chip("Mode", "Diversity"));
  if (result.exact_duration) {
    metaEl.appendChild(chip("Length", result.trimmed ? "Exact (trimmed)" : "Exact (no trim needed)"));
  }
  if (result.title_cards) {
    // Name the topic's own opening/closing pieces when it has them, so it's
    // obvious which folder the film actually picked up — falling back to
    // the generic label only when the standard text cards were used.
    const custom = [result.opening_title_piece, result.closing_title_piece].filter(Boolean);
    const added = formatSeconds(result.title_card_seconds);
    metaEl.appendChild(
      chip(
        "Intro/outro",
        custom.length
          ? `${custom.join(" / ")} (+${added}, not counted above)`
          : `Included (+${added}, not counted above)`
      )
    );
  }
  if (result.titles_exceed_target) {
    metaEl.appendChild(
      chip("Note", "Title pieces are longer than the requested length")
    );
  }
}

function renderHistoryItem(entry) {
  const li = document.createElement("li");
  const when = entry.generated_at ? new Date(entry.generated_at).toLocaleTimeString() : "";
  li.innerHTML = `
    <div class="history-row">
      <a href="${entry.film_url}" target="_blank">${entry.filename}</a>
      <button class="delete-btn" type="button" title="Delete this film" aria-label="Delete ${entry.filename}">&#10005;</button>
    </div>
    <span class="history-meta">${formatSeconds(entry.actual_duration)} — ${when}</span>
  `;
  li.querySelector(".delete-btn").addEventListener("click", () => deleteFilm(entry.filename));
  return li;
}

async function deleteFilm(filename) {
  if (!confirm(`Delete ${filename}? This can't be undone.`)) return;
  try {
    const res = await fetch(
      `/api/films/${encodeURIComponent(collectionSelect.value)}/${encodeURIComponent(filename)}`,
      { method: "DELETE" }
    );
    const result = await res.json();
    if (!res.ok) throw new Error(result.error || `Server returned ${res.status}`);
    if (player.src && player.src.endsWith(filename)) {
      playerSection.classList.add("hidden");
      traceSection.classList.add("hidden");
      player.removeAttribute("src");
    }
    await loadHistory();
  } catch (e) {
    setStatus(`Delete failed: ${e.message}`, "error");
  }
}

async function loadHistory() {
  if (!collectionSelect.value) return;
  try {
    const res = await fetch(`/api/films?collection=${encodeURIComponent(collectionSelect.value)}`);
    const films = await res.json();
    historyList.innerHTML = "";
    if (!films.length) {
      const li = document.createElement("li");
      li.className = "empty";
      li.textContent = "No films generated yet this session.";
      historyList.appendChild(li);
      return;
    }
    for (const entry of films) {
      historyList.appendChild(renderHistoryItem(entry));
    }
  } catch (e) {
    // History is a nice-to-have; a failed fetch shouldn't block generation.
    console.warn("Could not load film history:", e);
  }
}

function updateCollectionGate(collections) {
  const selected = collections.find((c) => c.id === collectionSelect.value);
  const empty = !selected || (selected.artifact_counts.total || 0) === 0;
  generateBtn.disabled = empty;
  if (empty && selected) {
    collectionHint.textContent =
      `'${selected.name}' has no footage yet — add clips to local-media/${selected.folder}/assets/ first.`;
    collectionHint.classList.remove("hidden");
  } else {
    collectionHint.classList.add("hidden");
  }
}

async function loadCollections() {
  try {
    const res = await fetch("/api/collections");
    const collections = await res.json();
    collectionSelect.innerHTML = "";

    for (const c of collections) {
      const opt = document.createElement("option");
      opt.value = c.id;
      const count = c.artifact_counts.total || 0;
      opt.textContent = `${c.name} (${count} clip${count === 1 ? "" : "s"})`;
      collectionSelect.appendChild(opt);
    }

    // Default to the first topic that actually has footage, so a new
    // empty topic (just created, waiting on real media) doesn't become
    // the default and immediately block Generate.
    const populated = collections.find((c) => (c.artifact_counts.total || 0) > 0);
    if (populated) collectionSelect.value = populated.id;

    updateCollectionGate(collections);
    collectionSelect.addEventListener("change", () => {
      updateCollectionGate(collections);
      playerSection.classList.add("hidden");
      traceSection.classList.add("hidden");
      loadHistory();
    });

    await loadHistory();
  } catch (e) {
    console.warn("Could not load film topics:", e);
  }
}

// Id for the run currently in flight, so the Cancel button can name it to
// the backend. Null whenever nothing is generating.
let activeJobId = null;

function newJobId() {
  // crypto.randomUUID needs a secure context — over a plain-http tunnel or
  // LAN address it may be missing, so fall back to a random-enough id.
  if (window.crypto && typeof window.crypto.randomUUID === "function") {
    return window.crypto.randomUUID();
  }
  return `job-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

async function cancelGeneration() {
  if (!activeJobId) return;
  cancelBtn.disabled = true;
  setStatus("Cancelling…", "active");
  try {
    await fetch("/api/generate/cancel", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ job_id: activeJobId }),
    });
    // The in-flight generate request unwinds on its own and reports the
    // cancellation — no need to update status further from here.
  } catch (e) {
    setStatus(`Could not cancel: ${e.message}`, "error");
  }
}

// Target length in whole seconds, whichever unit is showing. The engine
// only ever deals in seconds; minutes are purely an input convenience so a
// long film can be asked for as "90" rather than "5400".
function targetSeconds() {
  const value = parseFloat(durationInput.value);
  if (!Number.isFinite(value) || value <= 0) return null;
  const seconds = durationUnit.value === "minutes" ? value * 60 : value;
  return Math.max(1, Math.round(seconds));
}

// Half-minute steps so switching units can round-trip exactly — 90
// seconds becomes 1.5 minutes and back, instead of snapping to 2.
const UNIT_CONFIG = {
  seconds: { min: 1, max: 36000, step: 1 },
  minutes: { min: 0.5, max: 600, step: 0.5 },
};

function applyUnit(unit, convertValue) {
  if (!UNIT_CONFIG[unit]) unit = "seconds";
  const cfg = UNIT_CONFIG[unit];
  durationUnit.value = unit;

  if (convertValue) {
    const value = parseFloat(durationInput.value);
    if (Number.isFinite(value) && value > 0) {
      const converted = unit === "minutes" ? value / 60 : value * 60;
      // Keep minutes to one decimal; seconds are always whole.
      durationInput.value =
        unit === "minutes"
          ? Math.max(cfg.min, Math.round(converted * 10) / 10)
          : Math.max(cfg.min, Math.round(converted));
    }
  }

  durationInput.min = cfg.min;
  durationInput.max = cfg.max;
  durationInput.step = cfg.step;
  rememberDuration();
  updateDurationHint();
}

// The unit and the number are remembered together. Storing only the unit
// would mean returning to the page with the markup's default of 90 now
// read as 90 *minutes* — a 90-second film silently becoming a 90-minute
// one between visits.
function rememberDuration() {
  localStorage.setItem("dde-duration-unit", durationUnit.value);
  localStorage.setItem("dde-duration-value", durationInput.value);
}

// Shows what the entered number actually works out to, so there's no doubt
// that "90 minutes" means an hour and a half.
function updateDurationHint() {
  const seconds = targetSeconds();
  if (seconds === null) {
    durationHint.textContent = "Enter a length greater than zero.";
    return;
  }
  // The raw second count is only worth spelling out when it isn't already
  // what's shown — "= 45s (45 seconds)" says the same thing twice.
  const readable = formatSeconds(seconds);
  durationHint.textContent =
    readable === `${seconds}s`
      ? `= ${readable}`
      : `= ${readable} (${seconds} seconds)`;
}

durationUnit.addEventListener("change", () => applyUnit(durationUnit.value, true));
durationInput.addEventListener("input", () => {
  rememberDuration();
  updateDurationHint();
});

(function restoreDuration() {
  const storedValue = localStorage.getItem("dde-duration-value");
  applyUnit(localStorage.getItem("dde-duration-unit") || "seconds", false);
  if (storedValue !== null && parseFloat(storedValue) > 0) {
    durationInput.value = storedValue;
  }
  updateDurationHint();
})();

async function generateFilm() {
  const target = targetSeconds();
  if (target === null) {
    setStatus("Enter a target length greater than zero.", "error");
    return;
  }
  activeJobId = newJobId();
  generateBtn.disabled = true;
  generateBtn.classList.add("hidden");
  cancelBtn.classList.remove("hidden");
  cancelBtn.disabled = false;
  setStatus("Generating a unique sequence and rendering the film…", "active");
  traceSection.classList.add("hidden");

  try {
    const res = await fetch("/api/generate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        collection: collectionSelect.value,
        target_duration: target,
        diversity_mode: diversityToggle.checked,
        exact_duration: exactDurationToggle.checked,
        job_id: activeJobId,
      }),
    });
    const result = await res.json();

    // 409 is a deliberate cancel, not a failure — say so plainly rather
    // than showing it as an error.
    if (res.status === 409 && result.cancelled) {
      setStatus("Generation cancelled.", "done");
      return;
    }

    if (!res.ok) {
      throw new Error(result.error || `Server returned ${res.status}`);
    }

    player.src = result.film_url;
    playerSection.classList.remove("hidden");
    renderMeta(result);
    renderTrace(result);
    renderSyncNotice(result.library_sync);
    setStatus("Done.", "done");
    await loadHistory();
  } catch (e) {
    setStatus(`Generation failed: ${e.message}`, "error");
  } finally {
    activeJobId = null;
    generateBtn.disabled = false;
    generateBtn.classList.remove("hidden");
    cancelBtn.classList.add("hidden");
  }
}

generateBtn.addEventListener("click", generateFilm);
cancelBtn.addEventListener("click", cancelGeneration);
loadCollections();
