// minutes.js - non-invasive minutes upload + auto-apply
(function () {
  const qs  = (s, r=document) => r.querySelector(s);
  const qsa = (s, r=document) => Array.from(r.querySelectorAll(s));
  function status(msg){ const el=qs("#minutes-upload-status"); if(el) el.textContent=msg||""; }

  async function getOverrides(){
    try{ const r=await fetch("/api/minutes/overrides",{cache:"no-store"});
         if(!r.ok) return {overrides:{}}; return await r.json(); } catch { return {overrides:{}}; }
  }

  async function applyOverrides(){
    const data=await getOverrides();
    const map=(data&&data.overrides)||{};
    if(!Object.keys(map).length) return;
    const norm=s=>String(s||"").trim().toLowerCase().replace(/\s+/g," ");
    const rows=qsa("#teamTbl tbody tr");
    rows.forEach(tr=>{
      const nameCell=tr.querySelector("td:first-child");
      const input=tr.querySelector("input[name='mins']");
      if(!nameCell||!input) return;
      const key=norm(nameCell.textContent);
      const ov=map[key];
      if(ov && typeof ov.minutes==="number") input.value=ov.minutes;
    });
  }

  async function uploadCSV(file){
    const fd=new FormData(); fd.append("file",file);
    const r=await fetch("/api/minutes/upload",{method:"POST",body:fd});
    const j=await r.json(); if(!j.ok) throw new Error(j.error||"Upload failed");
    status(`Applied ${j.count} minutes (updated ${j.updated_at})`);
    await applyOverrides();
  }

  function wireUpload(){
    const btn=qs("#btn-upload-minutes"); const input=qs("#minutes-file");
    if(!btn||!input) return;
    btn.addEventListener("click",()=>input.click());
    input.addEventListener("change",async(ev)=>{
      const f=ev.target.files&&ev.target.files[0]; if(!f) return;
      status("Uploading…");
      try{ await uploadCSV(f);} catch(e){ status(`Error: ${e.message}`);} finally{ input.value=""; }
    });
  }

  function wireRoster(){
    const loadBtn=qs("#loadRosterBtn");
    if(!loadBtn) return;
    loadBtn.addEventListener("click",()=> setTimeout(applyOverrides, 300));
  }

  window.addEventListener("DOMContentLoaded",()=>{
    wireUpload(); wireRoster();
    getOverrides().then(d=> status(d.updated_at ? `Minutes loaded (${d.updated_at})` : "No minutes overrides"));
  });
})();