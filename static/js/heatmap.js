/**
 * heatmap.js — 32×32 pressure heatmap canvas renderer with timeline playback
 */
const HeatmapPlayer = (() => {
  let canvas, ctx, frames = [], idx = 0, timer = null, opts = {};

  /* Thermal colour map: deep blue → cyan → green → yellow → red */
  function toColor(v, max) {
    if (max === 0 || v === 0) return [10, 15, 30];
    const t = Math.max(0, Math.min(1, v / max));
    const stops = [[0,0,120],[0,180,220],[0,220,80],[255,220,0],[255,30,30]];
    const s = t * (stops.length - 1);
    const lo = Math.floor(s), hi = Math.min(stops.length-1, lo+1), f = s - lo;
    return stops[lo].map((c,i) => Math.round(c + (stops[hi][i]-c)*f));
  }

  function draw(matrix) {
    const W = canvas.width, H = canvas.height;
    const cw = W/32, ch = H/32;
    const max = Math.max(...matrix, 1);
    for (let r = 0; r < 32; r++) {
      for (let c = 0; c < 32; c++) {
        const v = matrix[r*32+c]||0;
        const [R,G,B] = toColor(v, max);
        ctx.fillStyle = v===0 ? '#090e1c' : `rgba(${R},${G},${B},0.93)`;
        ctx.fillRect(Math.round(c*cw), Math.round(r*ch), Math.ceil(cw), Math.ceil(ch));
      }
    }
  }

  function blank() {
    ctx.fillStyle = '#090e1c';
    ctx.fillRect(0, 0, canvas.width, canvas.height);
    ctx.fillStyle = '#64748b';
    ctx.font = '13px DM Sans, sans-serif';
    ctx.textAlign = 'center';
    ctx.fillText('No data uploaded yet', canvas.width/2, canvas.height/2);
  }

  async function loadFrame(id) {
    let url = opts.frameUrl + id + '/';
    // append patient_id query if already in framesUrl
    const m = (opts.framesUrl||'').match(/patient_id=(\d+)/);
    if (m) url += '?patient_id=' + m[1];
    const r = await fetch(url);
    if (!r.ok) return;
    const d = await r.json();
    draw(d.matrix);
    if (opts.peakEl)    document.getElementById(opts.peakEl).textContent = (d.peak_pressure||0).toFixed(0);
    if (opts.contactEl) document.getElementById(opts.contactEl).textContent = (d.contact_area_pct||0).toFixed(1)+'%';
    if (opts.avgEl)     document.getElementById(opts.avgEl).textContent = (d.avg_pressure||0).toFixed(1);
    const pel = opts.peakEl && document.getElementById(opts.peakEl);
    if (pel) pel.style.color = d.is_flagged ? '#f87171' : '';
  }

  function updateUI(i) {
    const sl = opts.frameSlider && document.getElementById(opts.frameSlider);
    if (sl) sl.value = i;
    const ts = opts.timestampEl && document.getElementById(opts.timestampEl);
    if (ts && frames[i]) ts.textContent = frames[i].timestamp;
    const co = opts.counterEl && document.getElementById(opts.counterEl);
    if (co) co.textContent = `Frame ${i+1} / ${frames.length}`;
  }

  async function goTo(i) {
    if (!frames.length) return;
    i = Math.max(0, Math.min(frames.length-1, i));
    idx = i; updateUI(i);
    await loadFrame(frames[i].id);
  }

  async function fetchFrames(sessionId) {
    let url = opts.framesUrl || '/dashboard/api/frames/';
    if (sessionId) url += (url.includes('?')?'&':'?') + 'session_id=' + sessionId;
    const r = await fetch(url);
    return r.ok ? await r.json() : [];
  }

  function play()  { if (!timer) timer = setInterval(()=>goTo((idx+1)%Math.max(1,frames.length)), 180); }
  function pause() { clearInterval(timer); timer = null; }

  async function init(canvasId, options) {
    canvas = document.getElementById(canvasId);
    if (!canvas) return;
    ctx = canvas.getContext('2d');
    opts = options || {};
    ctx.fillStyle = '#090e1c';
    ctx.fillRect(0,0,canvas.width,canvas.height);

    frames = await fetchFrames(null);
    if (!frames.length) { blank(); return; }

    const sl = opts.frameSlider && document.getElementById(opts.frameSlider);
    if (sl) {
      sl.max = frames.length - 1;
      sl.addEventListener('input', () => goTo(parseInt(sl.value)));
    }
    const pb = opts.playBtn  && document.getElementById(opts.playBtn);
    const ps = opts.pauseBtn && document.getElementById(opts.pauseBtn);
    if (pb) pb.addEventListener('click', play);
    if (ps) ps.addEventListener('click', pause);

    const ss = opts.sessionSelect && document.getElementById(opts.sessionSelect);
    if (ss) ss.addEventListener('change', async () => {
      pause(); frames = await fetchFrames(ss.value||null);
      if (sl) sl.max = Math.max(0, frames.length-1);
      idx = 0; if (frames.length) await goTo(frames.length-1);
    });

    await goTo(frames.length - 1);
  }

  return { init, goTo, play, pause };
})();
