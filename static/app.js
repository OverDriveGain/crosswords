const KEY = "crosswords.config.v1";
const f = document.getElementById("f");
const statusEl = document.getElementById("status");
const goBtn = document.getElementById("go");
const resetBtn = document.getElementById("reset");
const progEl = document.getElementById("progress");
const barFill = document.getElementById("bar-fill");
const progText = document.getElementById("progress-text");
const fields = ["from_date", "max_count", "target_page"];

const PHASE_LABEL = {
  queued: "Queued",
  scanning: "Scanning addiyar",
  downloading: "Downloading PDFs",
  processing: "Cropping crossword",
};
// Three phases of equal weight in the overall bar
const PHASE_WEIGHT = { scanning: 0, downloading: 1, processing: 2 };

function readForm() {
  const obj = {};
  for (const k of fields) obj[k] = document.getElementById(k).value;
  obj.max_count = parseInt(obj.max_count, 10);
  obj.target_page = parseInt(obj.target_page, 10);
  return obj;
}

function writeForm(cfg) {
  for (const k of fields) document.getElementById(k).value = cfg[k];
}

function save(cfg) {
  localStorage.setItem(KEY, JSON.stringify(cfg));
}

async function loadDefaults() {
  const r = await fetch("/api/defaults");
  return r.json();
}

async function init() {
  let cfg;
  try { cfg = JSON.parse(localStorage.getItem(KEY) || "null"); } catch {}
  if (!cfg) cfg = await loadDefaults();
  if (cfg.max_count > 15) cfg.max_count = 15;
  writeForm(cfg);
}

resetBtn.addEventListener("click", async () => {
  const cfg = await loadDefaults();
  writeForm(cfg);
  save(cfg);
  setStatus("Restored defaults.", "ok");
});

function setStatus(msg, cls = "") {
  statusEl.className = cls;
  statusEl.textContent = msg;
}

function setProgress(ev) {
  progEl.hidden = false;
  const phaseIdx = PHASE_WEIGHT[ev.phase] ?? 0;
  const phaseFrac = ev.total > 0 ? ev.done / ev.total : 0;
  const overall = ((phaseIdx + phaseFrac) / 3) * 100;
  barFill.style.width = `${Math.min(100, overall).toFixed(1)}%`;
  const label = PHASE_LABEL[ev.phase] || ev.phase;
  const detail = ev.current ? ` — ${ev.current}` : "";
  progText.textContent = `${label}: ${ev.done}/${ev.total}${detail}`;
}

function resetProgress() {
  progEl.hidden = true;
  barFill.style.width = "0%";
  progText.textContent = "";
}

async function downloadPdf(url, lastDate) {
  const r = await fetch(url);
  if (!r.ok) throw new Error(`PDF fetch failed: ${r.status}`);
  const blob = await r.blob();
  const objUrl = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = objUrl;
  a.download = `crosswords-${(lastDate || "").replaceAll("/", "-")}.pdf`;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(objUrl);
}

f.addEventListener("submit", async (e) => {
  e.preventDefault();
  const cfg = readForm();
  if (cfg.max_count > 15) cfg.max_count = 15;
  save(cfg);
  setStatus("Starting…", "busy");
  resetProgress();
  goBtn.disabled = true;

  try {
    const r = await fetch("/api/run", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(cfg),
    });
    if (!r.ok) throw new Error(`${r.status} — ${await r.text()}`);
    const { job_id } = await r.json();

    const es = new EventSource(`/api/jobs/${job_id}/events`);
    setStatus("", "busy");
    progEl.hidden = false;

    await new Promise((resolve, reject) => {
      es.addEventListener("progress", (msg) => {
        try { setProgress(JSON.parse(msg.data)); } catch {}
      });
      es.addEventListener("done", async (msg) => {
        es.close();
        try {
          const data = JSON.parse(msg.data);
          barFill.style.width = "100%";
          progText.textContent = `Done — ${data.count} crossword${data.count === 1 ? "" : "s"}`;
          await downloadPdf(data.pdf_url, data.last);
          if (data.next) {
            document.getElementById("from_date").value = data.next;
            save(readForm());
          }
          setStatus(`Got ${data.count} crossword${data.count === 1 ? "" : "s"} (${data.first} → ${data.last}). Next from-date set to ${data.next}.`, "ok");
          resolve();
        } catch (err) { reject(err); }
      });
      es.addEventListener("error", (msg) => {
        es.close();
        let m = "Stream error";
        try { m = JSON.parse(msg.data).message; } catch {}
        reject(new Error(m));
      });
    });
  } catch (err) {
    setStatus(err.message || String(err), "err");
    resetProgress();
  } finally {
    goBtn.disabled = false;
  }
});

init();
