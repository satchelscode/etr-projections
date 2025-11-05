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

function toCSV(rows){
  if(!rows.length) return "";
  const headers = Object.keys(rows[0]);
  const csv = [headers.join(",")].concat(
    rows.map(r => headers.map(h => (r[h] ?? "")).join(","))
  );
  return csv.join("\n");
}

async function init(){
  // --- DOM refs
  const selPlayer = document.getElementById('player');
  const selOpp = document.getElementById('opponent');
  const inpPSearch = document.getElementById('playerSearch');
  const inpOSearch = document.getElementById('opponentSearch');
  const minutesInput = document.getElementById('minutes');

  const teamForRoster = document.getElementById('teamForRoster');
  const defaultTeamMinutes = document.getElementById('defaultTeamMinutes');
  const loadRosterBtn = document.getElementById('loadRosterBtn');
  const projectRosterBtn = document.getElementById('projectRosterBtn');
  const downloadCsvBtn = document.getElementById('downloadCsvBtn');
  const teamTbl = document.getElementById('teamTbl');
  const teamTBody = teamTbl.querySelector('tbody');

  // --- load initial options
  const allOpponents = await fetchJSON('/api/opponents');
  let currentTeam = "";
  let allPlayers = await fetchJSON('/api/players');

  fillSelect(selOpp, allOpponents);
  fillSelect(teamForRoster, allOpponents);
  fillSelect(selPlayer, allPlayers);

  // ---- opponent filter / roster mode for single-player ----
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
      currentTeam = selOpp.value || "";
      reloadPlayersForTeam(currentTeam, inpPSearch.value.trim().toLowerCase());
    }, 120);
  });

  // ---- single player project ----
  document.getElementById('projectBtn').addEventListener('click', async ()=>{
    const player = selPlayer.value;
    const opponent = selOpp.value;
    const minutes = parseFloat(minutesInput.value || '0');
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

  // ===== TEAM SHEET =====

  async function loadRoster(team){
    const roster = await fetchJSON('/api/players?team='+encodeURIComponent(team));
    teamTBody.innerHTML = '';
    roster.forEach(p=>{
      const tr = document.createElement('tr');

      const tdP = document.createElement('td'); tdP.textContent = p;
      const tdO = document.createElement('td'); tdO.textContent = team;

      const tdM = document.createElement('td');
      const mInput = document.createElement('input');
      mInput.type = 'number'; mInput.step = '0.1';
      mInput.value = parseFloat(defaultTeamMinutes.value || '30');
      mInput.style.width = '80px';
      tdM.appendChild(mInput);

      // placeholder cells for projections
      const makeCell = () => document.createElement('td');
      const tdPTS = makeCell(), tdREB = makeCell(), tdAST = makeCell(), td3PM = makeCell(),
            tdSTL = makeCell(), tdBLK = makeCell(), tdTO = makeCell(), tdPRA = makeCell();

      tr.append(tdP, tdO, tdM, tdPTS, tdREB, tdAST, td3PM, tdSTL, tdBLK, tdTO, tdPRA);
      teamTBody.appendChild(tr);
    });
    teamTbl.style.display = 'table';
  }

  loadRosterBtn.addEventListener('click', async ()=>{
    const t = teamForRoster.value;
    if(!t){ alert('Pick a team'); return; }
    await loadRoster(t);
  });

  projectRosterBtn.addEventListener('click', async ()=>{
    const team = teamForRoster.value;
    const rows = [];
    [...teamTBody.querySelectorAll('tr')].forEach(tr=>{
      const player = tr.children[0].textContent;
      const minutes = parseFloat(tr.children[2].querySelector('input').value || '0');
      if(minutes > 0){
        rows.push({player, opponent: team, minutes});
      }
    });
    if(!rows.length){ alert('Enter minutes for at least one player'); return; }

    const out = await fetchJSON('/api/project_bulk', {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({rows})
    });

    // write results into table cells
    const idx = {}; out.forEach(r => { idx[r.player] = r; });
    [...teamTBody.querySelectorAll('tr')].forEach(tr=>{
      const p = tr.children[0].textContent;
      const r = idx[p]; if(!r) return;
      const cells = [
        r.Proj_Points, r.Proj_Rebounds, r.Proj_Assists,
        r['Proj_Three Pointers Made'], r.Proj_Steals, r.Proj_Blocks,
        r.Proj_Turnovers, r.Proj_PRA
      ];
      for(let i=0;i<cells.length;i++){
        tr.children[3+i].textContent = (cells[i]===undefined?'—':cells[i]);
      }
    });

    // store for CSV
    projectRosterBtn.dataset.lastCsv = JSON.stringify(out);
  });

  downloadCsvBtn.addEventListener('click', ()=>{
    const raw = projectRosterBtn.dataset.lastCsv;
    if(!raw){ alert('Run "Project All" first.'); return; }
    const rows = JSON.parse(raw);
    const keep = rows.map(r => ({
      Player: r.player, Opponent: r.opponent, Minutes: r.minutes,
      PTS: r.Proj_Points, REB: r.Proj_Rebounds, AST: r.Proj_Assists,
      "3PM": r['Proj_Three Pointers Made'], STL: r.Proj_Steals,
      BLK: r.Proj_Blocks, TO: r.Proj_Turnovers, PRA: r.Proj_PRA
    }));
    const csv = toCSV(keep);
    const blob = new Blob([csv], {type: "text/csv"});
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url; a.download = `etr_team_projections_${teamForRoster.value}.csv`;
    document.body.appendChild(a); a.click(); a.remove();
    URL.revokeObjectURL(url);
  });
}

init().catch(err=>{
  alert('Init failed: '+err.message);
  console.error(err);
});

