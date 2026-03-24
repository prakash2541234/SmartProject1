/**
 * charts.js — Chart.js line graphs for peak pressure & contact area
 */
const ChartManager = (() => {
  let peakChart = null, contactChart = null;
  let metricsUrl = '/dashboard/api/metrics/';
  let currentPid = null;

  const SCALE = {
    x: { ticks:{color:'#64748b',font:{size:10},maxTicksLimit:8}, grid:{color:'rgba(255,255,255,0.04)'} },
    y: { ticks:{color:'#64748b',font:{size:10}},                  grid:{color:'rgba(255,255,255,0.04)'} },
  };
  const TIP = { backgroundColor:'#1a2233', borderColor:'rgba(255,255,255,0.08)', borderWidth:1, titleColor:'#e2e8f0', bodyColor:'#94a3b8' };

  function fmt(ts) { const d=new Date(ts); return d.toLocaleTimeString([],{hour:'2-digit',minute:'2-digit'}); }

  async function load(hours) {
    let url = `${metricsUrl}?hours=${hours}`;
    if (currentPid) url += `&patient_id=${currentPid}`;
    const r = await fetch(url);
    return r.ok ? await r.json() : null;
  }

  function buildPeak(id, data) {
    const ctx = document.getElementById(id); if (!ctx) return;
    if (peakChart) peakChart.destroy();
    const colors = data.flags.map(f => f ? '#ef4444' : '#00d4aa');
    const radii  = data.flags.map(f => f ? 5 : 2);
    peakChart = new Chart(ctx, {
      type:'line',
      data:{ labels:data.labels.map(fmt),
             datasets:[{ label:'Peak Pressure', data:data.peak_pressure,
               borderColor:'#00d4aa', backgroundColor:'rgba(0,212,170,0.07)',
               borderWidth:2, fill:true, tension:0.35,
               pointBackgroundColor:colors, pointRadius:radii, pointHoverRadius:6 }] },
      options:{ responsive:true, animation:{duration:250},
        plugins:{ legend:{display:false}, tooltip:{...TIP, callbacks:{
          label: c=>`Peak: ${c.raw.toFixed(0)}${data.flags[c.dataIndex]?' ⚠️':''}` }} },
        scales:{ x:SCALE.x, y:{...SCALE.y, title:{display:true,text:'Pressure',color:'#64748b',font:{size:10}}} } }
    });
  }

  function buildContact(id, data) {
    const ctx = document.getElementById(id); if (!ctx) return;
    if (contactChart) contactChart.destroy();
    contactChart = new Chart(ctx, {
      type:'line',
      data:{ labels:data.labels.map(fmt),
             datasets:[
               { label:'Contact Area %', data:data.contact_area,
                 borderColor:'#0099cc', backgroundColor:'rgba(0,153,204,0.06)',
                 borderWidth:2, fill:true, tension:0.35, pointRadius:1.5 },
               { label:'Avg Pressure', data:data.avg_pressure,
                 borderColor:'#a78bfa', borderWidth:1.5, borderDash:[4,3],
                 fill:false, tension:0.35, pointRadius:1.5 }
             ] },
      options:{ responsive:true, animation:{duration:250},
        plugins:{ legend:{labels:{color:'#94a3b8',font:{family:'DM Sans',size:10}}}, tooltip:TIP },
        scales:SCALE }
    });
  }

  async function init(peakId, contactId, defaultHours, patientId, url) {
    if (url) metricsUrl = url;
    if (patientId) currentPid = patientId;
    const data = await load(defaultHours||6);
    if (data) { buildPeak(peakId, data); buildContact(contactId, data); }

    document.querySelectorAll('.tab-btn').forEach(btn => {
      btn.addEventListener('click', async () => {
        document.querySelectorAll('.tab-btn').forEach(b=>b.classList.remove('active'));
        btn.classList.add('active');
        const d = await load(parseInt(btn.dataset.hours));
        if (d) { buildPeak(peakId,d); buildContact(contactId,d); }
      });
    });
  }

  return { init };
})();
