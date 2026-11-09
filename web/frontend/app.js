const generateBtn = document.getElementById("generate-btn");
const collectionSelect = document.getElementById("collection-select");
const collectionHint = document.getElementById("collection-hint");
const durationInput = document.getElementById("duration");
const diversityToggle = document.getElementById("diversity-toggle");
const exactDurationToggle = document.getElementById("exact-duration-toggle");
const audioFadeSelect = document.getElementById("audio-fade-select");
const savedFade = localStorage.getItem("dde-audio-fade");
if (savedFade !== null) audioFadeSelect.value = savedFade;
audioFadeSelect.addEventListener("change", () => localStorage.setItem("dde-audio-fade", audioFadeSelect.value));
const filmOrder = document.getElementById("film-order");
const contextDateField = document.getElementById("context-date-field");
const contextDateMode = document.getElementById("context-date-mode");
const contextDate = document.getElementById("context-date");
const filterYears = document.getElementById("filter-years");
const filterSeason = document.getElementById("filter-season");
const filterLabels = document.getElementById("filter-labels");
const contextHint = document.getElementById("context-hint");
const CONTEXT_KEY = "dde-context";
let contextOptions = null;
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

function renderTraceEvent(ev, step) {
  const parsed = parseLabel(ev.chosen);
  const isPairing = ev.kind === "pairing";
  const marker = isPairing ? "type-x" : typeClass(parsed.type) || "type-a";
  const why = { memory: " · Memory trigger", next_date: " · Next date", flow: " · Follows on",
                dated: " · In date order" }[ev.kind] || "";
  const badgeLabel = isPairing ? "Audio pairing" : `Cut ${step}${why} · ${badgeText(parsed.type)}`;
  traceList.appendChild(buildCutCard(marker, marker, badgeLabel, parsed.title, ev.contrast));
}

function renderTrace(result) {
  traceList.innerHTML = "";

  // A memory film's first trace entry is the clip it opens on, and a film
  // in date order has no generated bookends — its first and last clips are
  // its first and last dates. Those entries go on the Open/Close cards
  // instead of being listed twice.
  const events = result.trace.slice();
  const dated = Boolean(result.date_order);
  const first = events[0];
  const opening = first && (first.kind === "opening" || (dated && first.kind === "dated"))
    ? events.shift() : null;
  let closing = null;
  let tail = [];
  if (dated) {
    let last = -1;
    events.forEach((ev, i) => { if (ev.kind !== "pairing") last = i; });
    if (last >= 0) {
      closing = events[last];
      tail = events.splice(last).slice(1);   // the close's own audio pairing
    }
  }

  // A memory film opens on today's best match, or — when nothing matches —
  // on the next date in the calendar.
  const why = !opening ? "Open"
    : opening.kind === "dated" ? "Open · In date order"
    : String((opening.contrast || [])[0] || "").startsWith("memory trigger") ? "Open · Memory trigger"
    : "Open · Next date";
  traceList.appendChild(
    buildCutCard("type-open", "type-open", why, parseLabel(result.opening).title, opening ? opening.contrast : null)
  );

  let step = 0;
  for (const ev of events) {
    if (ev.kind !== "pairing") step += 1;
    renderTraceEvent(ev, step);
  }

  if (!dated || closing) {
    traceList.appendChild(
      buildCutCard("type-close", "type-close", closing ? "Close · In date order" : "Close",
                   parseLabel(result.closing).title, closing ? closing.contrast : null)
    );
  }
  for (const ev of tail) renderTraceEvent(ev, step);

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
  if (result.context) {
    const plan = result.context;
    metaEl.appendChild(textChip("Order", plan.order_label || "Today's date leads"));
    if (plan.filters) metaEl.appendChild(textChip("Only", plan.filters));
  }
  if (result.date_order) {
    const d = result.date_order;
    metaEl.appendChild(textChip("Dated clips",
      d.played === d.dated_clips ? `all ${d.played} played` : `${d.played} of ${d.dated_clips} fit this length`));
  } else if (result.context && (result.context.order || "today") === "today") {
    metaEl.appendChild(textChip("Screening", `${formatContextDate(result.context.date)} · ${result.context.season}`));
    const memory = result.memory;
    if (memory) {
      metaEl.appendChild(textChip("Opened on", `${memory.title} — ${memory.reasons.join(", ")}`));
      const later = (result.triggered || []).filter((t) => t.artifact_id !== memory.artifact_id);
      if (later.length) {
        metaEl.appendChild(textChip("Then", later.map((t) => t.title).join(", ")));
      }
    } else {
      metaEl.appendChild(textChip("Opened on", "a random clip — none is labelled for this date or season yet"));
    }
  }
  // Who owns what played, from the Clip library's Ownership column.
  if (result.sources !== undefined) {
    const missing = result.clips_without_ownership || 0;
    const parts = [];
    if (result.sources.length) parts.push(result.sources.join("; "));
    if (missing) parts.push(`${missing} clip${missing === 1 ? "" : "s"} with no ownership recorded`);
    if (parts.length) metaEl.appendChild(textChip("Sources", parts.join(" · ")));
  }
}

