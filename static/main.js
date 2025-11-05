/* ====== ETR Projections — Main Client (v14) ======
   - Populates selects (players/teams/opponents)
   - Single-player projection
   - Team Sheet load/project/download
   - Minutes CSV upload + apply to Team Sheet
   - Works with app.py that returns Proj_* fields and /api/project_bulk
   -------------------------------------------------- */

const qs  = (s, r = document) => r.querySelector(s);
const qsa = (s, r = document) => Array.from(r.querySelectorAll(s));
const fmt1 = (x) => (x === null || x === undefined || Number.isNaN(+x) ? "" : (+x).toFixed(1));

/* -------------- CSV Parser (minimal) ---------------- */
function parseCSV(text) {
  const lines = text.trim().split(/\r?\n/);
  if (!lines.length) return [];
  const headers = lines[0].split(",").map(h => h.trim());
  return lines.slice(1).map(line => {
    const cols = line.split(",");
    const row = {};
    headers.forEach((h, i) => { row[h] = (cols[i] ?? "").trim(); });
    return row;
  });
}

/* -------------- CSV-driven meta fallback ------------ */
async function readPlayersFromCSV() {
  try {
    const r = await fetch("/players_master.csv", { cache: "no-store" });
    if (!r.ok) return { players: [], teams: [], opponents: [] };
    const txt = await r.text();
    const rows = parseCSV(txt);
    const players = rows
      .map(row => {
        const name = row.Player || row.player || row.Name || row.name || "";
        const team = row.Team || row.team || "";
        if (!name) return null;
        return { name, team };
      })
      .filter(Boolean);

    const teams = Array.from(new Set(players.map(p => p.team).filter(Boolean))).sort();
    return { players, teams, opponents: teams.slice() };
  } catch {
    return { players: [], teams: [], opponents: [] };
  }
}

/* ---------------- Minutes Overrides ----------------- */
const Minutes = {
  cache: { updated_at: null, overrides: {} },
  norm(s) { return String(s || "").trim().toLowerCase().replace(/\s+/g, " "); },

  async load() {
    try {
      const r = await fetch("/api/minutes/overrides", { cache: "no-store" });
      if (!r.ok) return;
      this.cache = await r.json();
      this.status(this.cache.updated_at ? `Minutes loaded (${this.cache.updated_at})` : "No minutes overrides");
    } catch {}
  },

  async upload(file) {
    const fd = new FormData();
    fd.append("file", file);
    const r = await fetch("/api/minutes/upload", { method: "POST", body: fd });
    const j = await r.json();
    if (!j.ok) throw new Error(j.error || "Upload failed");
    await this.load();
    return j;
  },

  status(msg) {
    const el = qs("#minutes-upload-status");
    if (el) el.textContent = msg || "";
  },

  attachUI() {
    const btn = qs("#btn-upload-minutes");
    const input = qs("#minutes-file");
    if (btn && input) {
      btn.onclick = () => input.click();
      input.onchange = async (ev) => {
        const f = ev.target.files?.[0];
        if (!f) return;
        this.status("Uploading…");
        try {
          const res = await this.upload(f);
          this.status(`Applied ${res.count} minutes (updated ${res.updated_at})`);
          await App.refreshCurrentTeam();
        } catch (e) {
          this.status(`Error: ${e.message}`);
        } finally {
          input.value = "";
        }
      };
    }
  },

  applyToRoster(roster) {
    if (!Array.isArray(roster)) return roster;
    return roster.map(p => {
      const name = p.player || p.Player || p.name || p.Name || "";
      const key  = this.norm(name);
      const ov   = this.cache.overrides[key];
      if (ov && typeof ov.minutes === "number" && !Number.isNaN(ov.minutes)) {
        if ("minutes" in p) p.minutes = ov.minutes;
        else if ("mins" in p) p.mins = ov.minutes;
        else p.minutes = ov.minutes;
      }
      return p;
    });
  }
};

