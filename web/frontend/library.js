/* Clip library — label clips in the browser.
 *
 * Every field saves on its own as soon as it is changed (when the person
 * moves to the next field), through PATCH /api/library/<topic>/<clip>. The
 * server checks the value, writes the topic's clip list and keeps a backup;
 * the next generated film uses it. Nothing here builds HTML from clip data:
 * titles and labels are set as text.
 */

const topicSelect = document.getElementById("topic-select");
const searchInput = document.getElementById("search");
const filterSelect = document.getElementById("filter-select");
const summaryEl = document.getElementById("summary");
const readonlyNote = document.getElementById("readonly-note");
const clipList = document.getElementById("clip-list");
const themeToggle = document.getElementById("theme-toggle");

const TOPIC_KEY = "dde-library-topic";
const MONTHS = ["January", "February", "March", "April", "May", "June", "July",
                "August", "September", "October", "November", "December"];

// How often a clip appears: the engine's weight, in plain words.
const WEIGHTS = [[0.2, "Rarely"], [0.35, "Less often"], [0.5, "Normal"], [0.7, "More often"], [0.9, "Often"]];

// The form, in the order it is shown. kind: text | list | enum | weight | date | notes
const GROUPS = [
  { legend: "About this clip", fields: [
    { field: "title", label: "Title", kind: "text", span: 2 },
    { field: "weight", label: "How often it appears", kind: "weight" },
    { field: "notes", label: "Notes (for people, not matched)", kind: "notes", span: 2 },
  ] },
  { legend: "People and places", fields: [
    { field: "people", label: "People", kind: "list", placeholder: "e.g. G. Moore, Ruth Moore", span: 2 },
    { field: "geography", label: "Place", kind: "text", placeholder: "e.g. Camp Swift", suggest: true, span: 2 },
  ] },
  { legend: "For contrast between cuts", fields: [
    { field: "mood", label: "Mood", kind: "text", placeholder: "e.g. somber", suggest: true },
    { field: "pacing", label: "Pacing", kind: "enum", options: "pacing" },
    { field: "tags", label: "Tags", kind: "list", placeholder: "e.g. soldiers, jeep, 1252nd", span: 2 },
    { field: "theme", label: "Themes", kind: "list", placeholder: "e.g. training, homecoming" },
    { field: "dominant_lines", label: "Line direction", kind: "enum", options: "dominant_lines" },
  ] },
  { legend: "Memory triggers", fields: [
    { field: "context.date", label: "Date", kind: "date", placeholder: "e.g. 18 December 1944" },
    { field: "context.season", label: "Season", kind: "enum", options: "seasons", empty: "Auto (from date)" },
    { field: "context.weather", label: "Weather", kind: "list", placeholder: "e.g. snow, cold", span: 2 },
  ] },
];

let collections = [];
let library = null;   // { collection, editable, options, suggestions, clips }

/* ---------------------------------------------------------------------------
 * Theme (same switch as the console)
 * ------------------------------------------------------------------------ */

function applyTheme(theme) {
  document.documentElement.setAttribute("data-theme", theme);
  try { localStorage.setItem("dde-theme", theme); } catch (e) { /* not stored */ }
  themeToggle.setAttribute("aria-label", theme === "dark" ? "Switch to light mode" : "Switch to dark mode");
}
themeToggle.addEventListener("click", () => {
  applyTheme(document.documentElement.getAttribute("data-theme") === "dark" ? "light" : "dark");
});

/* ---------------------------------------------------------------------------
 * Display helpers
 * ------------------------------------------------------------------------ */

// "1945-05-08" -> "8 May 1945"; "1944-12" -> "December 1944"; "1944" -> "1944".
function friendlyDate(iso) {
  if (!iso) return "";
  const [y, m, d] = iso.split("-");
  if (!m) return y;
  const month = MONTHS[parseInt(m, 10) - 1];
  return d ? `${parseInt(d, 10)} ${month} ${y}` : `${month} ${y}`;
}

function displayValue(def, value) {
  if (value === null || value === undefined) return "";
  if (def.kind === "list") return value.filter((v) => !String(v).startsWith("color-")).join(", ");
  if (def.kind === "date") return friendlyDate(value);
  return String(value);
}

// Auto-detected colour tags stay in the clip list but aren't shown for
// editing; they're added back on save so a person never loses them.
function hiddenTags(clip) {
  return (clip.fields.tags || []).filter((t) => String(t).startsWith("color-"));
}

function typeClass(type) {
  return { "A-roll": "type-a", "B-roll": "type-b", "X-roll": "type-x" }[type] || "";
}

function formatSeconds(s) {
  if (!s && s !== 0) return "";
  const total = Math.round(s);
  return total >= 60 ? `${Math.floor(total / 60)}m ${total % 60}s` : `${total}s`;
}