// Like chip(), but for values that come from clip metadata — set as text,
// never parsed as HTML.
function textChip(label, value) {
  const span = document.createElement("span");
  span.className = "chip";
  const strong = document.createElement("strong");
  strong.textContent = value;
  span.append(`${label} `, strong);
  return span;
}

/* ---------------------------------------------------------------------------
 * Film plan: order, screening date and "Only clips from" filters
 * (sent as the request's "context"; see engine/context.py)
 * ------------------------------------------------------------------------ */

const SEASON_BY_MONTH = ["winter", "winter", "spring", "spring", "spring", "summer",
                         "summer", "summer", "autumn", "autumn", "autumn", "winter"];

function contextDateValue() {
  return contextDateMode.value === "custom" && contextDate.value ? contextDate.value : null;
}

function formatContextDate(iso) {
  const [y, m, d] = iso.split("-").map(Number);
  return new Date(y, m - 1, d).toLocaleDateString([], { day: "numeric", month: "long", year: "numeric" });
}

function saveContextPrefs() {
  try {
    localStorage.setItem(CONTEXT_KEY, JSON.stringify({
      order: filmOrder.value,
      dateMode: contextDateMode.value,
      date: contextDate.value,
      years: filterYears.value,
      onlySeason: filterSeason.value,
      labels: filterLabels.value,
    }));
  } catch (e) {
    /* Private browsing or a full quota — the pickers still work. */
  }
}

function loadContextPrefs() {
  try {
    return JSON.parse(localStorage.getItem(CONTEXT_KEY)) || {};
  } catch (e) {
    return {};
  }
}

// "Only clips from …" in words, or "" when every clip may appear.
function filtersText() {
  const parts = [];
  if (filterYears.value.trim()) parts.push(filterYears.value.trim());
  if (filterSeason.value) parts.push(filterSeason.value);
  const labels = filterLabels.value.split(",").map((c) => c.trim()).filter(Boolean);
  if (labels.length) parts.push(`labelled “${labels.join("” or “")}”`);
  return parts.join(", ");
}

const ORDER_HINTS = {
  today: () => {
    const date = contextDateValue() || (contextOptions && contextOptions.today);
    const season = date ? SEASON_BY_MONTH[parseInt(date.slice(5, 7), 10) - 1] : "";
    return `Opens on the clip labelled closest to ${date ? formatContextDate(date) : "today"} ` +
      `(same day and month, then month, then ${season || "season"}). Other matching clips follow, ` +
      "then the next dates in the calendar, into January and round again, whatever the year. " +
      "Clips without a day or month follow by shared people, places, tags and moods.";
  },
  oldest: () => "Clips with a dated year play from the earliest to the latest. Clips without a year are left out.",
  newest: () => "Clips with a dated year play from the latest to the earliest. Clips without a year are left out.",
  calendar: () => "Clips play from January to December, whatever the year; a season-only clip sits at the start " +
    "of its season (winter at 1 December). Clips dated only by a year are left out.",
  contrast: () => "Every cut chosen to be as different as possible from the one before — the original engine.",
};

