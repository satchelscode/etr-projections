/* ====== ETR Projections — Main Client ======
   - Populates selects (players/teams/opponents)
   - Single-player projection
   - Team Sheet load/project/download
   - Minutes CSV upload + apply to Team Sheet
   ------------------------------------------- */

/* -------------------- Helpers -------------------- */
const qs  = (s, r = document) => r.querySelector(s);
const qsa = (s, r = document) => Array.from(r.querySelectorAll(s));
const fmt1 = (x) => (x === null || x === undefined || Number.isNaN(+x) ? "" : (+x).toFixed(1));

function downloadCSV(filename, rows) {
  const header = Object.keys(rows[0] || {});
  const lines = [header.join(",")].concat(
    rows.map(r => header.map(h => (r[h] ?? "")).join(","))
  );
  const blob = new Blob([lines.join("\n")], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url; a.download = filename; a.click();
  setTimeout(() => URL.revokeObjectURL(url), 500);
}

/* ---------------- Minutes Overrides --------------- */
const Minutes = {
  cache: { updated_at: null, overrides: {} },
  norm(s) { return String(s || "").trim().toLowerCase().replace(/\s+/g, " "); },

  async load() {
    try {
      const r = await fetch("/api/minutes/overrides");
      if (!r.ok) return;
      this.cache = await r.json();
      this.status(this.cache.updated_at ? `Minutes loaded (${this.cache.updated_at})` : "No minutes overrides");
    } catch { /* noop */ }
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

/* --------------------- API ------------------------ */
const API = {
  async getMeta() {
    // Try /api/meta first; fall back to granular endpoints
    try {
      const r = await fetch("/api/meta");
      if (r.ok) return await r.json();
    } catch { /* ignore */ }

    const [players, teams, opps] = await Promise.all([
      fetch("/api/players").then(r => r.ok ? r.json() : [] ).catch(() => []),
      fetch("/api/teams").then(r => r.ok ? r.json() : [] ).catch(() => []),
      fetch("/api/opponents").then(r => r.ok ? r.json() : [] ).catch(() => []),
    ]);

    // If teams/opps missing, derive from players
    const derivedTeams = (teams && teams.length) ? teams
      : Array.from(new Set((players || []).map(p => p.team).filter(Boolean))).sort();

    return {
      players: players || [],
      teams: derivedTeams,
      opponents: (opps && opps.length) ? opps : derivedTeams
    };
  },

  async roster(team) {
    // Try two common patterns
    const try1 = fetch(`/api/team/${encodeURIComponent(team)}/roster`).then(r => r.ok ? r.json() : null).catch(() => null);
    const try2 = fetch(`/api/roster?team=${encodeURIComponent(team)}`).then(r => r.ok ? r.json() : null).catch(() => null);
    const res = (await try1) || (await try2) || [];
    return Array.isArray(res) ? res : [];
  },

  async projectSingle({ player, opponent, minutes }) {
    const r = await fetch("/api/project", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ player, opponent, minutes })
    });
    if (!r.ok) throw new Error(await r.text());
    return await r.json();
  },

  async projectBulk(rows) {
    const r = await fetch("/api/project/bulk", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ rows })
    });
    if (!r.ok) throw new Error(await r.text());
    return await r.json();
  }
};

