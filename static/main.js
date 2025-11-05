async function fetchJSON(url, opts = {}) {
  const res = await fetch(url, opts);
  if (!res.ok) throw new Error(`fetch error: ${res.status}`);
  return res.json();
}

function fillSelect(sel, items) {
  if (!sel) return;
  sel.innerHTML = "";
  items.forEach((x) => {
    const o = document.createElement("option");
    o.value = x;
    o.textContent = x;
    sel.appendChild(o);
  });
}

function toCSV(rows) {
  if (!rows.length) return "";
  const headers = Object.keys(rows[0]);
  const csv = [
    headers.join(","),
    ...rows.map((r) =>
      headers
        .map((h) => {
          const v = r[h] ?? "";
          return String(v).replace(/"/g, '""');
        })
        .join(",")
    ),
  ].join("\n");
  return csv;
}

function download(filename, text) {
  const blob = new Blob([text], { type: "text/csv" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = filename;
  a.click();
  URL.revokeObjectURL(a.href);
}

async function init() {
  try {
    // Single-player fields
    const selPlayer = document.getElementById("player");
    const selOpp = document.getElementById("opponent");
    const inpPsearch = document.getElementById("playerSearch");
    const inpOsearch = document.getElementById("opponentSearch");
    const inpMinutes = document.getElementById("minutes");
    const btnProject = document.getElementById("projectBtn");
    const tblSingle = document.getElementById("result");
    const tbodySingle = tblSingle?.querySelector("tbody");

    // Team sheet fields
    const selTeamFor = document.getElementById("teamForRoster");
    const inpDefaultMin = document.getElementById("defaultTeamMinutes");
    const btnLoadRoster = document.getElementById("loadRosterBtn");
    const btnProjectRoster = document.getElementById("projectRosterBtn");
    const btnDownloadCsv = document.getElementById("downloadCsvBtn");
    const tblTeam = document.getElementById("teamTbl");
    const tbodyTeam = tblTeam?.querySelector("tbody");

    let allOpponents = [];
    let allPlayers = [];
    let rosterPlayers = [];

    // Load initial dropdowns
    allOpponents = await fetchJSON("/api/opponents");
    fillSelect(selOpp, allOpponents);
    fillSelect(selTeamFor, allOpponents);

    allPlayers = await fetchJSON("/api/players");
    fillSelect(selPlayer, allPlayers);

    // Filtering for single-player
    const filterOpp = async (prefix) => {
      const p = new URLSearchParams();
      if (prefix) p.set("q", prefix);
      const arr = await fetchJSON("/api/opponents?" + p.toString());
      fillSelect(selOpp, arr);
    };

    const filterPlayers = async (prefix, team = "") => {
      const p = new URLSearchParams();
      if (team) p.set("team", team);
      if (prefix) p.set("q", prefix);
      const arr = await fetchJSON("/api/players?" + p.toString());
      fillSelect(selPlayer, arr);
    };

    inpOsearch?.addEventListener("input", (ev) => {
      filterOpp(ev.target.value.trim().toLowerCase());
    });

    // Single-player: filter by text (no team param)
    inpPsearch?.addEventListener("input", (ev) => {
      filterPlayers(ev.target.value.trim().toLowerCase(), "");
    });

    // ---- Single Player Project ----
    btnProject?.addEventListener("click", async () => {
      const player = selPlayer?.value || "";
      const opponent = selOpp?.value || "";
      const minutes = parseFloat(inpMinutes?.value || 0);

      if (!player || !opponent || !minutes) {
        alert("Please provide player, opponent, and minutes");
        return;
      }

      const body = { player, opponent, minutes };
      const proj = await fetchJSON("/api/project", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });

      if (!tbodySingle) return;
      tbodySingle.innerHTML = "";
      const tr = document.createElement("tr");
      [
        "player",
        "opponent",
        "minutes",
        "Proj_Points",
        "Proj_Rebounds",
        "Proj_Assists",
        "Proj_Three Pointers Made",
        "Proj_Steals",
        "Proj_Blocks",
        "Proj_Turnovers",
        "Proj_PRA",
      ].forEach((h) => {
        const td = document.createElement("td");
        td.textContent = proj[h] ?? "";
        tr.appendChild(td);
      });
      tbodySingle.appendChild(tr);
      tblSingle.style.display = "";
    });

    // ---- Team Sheet Roster Load ----
    btnLoadRoster?.addEventListener("click", async () => {
      const team = selTeamFor?.value || "";
      if (!team) return;
      rosterPlayers = await fetchJSON(`/api/players?team=${team}`);
      rosterPlayers = rosterPlayers.slice(0, 12); // reasonable limit

      if (!tbodyTeam) return;
      tbodyTeam.innerHTML = "";
      const defMin = parseFloat(inpDefaultMin?.value || "30");

      rosterPlayers.forEach((p) => {
        const tr = document.createElement("tr");

        const tdName = document.createElement("td");
        tdName.textContent = p;
        tr.appendChild(tdName);

        const tdOpp = document.createElement("td");
        tdOpp.textContent = team;
        tr.appendChild(tdOpp);

        const tdMin = document.createElement("td");
        const mInput = document.createElement("input");
        mInput.type = "number";
        mInput.value = String(defMin);
        tdMin.appendChild(mInput);
        tr.appendChild(tdMin);

        ["PTS", "REB", "AST", "3PM", "STL", "BLK", "TO", "PRA"].forEach(() => {
          const td = document.createElement("td");
          td.textContent = "";
          tr.appendChild(td);
        });

        tbodyTeam.appendChild(tr);
      });

      tblTeam.style.display = "";
    });

    // ---- Team Sheet Project All ----
    btnProjectRoster?.addEventListener("click", async () => {
      if (!tbodyTeam) return;
      const rows = [];
      const trs = tbodyTeam.querySelectorAll("tr");

      trs.forEach((tr) => {
        const tds = tr.querySelectorAll("td");
        if (tds.length < 3) return;
        const player = tds[0].textContent;
        const opponent = tds[1].textContent;
        const minutes = parseFloat(tds[2].querySelector("input")?.value || 0);
        rows.push({ player, opponent, minutes });
      });

      if (!rows.length) return;

      const out = await fetchJSON("/api/project_bulk", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ rows }),
      });

      // Fill table
      out.forEach((r, i) => {
        const tr = trs[i];
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

    // ---- Download CSV ----
    btnDownloadCsv?.addEventListener("click", () => {
      if (!tbodyTeam) return;
      const trs = tbodyTeam.querySelectorAll("tr");
      const arr = [];

      trs.forEach((tr) => {
        const tds = tr.querySelectorAll("td");
        if (tds.length < 11) return;
        arr.push({
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
          PRA: tds[10].textContent,
        });
      });

      const csv = toCSV(arr);
      download("team_projections.csv", csv);
    });
  } catch (err) {
    alert(`Init failed: ${err.message}`);
    console.error(err);
  }
}

document.addEventListener("DOMContentLoaded", init);

