async function fetchJSON(url, opts){
  const res = await fetch(url, opts);
  if(!res.ok) throw new Error(await res.text());
  return res.json();
}

function fillSelect(sel, items){
  sel.innerHTML = "";
  items.forEach(v=>{
    const o = document.createElement('option');
    o.value = o.textContent = v;
    sel.appendChild(o);
  });
}

async function init(){
  // cache originals for filter resets
  const allOpponents = await fetchJSON('/api/opponents');

  const selPlayer = document.getElementById('player');
  const selOpp = document.getElementById('opponent');
  const inpPSearch = document.getElementById('playerSearch');
  const inpOSearch = document.getElementById('opponentSearch');

  // initial load: all players (server will return full list)
  let currentTeam = "";
  let allPlayers = await fetchJSON('/api/players');
  fillSelect(selPlayer, allPlayers);
  fillSelect(selOpp, allOpponents);

  // ---- opponent filter / roster mode ----
  async function reloadPlayersForTeam(teamCode, qPrefix=""){
    const params = new URLSearchParams();
    if(teamCode) params.set("team", teamCode);
    if(qPrefix) params.set("q", qPrefix);
    const list = await fetchJSON('/api/players?'+params.toString());
    fillSelect(selPlayer, list);
  }

  selOpp.addEventListener('change', async ()=>{
    currentTeam = selOpp.value || "";
    await reloadPlayersForTeam(currentTeam, inpPSearch.value.trim().toLowerCase());
  });

  // ---- type ahead for players (prefix filter) ----
  let pTimer;
  inpPSearch.addEventListener('input', ()=>{
    clearTimeout(pTimer);
    pTimer = setTimeout(async ()=>{
      const q = inpPSearch.value.trim().toLowerCase();
      await reloadPlayersForTeam(currentTeam, q);
    }, 120);
  });

  // ---- type ahead for opponents (client-side) ----
  let oTimer;
  inpOSearch.addEventListener('input', ()=>{
    clearTimeout(oTimer);
    oTimer = setTimeout(()=>{
      const q = inpOSearch.value.trim().toLowerCase();
      const filtered = allOpponents.filter(t => t.toLowerCase().startsWith(q));
      fillSelect(selOpp, filtered.length ? filtered : allOpponents);
      // keep currentTeam in sync if user typed a new team
      currentTeam = selOpp.value || "";
      // refresh players for that team
      reloadPlayersForTeam(currentTeam, inpPSearch.value.trim().toLowerCase());
    }, 120);
  });

  // ---- projection button ----
  document.getElementById('projectBtn').addEventListener('click', async ()=>{
    const player = selPlayer.value;
    const opponent = selOpp.value;
    const minutes = parseFloat(document.getElementById('minutes').value || '0');
    if(!player || !opponent || !minutes){
      alert('Pick player, opponent, and enter minutes.');
      return;
    }
    const data = await fetchJSON('/api/project', {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({player, opponent, minutes})
    });
    const tbl = document.getElementById('result');
    const tb = tbl.querySelector('tbody');
    tb.innerHTML = '';
    const tr = document.createElement('tr');
    const cells = [
      data.player, data.opponent, data.minutes,
      data.Proj_Points, data.Proj_Rebounds, data.Proj_Assists,
      data['Proj_Three Pointers Made'], data.Proj_Steals, data.Proj_Blocks,
      data.Proj_Turnovers, data.Proj_PRA
    ];
    cells.forEach(v=>{ const td=document.createElement('td'); td.textContent = (v===undefined?'—':v); tr.appendChild(td); });
    tb.appendChild(tr);
    tbl.style.display='table';
  });
}

init().catch(err=>{
  alert('Init failed: '+err.message);
  console.error(err);
});
