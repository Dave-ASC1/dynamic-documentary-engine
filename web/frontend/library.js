/* Clip library — label clips in a table.
 *
 * One row per clip; the clip column comes from the topic's folders (the
 * media sync detects new files), so rows always match the engine. Every cell
 * saves on its own as soon as it changes, through
 * PATCH /api/library/<topic>/<clip>: the server checks the value, writes the
 * topic's clip list and keeps a backup, and the next film uses it.
 *
 * Enter saves a cell and moves down to the same column in the next row, so a
 * column of dates can be typed straight through. Nothing here builds HTML
 * from clip data: titles and labels are always set as text.
 */

const topicSelect = document.getElementById("topic-select");
const searchInput = document.getElementById("search");
const filterSelect = document.getElementById("filter-select");
const summaryEl = document.getElementById("summary");
const readonlyNote = document.getElementById("readonly-note");
const rowsEl = document.getElementById("clip-rows");
const themeToggle = document.getElementById("theme-toggle");
const previewDialog = document.getElementById("preview-dialog");
const previewTitle = document.getElementById("preview-title");
const previewBody = document.getElementById("preview-body");
const previewStatus = document.getElementById("preview-status");

const TOPIC_KEY = "dde-library-topic";
const COLUMN_COUNT = 9;
const MONTHS = ["January", "February", "March", "April", "May", "June", "July",
                "August", "September", "October", "November", "December"];

// How often a clip appears: the engine's weight, in plain words.
const WEIGHTS = [[0.2, "Rarely"], [0.35, "Less often"], [0.5, "Normal"], [0.7, "More often"], [0.9, "Often"]];

// Table columns after the clip name. kind: text | list | enum | date
const COLUMNS = [
  { field: "title", label: "Title", kind: "text" },
  { field: "context.date", label: "Date", kind: "date", placeholder: "e.g. 18 Dec 1944", cell: "cell-date" },
  { field: "context.season", label: "Season", kind: "enum", options: "seasons", empty: "Auto", cell: "cell-season" },
  { field: "mood", label: "Mood", kind: "text", placeholder: "e.g. somber", suggest: true },
  { field: "tags", label: "Tags", kind: "list", placeholder: "comma, separated" },
  { field: "people", label: "People", kind: "list", placeholder: "e.g. G. Moore", suggest: true },
  { field: "geography", label: "Place", kind: "text", placeholder: "e.g. Camp Swift", suggest: true },
];

