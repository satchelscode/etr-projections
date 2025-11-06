/* static/daily.js
   - Projections tab: load /api/daily/projections/latest.csv, render
     Single Player + Team aggregates with filters.
   - Daily ETR Models tab: upload + library list from /api/daily/library.
*/

;(function () {
  // ---------- UTIL ----------
  const $  = (s) => document.querySelector(s);
  const $$ = (s) => Array.from(document.querySelectorAll(s));

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

  // very small CSV parser (no external deps)
  function parseCSV(text) {
    const lines = text.replace(/\r/g, "").split("\n").filter(Boolean);
    if (!lines.length) return { header: [], rows: [] };
    const header = splitCSVLine(lines[0]);
    const rows = lines.slice(1).map((ln) => {
      const cells = splitCSVLine(ln);
      const obj = {};
      header.forEach((h, i) => (obj[h.trim()] = cells[i] ?? ""));
      return obj;
    });
    return { header, rows };
  }
  function splitCSVLine(ln) {
    const out = [];
    let cur = "", q = false;
    for (let i = 0; i < ln.length; i++) {
      const c = ln[i];
      if (c === '"' && ln[i + 1] === '"') { cur += '"'; i++; continue; }
      if (c === '"') { q = !q; continue; }
      if (c === "," && !q) { out.push(cur); cur = ""; continue; }
      cur += c;
    }
    out.push(cur);
    return out;
  }
  function num(x) { const f = parseFloat(x); return isFinite(f) ? f : 0; }

  // ---------- PROJECTIONS (MAIN) ----------
  async function loadProjections() {
    try {
      const csv = await fetch("/api/daily/projections/latest.csv").then(r => {
        if (!r.ok) throw new Error("No projections artifact yet");
        return r.text();
      });
      const { header, rows } = parseCSV(csv);
      if (!rows.length) return;

      // normalize columns we use
      const norm = rows.map(r => ({
        Date: r.Date || "",
        Player: r.Player || "",
        Team: r.Team || "",
        Opp: r.Opp || "",
        Minutes: num(r.Minutes),
        PTS: num(r.PTS),
        REB: num(r.REB),
        AST: num(r.AST),
        "3PM": num(r["3PM"]),
        STL: num(r.STL),
        BLK: num(r.BLK),
        TO: num(r.TO),
        PRA: num(r.PRA),
      }));

      // fill team/opp filters
      const teamSet = new Set(norm.map(r => r.Team).filter(Boolean));
      const oppSet  = new Set(norm.map(r => r.Opp).filter(Boolean));
      const ft = $("#filter-team"), fo = $("#filter-opp"), fta = $("#filter-team-agg");
      if (ft && ft.options.length === 1) {
        [...teamSet].sort().forEach(t => ft.append(new Option(t, t)));
      }
      if (fo && fo.options.length === 1) {
        [...oppSet].sort().forEach(t => fo.append(new Option(t, t)));
      }
      if (fta && fta.options.length === 1) {
        [...teamSet].sort().forEach(t => fta.append(new Option(t, t)));
      }

      // show date
      const lastDate = norm[0]?.Date || "";
      const pill = $("#proj-date-pill");
      if (pill) pill.textContent = `Date: ${lastDate || "—"}`;

      // render players with filters
      function applyPlayerFilters() {
        const q   = ($("#search-player")?.value || "").toLowerCase();
        const tm  = $("#filter-team")?.value || "";
        const opp = $("#filter-opp")?.value || "";
        const stat= $("#filter-stat")?.value || "";

        let arr = norm.filter(r =>
          (!q || r.Player.toLowerCase().includes(q)) &&
          (!tm || r.Team === tm) &&
          (!opp || r.Opp === opp)
        );

        // if a stat selected, sort by it desc
        if (stat) {
          arr = arr.slice().sort((a,b)=>num(b[stat])-num(a[stat]));
        } else {
          arr = arr.slice().sort((a,b)=>a.Team.localeCompare(b.Team) || a.Player.localeCompare(b.Player));
        }

        const tbody = $("#players-tbody");
        tbody.innerHTML = "";
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
          tbody.appendChild(tr);
        }
        const pc = $("#player-count");
        if (pc) pc.textContent = `${arr.length} players`;
      }

      // aggregate teams
      function renderTeams() {
        const pick = $("#filter-team-agg")?.value || "";
        const map = new Map(); // team -> totals
        for (const r of norm) {
          if (pick && r.Team !== pick) continue;
          if (!map.has(r.Team)) {
            map.set(r.Team, { PTS:0,REB:0,AST:0,"3PM":0,STL:0,BLK:0,TO:0,PRA:0 });
          }
          const t = map.get(r.Team);
          t.PTS+=r.PTS; t.REB+=r.REB; t.AST+=r.AST; t["3PM"]+=r["3PM"]; t.STL+=r.STL; t.BLK+=r.BLK; t.TO+=r.TO; t.PRA+=r.PRA;
        }
        const rows = [...map.entries()].sort((a,b)=>a[0].localeCompare(b[0]));
        const tb = $("#teams-tbody"); tb.innerHTML = "";
        for (const [team, t] of rows) {
          const tr = document.createElement("tr");
          tr.innerHTML = `
            <td>${team}</td>
            <td class="right">${t.PTS.toFixed(1)}</td>
            <td class="right">${t.REB.toFixed(1)}</td>
            <td class="right">${t.AST.toFixed(1)}</td>
            <td class="right">${t["3PM"].toFixed(1)}</td>
            <td class="right">${t.STL.toFixed(1)}</td>
            <td class="right">${t.BLK.toFixed(1)}</td>
            <td class="right">${t.TO.toFixed(1)}</td>
            <td class="right">${t.PRA.toFixed(1)}</td>
          `;
          tb.appendChild(tr);
        }
      }

      // wire filters
      ["#search-player","#filter-team","#filter-opp","#filter-stat"].forEach(id=>{
        const n = $(id); if (n) n.addEventListener("input", applyPlayerFilters);
      });
      const fta = $("#filter-team-agg"); if (fta) fta.addEventListener("input", renderTeams);

      applyPlayerFilters();
      renderTeams();
    } catch (e) {
      console.error("loadProjections:", e);
      // leave tables empty if artifact not ready
    }
  }

  // ---------- DAILY ETR MODELS (UPLOAD + LIBRARY) ----------
  async function loadLibrary() {
    const tbody = $("#upload-library-body");
    const note = $("#upload-library-note");
    if (!tbody) return;

    tbody.innerHTML = "";
    if (note) note.textContent = "";

    try {
      const res = await jsonFetch("/api/daily/library");
      const rows = res.items || res.data || res.rows || res.list || (Array.isArray(res)?res:[]);
      if (!rows.length) {
        tbody.innerHTML = `<tr><td colspan="3" style="padding:10px;color:#666">No uploads found yet.</td></tr>`;
        return;
      }
      for (const r of rows) {
        const tr = document.createElement("tr");
        const href = r.download || r.href || r.url || r.download_url || "#";
        tr.innerHTML = `
          <td>${r.date || ""}</td>
          <td>${r.size || (r.size_kb!=null?`${r.size_kb} KB`:"")}</td>
          <td><a href="${href}" target="_blank" rel="noopener">Download</a></td>
        `;
        tbody.appendChild(tr);
      }
    } catch (e) {
      console.error("loadLibrary:", e);
      tbody.innerHTML = `<tr><td colspan="3" style="padding:10px;color:#b00">Failed to load upload history.</td></tr>`;
    }
  }

  async function wireUpload() {
    const fileInput = $("#etr-file");
    const dateInput = $("#etr-date");
    const btn = $("#upload-btn");
    const status = $("#upload-status");
    if (!btn || !fileInput || !dateInput) return;

    // default date = today
    if (!dateInput.value) {
      const now = new Date();
      const y = now.getFullYear(), m = String(now.getMonth()+1).padStart(2,"0"), d = String(now.getDate()).padStart(2,"0");
      dateInput.value = `${y}-${m}-${d}`;
    }

    btn.addEventListener("click", async (e) => {
      e.preventDefault();
      if (!fileInput.files || !fileInput.files.length) { if (status) status.textContent = "Choose a CSV first."; return; }
      const fd = new FormData();
      fd.append("file", fileInput.files[0]);
      fd.append("date", dateInput.value);

      btn.disabled = true; if (status) status.textContent = "Uploading & retraining…";
      try {
        const res = await jsonFetch("/api/daily/upload", { method:"POST", body:fd });
        const rows = res.rows_uploaded ?? res.rows ?? res.uploaded_rows ?? "N";
        if (status) status.textContent = `OK — Uploaded ${rows} rows for ${res.date} and retrained artifacts.`;
        await loadLibrary();      // refresh list
        await loadProjections();  // refresh projections immediately
      } catch (err) {
        if (status) status.textContent = `Upload failed: ${err.message || err}`;
      } finally {
        btn.disabled = false; fileInput.value = "";
      }
    });
  }

  // ---------- INIT ----------
  document.addEventListener("DOMContentLoaded", async () => {
    await loadProjections();
    await wireUpload();
    await loadLibrary();
    const dl = $("#download-latest");
    if (dl) dl.href = "/api/daily/projections/latest.csv";
  });
})();
