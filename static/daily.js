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
      const json = await resp.json();
      if (!json.ok) {
        if (status) status.textContent = `Error: ${json.error || 'Upload failed'}`;
        return;
      }
      if (status) status.textContent = `OK — ${json.message}`;
    } catch (e) {
      if (status) status.textContent = 'Network error.';
    }
  }

  function bind() {
    const btn = $('#daily-upload-btn');
    if (btn && !btn.__bound) { btn.__bound = true; btn.addEventListener('click', uploadDaily); }
  }

  document.addEventListener('DOMContentLoaded', bind);
})();