// Less-used labels, in the details row under each clip.
const DETAILS = [
  { field: "weight", label: "How often it appears", kind: "weight" },
  { field: "pacing", label: "Pacing", kind: "enum", options: "pacing" },
  { field: "dominant_lines", label: "Line direction", kind: "enum", options: "dominant_lines" },
  { field: "theme", label: "Themes", kind: "list", placeholder: "e.g. training, homecoming", span: 3 },
  { field: "notes", label: "Notes (for people, not used by the engine)", kind: "notes", span: 3 },
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

function capital(s) { return s[0].toUpperCase() + s.slice(1); }

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
 * Inputs
 * ------------------------------------------------------------------------ */

function buildInput(def, clip, className) {
  const value = clip.fields[def.field];
  const disabled = !library.editable;
  const label = `${def.label} — ${clip.fields.title || clip.artifact_id}`;

  if (def.kind === "enum") {
    const select = el("select", { className, disabled, "aria-label": label });
    select.appendChild(el("option", { value: "" }, def.empty || "—"));
    for (const opt of library.options[def.options]) select.appendChild(el("option", { value: opt }, capital(opt)));
    select.value = value || "";
    return select;
  }

  if (def.kind === "weight") {
    const select = el("select", { className, disabled, "aria-label": label });
    const current = value ?? 0.5;
    const known = WEIGHTS.some(([w]) => Math.abs(w - current) < 1e-6);
    for (const [w, text] of WEIGHTS) select.appendChild(el("option", { value: w }, text));
    if (!known) select.appendChild(el("option", { value: current }, `Custom (${current})`));
    select.value = String(current);
    return select;
  }

  if (def.kind === "notes") {
    const area = el("textarea", { className, rows: 2, disabled, "aria-label": label });
    area.value = value || "";
    return area;
  }

  const input = el("input", { type: "text", className, placeholder: def.placeholder, disabled,
                              list: def.suggest ? `suggest-${def.field}` : null, autocomplete: "off",
                              "aria-label": label });
  input.value = displayValue(def, value);
  return input;
}

// Enter: save (via the change event) and move down to the same column in
// the next visible row — quick for filling a column of dates.
function onCellKeydown(event) {
  if (event.key !== "Enter" || event.target.tagName === "TEXTAREA") return;
  event.preventDefault();
  const input = event.target;
  const td = input.closest("td");
  const col = td.cellIndex;
  let row = input.closest("tr").nextElementSibling;
  while (row && !row.classList.contains("clip-row")) row = row.nextElementSibling;
  input.blur();
  const next = row && row.cells[col] && row.cells[col].querySelector(".cell-input");
  if (next) next.focus();
}

/* ---------------------------------------------------------------------------
 * Rows
 * ------------------------------------------------------------------------ */

function buildRow(clip) {
  const tr = el("tr", { className: "clip-row", "data-id": clip.artifact_id });

  const nameCell = el("td", { className: "clip-name" });
  const cell = el("div", { className: "clip-cell" });
  cell.appendChild(buildThumb(clip));
  const text = el("div");
  const fileName = (clip.filename || clip.artifact_id).split("/").pop();
  text.appendChild(el("div", { className: "file", title: fileName }, fileName));
  const sub = el("div", { className: "sub" });
  sub.appendChild(el("span", { className: `type-badge ${typeClass(clip.artifact_type)}` }, clip.artifact_type || ""));
  sub.appendChild(el("span", {}, formatSeconds(clip.duration_seconds)));
  text.appendChild(sub);
  cell.appendChild(text);
  nameCell.appendChild(cell);
  tr.appendChild(nameCell);

  for (const def of COLUMNS) {
    const td = el("td", { className: def.cell || null });
    const input = buildInput(def, clip, "cell-input");
    input.addEventListener("change", () => saveField(clip, def, input, td));
    input.addEventListener("keydown", onCellKeydown);
    td.appendChild(input);
    tr.appendChild(td);
  }

  const moreCell = el("td");
  const more = el("button", { type: "button", className: "more-btn", "aria-expanded": "false" }, "Details ▾");
  more.addEventListener("click", () => toggleDetails(clip, tr, more));
  moreCell.appendChild(more);
  tr.appendChild(moreCell);
  return tr;
}

// A still from the clip that is also its play button. Sound-only clips get
// a note symbol instead of a picture.
function buildThumb(clip) {
  const name = clip.fields.title || clip.artifact_id;
  const audio = !clip.thumbnail_url;
  const button = el("button", { type: "button", className: `thumb${audio ? " thumb-audio" : ""}`,
                                "aria-label": `Play ${name}`, title: `Play ${name}` });
  if (!audio) {
    const img = el("img", { src: clip.thumbnail_url, alt: "", loading: "lazy", decoding: "async" });
    img.addEventListener("error", () => img.remove());   // dark tile + play button remain
    button.appendChild(img);
  }
  button.appendChild(el("span", { className: "play", "aria-hidden": "true" }, "\u25B6"));
  button.addEventListener("click", () => openPreview(clip));
  return button;
}

/* ---------------------------------------------------------------------------
 * Preview player (opens over the table)
 * ------------------------------------------------------------------------ */

function openPreview(clip) {
  previewTitle.textContent = clip.fields.title || clip.artifact_id;
  previewBody.innerHTML = "";
  previewStatus.textContent = "";
  let media;
  if (clip.preview_url) {
    // The first play of a clip makes its small preview copy, which can take
    // a few seconds for long or 4K footage; it's instant after that.
    media = el("video", { src: clip.preview_url, controls: true, autoplay: true, playsinline: true,
                          poster: clip.thumbnail_url || null });
    previewStatus.textContent = "Preparing preview…";
  } else if (clip.media_url) {
    media = el("audio", { src: encodeURI(clip.media_url), controls: true, autoplay: true });
  } else {
    previewStatus.textContent = "This clip has no file to play.";
  }
  if (media) {
    media.addEventListener("canplay", () => {
      previewStatus.textContent = `${clip.filename || ""}${clip.duration_seconds ? ` · ${formatSeconds(clip.duration_seconds)}` : ""}`;
    });
    media.addEventListener("error", () => {
      previewStatus.textContent = "This clip couldn't be played. The engine may not be able to read its file.";
    });
    previewBody.appendChild(media);
  }
  previewDialog.showModal();
}

function closePreview() {
  if (previewDialog.open) previewDialog.close();
}

// Closing stops playback (also on Esc, which closes the dialog by itself).
previewDialog.addEventListener("close", () => { previewBody.innerHTML = ""; });
document.getElementById("preview-close").addEventListener("click", closePreview);
// A click on the dimmed area outside the player closes it.
previewDialog.addEventListener("click", (event) => {
  if (event.target === previewDialog) closePreview();
});

function toggleDetails(clip, tr, button) {
  const open = tr.nextElementSibling && tr.nextElementSibling.classList.contains("detail-row");
  if (open) {
    tr.nextElementSibling.remove();
    tr.classList.remove("open");
    button.setAttribute("aria-expanded", "false");
    button.textContent = "Details ▾";
    return;
  }
  tr.classList.add("open");
  button.setAttribute("aria-expanded", "true");
  button.textContent = "Close ▴";

  const detail = el("tr", { className: "detail-row" });
  const td = el("td", { colspan: COLUMN_COUNT });
  const grid = el("div", { className: "detail-grid" });

  const media = el("div", { className: "detail-media" });
  if (clip.preview_url) {
    media.appendChild(el("video", { src: clip.preview_url, controls: true, preload: "none",
                                    playsinline: true, poster: clip.thumbnail_url || null }));
  } else if (clip.media_url) {
    media.appendChild(el("div", { className: "detail-audio-only" }, "Sound only (X-roll)"));
    media.appendChild(el("audio", { src: encodeURI(clip.media_url), controls: true, preload: "none" }));
  }
  grid.appendChild(media);

  const fields = el("div", { className: "detail-fields" });
  for (const def of DETAILS) {
    const wrap = el("label", { className: `detail-field${def.span === 3 ? " span-3" : ""}` });
    wrap.appendChild(el("span", {}, def.label));
    const input = buildInput(def, clip, null);
    input.addEventListener("change", () => saveField(clip, def, input, wrap));
    wrap.appendChild(input);
    fields.appendChild(wrap);
  }
  grid.appendChild(fields);

  td.appendChild(grid);
  detail.appendChild(td);
  tr.after(detail);
}

/* ---------------------------------------------------------------------------
 * Saving
 * ------------------------------------------------------------------------ */

function showError(container, input, message) {
  input.classList.add("invalid");
  let err = container.querySelector(".cell-error");
  if (!err) {
    err = el("div", { className: "cell-error", role: "alert" });
    container.appendChild(err);
  }
  err.textContent = message;
}

function clearError(container, input) {
  input.classList.remove("invalid");
  const err = container.querySelector(".cell-error");
  if (err) err.remove();
}

async function saveField(clip, def, input, container) {
  let value = input.value;
  if (def.field === "tags") {
    // Keep the auto-detected colour tags the table doesn't show.
    value = [...value.split(","), ...hiddenTags(clip)].join(",");
  }
  try {
    const res = await fetch(
      `/api/library/${encodeURIComponent(library.collection.id)}/${encodeURIComponent(clip.artifact_id)}`,
      { method: "PATCH", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ [def.field]: value }) },
    );
    const data = await res.json();
    if (!res.ok) {
      showError(container, input,
        (data.errors && data.errors[def.field]) || data.error || `Not saved (${res.status}).`);
      return;
    }
    // Show the value as stored (dates tidied, duplicates removed).
    Object.assign(clip, data);
    input.value = def.kind === "weight" ? String(clip.fields.weight ?? 0.5) : displayValue(def, clip.fields[def.field]);
    clearError(container, input);
    input.classList.add("saved");
    setTimeout(() => input.classList.remove("saved"), 900);
    updateSummary();
  } catch (e) {
    showError(container, input, "Not saved — is the engine still running?");
  }
}

