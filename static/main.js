// =============== helpers ===============
async function fetchJSON(url, opts = {}) {
  const res = await fetch(url, opts);
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

function toCSV(rows) {
  if (!rows || !rows.length) return "";
  const headers = Object.keys(rows[0]);
  const out = [headers.join(",")];
  rows.forEach(r => {
    out.push(headers.map(h => String(r[h] ?? "").replace(/"/g, '""')).join(","));
  });
  return out.join("\n");
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

// =============== state / DOM ===============
let selPlayer, selOpp, inpMinutes;
let inpPlayerSearch, inpOppSearch;

let selRosterTeam, selOpponentTeam, inpDefaultMinutes;
let btnLoadRoster, btnProjectAll, btnDownloadCsv;
let teamTblBody;

// =============== init ===============
document.addEventListener("DOMContentLoaded", async () => {
  // single player
  selPlayer = document.getElementById("player");
  selOpp = document.getElementById("opponent");
  inpMinutes = document.getElementById("minutes");
  inpPlayerSearch = document.getElementById("playerSearch");
  inpOppSearch = document.getElementById("opponentSearch");

  // team sheet
  selRosterTeam = document.getElementById("teamForRoster");
  selOpponentTeam = document.getElementById("teamOpp");
  inpDefaultMinutes = document.getElementById("defaultTeamMinutes");
  btnLoadRoster = document.getElementById("loadRosterBtn");
  btnProjectAll = document.getElementById("projectRosterBtn");
  btnDownloadCsv = document.getElementById("downloadCsvBtn");
  teamTblBody = document.querySelector("#teamTbl tbody");

  // populate dropdowns
  const [players, opponents, master] = await Promise.all([
    fetchJSON("/api/players"),
    fetchJSON("/api/opponents"),
    fetchJSON("/api/players_master"),
  ]);

  fillSelect(selPlayer, players);
  fillSelect(selOpp, opponents);
  fillSelect(selRosterTeam, master.teams);
  fillSelect(selOpponentTeam, master.teams);

  // type-to-filter for selects
  attachTypeFilter(inpPlayerSearch, selPlayer);
  attachTypeFilter(inpOppSearch, selOpp);

  // single player submit
  document.getElementById("singleForm").addEventListener("submit", async (e) => {
    e.preventDefault();
    const p = selPlayer.value;
    const o = selOpp.value;
    const m = Number(inpMinutes.value);
    if (!p || !o || !Number.isFinite(m)) return;
    const rows = await fetchJSON(
      `/api/project?player=${encodeURIComponent(p)}&opponent=${encodeURIComponent(o)}&minutes=${m}`
    );
    renderSingle(rows);
  });

  // team sheet actions
  btnLoadRoster.addEventListener("click", async () => {
    const team = selRosterTeam.value;
    if (!team) return;
    const roster = await fetchJSON(`/api/roster?team=${encodeURIComponent(team)}`);
    renderRoster(roster, selOpponentTeam.value, Number(inpDefaultMinutes.value) || 30);
  });

  btnProjectAll.addEventListener("click", async () => {
    await projectAllRows();
  });

  btnDownloadCsv.addEventListener("click", () => {
    const rows = extractTeamRows();
    const csv = toCSV(rows);
    const blob = new Blob([csv], { type: "text/csv" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = "team_projections.csv";
    a.click();
    URL.revokeObjectURL(a.href);
  });
});

// =============== UI helpers ===============
function fillSelect(sel, items) {
  sel.innerHTML = "";
  items.forEach(v => {
    const o = document.createElement("option");
    o.value = v;
    o.textContent = v;
    sel.appendChild(o);
  });
}

function attachTypeFilter(input, select) {
  input.addEventListener("input", () => {
    const q = norm(input.value);
    for (let i = 0; i < select.options.length; i++) {
      const txt = norm(select.options[i].textContent);
      select.options[i].style.display = txt.includes(q) ? "" : "none";
    }
  });
}

// =============== single player table ===============
function renderSingle(rows) {
  const tb = document.querySelector("#singleTbl tbody");
  tb.innerHTML = "";
  rows.forEach(r => {
    const tr = document.createElement("tr");
    ["player","opponent","minutes","pts","reb","ast","3pm","stl","blk","to","pra"].forEach(k => {
      const td = document.createElement("td");
      td.textContent = r[k];
      tr.appendChild(td);
    });
    tb.appendChild(tr);
  });
}

// =============== team sheet table ===============
function renderRoster(rosterPlayers, opponentTeam, defaultMinutes) {
  teamTblBody.innerHTML = "";
  rosterPlayers.forEach(name => {
    const tr = document.createElement("tr");

    const tdP = document.createElement("td");
    tdP.textContent = name;
    tr.appendChild(tdP);

    const tdO = document.createElement("td");
    tdO.textContent = opponentTeam || "";
    tr.appendChild(tdO);

    const tdM = document.createElement("td");
    const inp = document.createElement("input");
    inp.type = "number";
    inp.value = Number.isFinite(defaultMinutes) ? defaultMinutes : 30;
    tdM.appendChild(inp);
    tr.appendChild(tdM);

    // empty stat columns for now
    ["pts","reb","ast","3pm","stl","blk","to","pra"].forEach(() => {
      const td = document.createElement("td");
      td.textContent = "";
      tr.appendChild(td);
    });

    teamTblBody.appendChild(tr);
  });
}

async function projectAllRows() {
  const trs = [...teamTblBody.querySelectorAll("tr")];
  for (const tr of trs) {
    const tds = tr.querySelectorAll("td");
    const player = tds[0].textContent;
    const opp = tds[1].textContent;
    const mins = Number(tds[2].querySelector("input").value);
    if (!player || !opp || !Number.isFinite(mins)) continue;

    const out = await fetchJSON(
      `/api/project?player=${encodeURIComponent(player)}&opponent=${encodeURIComponent(opp)}&minutes=${mins}`
    );
    const r = out[0] || {};
    const statKeys = ["pts","reb","ast","3pm","stl","blk","to","pra"];
    statKeys.forEach((k, i) => {
      tds[3 + i].textContent = r[k] ?? "";
    });
  }
}

function extractTeamRows() {
  const rows = [];
  const trs = [...teamTblBody.querySelectorAll("tr")];
  trs.forEach(tr => {
    const tds = tr.querySelectorAll("td");
    rows.push({
      Player: tds[0].textContent,
      Opponent: tds[1].textContent,
      Minutes: tds[2].querySelector("input")?.value ?? "",
      PTS: tds[3].textContent,
      REB: tds[4].textContent,
      AST: tds[5].textContent,
      "3PM": tds[6].textContent,
      STL: tds[7].textContent,
      BLK: tds[8].textContent,
      TO:  tds[9].textContent,
      PRA: tds[10].textContent,
    });
  });
  return rows;
}
