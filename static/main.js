/* global fetch */

const Minutes = {
  cache: {
    updated_at: null,
    overrides: {}
  },
  normName(s) {
    return s.trim().toLowerCase().replace(/\s+/g, " ");
  },
  async load() {
    try {
      const res = await fetch("/api/minutes/overrides");
      if (!res.ok) return;
      const data = await res.json();
      Minutes.cache = data || { updated_at: null, overrides: {} };
      Minutes.setStatus(
        Minutes.cache.updated_at
          ? `Minutes loaded (${Minutes.cache.updated_at})`
          : `No minutes overrides`
      );
    } catch (e) {
      // silent
    }
  },
  async upload(file) {
    const fd = new FormData();
    fd.append("file", file);
    const res = await fetch("/api/minutes/upload", { method: "POST", body: fd });
    const data = await res.json();
    if (!data.ok) throw new Error(data.error || "Upload failed");
    await Minutes.load();
    return data;
  },
  setStatus(msg) {
    const el = document.getElementById("minutes-upload-status");
    if (el) el.textContent = msg || "";
  },
  attachUI() {
    const btn = document.getElementById("btn-upload-minutes");
    const input = document.getElementById("minutes-file");
    const link = document.getElementById("link-minutes-template");

    if (btn && input) {
      btn.onclick = () => input.click();
      input.onchange = async (ev) => {
        if (!ev.target.files || !ev.target.files[0]) return;
        const file = ev.target.files[0];
        Minutes.setStatus("Uploading…");
        try {
          const res = await Minutes.upload(file);
          Minutes.setStatus(`Applied ${res.count} minutes (updated ${res.updated_at})`);
          // Trigger a re-render of current team if one is open
          try { await App.refreshCurrentTeam(); } catch (_) {}
        } catch (e) {
          Minutes.setStatus(`Error: ${e.message}`);
        } finally {
          input.value = "";
        }
      };
    }
    if (link) {
      link.onclick = () => {
        // allow default navigation
      };
    }
  },
  applyToRoster(roster) {
    // roster: array of player objects used by your Team Sheet render pipeline
    // Expected player field names we try in order:
    //   player, name, Player, Name
    if (!Array.isArray(roster)) return roster;
    const out = roster.map((p) => {
      const name = p.player || p.name || p.Player || p.Name || "";
      const key = Minutes.normName(String(name));
      const o = Minutes.cache.overrides[key];
      if (o && typeof o.minutes === "number" && !Number.isNaN(o.minutes)) {
        // prefer to set to common fields: minutes / mins / proj_minutes
        if ("minutes" in p) p.minutes = o.minutes;
        else if ("mins" in p) p.mins = o.minutes;
        else p.minutes = o.minutes;
        // we do NOT alter any other stat; just minutes
      }
      return p;
    });
    return out;
  }
};

// ---------------------------------------------
// Minimal App skeleton you probably already have
// Keep your existing code; just wire Minutes.applyToRoster
// into the Team Sheet render path.
// ---------------------------------------------
const App = {
  // Track which team is currently selected so we can re-render after upload
  _currentTeamId: null,

  async init() {
    Minutes.attachUI();
    await Minutes.load();
    // ... your other init
  },

  async selectTeam(teamId) {
    App._currentTeamId = teamId;
    // 1) fetch roster as you currently do
    const roster = await App.fetchTeamRoster(teamId); // <- you already have this
    // 2) apply minutes overrides
    const rosterWithMinutes = Minutes.applyToRoster(roster);
    // 3) render as you already do
    await App.renderTeamSheet(rosterWithMinutes);     // <- your existing renderer
  },

  async refreshCurrentTeam() {
    if (App._currentTeamId) {
      await App.selectTeam(App._currentTeamId);
    }
  },

  // ------- placeholders; keep your real ones -------
  async fetchTeamRoster(teamId) {
    // Example: const res = await fetch(`/api/team/${teamId}/roster`);
    // return await res.json();
    return []; // your real implementation populates this
  },
  async renderTeamSheet(roster) {
    // Your existing DOM update logic goes here.
    // We intentionally don't change your layout/controls.
  }
};

// Boot
window.addEventListener("DOMContentLoaded", () => {
  App.init();
});
