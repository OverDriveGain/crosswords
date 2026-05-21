const KEY = "crosswords.config.v1";
const f = document.getElementById("f");
const statusEl = document.getElementById("status");
const goBtn = document.getElementById("go");
const resetBtn = document.getElementById("reset");
const fields = ["from_date", "max_count", "target_page"];

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
  writeForm(cfg);
}

resetBtn.addEventListener("click", async () => {
  const cfg = await loadDefaults();
  writeForm(cfg);
  save(cfg);
  setStatus("Restored defaults from server.", "ok");
});

function setStatus(msg, cls = "") {
  statusEl.className = cls;
  statusEl.textContent = msg;
}

f.addEventListener("submit", async (e) => {
  e.preventDefault();
  const cfg = readForm();
  save(cfg);
  setStatus("Fetching… this can take a minute for large ranges.", "busy");
  goBtn.disabled = true;
  try {
    const r = await fetch("/api/run", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(cfg),
    });
    if (!r.ok) {
      const t = await r.text();
      throw new Error(`${r.status} — ${t}`);
    }
    const count = r.headers.get("X-Processed-Count");
    const firstDate = r.headers.get("X-First-Date");
    const lastDate = r.headers.get("X-Last-Date");
    const nextDate = r.headers.get("X-Next-Date");
    const blob = await r.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `crosswords-${(lastDate || "").replaceAll("/", "-")}.pdf`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
    if (nextDate) {
      document.getElementById("from_date").value = nextDate;
      save(readForm());
    }
    setStatus(`Got ${count} crossword${count === "1" ? "" : "s"} (${firstDate} → ${lastDate}). Next from-date set to ${nextDate}.`, "ok");
  } catch (err) {
    setStatus(err.message, "err");
  } finally {
    goBtn.disabled = false;
  }
});

init();
