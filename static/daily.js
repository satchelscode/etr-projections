// static/daily.js
(function(){
  const qs = (s, r=document)=>r.querySelector(s);

  async function uploadDaily() {
    const file = qs('#daily-file').files[0];
    const date = qs('#daily-date').value;
    const status = qs('#daily-status');

    if (!file) { status.textContent = 'Choose a CSV file first.'; return; }
    status.textContent = 'Uploading & retraining…';

    const fd = new FormData();
    fd.append('file', file);
    if (date) fd.append('date', date);

    let resp, json;
    try {
      resp = await fetch('/api/daily/upload', { method: 'POST', body: fd });
      json = await resp.json();
    } catch (e) {
      status.textContent = 'Network error.';
      return;
    }
    if (!json.ok) {
      status.textContent = `Error: ${json.error || 'Upload failed'}`;
      return;
    }
    status.textContent = `OK — ${json.message}`;
  }

  window.addEventListener('DOMContentLoaded', ()=>{
    const btn = qs('#daily-upload-btn');
    if (btn) btn.addEventListener('click', uploadDaily);
  });
})();