function updateContextUI() {
  contextDateField.classList.toggle("hidden", filmOrder.value !== "today");
  contextDate.classList.toggle("hidden", contextDateMode.value !== "custom");
  const filters = filtersText();
  const hint = ORDER_HINTS[filmOrder.value] || (() => "");
  contextHint.textContent = hint() + (filters ? ` Only clips from ${filters}.` : "");
  saveContextPrefs();
}

async function loadContextOptions() {
  try {
    const res = await fetch("/api/context-options");
    contextOptions = await res.json();
  } catch (e) {
    contextOptions = null;
  }

  // The orders and seasons come from the engine, so the page and the
  // engine always agree on them.
  if (contextOptions && contextOptions.orders) {
    filmOrder.innerHTML = "";
    for (const o of contextOptions.orders) {
      const opt = document.createElement("option");
      opt.value = o.id;
      opt.textContent = o.label;
      filmOrder.appendChild(opt);
    }
  }
  if (contextOptions && contextOptions.seasons) {
    for (const season of contextOptions.seasons) {
      const opt = document.createElement("option");
      opt.value = season;
      opt.textContent = season[0].toUpperCase() + season.slice(1);
      filterSeason.appendChild(opt);
    }
  }

  // Older saved choices had an on/off switch and a "cue": off meant the
  // random contrast film, and a cue is now the "Labelled" filter.
  const prefs = loadContextPrefs();
  filmOrder.value = prefs.order || (prefs.enabled === false ? "contrast" : "today");
  if (!filmOrder.value) filmOrder.value = "today";
  if (prefs.dateMode) contextDateMode.value = prefs.dateMode;
  contextDate.value = prefs.date || (contextOptions ? contextOptions.today : "");
  filterYears.value = prefs.years || "";
  filterSeason.value = prefs.onlySeason || "";
  filterLabels.value = prefs.labels !== undefined ? prefs.labels : (prefs.cue || "");
  updateContextUI();
}

// The request's film plan, or undefined (dropped from the JSON) for the
// plain random-contrast film, which is the engine exactly as it always was.
function contextPayload() {
  const years = filterYears.value.trim();
  const labels = filterLabels.value.trim();
  if (filmOrder.value === "contrast" && !years && !filterSeason.value && !labels) return undefined;
  return {
    order: filmOrder.value,
    date: contextDateValue() || "today",
    years: years || null,
    only_season: filterSeason.value || null,
    labels: labels || null,
  };
}

for (const el of [filmOrder, contextDateMode, contextDate, filterSeason]) {
  el.addEventListener("change", updateContextUI);
}
for (const el of [filterYears, filterLabels]) {
  el.addEventListener("input", updateContextUI);
}
// Asking for a year usually means "show me that year in order", so typing
// one switches "Today's date leads" to the timeline; any other order the
// person picked stays.
filterYears.addEventListener("change", () => {
  if (filterYears.value.trim() && filmOrder.value === "today") {
    filmOrder.value = "oldest";
    updateContextUI();
  }
});

function renderHistoryItem(entry) {
  const li = document.createElement("li");
  const when = entry.generated_at
    ? new Date(entry.generated_at).toLocaleString([], {
        month: "short", day: "numeric", year: "numeric",
        hour: "numeric", minute: "2-digit",
      })
    : "";
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
        audio_fade_seconds: parseFloat(audioFadeSelect.value),
        context: contextPayload(),
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
loadContextOptions();
