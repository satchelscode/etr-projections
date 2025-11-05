// =======================================================
// helpers
// =======================================================
async function fetchJSON(url, opts = {}) {
  const res = await fetch(url, opts);
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

function toCSV(rows) {
  if (!rows || !rows.length) return "";
  const headers = Object.keys(rows[0]);
  const lines = [headers.join(",")];
  rows.forEach((r) => {
    lines.push(headers.map((h) => String(r[h] ?? "").replace(/"/g, '""')).join(","));
  });
  return lines.join("\n");
}

function norm(s) {
  return (s || "")
    .toLowerCase()
    .normalize("NFKD")
    .replace(/[\u0300-\u036f]/g, "")
    .replace(/[^a-z0-9 ]/g, "")
    .replace(/\s+/g, " ")
    .trim();
}


// =======================================================
// DOM
// =======================================================
let selPlayer, selOpp, inpMinutes;
let inpPlayerSearch, inpOppSearch;

let selRoster, selRosterOpp;
let selDefaultTeamMinutes;
let teamTblBody;

let loadRosterBtn, projectRosterBtn;


// =======================================================
// INIT
// =======================================================
async function init() {
  selPlayer = document.getElementById("player");
  selOpp = document.getElementById("opponent");
  inpMinutes = document.getElementById("minutes");
  inpPlayerSearch = document.getElementById("playerSearch");
  inpOppSearch = document.getElementById("opponentSearch");

  selRoster = document.getElementById("teamForRoster");
  selRosterOpp = document.getElementById("teamOpp");

  selDefaultTeamMinutes = document.getElementById("defaultTeamMinutes");

  teamTblBody = document.querySelector("#teamTbl tbody");

  loadRosterBtn = document.getElementById("loadRosterBtn");
  projectRosterBtn = document.getElementById("projectRosterBtn");

  // load lists
  const allPlayers = await fetchJSON("/api/players");
  const allOpps = await fetchJSON("/api/opponents");
  const master = await fetchJSON("/api/players_master");

  fillSelect(selPlayer, allPlayers);
  fillSelect(selOpp, allOpps);

  // roster team dropdown
  fillSelect(selRoster, master.teams);
  fillSelect(selRosterOpp, master.teams);

  // type-to filter — single player
  attachSearch(inpPlayerSearch, selPlayer);
  attachSearch(inpOppSearch, selOpp);

  // single-player form
  document.getElementById("singleForm").addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const p = selPlayer.value;
    const o = selOpp.value;
    const m = Number(inpMinutes.value);
    if (!p || !o || !m) return;

    const out = await fetchJSON(`/api/project?player=${encodeURIComponent(p)}&opponent=${encodeURIComponent(o)}&minutes=${m}`);
    renderSingle(out);
  });

  // team load
  loadRosterBtn.addEventListener("click", async () => {
    const tm = selRoster.value;
    if (!tm) return;
    const roster = await fetchJSON(`/api/roster?team=${tm}`);
    renderRoster(roster, selRosterOpp.value, Number(selDefaultTeamMinutes.value));
  });

  // team project
  projectRosterBtn.addEventListener("click", async () => {
    await projectAllRows();
  });

  // CSV map
  window.csvMinutesMap = new Map();
}
document.addEventListener("DOMContentLoaded", init);


// =======================================================
// dropdown filler
// =======================================================
function fillSelect(sel, items) {
  sel.innerHTML = "";
  items.forEach((i) => {
    const o = document.createElement("option");
    o.value = i;
    o.textContent = i;
    sel.appendChild(o);
  });
}

function attachSearch(input, select) {
  input.addEventListener("input", () => {
    const q = norm(input.value);
    for (let i = 0; i < select.options.length; i++) {
      const t = norm(select.options[i].textContent);
      select.options[i].style.display = t.includes(q) ? "" : "none";
    }
  });
}


// =======================================================
// Single player
// =======================================================
function renderSingle(rows) {
  const tb = document.querySelector("#singleTbl tbody");
  tb.innerHTML = "";
  rows.forEach((r) => {
    const tr = document.createElement("tr");
    ["player", "opponent", "minutes", "pts", "reb", "ast", "3pm", "stl", "blk", "to", "pra"].forEach((k) => {
      const td = document.createElement("td");
      td.textContent = r[k];
      tr.appendChild(td);
    });
    tb.appendChild(tr);
  });
}


// =======================================================
// Roster table
// =======================================================
function renderRoster(roster, opp, defMin) {
  teamTblBody.innerHTML = "";
  roster.forEach((p) => {
    const tr = document.createElement("tr");

    // Player
    const tdP = document.createElement("td");
    tdP.textContent = p;
    tr.appendChild(tdP);

    // Opp
    const tdO = document.createElement("td");
    tdO.textContent = opp;
    tr.appendChild(tdO);

    // Minutes
    const tdM = document.createElement("td");
    const inp = document.createElement("input");
    inp.type = "number";
    inp.value = defMin;
    tdM.appendChild(inp);
    tr.appendChild(tdM);

    // stats placeholders
    ["pts", "reb", "ast", "3pm", "stl", "blk", "to", "pra"].forEach(() => {
      const td = document.createElement("td");
      td.textContent = "";
      tr.appendChild(td);
    });

    teamTblBody.appendChild(tr);
  });
}


// =======================================================
// Bulk project
// =======================================================
async function projectAllRows() {
  const trs = [...teamTblBody.querySelectorAll("tr")];
  for (const tr of trs) {
    const tds = tr.querySelectorAll("td");
    const p = tds[0].textContent;
    const o = tds[1].textContent;
    const m = Number(tds[2].querySelector("input").value);

    const out = await fetchJSON(`/api/project?player=${encodeURIComponent(p)}&opponent=${encodeURIComponent(o)}&minutes=${m}`);
    const r = out[0];
    ["pts", "reb", "ast", "3pm", "stl", "blk", "to", "pra"].forEach((k, idx) => {
      tds[3 + idx].textContent = r[k];
    });
  }
}


// =======================================================
// CSV Upload → minutes map
// =======================================================

function parseCSV(raw) {
  const rows = [];
  let row = [], cur = "";
  let inQ = false;

  function pushCell() {
    row.push(cur);
    cur = "";
  }
  function pushRow() {
    rows.push(row);
    row = [];
  }

  for (let i = 0; i < raw.length; i++) {
    const c = raw[i];
    if (inQ) {
      if (c === '"') {
        if (raw[i + 1] === '"') {
          cur += '"';
          i++;
        } else {
          inQ = false;
        }
      } else {
        cur += c;
      }
    } else {
      if (c === '"') {
        inQ = true;
      } else if (c === ",") {
        pushCell();
      } else if (c === "\n" || c === "\r") {
        if (c === "\r" && raw[i + 1] === "\n") i++;
        pushCell();
        pushRow();
      } else {
        cur += c;
      }
    }
  }
  pushCell();
  pushRow();

  if (!rows.length) return { headers: [], data: [] };
  const headers = rows[0].map((h) => h.trim());
  const data = rows.slice(1).map((r) => {
    const o = {};
    headers.forEach((h, i) => {
      o[h] = (r[i] ?? "").toString().trim();
    });
    return o;
  });
  return { headers, data };
}

document.getElementById("minsCsv")?.addEventListener("change", async (ev) => {
  const status = document.getElementById("uploadStatus");
  const file = ev.target.files?.[0];
  if (!file) return;
  const text = await file.text();

  const { headers, data } = parseCSV(text);

  const lower = Object.fromEntries(headers.map(h => [h.toLowerCase(), h]));
  const playerH = lower.player || lower.name;
  const minH = lower.minutes || lower.mins;
  const oppH = lower.opponent || lower.opp || lower.team;

  if (!playerH || !minH) {
    status.textContent = "CSV must have player + minutes";
    return;
  }

  window.csvMinutesMap.clear();
  let loaded = 0;

  data.forEach((r) => {
    const key = norm(r[playerH]);
    if (!key) return;
    const m = Number(r[minH]);
    if (!Number.isFinite(m)) return;

    const info = { minutes: m };
    if (oppH) {
      const opp = r[oppH]?.toUpperCase();
      if (/^[A-Z]{2,4}$/.test(opp)) info.opp = opp;
    }
    window.csvMinutesMap.set(key, info);
    loaded++;
  });

  status.textContent = `Loaded minutes for ${loaded} players`;
});


// =======================================================
// global CSV buttons
// =======================================================
window.__applyCsvMinutes = function () {
  const status = document.getElementById("uploadStatus");
  let applied = 0;

  [...teamTblBody.querySelectorAll("tr")].forEach(tr => {
    const tds = tr.querySelectorAll("td");
    const key = norm(tds[0].textContent);

    if (window.csvMinutesMap.has(key)) {
      const info = window.csvMinutesMap.get(key);
      const minInput = tds[2].querySelector("input");
      if (info.minutes != null && minInput) {
        minInput.value = info.minutes;
        applied++;
      }
      if (info.opp) {
        tds[1].textContent = info.opp;
      }
    }
  });

  status.textContent = applied
    ? `Applied minutes to ${applied} players`
    : `No matching players`;
};


window.__downloadMinutesTemplate = function () {
  const tbody = teamTblBody;
  let rows = [];

  [...tbody.querySelectorAll("tr")].forEach(tr => {
    const tds = tr.querySelectorAll("td");
    rows.push({
      Player: tds[0].textContent,
      Opponent: tds[1].textContent,
      Minutes: tds[2].querySelector("input")?.value ?? ""
    });
  });

  if (!rows.length) rows = [{ Player: "", Opponent: "", Minutes: "" }];

  const csv = toCSV(rows);
  const blob = new Blob([csv], { type: "text/csv" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = "minutes_template.csv";
  a.click();
  URL.revokeObjectURL(a.href);
};