/* --------------------- App ------------------------ */
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

    // Populate selects
    const playerSel = qs("#player");
    const playerSearch = qs("#playerSearch");
    const oppSel = qs("#opponent");
    const oppSearch = qs("#opponentSearch");
    const rosterTeamSel = qs("#rosterTeam");
    const opponentTeamSel = qs("#opponentTeam");

    // Players
    this.fillSelect(playerSel, this.meta.players.map(p => ({
      label: p.name || p.player || "",
      value: p.name || p.player || ""
    })));

    // Opponents (single-player)
    this.fillSelect(oppSel, this.meta.opponents.map(t => ({ label: t, value: t })));

    // Team Sheet selectors
    this.fillSelect(rosterTeamSel, this.meta.teams.map(t => ({ label: t, value: t })));
    this.fillSelect(opponentTeamSel, this.meta.opponents.map(t => ({ label: t, value: t })));

    // Simple type-to-filter behavior
    const filterSelect = (sel, items, q) => {
      const normq = (q || "").toLowerCase();
      const filtered = items.filter(x => (x.label || "").toLowerCase().includes(normq));
      this.fillSelect(sel, filtered);
    };

    playerSearch?.addEventListener("input", (e) => {
      const items = this.meta.players.map(p => ({ label: p.name || p.player || "", value: p.name || p.player || "" }));
      filterSelect(playerSel, items, e.target.value);
    });

    oppSearch?.addEventListener("input", (e) => {
      const items = this.meta.opponents.map(t => ({ label: t, value: t }));
      filterSelect(oppSel, items, e.target.value);
    });
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
      // Normalize roster items: { player, opponent, minutes }
      roster = roster.map(r => ({
        player: r.player || r.Player || r.name || r.Name || "",
        opponent: opp || r.opponent || r.Opponent || "",
        minutes: ("minutes" in r) ? r.minutes : ("mins" in r ? r.mins : (r.minutes ?? "")),
        _raw: r
      }));

      // Apply default minutes if empty
      const def = parseFloat(qs("#defaultTeamMinutes")?.value || "30");
      roster.forEach(r => { if (!r.minutes && r.minutes !== 0) r.minutes = def; });

      // Apply overrides from Minutes CSV
      roster = Minutes.applyToRoster(roster);

      this._roster = roster;
      this.renderRoster(roster);
    });

    qs("#projectRosterBtn")?.addEventListener("click", async () => {
      if (!this._roster.length) return;

      // collect current table minutes edits (if any)
      const rows = qsa("#teamTbl tbody tr").map(tr => {
        const player = tr.dataset.player;
        const opponent = tr.dataset.opponent || qs("#opponentTeam")?.value || "";
        const minutes = parseFloat(qs("input[name='mins']", tr)?.value || "0");
        return { player, opponent, minutes };
      });

      try {
        const res = await API.projectBulk(rows);
        // res expected: array of { player, opponent, minutes, pts, reb, ast, 3pm, stl, blk, to, pra }
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

      downloadCSV("team_projections.csv", rows);
    });
  },

  wireSearchFilters() {
    // (Already handled in loadMeta via inputs)
  },

  renderSingle(player, opponent, minutes, proj) {
    const tbl = qs("#result");
    const tb  = qs("#result tbody");
    if (!tbl || !tb) return;
    tbl.style.display = "table";
    tb.innerHTML = "";
    const row = document.createElement("tr");
    const safe = (k) => fmt1(proj?.[k]);
    row.innerHTML = `
      <td>${player}</td>
      <td>${opponent}</td>
      <td>${minutes}</td>
      <td>${safe("pts")}</td>
      <td>${safe("reb")}</td>
      <td>${safe("ast")}</td>
      <td>${safe("3pm")}</td>
      <td>${safe("stl")}</td>
      <td>${safe("blk")}</td>
      <td>${safe("to")}</td>
      <td>${safe("pra")}</td>
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
      const set = (k, v) => { const cell = qs(`td[data-k='${k}']`, tr); if (cell) cell.textContent = fmt1(v); };
      set("pts", r.pts);
      set("reb", r.reb);
      set("ast", r.ast);
      set("3pm", r["3pm"]);
      set("stl", r.stl);
      set("blk", r.blk);
      set("to",  r.to);
      set("pra", r.pra);
    });
  },

  async selectTeam(teamId) {
    // used by Minutes.refreshCurrentTeam
    qs("#rosterTeam").value = teamId;
    await qs("#loadRosterBtn").click();
  },

  async refreshCurrentTeam() {
    if (this._currentTeam) await this.selectTeam(this._currentTeam);
  }
};

/* Boot after DOM is ready */
window.addEventListener("DOMContentLoaded", () => {
  App.init().catch((e) => {
    console.error("Init failed:", e);
  });
});
