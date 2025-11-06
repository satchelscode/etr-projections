/* static/daily.js
   UI logic for:
   - Uploading an ETR CSV to /api/daily/upload
   - Listing the upload library from /api/daily/library
   - (Optional) quick link to projections artifact
*/

;(function () {
  // ---------- UTIL ----------
  function $(sel) { return document.querySelector(sel); }
  function el(tag, html) { const e = document.createElement(tag); e.innerHTML = html; return e; }

  async function jsonFetch(url, opts) {
    const r = await fetch(url, opts);
    const ct = r.headers.get("content-type") || "";
    if (!ct.includes("application/json")) {
      // Allow plain text for CSV endpoints etc.
      return { ok: r.ok, status: r.status, text: await r.text() };
    }
    const j = await r.json();
    if (!r.ok) throw new Error(j.error || r.statusText);
    return j;
  }

  // ---------- LIBRARY ----------
  async function loadLibrary() {
    const tbody = $("#upload-library-body");
    const note = $("#upload-library-note");
    if (tbody) tbody.innerHTML = "";
    if (note)  note.textContent = "";

    try {
      const res = await jsonFetch("/api/daily/library");

      // Accept any of these shapes
      const rows =
        res.items ||
        res.data  ||
        res.rows  ||
        res.list  ||
        Array.isArray(res) ? res : [];

      if (!rows.length) {
        if (tbody) {
          tbody.innerHTML = `<tr><td colspan="3" style="padding:10px;color:#666">No uploads found yet.</td></tr>`;
        } else if (note) {
          note.textContent = "No uploads found yet.";
        }
        return;
      }

      if (tbody) {
        for (const row of rows) {
          const date = row.date || "";
          const size = row.size || (row.size_kb != null ? `${row.size_kb} KB` : "");
          const href = row.download || row.href || row.url || row.download_url || "#";
          const tr = document.createElement("tr");
          tr.innerHTML = `
            <td>${date}</td>
            <td>${size}</td>
            <td><a href="${href}" target="_blank" rel="noopener noreferrer">Download</a></td>
          `;
          tbody.appendChild(tr);
        }
      }
    } catch (err) {
      console.error("loadLibrary error:", err);
      if (tbody) {
        tbody.innerHTML = `<tr><td colspan="3" style="padding:10px;color:#b00">Failed to load upload history.</td></tr>`;
      } else if (note) {
        note.textContent = "Failed to load upload history.";
      }
    }
  }

  // ---------- UPLOAD ----------
  async function wireUpload() {
    const form = $("#etr-upload-form");
    const fileInput = $("#etr-file");
    const dateInput = $("#etr-date");
    const btn = $("#upload-btn");
    const status = $("#upload-status");

    if (!form || !fileInput || !dateInput || !btn) return;

    // default date = today if empty
    if (!dateInput.value) {
      const now = new Date();
      const y = now.getFullYear();
      const m = String(now.getMonth()+1).padStart(2, "0");
      const d = String(now.getDate()).padStart(2, "0");
      dateInput.value = `${y}-${m}-${d}`;
    }

    btn.addEventListener("click", async (e) => {
      e.preventDefault();
      if (!fileInput.files || fileInput.files.length === 0) {
        if (status) status.textContent = "Please choose a CSV file first.";
        return;
      }
      const fd = new FormData();
      fd.append("file", fileInput.files[0]);
      fd.append("date", dateInput.value);

      btn.disabled = true;
      if (status) status.textContent = "Uploading & retraining…";

      try {
        const res = await jsonFetch("/api/daily/upload", {
          method: "POST",
          body: fd
        });

        const rows = res.rows_uploaded ?? res.rows ?? res.uploaded_rows ?? "N";
        if (status) status.textContent = `OK — Uploaded ${rows} rows for ${res.date} and retrained artifacts.`;

        // refresh library after a successful upload
        await loadLibrary();
      } catch (err) {
        console.error("upload error:", err);
        if (status) status.textContent = `Upload failed: ${err.message || err}`;
      } finally {
        btn.disabled = false;
        // clear file input for safety
        if (fileInput) fileInput.value = "";
      }
    });
  }

  // ---------- PROJECTIONS QUICK LINK (optional) ----------
  function showProjectionsLink() {
    const elLink = $("#projections-latest-link");
    if (!elLink) return;
    elLink.innerHTML =
      `<a href="/api/daily/projections/latest.csv" target="_blank" rel="noopener noreferrer">Download latest projections CSV</a>`;
  }

  // ---------- INIT ----------
  document.addEventListener("DOMContentLoaded", async () => {
    await wireUpload();
    await loadLibrary();
    showProjectionsLink();
  });
})();
