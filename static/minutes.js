// static/minutes.js
(function () {
  const qs  = (s, r=document) => r.querySelector(s);
  const qsa = (s, r=document) => Array.from(r.querySelectorAll(s));
  const status = (m) => { const el = qs("#minutes-upload-status"); if (el) el.textContent = m || ""; };

  async function getOverrides() {
    try {
      const r = await fetch("/api/minutes/overrides", { cache: "no-store" });
      if (!r.ok) return { overrides: {} };
      return await r.json();
    } catch { return { overrides: {} }; }
  }

  async function applyOverridesToTeamTable() {
    const data = await getOverrides();
    const map = (data && data.overrides) || {};
    if (!Object.keys(map).length) return;

    const norm = (s) => String(s || "").trim().toLowerCase().replace(/\s+/g, " ");

    qsa("#teamTbl tbody tr").forEach(tr => {
      const nameCell = tr.querySelector("td:first-child");
      const minsInput = tr.querySelector("input[name='mins']");
      if (!nameCell || !minsInput) return;
      const key = norm(nameCell.textContent);
      const ov = map[key];
      if (ov && typeof ov.minutes === "number") {
        minsInput.value = ov.minutes;
      }
    });
  }

  async function uploadCSV(file) {
    const fd = new FormData();
    fd.append("file", file);
    const r = await fetch("/api/minutes/upload", { method: "POST", body: fd });
    const j = await r.json();
    if (!j.ok) throw new Error(j.error || "Upload failed");
    status(`Applied ${j.count} minutes (updated ${j.updated_at})`);
    await applyOverridesToTeamTable();
  }

  function wireUpload() {
    const btn = qs("#btn-upload-minutes");
    const input = qs("#minutes-file");
    if (!btn || !input) return;
    btn.addEventListener("click", () => input.click());
    input.addEventListener("change", async (ev) => {
      const f = ev.target.files && ev.target.files[0];
      if (!f) return;
      status("Uploading…");
      try { await uploadCSV(f); }
      catch (e) { status(`Error: ${e.message}`); }
      finally { input.value = ""; }
    });
  }

  function wireRosterHook() {
    const loadBtn = qs("#loadRosterBtn");
    if (!loadBtn) return;
    loadBtn.addEventListener("click", () => setTimeout(applyOverridesToTeamTable, 300));
  }

  window.addEventListener("DOMContentLoaded", () => {
    wireUpload();
    wireRosterHook();
    getOverrides().then(d => status(d.updated_at ? `Minutes loaded (${d.updated_at})` : "No minutes overrides"));
  });
})();
