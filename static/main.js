async function fetchJSON(url, opts = {}) {
  const res = await fetch(url, opts);
  if (!res.ok) throw new Error(`fetch error ${res.status}`);
  return res.json();
}

function fillSelect(sel, items) {
  if (!sel) return;
  sel.innerHTML = "";
  items.forEach(v => {
    const o = document.createElement("option");
    o.value = v; o.textContent = v;
    sel.appendChild(o);
  });
}

function toCSV(rows) {
  if (!rows.length) return "";
  const headers = Object.keys(rows[0]);
  const lines = [headers.join(",")];
  rows.forEach(r => {
    lines.push(headers.map(h => String(r[h] ?? "").replace(/"/g, '""')).join(","));
  });
  return lines.join("\n");
}

function downloadCsv(name, text) {
  const blob = new Blob([text], { type: "text/csv" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = name;
  a.click();
  URL.revokeObjectURL(a.href);
}

document.addEventListener("DOMContentLoaded", init);

async function init() {
  try {
    // SINGLE PLAYER ELEMENTS
    const selPlayer = document.getElementById("player");
    const selOpp = document.getElementById("opponent");
    const inpPsearch = document.getElementById("playerSearch");
    const inpOsearch = document.getElementById("opponentSearch");
    const inpMinutes = document.getElementById("minutes");
    const btnProject = document.getElementById("projectBtn");
    const tblSingle = document.getElementById("result");
    const tbodySingle = tblSingle?.querySelector("tbody");

    // TEAM SHEET ELEMENTS
    const selRosterTeam = document.getElementById("rosterTeam");
    const selOpponentTeam = document.getElementById("opponentTeam");
    const inpDefaultMin = document.getElementById("defaultTeamMinutes");
    const btnLoadRoster = document.getElementById("loadRosterBtn");
    const btnProjectRoster = document.getElementById("projectRosterBtn");
    const btnDownloadCsv = document.getElementById("downloadCsvBtn");
    const tblTeam = document.getElementById("teamTbl");
    const tbodyTeam = tblTeam?.querySelector("tbody");

    // Load base data
    const opponents = await fetchJSON("/api/opponents");

    // Always fill these three immediately so UI is never empty
    fillSelect(selOpp, opponents);
    fillSelect(selOpponentTeam, opponents);
    fillSelect(selRosterTeam, opponents); // <-- NEW: seed rosterTeam with NBA codes right away

    // Players for single-player select
    const allPlayers = await fetchJSON("/api/players");
    fillSelect(selPlayer, allPlayers);

    // Try to load players_master for real rosters (optional)
    try {
      const playersMaster = await fetchJSON("/api/players_master");
      const teamSet = [...new Set(
        playersMaster.map(r => String(r.Team || "").toUpperCase()).filter(Boolean)
      )].sort();

      // If players_master is present and non-empty, override rosterTeam with precise list
      if (teamSet.length) {
        fillSelect(selRosterTeam, teamSet);
      }
    } catch (_) {
      // ignore — we already seeded rosterTeam with opponents list
    }

    // Single-player filtering
    inpOsearch?.addEventListener("input", async (ev) => {
      const q = ev.target.value.trim().toLowerCase();
      const filtered = opponents.filter(t => t.toLowerCase().startsWith(q));
      fillSelect(selOpp, filtered.length ? filtered : opponents);
    });

    inpPsearch?.addEventListener("input", async (ev) => {
      const q = ev.target.value.trim().toLowerCase();
      const p = new URLSearchParams();
      if (q) p.set("q", q);
      const arr = await fetchJSON("/api/players?" + p.toString());
      fillSelect(selPlayer, arr);
    });

    // Single-player projections
    btnProject?.addEventListener("click", async () => {
      const player = selPlayer?.value || "";
      const opponent = selOpp?.value || "";
      const minutes = parseFloat(inpMinutes?.value || 0);
      if (!player || !opponent || !minutes) {
        alert("Please provide player, opponent, and minutes");
        return;
      }
      const out = await fetchJSON("/api/project", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ player, opponent, minutes })
      });

      if (!tbodySingle) return;
      tbodySingle.innerHTML = "";
      const tr = document.createElement("tr");
      [
        "player","opponent","minutes",
        "Proj_Points","Proj_Rebounds","Proj_Assists","Proj_Three Pointers Made",
        "Proj_Steals","Proj_Blocks","Proj_Turnovers","Proj_PRA"
      ].forEach(k => {
        const td = document.createElement("td");
        td.textContent = out[k] ?? "";
        tr.appendChild(td);
      });
      tbodySingle.appendChild(tr);
      tblSingle.style.display = "";
    });

    // Helper: get roster list for given team
    async function getRoster(team) {
      try {
        const pm = await fetchJSON("/api/players_master");
        const roster = pm
          .filter(r => String(r.Team || "").toUpperCase() === String(team).toUpperCase())
          .map(r => String(r.Player || ""))
          .filter(Boolean)
          .sort();
        if (roster.length) return roster;
      } catch (_) {
        // fall through to backend filter
      }
      // fallback: ask backend to filter
      const arr = await fetchJSON("/api/players?team=" + encodeURIComponent(team));
      return arr;
    }

    // Load roster button
    btnLoadRoster?.addEventListener("click", async () => {
      const rosterTeam = selRosterTeam?.value || "";
      if (!rosterTeam) return;

      const roster = await getRoster(rosterTeam);
      if (!tbodyTeam) return;

      tbodyTeam.innerHTML = "";
      const defMin = parseFloat(inpDefaultMin?.value || "30");
      const oppTeam = selOpponentTeam?.value || "";

      roster.forEach(p => {
        const tr = document.createElement("tr");

        const tdP = document.createElement("td"); tdP.textContent = p; tr.appendChild(tdP);
        const tdO = document.createElement("td"); tdO.textContent = oppTeam; tr.appendChild(tdO);

        const tdM = document.createElement("td");
        const mInput = document.createElement("input");
        mInput.type = "number"; mInput.step = "0.1"; mInput.value = String(defMin);
        tdM.appendChild(mInput);
        tr.appendChild(tdM);

        ["PTS","REB","AST","3PM","STL","BLK","TO","PRA"].forEach(() => {
          const td = document.createElement("td");
          td.textContent = "";
          tr.appendChild(td);
        });
        tbodyTeam.appendChild(tr);
      });

      tblTeam.style.display = "";
    });

    // Project all
    btnProjectRoster?.addEventListener("click", async () => {
      if (!tbodyTeam) return;
      const oppTeam = selOpponentTeam?.value || "";
      const rows = [];
      [...tbodyTeam.querySelectorAll("tr")].forEach(tr => {
        const tds = tr.querySelectorAll("td");
        if (tds.length < 3) return;
        const player = tds[0].textContent;
        const minutes = parseFloat(tds[2].querySelector("input")?.value || 0);
        rows.push({ player, opponent: oppTeam, minutes });
      });
      if (!rows.length) return;

      const out = await fetchJSON("/api/project_bulk", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ rows })
      });

      out.forEach((r, i) => {
        const tr = tbodyTeam.querySelectorAll("tr")[i];
        if (!tr) return;
        const tds = tr.querySelectorAll("td");
        if (tds.length < 11) return;
        tds[3].textContent = r.Proj_Points ?? "";
        tds[4].textContent = r.Proj_Rebounds ?? "";
        tds[5].textContent = r.Proj_Assists ?? "";
        tds[6].textContent = r["Proj_Three Pointers Made"] ?? "";
        tds[7].textContent = r.Proj_Steals ?? "";
        tds[8].textContent = r.Proj_Blocks ?? "";
        tds[9].textContent = r.Proj_Turnovers ?? "";
        tds[10].textContent = r.Proj_PRA ?? "";
      });
    });

    // Download CSV
    btnDownloadCsv?.addEventListener("click", () => {
      if (!tbodyTeam) return;
      const rows = [];
      [...tbodyTeam.querySelectorAll("tr")].forEach(tr => {
        const tds = tr.querySelectorAll("td");
        if (tds.length < 11) return;
        rows.push({
          Player: tds[0].textContent,
          Opp: tds[1].textContent,
          Minutes: tds[2].querySelector("input")?.value || "",
          PTS: tds[3].textContent,
          REB: tds[4].textContent,
          AST: tds[5].textContent,
          "3PM": tds[6].textContent,
          STL: tds[7].textContent,
          BLK: tds[8].textContent,
          TO: tds[9].textContent,
          PRA: tds[10].textContent
        });
      });
      downloadCsv("team_projections.csv", toCSV(rows));
    });

  } catch (err) {
    alert(`Init failed: ${err.message}`);
    console.error(err);
  }
}
