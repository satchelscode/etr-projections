/* static/daily.js
   - Projections tab: render players + teams from /api/daily/projections/latest.csv
   - Daily ETR Models tab: upload CSV (click + submit), show library
*/

;(function () {
  const $ = (s) => document.querySelector(s);

  // ---------- helpers ----------
  async function jsonFetch(url, opts) {
    const r = await fetch(url, opts);
    const ct = r.headers.get("content-type") || "";
    if (ct.includes("application/json")) {
      const j = await r.json();
      if (!r.ok) throw new Error(j.error || r.statusText);
      return j;
    }
    const t = await r.text();
    if (!r.ok) throw new Error(t || r.statusText);
    return t;
  }
  function parseCSV(text) {
    const lines = text.replace(/\r/g, "").split("\n");
    const good = lines.filter(l => l.trim().length);
    if (!good.length) return { header: [], rows: [] };
    const header = splitCSVLine(good[0]);
    const rows = good.slice(1).map(ln => {
      const cells = splitCSVLine(ln);
      const obj = {};
      header.forEach((h,i) => obj[h] = cells[i] ?? "");
      return obj;
    });
    return { header, rows };
  }
  function splitCSVLine(ln) {
    const out = []; let cur = "", q = false;
    for (let i=0;i<ln.length;i++) {
      const c = ln[i];
      if (c === '"' && ln[i+1] === '"') { cur += '"'; i++; continue; }
      if (c === '"') { q = !q; continue; }
      if (c === "," && !q) { out.push(cur); cur = ""; continue; }
      cur += c;
    }
    out.push(cur);
    return out;
  }
  const toNum = (x) => {
    if (x == null) return 0;
    const f = parseFloat(String(x).replace(/[^0-9.\-]/g,""));
    return Number.isFinite(f) ? f : 0;
  };

  // normalize a row with case-insensitive keys and common aliases
  function normRow(r) {
    const map = {};
    for (const k of Object.keys(r)) map[k.trim().toLowerCase()] = r[k];

    function pick(...alts) {
      for (const a of alts) {
        const v = map[a.toLowerCase()];
        if (v != null && v !== "") return v;
      }
      return "";
    }

    return {
      Date: pick("date"),
      Player: pick("player","name"),
      Team: pick("team"),
      Opp: pick("opp","opponent","opp."),
      Minutes: toNum(pick("minutes","min","mins","m")),
      PTS: toNum(pick("pts","points")),
      REB: toNum(pick("reb","rebs","rebounds")),
      AST: toNum(pick("ast","assists")),
      "3PM": toNum(pick("3pm","threes","3pt","3pt made","three pm")),
      STL: toNum(pick("stl","steals")),
      BLK: toNum(pick("blk","blocks")),
      TO: toNum(pick("to","tov","turnovers")),
      PRA: toNum(pick("pra"))
    };
  }

  // ---------- PROJECTIONS ----------
  async function loadProjections() {
    try {
      const resp = await fetch("/api/daily/projections/latest.csv");
      if (!resp.ok) return; // nothing yet
      const csv = await resp.text();
      const { rows } = parseCSV(csv);
      if (!rows.length) return;

      const norm = rows.map(normRow).filter(r => r.Player);

      // fill filters
      const teams = Array.from(new Set(norm.map(r => r.Team).filter(Boolean))).sort();
      const opps  = Array.from(new Set(norm.map(r => r.Opp).filter(Boolean))).sort();
      const teamSel = $("#filter-team"), oppSel = $("#filter-opp"), teamAgg = $("#filter-team-agg");
      if (teamSel && teamSel.options.length === 1) teams.forEach(t => teamSel.append(new Option(t,t)));
      if (oppSel  && oppSel.options.length  === 1) opps.forEach(o => oppSel.append(new Option(o,o)));
      if (teamAgg && teamAgg.options.length === 1) teams.forEach(t => teamAgg.append(new Option(t,t)));

      const lastDate = norm[0]?.Date || "";
      const pill = $("#proj-date-pill"); if (pill) pill.textContent = `Date: ${lastDate || "—"}`;

      function applyPlayerFilters() {
        const q = ($("#search-player")?.value || "").toLowerCase();
        const team = $("#filter-team")?.value || "";
        const opp  = $("#filter-opp")?.value || "";
        const stat = $("#filter-stat")?.value || "";

        let arr = norm.filter(r =>
          (!q || r.Player.toLowerCase().includes(q)) &&
          (!team || r.Team === team) &&
          (!opp  || r.Opp  === opp)
        );
        if (stat) arr = arr.slice().sort((a,b)=>toNum(b[stat])-toNum(a[stat]));
        else arr = arr.slice().sort((a,b)=>a.Team.localeCompare(b.Team)||a.Player.localeCompare(b.Player));

        const tb = $("#players-tbody"); tb.innerHTML = "";
        for (const r of arr) {
          const tr = document.createElement("tr");
          tr.innerHTML = `
            <td>${r.Player}</td>
            <td>${r.Team}</td>
            <td>${r.Opp}</td>
            <td class="right">${r.Minutes.toFixed(1)}</td>
            <td class="right">${r.PTS.toFixed(1)}</td>
            <td class="right">${r.REB.toFixed(1)}</td>
            <td class="right">${r.AST.toFixed(1)}</td>
            <td class="right">${r["3PM"].toFixed(1)}</td>
            <td class="right">${r.STL.toFixed(1)}</td>
            <td class="right">${r.BLK.toFixed(1)}</td>
            <td class="right">${r.TO.toFixed(1)}</td>
            <td class="right">${r.PRA.toFixed(1)}</td>
          `;
          tb.appendChild(tr);
        }
        const pc = $("#player-count"); if (pc) pc.textContent = `${arr.length} players`;
      }

      function renderTeams() {
        const pick = $("#filter-team-agg")?.value || "";
        const sums = new Map();
        for (const r of norm) {
          if (pick && r.Team !== pick) continue;
          if (!sums.has(r.Team)) sums.set(r.Team, {PTS:0,REB:0,AST:0,THREE:0,STL:0,BLK:0,TO:0,PRA:0});
          const t = sums.get(r.Team);
          t.PTS+=r.PTS; t.REB+=r.REB; t.AST+=r.AST; t.THREE+=r["3PM"]; t.STL+=r.STL; t.BLK+=r.BLK; t.TO+=r.TO; t.PRA+=r.PRA;
        }
        const list = [...sums.entries()].sort((a,b)=>a[0].localeCompare(b[0]));
        const tb = $("#teams-tbody"); tb.innerHTML = "";
        for (const [team, t] of list) {
          const tr = document.createElement("tr");
          tr.innerHTML = `
            <td>${team}</td>
            <td class="right">${t.PTS.toFixed(1)}</td>
            <td class="right">${t.REB.toFixed(1)}</td>
            <td class="right">${t.AST.toFixed(1)}</td>
            <td class="right">${t.THREE.toFixed(1)}</td>
            <td class="right">${t.STL.toFixed(1)}</td>
            <td class="right">${t.BLK.toFixed(1)}</td>
            <td class="right">${t.TO.toFixed(1)}</td>
            <td class="right">${t.PRA.toFixed(1)}</td>
          `;
          tb.appendChild(tr);
        }
      }

      ["#search-player","#filter-team","#filter-opp","#filter-stat"].forEach(id=>{
        const n = $(id); if (n) n.addEventListener("input", applyPlayerFilters);
      });
      const fta = $("#filter-team-agg"); if (fta) fta.addEventListener("input", renderTeams);

      applyPlayerFilters();
      renderTeams();
    } catch (e) {
      console.warn("Projections not ready yet:", e.message);
    }
  }

  // ---------- DAILY ETR MODELS ----------
  async function loadLibrary() {
    const tbody = $("#upload-library-body"); if (!tbody) return;
    tbody.innerHTML = "";
    try {
      const res = await jsonFetch("/api/daily/library");
      const rows = res.items || res.data || res.rows || res.list || (Array.isArray(res)?res:[]);
      if (!rows.length) {
        tbody.innerHTML = `<tr><td colspan="3" style="padding:10px;color:#666">No uploads found yet.</td></tr>`;
        return;
      }
      for (const r of rows) {
        const href = r.download || r.href || r.url || r.download_url || "#";
        const tr = document.createElement("tr");
        tr.innerHTML = `<td>${r.date||""}</td><td>${r.size||((r.size_kb!=null)?(r.size_kb+" KB"):"")}</td>
                        <td><a href="${href}" target="_blank" rel="noopener">Download</a></td>`;
        tbody.appendChild(tr);
      }
    } catch (e) {
      console.error("loadLibrary:", e);
      tbody.innerHTML = `<tr><td colspan="3" style="padding:10px;color:#b00">Failed to load upload history.</td></tr>`;
    }
  }

  function defaultDate() {
    const input = $("#etr-date");
    if (!input || input.value) return;
    const now = new Date();
    const y = now.getFullYear(), m = String(now.getMonth()+1).padStart(2,"0"), d = String(now.getDate()).padStart(2,"0");
    input.value = `${y}-${m}-${d}`;
  }

  async function wireUpload() {
    const form = $("#etr-upload-form"); if (!form) return;
    const fileInput = $("#etr-file");
    const dateInput = $("#etr-date");
    const status = $("#upload-status");

    defaultDate();

    async function doUpload(e) {
      e.preventDefault();
      if (!fileInput.files || !fileInput.files.length) { status.textContent = "Choose a CSV first."; return; }
      const fd = new FormData();
      fd.append("file", fileInput.files[0]);
      fd.append("date", dateInput.value);

      status.textContent = "Uploading & retraining…";
      try {
        const res = await jsonFetch("/api/daily/upload", { method:"POST", body:fd });
        const rows = res.rows_uploaded ?? res.rows ?? res.uploaded_rows ?? "N";
        status.textContent = `OK — Uploaded ${rows} rows for ${res.date} and retrained artifacts.`;
        fileInput.value = "";
        await loadLibrary();
        await loadProjections(); // refresh main tab immediately
      } catch (err) {
        status.textContent = `Upload failed: ${err.message || err}`;
      }
    }

    form.addEventListener("submit", doUpload);
    // also bind click in case the button is type="button" somewhere else later
    const btn = $("#upload-btn"); if (btn) btn.addEventListener("click", doUpload);
  }

  // ---------- init ----------
  document.addEventListener("DOMContentLoaded", async () => {
    $("#download-latest")?.setAttribute("href","/api/daily/projections/latest.csv");
    await loadProjections();
    await wireUpload();
    await loadLibrary();
  });
})();

})();
