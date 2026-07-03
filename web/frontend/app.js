const generateBtn = document.getElementById("generate-btn");
const durationInput = document.getElementById("duration");
const statusEl = document.getElementById("status");
const playerSection = document.getElementById("player-section");
const player = document.getElementById("player");
const metaEl = document.getElementById("meta");
const traceSection = document.getElementById("trace-section");
const traceList = document.getElementById("trace-list");
const historyList = document.getElementById("history-list");

function setStatus(text, isError) {
  statusEl.textContent = text;
  statusEl.classList.toggle("error", Boolean(isError));
}

function formatSeconds(s) {
  if (s == null) return "?";
  return `${Math.round(s)}s`;
}

function renderTrace(result) {
  traceList.innerHTML = "";

  const openLi = document.createElement("li");
  openLi.innerHTML = `<span class="cut-badge">open</span><span class="cut-title">${result.opening}</span>`;
  traceList.appendChild(openLi);

  let step = 0;
  for (const ev of result.trace) {
    step += 1;
    const li = document.createElement("li");
    const badge = ev.kind === "pairing" ? "audio pairing" : `cut ${step}`;
    li.innerHTML = `
      <span class="cut-badge">${badge}</span>
      <span class="cut-title">${ev.chosen}</span>
      <div class="cut-contrast">contrast vs. previous: ${ev.contrast.join(", ")}</div>
    `;
    traceList.appendChild(li);
  }

  const closeLi = document.createElement("li");
  closeLi.innerHTML = `<span class="cut-badge">close</span><span class="cut-title">${result.closing}</span>`;
  traceList.appendChild(closeLi);

  traceSection.classList.remove("hidden");
}

function renderHistoryItem(entry) {
  const li = document.createElement("li");
  const when = entry.generated_at ? new Date(entry.generated_at).toLocaleTimeString() : "";
  li.innerHTML = `
    <a href="${entry.film_url}" target="_blank">${entry.filename}</a>
    <span class="history-meta">${formatSeconds(entry.actual_duration)} — ${when}</span>
  `;
  return li;
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
  setStatus("Generating a unique sequence and rendering the film...");
  traceSection.classList.add("hidden");

  try {
    const res = await fetch("/api/generate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ target_duration: target }),
    });
    const result = await res.json();

    if (!res.ok) {
      throw new Error(result.error || `Server returned ${res.status}`);
    }

    player.src = result.film_url;
    playerSection.classList.remove("hidden");
    metaEl.textContent =
      `${result.collection_name} — requested ${formatSeconds(result.target_duration)}, ` +
      `actual ${formatSeconds(result.actual_duration)} — ${result.slots.length} slots`;

    renderTrace(result);
    setStatus("Done.");
    await loadHistory();
  } catch (e) {
    setStatus(`Generation failed: ${e.message}`, true);
  } finally {
    generateBtn.disabled = false;
  }
}

generateBtn.addEventListener("click", generateFilm);
loadHistory();
