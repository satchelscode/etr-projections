// static/daily.js
(function(){
  const $  = (s, r=document)=>r.querySelector(s);
  const $$ = (s, r=document)=>Array.from(r.querySelectorAll(s));

  async function uploadDaily() {
    const file = $('#daily-file')?.files?.[0];
    const date = $('#daily-date')?.value || '';
    const status = $('#daily-status');

    if (!file) { if(status) status.textContent = 'Choose a CSV file first.'; return; }
    if (status) status.textContent = 'Uploading & retraining…';

    const fd = new FormData();
    fd.append('file', file);
    if (date) fd.append('date', date);

    try {
      const resp = await fetch('/api/daily/upload', { method: 'POST', body: fd });
      const ctype = resp.headers.get('content-type') || '';
      let payload = null, text = '';
      if (ctype.includes('application/json')) {
        payload = await resp.json();
      } else {
        text = await resp.text();
      }

      if (!resp.ok) {
        if (payload && payload.error) {
          if (status) status.textContent = `Error ${resp.status}: ${payload.error}`;
        } else {
          if (status) status.textContent = `Error ${resp.status}${text ? `: ${text.slice(0,200)}` : ''}`;
        }
        return;
      }

      if (!payload || !payload.ok) {
        if (status) status.textContent = `Error: ${(payload && payload.error) ? payload.error : 'Upload failed'}`;
        return;
      }

      if (status) status.textContent = `OK — Uploaded ${payload.added_rows} rows for ${payload.date} and retrained artifacts.`;
      // refresh the library list
      loadDailyLibrary();
    } catch (e) {
      if (status) status.textContent = 'Network error.';
    }
  }

  async function loadDailyLibrary() {
    const box = $('#daily-library');
    if (!box) return;
    box.innerHTML = 'Loading history…';
    try {
      const resp = await fetch('/api/daily/raw_list');
      const data = await resp.json();
      if (!data.ok) { box.textContent = data.error || 'Failed to load.'; return; }
      if (!data.items.length) { box.textContent = 'No uploads yet.'; return; }

      const rows = data.items.map(item => {
        const sizeKB = Math.round(item.size_bytes / 102.4) / 10;
        return `
          <tr>
            <td>${item.date}</td>
            <td>${sizeKB.toLocaleString()} KB</td>
            <td><a href="${item.download}">Download</a></td>
          </tr>`;
      }).join('');

      box.innerHTML = `
        <h4 style="margin:16px 0 8px;">Upload Library</h4>
        <table style="width:100%; border-collapse: collapse;">
          <thead>
            <tr><th style="text-align:left;border-bottom:1px solid #ddd;padding:6px 0;">Date</th>
                <th style="text-align:left;border-bottom:1px solid #ddd;padding:6px 0;">Size</th>
                <th style="text-align:left;border-bottom:1px solid #ddd;padding:6px 0;">File</th></tr>
          </thead>
          <tbody>${rows}</tbody>
        </table>`;
    } catch (_) {
      box.textContent = 'Failed to load upload history.';
    }
  }

  function bind() {
    const btn = document.getElementById('daily-upload-btn');
    if (btn && !btn.__bound) { btn.__bound = true; btn.addEventListener('click', uploadDaily); }
    loadDailyLibrary();
  }

  document.addEventListener('DOMContentLoaded', bind);
})();
