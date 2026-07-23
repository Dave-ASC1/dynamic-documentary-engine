const generateBtn = document.getElementById("generate-btn");
const durationInput = document.getElementById("duration");
const diversityToggle = document.getElementById("diversity-toggle");
const exactDurationToggle = document.getElementById("exact-duration-toggle");
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

function formatSeconds(s) {
  if (s == null) return "?";
  return `${Math.round(s)}s`;
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
    const res = await fetch(`/api/films/${encodeURIComponent(filename)}`, { method: "DELETE" });
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
  try {
    const res = await fetch("/api/films");
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

async function generateFilm() {
  const target = parseInt(durationInput.value, 10) || 90;
  generateBtn.disabled = true;
  setStatus("Generating a unique sequence and rendering the film…", "active");
  traceSection.classList.add("hidden");

  try {
    const res = await fetch("/api/generate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        target_duration: target,
        diversity_mode: diversityToggle.checked,
        exact_duration: exactDurationToggle.checked,
      }),
    });
    const result = await res.json();

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
    generateBtn.disabled = false;
  }
}

generateBtn.addEventListener("click", generateFilm);
loadHistory();
