async function fetchJSON(url, opts){
  const res = await fetch(url, opts);
  if(!res.ok) throw new Error(await res.text());
  return res.json();
}

async function init(){
  try {
    const players = await fetchJSON('/api/players');
    const opponents = await fetchJSON('/api/opponents');

    const selPlayer = document.getElementById('player');
    const selOpp = document.getElementById('opponent');

    players.forEach(p=>{ const o=document.createElement('option'); o.value=o.textContent=p; selPlayer.appendChild(o); });
    opponents.forEach(t=>{ const o=document.createElement('option'); o.value=o.textContent=t; selOpp.appendChild(o); });

    document.getElementById('projectBtn').addEventListener('click', async ()=>{
      const player = selPlayer.value;
      const opponent = selOpp.value;
      const minutes = parseFloat(document.getElementById('minutes').value || '0');
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
  } catch (e){
    alert('Init failed: '+e.message);
    console.error(e);
  }
}

init();