function el(tag, attrs = {}, text) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (v === undefined || v === null || v === false) continue;
    if (k === "className") node.className = v;
    else node.setAttribute(k, v === true ? "" : v);
  }
  if (text !== undefined) node.textContent = text;
  return node;
}

/* ---------------------------------------------------------------------------
 * Building a clip card
 * ------------------------------------------------------------------------ */

function buildInput(def, clip, inputId) {
  const value = clip.fields[def.field];
  const disabled = !library.editable;

  if (def.kind === "enum") {
    const select = el("select", { id: inputId, disabled });
    select.appendChild(el("option", { value: "" }, def.empty || "—"));
    for (const opt of library.options[def.options]) {
      select.appendChild(el("option", { value: opt }, opt[0].toUpperCase() + opt.slice(1)));
    }
    select.value = value || "";
    return select;
  }

  if (def.kind === "weight") {
    const select = el("select", { id: inputId, disabled });
    const current = value ?? 0.5;
    const known = WEIGHTS.some(([w]) => Math.abs(w - current) < 1e-6);
    for (const [w, label] of WEIGHTS) select.appendChild(el("option", { value: w }, label));
    if (!known) select.appendChild(el("option", { value: current }, `Custom (${current})`));
    select.value = String(current);
    return select;
  }

  if (def.kind === "notes") {
    const area = el("textarea", { id: inputId, rows: 2, disabled });
    area.value = value || "";
    return area;
  }

  const input = el("input", { type: "text", id: inputId, placeholder: def.placeholder, disabled,
                              list: def.suggest ? `suggest-${def.field}` : null, autocomplete: "off" });
  input.value = displayValue(def, value);
  return input;
}

function buildField(def, clip) {
  const inputId = `f-${clip.artifact_id}-${def.field}`;
  const wrap = el("label", { className: `clip-field${def.span === 2 ? " span-2" : ""}`, for: inputId });
  wrap.appendChild(el("span", {}, def.label));
  const input = buildInput(def, clip, inputId);
  wrap.appendChild(input);
  const status = el("span", { className: "field-status", "aria-live": "polite" });
  wrap.appendChild(status);

  input.addEventListener("change", () => saveField(clip, def, input, wrap, status));
  return wrap;
}

function buildCard(clip) {
  const card = el("article", { className: "clip-card", "data-id": clip.artifact_id });

  const media = el("div", { className: "clip-media" });
  if (clip.media_url && clip.artifact_type !== "X-roll") {
    // "#t=0.5" makes the browser show a frame from the clip as its picture.
    media.appendChild(el("video", { src: `${encodeURI(clip.media_url)}#t=0.5`, controls: true,
                                    preload: "metadata", playsinline: true }));
  } else if (clip.media_url) {
    media.appendChild(el("div", { className: "clip-audio-only" }, "Sound only (X-roll)"));
    media.appendChild(el("audio", { src: encodeURI(clip.media_url), controls: true, preload: "none" }));
  }
  media.appendChild(el("div", { className: "clip-meta" },
    `${clip.filename || ""}${clip.duration_seconds ? ` · ${formatSeconds(clip.duration_seconds)}` : ""}`));
  card.appendChild(media);

  const body = el("div", { className: "clip-body" });
  const head = el("div", { className: "clip-head" });
  head.appendChild(el("span", { className: `type-badge ${typeClass(clip.artifact_type)}` }, clip.artifact_type || ""));
  const title = el("h3", {}, clip.fields.title || clip.artifact_id);
  head.appendChild(title);
  const state = el("span", { className: `label-state${clip.labelled ? " done" : ""}` },
                   clip.labelled ? "Labelled" : "Needs labels");
  head.appendChild(state);
  body.appendChild(head);

  const groups = el("div", { className: "clip-groups" });
  for (const group of GROUPS) {
    const fs = el("fieldset", { className: `clip-group${group.wide ? " clip-group-wide" : ""}` });
    fs.appendChild(el("legend", {}, group.legend + (group.hint ? ` · ${group.hint}` : "")));
    const fields = el("div", { className: "clip-group-fields" });
    for (const def of group.fields) fields.appendChild(buildField(def, clip));
    fs.appendChild(fields);
    groups.appendChild(fs);
  }
  body.appendChild(groups);
  card.appendChild(body);
  return card;
}

/* ---------------------------------------------------------------------------
 * Saving
 * ------------------------------------------------------------------------ */

