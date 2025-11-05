// static/daily.js
(function(){
  const $ = (s, r=document)=>r.querySelector(s);

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

      // Try to parse JSON if possible; otherwise show status + text
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

      if (status) status.textContent = `OK — ${payload.message}`;
    } catch (e) {
      if (status) status.textContent = 'Network error.';
    }
  }

  function bind() {
    const btn = document.getElementById('daily-upload-btn');
    if (btn && !btn.__bound) { btn.__bound = true; btn.addEventListener('click', uploadDaily); }
  }

  document.addEventListener('DOMContentLoaded', bind);
})();