/* ---------------------- API ------------------------ */
const API = {
  async getMeta() {
    // Preferred: /api/meta
    try {
      const r = await fetch("/api/meta", { cache: "no-store" });
      if (r.ok) {
        const j = await r.json();
        if (j?.players?.length || j?.teams?.length) return j;
      }
    } catch {}

    // Fallbacks
    try {
      const [players, teams, opps] = await Promise.all([
        fetch("/api/players",   { cache: "no-store" }).then(r => r.ok ? r.json() : [] ).catch(() => []),
        fetch("/api/teams",     { cache: "no-store" }).then(r => r.ok ? r.json() : [] ).catch(() => []),
        fetch("/api/opponents", { cache: "no-store" }).then(r => r.ok ? r.json() : [] ).catch(() => []),
      ]);
      const teams2 = teams?.length ? teams
        : Array.from(new Set((players || []).map(p => p.team).filter(Boolean))).sort();
      if ((players?.length || teams2?.length)) {
        return { players: players || [], teams: teams2, opponents: (opps?.length ? opps : teams2) };
      }
    } catch {}

    return await readPlayersFromCSV();
  },

  async roster(team) {
    const try1 = fetch(`/api/team/${encodeURIComponent(team)}/roster`, { cache: "no-store" })
      .then(r => r.ok ? r.json() : null).catch(() => null);
    const try2 = fetch(`/api/roster?team=${encodeURIComponent(team)}`, { cache: "no-store" })
      .then(r => r.ok ? r.json() : null).catch(() => null);
    let res = (await try1) || (await try2);
    if (Array.isArray(res)) return res;

    const meta = await readPlayersFromCSV();
    const players = meta.players.filter(p => (p.team || "").toLowerCase() === String(team || "").toLowerCase());
    return players.map(p => ({ player: p.name, opponent: "", minutes: "" }));
  },

  async projectSingle(payload) {
    const r = await fetch("/api/project", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });
    if (!r.ok) throw new Error(await r.text());
    return await r.json();
  },

  async projectBulk(rows) {
    // NOTE: backend uses underscore: /api/project_bulk
    const r = await fetch("/api/project_bulk", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ rows })
    });
    if (!r.ok) throw new Error(await r.text());
    return await r.json();
  }
};