/* ---------------------------------------------------------------------------
 * Loading, filtering, rendering
 * ------------------------------------------------------------------------ */

function visibleClips() {
  const q = searchInput.value.trim().toLowerCase();
  const filter = filterSelect.value;
  return library.clips.filter((c) => {
    if (filter === "undated" && c.dated) return false;
    if (filter === "labelled" && !c.labelled) return false;
    if (filter === "unlabelled" && c.labelled) return false;
    if (!q) return true;
    return `${c.fields.title || ""} ${c.filename || ""}`.toLowerCase().includes(q);
  });
}

function updateSummary() {
  const total = library.clips.length;
  const dated = library.clips.filter((c) => c.dated).length;
  const done = library.clips.filter((c) => c.labelled).length;
  summaryEl.textContent = total
    ? `${library.collection.name}: ${total} clip${total === 1 ? "" : "s"} · ${dated} with a date or season · ${done} labelled.`
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
  rowsEl.innerHTML = "";
  const clips = visibleClips();
  if (!clips.length) {
    const tr = el("tr", { className: "table-empty" });
    tr.appendChild(el("td", { colspan: COLUMN_COUNT },
      library.clips.length ? "No clips match." : "No clips in this topic yet."));
    rowsEl.appendChild(tr);
    return;
  }
  for (const clip of clips) rowsEl.appendChild(buildRow(clip));
}

async function loadLibrary(topicId) {
  summaryEl.textContent = "Loading clips…";
  rowsEl.innerHTML = "";
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
