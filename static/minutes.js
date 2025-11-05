// static/minutes.js
(function () {
  const qs  = (s, r=document) => r.querySelector(s);
  const qsa = (s, r=document) => Array.from(r.querySelectorAll(s));
  const status = (m) => { const el = qs("#minutes-upload-status"); if (el) el.textContent = m || ""; };

  function findMinutesInput(tr) {
    // Minutes input is the 3rd column, but be flexible
    return (
      tr.querySelector('input[name="mins"]') ||
      tr.querySelector('input.minutes') ||
      tr.querySelector('td:nth-child(3) input') ||
      tr.querySelector('input[type="number"]') ||
      tr.querySelector('input')
    );
  }

  async function getOverrides() {
    try {
      const r = await fetch("/api/minutes/overrides", { cache: "no-store" });
      if (!r.ok) return { overrides: {} };
      return await r.json();
    } catch {
      return { overrides: {} };
    }
  }

  async function applyOverridesToTeamTable() {
    const data = await getOverrides();
    const map = (data && data.overrides) || {};
    if (!Object.keys(map).length) return;

    const norm = (s) => String(s || "").trim().toLowerCase().replace(/\s+/g, " ");

    qsa("#teamTbl tbody tr").forEach(tr => {
      const nameCell = tr.querySelector("td:first-child");
      const minsInput = findMinutesInput(tr);
      if (!nameCell || !minsInput) return;
      const key = norm(nameCell.textContent);
      const ov = map[key];
      if (ov && typeof ov.minutes === "number") {
        minsInput.value = ov.minutes;
        minsInput.dispatchEvent(new Event("input", { bubbles: true }));
        minsInput.dispatchEvent(new Event("change", { bubbles: true }));
      }
    });
  }

  async function uploadCSV(file) {
    const fd = new FormData();
    fd.append("file", file);

    let resp, json;
    try {
      resp = await fetch("/api/minutes/upload", { method: "POST", body: fd });
    } catch (e) {
      status(`Network error: ${e.message}`);
      return;
    }

    try {
      json = await resp.json();
    } catch (e) {
      status(`Bad response`);
      return;
    }

    if (!json.ok) {
      status(`Error: ${json.error || "Upload failed"}`);
      return;
    }

    status(`Applied ${json.count} minutes (updated ${json.updated_at})`);
    await applyOverridesToTeamTable();
  }

  function wireUpload() {
    const btn = qs("#btn-upload-minutes");
    const input = qs("#minutes-file");
    if (!btn || !input) {
      status("Upload controls not found");
      return;
    }
    btn.addEventListener("click", () => input.click());
    input.addEventListener("change", async (ev) => {
      const f = ev.target.files && ev.target.files[0];
      if (!f) { status("No file selected"); return; }
      status("Uploading…");
      await uploadCSV(f);
      input.value = "";
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