/* ---------------------- App ------------------------ */
const App = {
  meta: { players: [], teams: [], opponents: [] },
  _currentTeam: null,
  _roster: [],

  async init() {
    Minutes.attachUI();
    await Minutes.load();
    await this.loadMeta();
    this.wireSearchFilters();
    this.wireButtons();
  },

  async loadMeta() {
    this.meta = await API.getMeta();

    const playerSel = qs("#player");
    const playerSearch = qs("#playerSearch");
    const oppSel = qs("#opponent");
    const oppSearch = qs("#opponentSearch");
    const rosterTeamSel = qs("#rosterTeam");
    const opponentTeamSel = qs("#opponentTeam");

    const playerItems = (this.meta.players || []).map(p => ({
      label: p.name || p.player || "",
      value: p.name || p.player || ""
    })).filter(x => x.label);

    const oppItems = (this.meta.opponents || []).map(t => ({ label: t, value: t }));
    const teamItems = (this.meta.teams || []).map(t => ({ label: t, value: t }));

    this.fillSelect(playerSel, playerItems);
    this.fillSelect(oppSel, oppItems);
    this.fillSelect(rosterTeamSel, teamItems);
    this.fillSelect(opponentTeamSel, oppItems.length ? oppItems : teamItems);

    const filterSelect = (sel, items, q) => {
      const normq = (q || "").toLowerCase();
      const filtered = items.filter(x => (x.label || "").toLowerCase().includes(normq));
      this.fillSelect(sel, filtered);
    };

    playerSearch?.addEventListener("input", (e) => filterSelect(playerSel, playerItems, e.target.value));
    oppSearch?.addEventListener("input", (e) => filterSelect(oppSel, oppItems.length ? oppItems : teamItems, e.target.value));
  },

  fillSelect(selectEl, items) {
    if (!selectEl) return;
    selectEl.innerHTML = "";
    for (const it of items) {
      const opt = document.createElement("option");
      opt.value = it.value ?? it.label ?? "";
      opt.textContent = it.label ?? it.value ?? "";
      selectEl.appendChild(opt);
    }
  },

  wireButtons() {
    qs("#projectBtn")?.addEventListener("click", async () => {
      const player   = qs("#player")?.value || "";
      const opponent = qs("#opponent")?.value || "";
      const minutes  = parseFloat(qs("#minutes")?.value || "0");
      if (!player || !opponent || !minutes) return;

      try {
        const proj = await API.projectSingle({ player, opponent, minutes });
        this.renderSingle(player, opponent, minutes, proj);
      } catch (e) {
        console.error(e);
        alert("Projection failed.");
      }
    });

    qs("#loadRosterBtn")?.addEventListener("click", async () => {
      const team = qs("#rosterTeam")?.value || "";
      const opp  = qs("#opponentTeam")?.value || "";
      if (!team) return;
      this._currentTeam = team;

      let roster = await API.roster(team);
      roster = roster.map(r => ({
        player: r.player || r.Player || r.name || r.Name || "",
        opponent: opp || r.opponent || r.Opponent || "",
        minutes: ("minutes" in r) ? r.minutes : ("mins" in r ? r.mins : (r.minutes ?? "")),
        _raw: r
      }));

      const def = parseFloat(qs("#defaultTeamMinutes")?.value || "30");
      roster.forEach(r => { if (!r.minutes && r.minutes !== 0) r.minutes = def; });

      roster = Minutes.applyToRoster(roster);

      this._roster = roster;
      this.renderRoster(roster);
    });

    qs("#projectRosterBtn")?.addEventListener("click", async () => {
      if (!this._roster.length) return;

      const rows = qsa("#teamTbl tbody tr").map(tr => {
        const player = tr.dataset.player;
        const opponent = tr.dataset.opponent || qs("#opponentTeam")?.value || "";
        const minutes = parseFloat(qs("input[name='mins']", tr)?.value || "0");
        return { player, opponent, minutes };
      });

      try {
        const res = await API.projectBulk(rows);
        this.renderRosterProjected(res);
      } catch (e) {
        console.error(e);
        alert("Bulk projection failed.");
      }
    });

    qs("#downloadCsvBtn")?.addEventListener("click", () => {
      const bodyRows = qsa("#teamTbl tbody tr");
      if (!bodyRows.length) return;

      const rows = bodyRows.map(tr => {
        const get = (sel) => (qs(sel, tr)?.textContent || "").trim();
        const minv = qs("input[name='mins']", tr)?.value || "";
        return {
          player: tr.dataset.player || get("td:nth-child(1)"),
          opponent: tr.dataset.opponent || get("td:nth-child(2)"),
          minutes: minv,
          pts: get("td[data-k='pts']"),
          reb: get("td[data-k='reb']"),
          ast: get("td[data-k='ast']"),
          "3pm": get("td[data-k='3pm']"),
          stl: get("td[data-k='stl']"),
          blk: get("td[data-k='blk']"),
          to:  get("td[data-k='to']"),
          pra: get("td[data-k='pra']")
        };
      });

      const fname = `team_projections_${(new Date()).toISOString().slice(0,10)}.csv`;
      downloadCSV(fname, rows);
    });
  },

  // Map either Proj_* or short keys to numbers
  readStat(obj, longKey, shortKey) {
    if (obj == null) return "";
    if (longKey in obj) return fmt1(obj[longKey]);
    if (shortKey in obj) return fmt1(obj[shortKey]);
    return "";
  },

  renderSingle(player, opponent, minutes, proj) {
    const tbl = qs("#result");
    const tb  = qs("#result tbody");
    if (!tbl || !tb) return;
    tbl.style.display = "table";
    tb.innerHTML = "";
    const row = document.createElement("tr");
    row.innerHTML = `
      <td>${player}</td>
      <td>${opponent}</td>
      <td>${minutes}</td>
      <td>${this.readStat(proj, "Proj_Points", "pts")}</td>
      <td>${this.readStat(proj, "Proj_Rebounds", "reb")}</td>
      <td>${this.readStat(proj, "Proj_Assists", "ast")}</td>
      <td>${this.readStat(proj, "Proj_Three Pointers Made", "3pm")}</td>
      <td>${this.readStat(proj, "Proj_Steals", "stl")}</td>
      <td>${this.readStat(proj, "Proj_Blocks", "blk")}</td>
      <td>${this.readStat(proj, "Proj_Turnovers", "to")}</td>
      <td>${this.readStat(proj, "Proj_PRA", "pra")}</td>
    `;
    tb.appendChild(row);
  },

  renderRoster(roster) {
    const tbl = qs("#teamTbl");
    const tb  = qs("#teamTbl tbody");
    if (!tbl || !tb) return;
    tbl.style.display = "table";
    tb.innerHTML = "";
    roster.forEach(r => {
      const tr = document.createElement("tr");
      tr.dataset.player = r.player;
      tr.dataset.opponent = r.opponent || "";
      tr.innerHTML = `
        <td>${r.player}</td>
        <td>${r.opponent || ""}</td>
        <td>
          <input name="mins" type="number" step="0.1" value="${r.minutes ?? ""}" style="width:100px"/>
        </td>
        <td data-k="pts"></td>
        <td data-k="reb"></td>
        <td data-k="ast"></td>
        <td data-k="3pm"></td>
        <td data-k="stl"></td>
        <td data-k="blk"></td>
        <td data-k="to"></td>
        <td data-k="pra"></td>
      `;
      tb.appendChild(tr);
    });
  },

  renderRosterProjected(rows) {
    const tb = qs("#teamTbl tbody");
    if (!tb) return;
    const byPlayer = new Map(rows.map(r => [r.player, r]));
    qsa("tr", tb).forEach(tr => {
      const name = tr.dataset.player;
      const r = byPlayer.get(name);
      if (!r) return;
      const set = (k, longKey, shortKey) => {
        const cell = qs(`td[data-k='${k}']`, tr);
        if (!cell) return;
        cell.textContent = this.readStat(r, longKey, shortKey);
      };
      set("pts", "Proj_Points", "pts");
      set("reb", "Proj_Rebounds", "reb");
      set("ast", "Proj_Assists", "ast");
      set("3pm", "Proj_Three Pointers Made", "3pm");
      set("stl", "Proj_Steals", "stl");
      set("blk", "Proj_Blocks", "blk");
      set("to",  "Proj_Turnovers", "to");
      set("pra", "Proj_PRA", "pra");
    });
  },

  async selectTeam(teamId) {
    qs("#rosterTeam").value = teamId;
    await qs("#loadRosterBtn").click();
  },

  async refreshCurrentTeam() {
    if (this._currentTeam) await this.selectTeam(this._currentTeam);
  }
};

/* Boot */
window.addEventListener("DOMContentLoaded", () => {
  App.init().catch((e) => console.error("Init failed:", e));
});