async function saveField(clip, def, input, wrap, status) {
  let value = input.value;
  if (def.field === "tags") {
    // Keep the auto-detected colour tags the form doesn't show.
    value = [...value.split(","), ...hiddenTags(clip)].join(",");
  }
  status.className = "field-status";
  status.textContent = "Saving…";
  try {
    const res = await fetch(
      `/api/library/${encodeURIComponent(library.collection.id)}/${encodeURIComponent(clip.artifact_id)}`,
      { method: "PATCH", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ [def.field]: value }) },
    );
    const data = await res.json();
    if (!res.ok) {
      const message = (data.errors && data.errors[def.field]) || data.error || `Not saved (${res.status}).`;
      wrap.classList.add("invalid");
      status.className = "field-status error";
      status.textContent = message;
      return;
    }
    // Show the value as stored (dates tidied, duplicates removed).
    Object.assign(clip, data);
    input.value = def.kind === "weight" ? String(clip.fields.weight ?? 0.5) : displayValue(def, clip.fields[def.field]);
    wrap.classList.remove("invalid");
    status.className = "field-status saved";
    status.textContent = "Saved";
    setTimeout(() => { if (status.textContent === "Saved") status.textContent = ""; }, 2500);

    const card = wrap.closest(".clip-card");
    card.querySelector("h3").textContent = clip.fields.title || clip.artifact_id;
    const state = card.querySelector(".label-state");
    state.className = `label-state${clip.labelled ? " done" : ""}`;
    state.textContent = clip.labelled ? "Labelled" : "Needs labels";
    updateSummary();
  } catch (e) {
    wrap.classList.add("invalid");
    status.className = "field-status error";
    status.textContent = "Not saved — is the engine still running?";
  }
}

/* ---------------------------------------------------------------------------
 * Loading, filtering, rendering
 * ------------------------------------------------------------------------ */

function visibleClips() {
  const q = searchInput.value.trim().toLowerCase();
  const filter = filterSelect.value;
  return library.clips.filter((c) => {
    if (filter === "labelled" && !c.labelled) return false;
    if (filter === "unlabelled" && c.labelled) return false;
    if (!q) return true;
    return `${c.fields.title || ""} ${c.filename || ""}`.toLowerCase().includes(q);
  });
}

function updateSummary() {
  const total = library.clips.length;
  const done = library.clips.filter((c) => c.labelled).length;
  summaryEl.textContent = total
    ? `${library.collection.name}: ${total} clip${total === 1 ? "" : "s"}, ${done} labelled, ${total - done} still need labels.`
    : `${library.collection.name} has no clips yet. Drop video or audio into its assets folders, then reload this page.`;
}

function renderSuggestions() {
  document.querySelectorAll("datalist[data-suggest]").forEach((d) => d.remove());
  for (const [field, values] of Object.entries(library.suggestions)) {
    const list = el("datalist", { id: `suggest-${field}`, "data-suggest": true });
    for (const v of values) list.appendChild(el("option", { value: v }));
    document.body.appendChild(list);
  }
}

function render() {
  clipList.innerHTML = "";
  const clips = visibleClips();
  if (!clips.length) {
    clipList.appendChild(el("p", { className: "clip-empty" },
      library.clips.length ? "No clips match this search." : "No clips in this topic yet."));
    return;
  }
  for (const clip of clips) clipList.appendChild(buildCard(clip));
}

async function loadLibrary(topicId) {
  summaryEl.textContent = "Loading clips…";
  clipList.innerHTML = "";
  try {
    const res = await fetch(`/api/library/${encodeURIComponent(topicId)}`);
    library = await res.json();
    if (!res.ok) throw new Error(library.error || res.status);
  } catch (e) {
    summaryEl.textContent = `Couldn't load clips: ${e.message}`;
    return;
  }
  readonlyNote.classList.toggle("hidden", library.editable);
  renderSuggestions();
  updateSummary();
  render();
}

async function loadTopics() {
  try {
    collections = await (await fetch("/api/collections")).json();
  } catch (e) {
    summaryEl.textContent = "Couldn't reach the engine. Is it running?";
    return;
  }
  for (const c of collections) {
    const count = c.artifact_counts?.total || 0;
    topicSelect.appendChild(el("option", { value: c.id }, `${c.name} (${count} clip${count === 1 ? "" : "s"})`));
  }
  let saved = null;
  try { saved = localStorage.getItem(TOPIC_KEY); } catch (e) { /* not stored */ }
  const fallback = collections.find((c) => (c.artifact_counts?.total || 0) > 0) || collections[0];
  topicSelect.value = collections.some((c) => c.id === saved) ? saved : fallback?.id;
  if (topicSelect.value) loadLibrary(topicSelect.value);
}

topicSelect.addEventListener("change", () => {
  try { localStorage.setItem(TOPIC_KEY, topicSelect.value); } catch (e) { /* not stored */ }
  loadLibrary(topicSelect.value);
});
searchInput.addEventListener("input", () => library && render());
filterSelect.addEventListener("change", () => library && render());

loadTopics();
