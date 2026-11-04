// Kaaval bench: the review plays out live. Every colour and animation is driven by a simulation result.
try { document.getElementById('zoom').href = location.pathname.replace(/\/$/, '') + '/chip' } catch (e) {}
try { document.getElementById('l3d').href = location.pathname.replace(/\/$/, '') + '/layout3d' } catch (e) {}
(() => {
  const $ = s => document.querySelector(s);
  const esc = s => String(s).replace(/[&<>"]/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;'}[c]));
  const reduce = matchMedia('(prefers-reduced-motion: reduce)').matches;
  const G = (window.gsap && !reduce) ? gsap : null;
  const RID = location.pathname.split('/').pop();
  const root = document.documentElement;
  $('#theme').onclick = () => {
    const dark = root.dataset.theme ? root.dataset.theme === 'dark' : matchMedia('(prefers-color-scheme: dark)').matches;
    root.dataset.theme = dark ? 'light' : 'dark'; try { localStorage.setItem('kv-theme', root.dataset.theme) } catch (e) {}
  };
  fetch('/api/status').then(r => r.json()).then(m => { museOn = !!m.muse;
    if (museOn) { $('#who-st').textContent = 'checks proven in ngspice · Muse Spark connected'; $('#ask').placeholder = 'Ask Muse Spark about this review…';
      $('#ask').disabled = false; const n = document.querySelector('.composer .note');
      if (n) n.textContent = 'Muse Spark answers from this review\'s own findings, even while it runs. Every number above comes from a simulation.' }
    // the simulator and PDK the engine reports it actually runs, not a label
    const s = $('#simchip'); s.classList.add(m.sim_ok ? 'on' : 'off');
    s.querySelector('.t').textContent = m.sim_ok ? `${m.ngspice} · ${m.pdk}` : (m.ok ? 'simulator not found' : 'engine offline');
    s.title = m.sim_ok ? `Verified on the engine: ${m.ngspice}, ${m.pdk} models installed` : 'The engine could not confirm its simulator and PDK' });

  const ICON = {
    trap: '<svg viewBox="0 0 16 16"><path d="M4.5 4.5l7 7m0-7l-7 7" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/></svg>',
    ok: '<svg viewBox="0 0 16 16"><path d="M3.5 8.5l3 3 6-7" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg>',
    units: '<svg class="ic" viewBox="0 0 16 16"><path d="M2 12.5h12M4 12.5V9m3 3.5V6m3 6.5V8m3 4.5V4" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linecap="round"/></svg>',
    region: '<svg class="ic" viewBox="0 0 16 16"><path d="M2 13c3 0 3-9 6-9s3 9 6 9" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linecap="round"/></svg>',
    bias: '<svg class="ic" viewBox="0 0 16 16"><path d="M8 2v4m0 4v4M4 8h8" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linecap="round"/><circle cx="8" cy="8" r="2" fill="none" stroke="currentColor" stroke-width="1.4"/></svg>',
    spec: '<svg class="ic" viewBox="0 0 16 16"><path d="M4 2.5h6l2.5 2.5v8.5h-8.5zM6 7h4M6 9.5h4" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linejoin="round"/></svg>',
    fix: '<svg class="ic" viewBox="0 0 16 16"><path d="M10.5 2.5a3 3 0 0 0-3.9 3.9L2.5 10.5l3 3 4.1-4.1a3 3 0 0 0 3.9-3.9l-2 2-2-2z" fill="none" stroke="currentColor" stroke-width="1.3" stroke-linejoin="round"/></svg>',
  };
  const eng = (v, u) => { if (v == null) return '—'; const P = [[1e-12, 'p'], [1e-9, 'n'], [1e-6, 'µ'], [1e-3, 'm'], [1, '']];
    let s = P[0]; for (const p of P) if (Math.abs(v) >= p[0] * 0.9995) s = p; return (v / s[0]).toPrecision(3) + ' ' + s[1] + u };
  const condTxt = c => `${c[0]} · ${c[1]} °C · supply ×${c[2]}`;

  // ---------- canvas: pan / zoom, crisp at any zoom (non-scaling strokes) ----------
  const cv = $('#canvas'), stage = $('#stage');
  let view = {x: 0, y: 0, k: 1}, svg = null, box = null;
  const apply = (anim) => {
    const t = `translate(${view.x}px,${view.y}px) scale(${view.k})`;
    if (anim && G) G.to(stage, {transform: t, duration: 0.45, ease: 'power3.out'}); else stage.style.transform = t;
  };
  const fit = (anim) => {
    if (!svg) return; const W = cv.clientWidth, H = cv.clientHeight, pad = 56;
    view.k = Math.min((W - pad * 2) / box.w, (H - pad * 2 - 40) / box.h);
    view.x = (W - box.w * view.k) / 2; view.y = (H - box.h * view.k) / 2 + 10; apply(anim);
  };
  cv.addEventListener('wheel', e => {
    e.preventDefault(); const r = cv.getBoundingClientRect(), mx = e.clientX - r.left, my = e.clientY - r.top;
    const k2 = Math.min(12, Math.max(0.2, view.k * Math.exp(-e.deltaY * 0.0015)));
    view.x = mx - (mx - view.x) * k2 / view.k; view.y = my - (my - view.y) * k2 / view.k; view.k = k2; apply(false);
  }, {passive: false});
  let drag = null;
  cv.addEventListener('pointerdown', e => { if (e.target.closest('.tools,.label')) return; drag = {x: e.clientX, y: e.clientY, vx: view.x, vy: view.y}; cv.classList.add('drag'); cv.setPointerCapture(e.pointerId) });
  cv.addEventListener('pointermove', e => { if (!drag) return; view.x = drag.vx + e.clientX - drag.x; view.y = drag.vy + e.clientY - drag.y; apply(false) });
  cv.addEventListener('pointerup', () => { drag = null; cv.classList.remove('drag') });
  $('#zin').onclick = () => { const c = {x: cv.clientWidth / 2, y: cv.clientHeight / 2}; const k2 = view.k * 1.3; view.x = c.x - (c.x - view.x) * 1.3; view.y = c.y - (c.y - view.y) * 1.3; view.k = k2; apply(true) };
  $('#zout').onclick = () => { const c = {x: cv.clientWidth / 2, y: cv.clientHeight / 2}; view.x = c.x - (c.x - view.x) / 1.3; view.y = c.y - (c.y - view.y) / 1.3; view.k /= 1.3; apply(true) };
  $('#zfit').onclick = () => fit(true);
  new ResizeObserver(() => fit(false)).observe(cv);

  const loadSvg = async () => {
    const j = await (await fetch(`/api/runs/${RID}?svg=1&after=1e12`)).json();
    if (!j.live.svg) return false;
    stage.innerHTML = j.live.svg; svg = stage.querySelector('svg'); top = {svg: j.live.svg, dut: j.live.dut, tb: j.live.testbench, inst: (j.live.dut_inst || '').toLowerCase()};
    if (!matchMedia('(prefers-reduced-motion: reduce)').matches) {
      const els = [...svg.querySelectorAll('line, path, polyline, rect, circle')];
      els.forEach((e, i) => { e.setAttribute('pathLength', 1); e.classList.add('draw'); e.style.animationDelay = Math.min(1600, i * 6) + 'ms' });
      setTimeout(() => els.forEach(e => { e.classList.remove('draw'); e.removeAttribute('pathLength') }), 3200);
    }
    const vb = svg.viewBox.baseVal; box = {w: vb.width, h: vb.height};
    svg.setAttribute('width', vb.width); svg.setAttribute('height', vb.height);
    $('#cv-empty').hidden = true; $('#legend').hidden = false;
    const lab = $('#cv-label'); lab.hidden = false; lab.innerHTML = `<b>${esc(j.live.dut)}</b> · simulated by ${esc(j.live.testbench)}`;
    fit(false);
    if (G) { G.from(svg.querySelectorAll('.w'), {opacity: 0, duration: 0.6, stagger: {each: 0.004, from: 'random'}, ease: 'power2.out'});
             G.from(svg.querySelectorAll('.dev'), {opacity: 0, duration: 0.5, stagger: 0.01, ease: 'power2.out', delay: 0.15}) }
    return true;
  };
  // ---------- sub-sheets: a device below the top schematic is shown on the sheet where it is drawn ----------
  let top = null, sheet = '', lastDevices = {}, lastLive = {};
  const mount = (html, label) => {
    stage.innerHTML = html; svg = stage.querySelector('svg');
    const vb = svg.viewBox.baseVal; box = {w: vb.width, h: vb.height};
    svg.setAttribute('width', vb.width); svg.setAttribute('height', vb.height);
    const lab = $('#cv-label'); lab.hidden = false; lab.innerHTML = label; fit(false);
    const up = lab.querySelector('[data-up]'); if (up) up.onclick = e => { e.stopPropagation(); toTop() };
  };
  const toTop = () => { if (!top || !sheet) return; sheet = '';
    mount(top.svg, `<b>${esc(top.dut)}</b> · simulated by ${esc(top.tb)}`); colour(lastDevices) };
  const openSheet = async (path, leaf, cell) => {
    const key = (cell || '') + '|' + path;
    if (sheet === key) return true;
    const r = await fetch(`/api/runs/${RID}/sheet?path=${encodeURIComponent(path)}&hl=${encodeURIComponent(leaf)}` + (cell ? `&cell=${encodeURIComponent(cell)}` : ''));
    if (!r.ok) return false;
    const j = await r.json(); sheet = key;
    const crumbs = j.sheets.map((n, i) => `<span class="${i === j.sheets.length - 1 ? 'cur' : ''}">${esc(n.split('/').pop())}</span>`).join('<i>›</i>');
    mount(j.svg, `<button class="up" type="button" data-up title="Back to the top sheet">↑</button>${crumbs}<span class="via">via ${esc(path)}</span>`);
    return true;
  };
  // x1.x1.xm13 under DUT instance x1 -> sheet path "x1", drawn name "m13"
  const whereIs = sim => {
    const p = String(sim || '').toLowerCase().split('.');
    if (!top || p.length < 3 || p[0] !== top.inst) return null;
    return {path: p.slice(1, -1).join('.'), leaf: p[p.length - 1].replace(/^x(?=[mrcdqlv])/, '')};
  };
  const devEl = name => {
    if (!svg) return null; const n = name.toLowerCase();
    return [...svg.querySelectorAll('.dev')].find(g => { const d = (g.dataset.dev || '').toLowerCase(); return d === n || 'x' + d === n || d === 'x' + n });
  };
  const colour = devices => {
    for (const [name, d] of Object.entries(devices || {})) {
      const g = devEl(name); if (!g) continue;
      const cls = d.nominal !== 'sat' ? '' : d.margin == null ? '' : d.margin < 0 ? 'st-bad' : d.margin < 0.1 ? 'st-thin' : 'st-ok';
      const prev = g.dataset.st || '';
      if (cls !== prev) {
        g.classList.remove('st-ok', 'st-thin', 'st-bad'); if (cls) g.classList.add(cls); g.dataset.st = cls;
        if (G && cls === 'st-bad') G.fromTo(g, {opacity: 0.25}, {opacity: 1, duration: 0.5, repeat: 1, ease: 'power1.inOut'});
      }
      g.dataset.tip = d.margin == null ? `${name}: ${d.nominal} at nominal` :
        `${name}: worst margin ${(d.margin * 1e3).toFixed(0)} mV at ${condTxt(d.worst)}`;
    }
  };

  // ---------- PVT matrix ----------
  let grid = null; const cellEls = {};
  const buildMatrix = g => {
    grid = g; const m = $('#matrix');
    let h = '<span></span>' + g.temps.map(t => `<span class="ch">${t} °C</span>`).join('');
    h += '<span></span>' + g.temps.map(() => `<div class="grp">${g.vscales.map(v => `<span class="sub">×${v}</span>`).join('')}</div>`).join('');
    for (const c of g.corners) {
      h += `<span class="rh">${c}</span>` + g.temps.map(t => `<div class="grp">${g.vscales.map(v =>
        `<span class="cell${c === 'tt' && t === 27 && v === 1 ? ' nom' : ''}" data-k="${c}|${t}|${v}"></span>`).join('')}</div>`).join('');
    }
    m.innerHTML = h; m.querySelectorAll('.cell').forEach(el => { cellEls[el.dataset.k] = el; el.tabIndex = 0; el.setAttribute('role', 'button') });
    // a condition, clicked: its transistors that fail there are marked on the schematic, and the grid says what happened
    m.addEventListener('click', e => { const el = e.target.closest('.cell'); if (el) pickCell(el.dataset.k) });
    m.addEventListener('keydown', e => { const el = e.target.closest('.cell'); if (el && (e.key === 'Enter' || e.key === ' ')) { e.preventDefault(); pickCell(el.dataset.k) } });
  };
  const pickCell = k => {
    const c = lastCells.find(x => `${x.corner}|${x.temp}|${x.vscale}` === k); if (!c) return;
    Object.values(cellEls).forEach(x => x.classList.remove('picked')); cellEls[k].classList.add('picked');
    if (sheet) toTop();
    svg && svg.querySelectorAll('.dev.sel, .dev.cond').forEach(g => g.classList.remove('sel', 'cond'));
    const devs = (c.devices || []).map(d => String(d).split(' ')[0]), els = devs.map(devEl).filter(Boolean);
    els.forEach(g => g.classList.add('cond')); stage.classList.toggle('trail', els.length > 0);
    $('#pvt-n').innerHTML = `${seen.size} / 45<span class="selnote">· ${esc(condTxt([c.corner, c.temp, c.vscale]))}: ` +
      (c.status === 'err' ? `did not simulate (${esc(c.note || '')})` : devs.length ? `${devs.length} transistor(s) fail here: ${esc(devs.slice(0, 6).join(', '))}` :
       c.outputs ? 'behaves as at nominal' : 'every saturated transistor keeps saturation') + '</span>';
  };
  const seen = new Set();
  const addCells = cells => {
    for (const c of cells) {
      const k = `${c.corner}|${c.temp}|${c.vscale}`; if (seen.has(k)) continue; seen.add(k);
      const el = cellEls[k]; if (!el) continue;
      el.classList.add(c.status);
      const outs = c.outputs ? Object.entries(c.outputs).map(([k, v]) => `<br><span class="mono">${esc(k)}</span> ` +
        (v.freq > 0 ? `${(v.freq / 1e6).toPrecision(3)} MHz, ${v.pp.toFixed(2)} V swing` : `${v.mean.toFixed(3)} V`)).join('') : '';
      if (c.outputs) { el.dataset.tip = `<b>${condTxt([c.corner, c.temp, c.vscale])}</b>` + (c.devices && c.devices.length ?
        `<br>${esc(c.devices.join('; '))}` : '<br>behaves as at nominal') + outs; if (G) G.from(el, {scale: 0.4, opacity: 0, duration: 0.45, ease: 'back.out(2)'}); continue }
      el.dataset.tip = c.status === 'err' ? `<b>${condTxt([c.corner, c.temp, c.vscale])}</b><br>did not simulate: ${esc(c.note || '')}` :
        `<b>${condTxt([c.corner, c.temp, c.vscale])}</b><br>${c.n_triode ? c.n_triode + ' transistor(s) fall into triode' : 'every saturated transistor keeps saturation'}` +
        (c.worst_margin != null ? `<br>worst margin ${(c.worst_margin * 1e3).toFixed(0)} mV` : '') +
        (c.devices && c.devices.length ? `<br><span class="mono">${esc(c.devices.slice(0, 6).join(', '))}</span>` : '');
      if (G) G.from(el, {scale: 0.4, opacity: 0, duration: 0.45, ease: 'back.out(2)'});
    }
    $('#pvt-n').textContent = `${seen.size} / ${grid ? grid.corners.length * grid.temps.length * grid.vscales.length : 45}`;
  };

  // tooltips for cells and devices
  const tip = $('#tip');
  document.addEventListener('pointermove', e => {
    const t = e.target.closest('[data-tip]');
    if (!t) { tip.style.opacity = 0; return }
    tip.innerHTML = t.dataset.tip; tip.style.opacity = 1;
    const x = Math.min(e.clientX + 14, innerWidth - tip.offsetWidth - 8), y = Math.min(e.clientY + 14, innerHeight - tip.offsetHeight - 8);
    tip.style.left = x + 'px'; tip.style.top = y + 'px';
  });

  // ---------- left: stepper and check families ----------
  const renderSteps = (live, names, order) => {
    $('#steps').innerHTML = order.map(s => {
      const st = (live.stages || {})[s] || {state: 'pending'};
      const t = st.state === 'running' && st.t0 ? Math.round(Date.now() / 1000 - st.t0) + ' s' : st.dt != null ? st.dt + ' s' : '';
      return `<li class="step ${st.state}"><span class="mk"></span><span class="l">${names[s]}</span><span class="t num">${t}</span><span class="n">${esc(st.note || '')}</span></li>`;
    }).join('');
  };
  // a check is a filter: clicking it shows only its findings in the list (and says so when it found none)
  const FAMS = [['units/', 'Units and impossible sizes'], ['analog/headroom', 'Headroom across PVT'], ['analog/bias', 'Bias that collapses'],
    ['analog/stops_switching', 'Switching across PVT'], [/^analog\/(no_startup|two_states|oscillates|marginal_startup|floating_input)/, 'Power-up'],
    [/^analog\/(unstable|low_phase_margin)/, 'Stability'], ['analog/sequence_dependent', 'Chip power-up sequence'],
    ['analog/overstress', 'Cross-domain overstress'], ['analog/weak_output', 'Pad drive'], ['layout/', 'Layout against schematic']];
  const famOf = (p, rule) => typeof p === 'string' ? rule.startsWith(p) : p.test(rule);
  let filt = null, lastFs = [];
  const applyFilter = () => {
    let n = 0;
    Object.values(cards).forEach(c => { const on = !filt || famOf(filt[0], c.f.rule); c.el.hidden = !on; n += on });
    let bar = $('#fbar'); if (!bar) { bar = document.createElement('div'); bar.id = 'fbar'; bar.className = 'fbar'; flist.prepend(bar) }
    bar.hidden = !filt;
    if (filt) bar.innerHTML = `<span>${n ? `${n} finding${n > 1 ? 's' : ''} from <b>${esc(filt[1])}</b>` :
      `<b>${esc(filt[1])}</b> found nothing in this review`}</span><button class="btn" type="button" id="fall">Show all</button>`;
    if (filt) $('#fall').onclick = () => { filt = null; applyFilter(); document.querySelectorAll('.famrow.on').forEach(x => x.classList.remove('on')) };
  };
  $('#fams').addEventListener('click', e => {
    const r = e.target.closest('.famrow[data-fam]'); if (!r) return;
    const f = FAMS[+r.dataset.fam]; filt = filt && filt[1] === f[1] ? null : f;
    document.querySelectorAll('.famrow').forEach(x => x.classList.toggle('on', !!filt && x === r));
    tab('f'); applyFilter();
  });
  $('#fams').addEventListener('keydown', e => { if ((e.key === 'Enter' || e.key === ' ') && e.target.closest('.famrow[data-fam]')) { e.preventDefault(); e.target.click() } });
  const renderFams = (fs, lv) => {
    lastFs = fs;
    const n = p => fs.filter(f => f.rule.startsWith(p)).length;
    const dyn = lv && lv.kind === 'dynamic';
    const rows = [[ICON.units, 'Units and impossible sizes', n('units/')], [ICON.region, 'Headroom across PVT', dyn ? 'n/a' : n('analog/headroom')],
      [ICON.bias, 'Bias that collapses', dyn ? 'n/a' : n('analog/bias')],
      [ICON.region, 'Switching across PVT', dyn ? n('analog/stops_switching') : 'n/a'],
      [ICON.bias, 'Power-up, tests by Muse Spark', lv && lv.stages && lv.stages.muse && lv.stages.muse.state === 'skipped' ? 'n/a'
        : fs.filter(f => /^analog\/(no_startup|two_states|oscillates)/.test(f.rule)).length],
      [ICON.region, 'Stability (testbench loops, and tests by Muse Spark)', fs.filter(f => /^analog\/(unstable|low_phase_margin)/.test(f.rule)).length],
      [ICON.bias, 'Chip power-up sequence, by Muse Spark', lv && lv.stages && lv.stages.muse && lv.stages.muse.state === 'skipped' ? 'n/a'
        : fs.filter(f => f.rule === 'analog/sequence_dependent').length],
      [ICON.region, 'Cross-domain overstress (1.8 V devices, 3.3 V nodes)', fs.filter(f => f.rule === 'analog/overstress').length],
      [ICON.region, 'Pad drive (what the board and meter load)', fs.filter(f => f.rule === 'analog/weak_output').length],
      [ICON.units, 'Layout against schematic (Magic + Netgen)', n('layout/')],
      [ICON.fix, 'Sizing fixes by Muse Spark, proven at 45 conditions', null]];
    const sel = filt && filt[1];
    $('#fams').innerHTML = rows.map(([ic, l, c], i) => { const fi = i < FAMS.length ? i : -1;
      return `<div class="famrow${c && c !== 'n/a' ? ' has' : ''}${fi >= 0 ? ' click' : ''}${sel && fi >= 0 && FAMS[fi][1] === sel ? ' on' : ''}"` +
        (fi >= 0 ? ` data-fam="${fi}" role="button" tabindex="0"` : '') + (c === 'n/a' ? ` title="${esc(lv.kind_reason || '')}"` : '') + `>${ic}<span>${l}</span>` +
        (c == null ? '<span class="soon">next</span>' : c === 'n/a' ? '<span class="soon">n/a</span>' : `<span class="c num">${c}</span>`) + '</div>' }).join('');
  };

  // ---------- right: reviewer feed ----------
  const feed = $('#feed'), flist = $('#flist'); const shown = new Set(); let after = 0;
  // ---------- ask: a question about the finished review, answered by Muse Spark from the review's own findings ----------
  let museOn = false, asking = false; const byId = {};
  const askBox = $('#ask');
  const askQ = async () => {
    const q = askBox.value.trim(); if (!q || asking) return;
    asking = true; askBox.value = ''; tab('a');
    say(`<span class="ts">you</span>${esc(q)}`, 'q');
    const wait = document.createElement('div'); wait.className = 'msg a'; wait.innerHTML = '<span class="spin s"></span>Muse Spark is reading the review…';
    feed.appendChild(wait); wait.scrollIntoView({block: 'end'});
    try {
      let code = ''; try { code = sessionStorage.getItem('kv-code') || '' } catch (e2) {}   // the code the intake page asked for
      const r = await fetch(`/api/runs/${RID}/ask`, {method: 'POST', headers: {'Content-Type': 'application/json', 'X-Kaaval-Code': code}, body: JSON.stringify({q})});
      const j = await r.json();
      if (!j.ok) { wait.innerHTML = `<span class="ts">Muse Spark</span>${esc(j.error || 'no answer')}`; return }
      const chips = (j.cites || []).map(id => { const f = byId[id]; return f ? `<span class="cite"><button type="button" data-open="${id}">${esc(f.rule.split('/').pop())}</button>` +
        `<button type="button" data-walkto="${id}" title="Walk me through it">▶</button></span>` : '' }).join('');
      wait.innerHTML = `<span class="ts">Muse Spark</span>${esc(j.answer)}${chips ? `<div class="cites">${chips}</div>` : ''}`;
      const open = id => { tab('f'); select(byId[id], cards[id].el) };
      wait.querySelectorAll('[data-open]').forEach(b => b.onclick = () => open(b.dataset.open));
      // the walk-through when this bench has it (tour.js), else the finding itself
      wait.querySelectorAll('[data-walkto]').forEach(b => b.onclick = () => typeof walk === 'function' ? walk(byId[b.dataset.walkto]) : open(b.dataset.walkto));
    } catch (e) { wait.textContent = 'Muse Spark could not answer: ' + e } finally { asking = false }
  };
  askBox.addEventListener('keydown', e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); askQ() } });
  const tab = which => { const f = which === 'f'; $('#tab-f').setAttribute('aria-selected', f); $('#tab-a').setAttribute('aria-selected', !f);
    flist.hidden = !f; feed.hidden = f };
  $('#tab-f').onclick = () => tab('f'); $('#tab-a').onclick = () => tab('a');
  let switched = false;
  const say = (html, cls = '') => { const d = document.createElement('div'); d.className = 'msg ' + cls; d.innerHTML = html; feed.appendChild(d);
    if (G) G.from(d, {y: 6, opacity: 0, duration: 0.35, ease: 'power2.out'}); d.scrollIntoView({block: 'end'}) };
  const cards = {};
  const fixHtml = f => {
    const x = f.fix;
    if (f.kind !== 'risk' || !/^analog\/headroom/.test(f.rule)) return '';   // the sizing search answers headroom findings
    if (!x && !museOn) return '';                                            // Muse Spark proposes the sizes: offered when it is connected
    if (!x) return `<button class="btn fixbtn" type="button" data-fix="${f.id}">${ICON.fix.replace('class="ic"', '')}Ask Muse Spark for a sizing fix</button>`;
    if (x.state === 'running') return '<div class="fixres run"><span class="spin s"></span>Muse Spark is proposing sizes; each proposal is re-simulated at all 45 conditions…</div>';
    if (x.state === 'error') return `<div class="fixres bad">Could not size: ${esc(x.why || '')}</div>`;
    const chg = c => (c || []).map(d => `${esc(d.device)} ${esc(d.before || '')} → ${esc(d.after || `W=${d.W} L=${d.L}`)}`).join(', ');
    if (x.by === 'muse') return x.verified
      ? `<div class="fixres good">${ICON.ok}<div><b>Verified fix, proposed by Muse Spark.</b> ${chg(x.changes)}: saturated at all ${x.n_conditions} conditions, no new finding`
        + ` (round ${x.rounds.length} of ${x.rounds.length}).<div class="why">${esc(x.why || '')}</div></div></div>`
      : `<div class="fixres meh"><div><b>No verified fix.</b> ${esc(x.why || '')}</div><details><summary>${x.rounds.length} proposal(s) by Muse Spark</summary>`
        + x.rounds.map(r => `<div class="mono">${chg(r.changes)}: ${esc(r.result.why || (r.result.n_bad ? `still in triode at ${r.result.n_bad}/45` : (r.result.new || []).join(' | ')))}</div>`).join('') + '</details></div>';
    if (x.verified) return `<div class="fixres good">${ICON.ok}<div><b>Verified fix.</b> Widen ${esc(x.group.join(', '))} ×${x.factor}: saturated at all ${x.n_conditions} conditions, `
      + `worst margin ${(x.margin_before * 1e3).toFixed(0)} → ${(x.margin_after * 1e3).toFixed(0)} mV, nominal currents within ${(x.nominal_shift * 100).toFixed(1)} %.</div></div>`;
    const last = (x.tried || []).slice(-1)[0];
    return `<div class="fixres meh"><div><b>No sizing fix.</b> Widening ${esc((x.group || []).join(', '))} up to ×8 ${last ? 'still fails: ' + esc(last[2]) : ''}. `
      + `The stack has no headroom at this condition: it needs re-biasing, or an operating range that excludes it.</div>`
      + `<details><summary>${(x.tried || []).length} attempts</summary>${(x.tried || []).map(t => `<div class="mono">×${t[0]} · current shift ${(t[1] * 100).toFixed(1)} % · ${esc(t[2])}</div>`).join('')}</details></div>`;
  };
  // a planned test's finding can be checked without Kaaval: the plan, every measured condition and an ngspice deck
  const evHtml = f => f.detail && (Number.isInteger(f.detail.k) || f.detail.loop) ?
    `<a class="evdl" href="/api/runs/${RID}/findings/${f.id}/evidence" download>Download evidence (plan, results, ngspice deck)</a>` : '';
  const PLAIN = {'analog/no_startup': 'This circuit can wake up dead.', 'analog/two_states': 'This circuit can wake up in the wrong state.',
    'analog/oscillates': 'This circuit never settles: it oscillates.', 'analog/unstable': 'This loop is unstable.',
    'analog/low_phase_margin': 'This loop rings: its margins are thin.',
    'analog/sequence_dependent': 'This circuit works only if the chip powers up in the right order.',
    'analog/overstress': 'A 1.8 V transistor sees a 3.3 V voltage: it will wear out or break.',
    'analog/weak_output': 'This output cannot drive the pad: what you measure depends on your meter.',
    'layout/devices_differ': 'The layout builds other devices than the schematic: the chip is not the circuit you simulated, or the schematic is out of date.',
    'layout/sizes_differ': 'The layout draws its devices at other sizes than the schematic.',
    'layout/ports_differ': 'The same circuit as the schematic, but its ports are named or wired otherwise: check that every port is connected.',
    'layout/dummies': 'The layout adds dummy devices (off, or driving nothing) that the schematic does not have.',
    'layout/ideal_parts': 'The schematic simulates ideal parts (a capacitor written as its value, an R with no model) that the layout cannot draw.',
    'layout/bodies_untied': 'The layout leaves transistor bodies (an n-well, the substrate) on a net of their own; tied as the schematic ties them, the circuit matches.',
    'layout/split_pin': 'A pin is drawn in pieces that are not connected to each other: only what joins them above makes them one net.'};
  const card = f => {
    const d = document.createElement('div'); d.className = 'card'; d.tabIndex = 0;
    const pill = f.kind === 'trap' ? `<span class="pill trap">${ICON.trap}Simulation trap</span>` :
      f.kind === 'note' ? '<span class="pill note">Spread</span>' : '<span class="pill risk">Design risk</span>';
    const corr = f.detail && f.detail.corrected ? '<div class="corr">Simulated with the units trap corrected</div>' : '';
    // power-up findings lead with what they mean, in plain words; the measured detail follows
    const plain = PLAIN[f.rule] ? `<div class="plain">${PLAIN[f.rule]}</div>` : '';
    const st = (f.detail && f.detail.states) || [];
    const states = f.rule === 'analog/two_states' && st.length === 2 ? `<div class="states num">${st.map((x, i) =>
      `<span><i>${i ? 'after power-up' : 'DC analysis'}</i>${(x.v != null ? x.v.toFixed(3) + ' V · ' : '')}${(x.i * 1e6).toFixed(1)} µA</span>`).join('')}</div>` : '';
    const by = f.detail && f.detail.planner === 'muse' ? '<div class="by">Test written by Muse Spark · run by the engine</div>' : '';
    const simDev = (f.detail && f.detail.device) || '', dv = simDev.split('.').length > 2 ? simDev.split('.').slice(1).join('.') : (f.device || '');
    d.innerHTML = `<div class="h">${pill}<span class="dv">${esc(dv)}</span></div>${plain}${states}<div class="tt">${esc(f.title)}</div>${by}${corr}<div class="loc">${esc(f.location)}</div><div class="fx">${fixHtml(f)}</div>${evHtml(f)}<div class="walkrow"><button class="btn walk" type="button" data-walk>Walk me through it</button><a class="chiplink" href="${location.pathname.replace(/\/$/, '')}/chip?f=${f.id}">See it on the chip</a></div>`;
    d.onclick = e => { if (e.target.closest('.evdl, .chiplink')) return; if (e.target.closest('[data-walk]')) { e.stopPropagation(); walk(f); return } const b = e.target.closest('[data-fix]'); if (b) { e.stopPropagation(); askFix(b.dataset.fix); return } if (e.target.closest('details')) return; select(f, d) };
    d.onkeydown = e => { if (e.key === 'Enter') select(f, d) };
    cards[f.id] = {el: d, key: JSON.stringify(f.fix || null), f};
    if (filt && !famOf(filt[0], f.rule)) d.hidden = true;
    flist.appendChild(d); if (G) G.from(d, {y: 8, opacity: 0, duration: 0.4, ease: 'power2.out'});
  };
  const updateCard = f => {
    const c = cards[f.id]; const k = JSON.stringify(f.fix || null); if (!c || c.key === k) return;
    c.key = k; const fx = c.el.querySelector('.fx'); fx.innerHTML = fixHtml(f);
    if (G) G.from(fx, {opacity: 0, y: 4, duration: 0.3, ease: 'power2.out'});
  };
  let polling = true;
  const askFix = async fid => {
    await fetch(`/api/runs/${RID}/findings/${fid}/fix`, {method: 'POST'});
    if (!polling) { polling = true; tick() }
  };
  // ---------- evidence: what the selected finding's test actually measured ----------
  const CORN = ['tt', 'ss', 'ff', 'sf', 'fs'], TEMPS = [-40, 27, 125], VS = [0.9, 1.0, 1.1];
  const cssv = n => getComputedStyle(document.documentElement).getPropertyValue(n).trim();
  const evid = $('#evid'), evcv = $('#ev-cv');
  $('#ev-x').onclick = () => { evid.hidden = true; $('.pvt').hidden = false };
  const evGrid = (rows, cls, label, onPick) => {
    const at = {}; rows.forEach(x => at[`${x.corner}|${x.temp}|${x.vscale}`] = x);
    const vs = [...new Set(rows.map(x => x.vscale))].sort(), ts = [...new Set(rows.map(x => x.temp))].sort((a, b) => a - b),
      cs = CORN.filter(c => rows.some(x => x.corner === c));
    const g = $('#ev-lat'); g.style.gridTemplateColumns = `22px repeat(${ts.length},minmax(0,1fr))`;
    g.innerHTML = '<span></span>' + ts.map(t => `<span class="hd">${t}°</span>`).join('') + cs.map(c => `<span class="ck">${c}</span>` +
      ts.map(t => `<span class="tg" style="grid-template-columns:repeat(${vs.length},minmax(0,1fr))">${vs.map(v => { const x = at[`${c}|${t}|${v}`];
        return x ? `<button class="c ${cls(x)}" data-k="${c}|${t}|${v}" title="${c}, ${t} °C, ×${v}">${label(x)}</button>` : '<span></span>' }).join('')}</span>`).join('')).join('');
    g.querySelectorAll('button').forEach(b => b.onclick = () => { g.querySelectorAll('.sel').forEach(x => x.classList.remove('sel')); b.classList.add('sel'); onPick(at[b.dataset.k]) });
    return g;
  };
  const plotSetup = () => { const d = devicePixelRatio || 1, r = evcv.getBoundingClientRect(); evcv.width = Math.round(r.width * d); evcv.height = Math.round(r.height * d);
    const x = evcv.getContext('2d'); x.setTransform(d, 0, 0, d, 0, 0); x.clearRect(0, 0, r.width, r.height); x.font = `10px ${cssv('--mono')}`; return {x, w: r.width, h: r.height} };
  const axes = (g, x0, y0, w, h, xl, yl, ticksX, ticksY) => {
    const x = g.x; x.strokeStyle = cssv('--border'); x.fillStyle = cssv('--text-3'); x.lineWidth = 1;
    ticksY.forEach(([v, y]) => { x.beginPath(); x.moveTo(x0, y + .5); x.lineTo(x0 + w, y + .5); x.stroke(); x.fillText(v, 2, y + 3) });
    ticksX.forEach(([v, xx]) => { x.beginPath(); x.moveTo(xx + .5, y0); x.lineTo(xx + .5, y0 + h); x.stroke(); x.fillText(v, xx - 8, y0 + h + 11) });
    x.fillText(yl, x0 + 4, y0 + 10); x.fillText(xl, x0 + w - 40, y0 + h - 4);
  };
  const SI = v => { const a = Math.abs(v); return a >= 1e9 ? (v / 1e9) + 'G' : a >= 1e6 ? (v / 1e6) + 'M' : a >= 1e3 ? (v / 1e3) + 'k' : String(v) };
  const bode = (rows, pick) => {
    const g = plotSetup(), x = g.x, L = 46, W = g.w - L - 8, H = (g.h - 26) / 2;
    const all = rows.filter(r => r.f && r.f.length), f0 = Math.min(...all.map(r => r.f[0])), f1 = Math.max(...all.map(r => r.f[r.f.length - 1]));
    const X = f => L + Math.log10(f / f0) / Math.log10(f1 / f0) * W;
    const mags = all.flatMap(r => r.mag), mlo = Math.max(-60, Math.min(...mags)), mhi = Math.max(...mags) + 5;
    const Ym = m => 4 + (mhi - Math.max(mlo, m)) / (mhi - mlo) * (H - 8), Yp = p => H + 18 + (Math.max(...[0]) - p) / 270 * (H - 8);
    const dec = []; for (let e = Math.ceil(Math.log10(f0)); e <= Math.log10(f1); e++) dec.push([SI(10 ** e), X(10 ** e)]);
    axes(g, L, 4, W, H - 4, 'Hz', '|T| dB', [], [[Math.round(mhi), Ym(mhi)], [0, Ym(0)], [Math.round(mlo), Ym(mlo)]]);
    axes(g, L, H + 18, W, H - 8, 'Hz', 'phase °', dec, [[0, Yp(0)], [-90, Yp(-90)], [-180, Yp(-180)], [-270, Yp(-270)]]);
    const line = (r, col, lw) => { x.strokeStyle = col; x.lineWidth = lw;
      x.beginPath(); r.f.forEach((f, i) => i ? x.lineTo(X(f), Ym(r.mag[i])) : x.moveTo(X(f), Ym(r.mag[i]))); x.stroke();
      x.beginPath(); r.f.forEach((f, i) => i ? x.lineTo(X(f), Yp(r.phase[i] - (r.phase[0] > 90 ? 180 : 0))) : x.moveTo(X(f), Yp(r.phase[i] - (r.phase[0] > 90 ? 180 : 0)))); x.stroke() };
    all.forEach(r => line(r, cssv('--border-strong'), 1));
    line(pick, cssv('--redline'), 2);
    if (pick.ugf) { const ux = X(pick.ugf); x.strokeStyle = cssv('--redline'); x.setLineDash([3, 3]); x.beginPath(); x.moveTo(ux, 4); x.lineTo(ux, g.h - 12); x.stroke(); x.setLineDash([]) }
    $('#ev-read').textContent = `${pick.corner}, ${pick.temp} °C, ×${pick.vscale}: ` + (pick.pm != null ? `phase margin ${pick.pm.toFixed(1)}°` : 'no unity-gain crossing') +
      (pick.gm_db != null ? ` · gain margin ${pick.gm_db.toFixed(1)} dB` : '') + (pick.ugf ? ` · unity gain ${(pick.ugf / 1e6).toPrecision(3)} MHz` : '') + ` · DC loop gain ${pick.dc_gain_db.toFixed(1)} dB`;
  };
  const wavePlot = async (k, row) => {
    $('#ev-read').textContent = `simulating the power-up at ${row.corner}, ${row.temp} °C, ×${row.vscale}${row.case ? ' · ' + row.case : ''}…`;
    const cq = row.case ? `&case=${encodeURIComponent(row.case)}` : '';
    const j = await (await fetch(`/api/runs/${RID}/wave?k=${k}&corner=${row.corner}&temp=${row.temp}&vscale=${row.vscale}${cq}`)).json();
    if (!j.ok || !j.wave) { $('#ev-read').textContent = 'Could not run the waveform: ' + (j.error || 'unknown'); return }
    const w = j.wave, g = plotSetup(), x = g.x, L = 46, W = g.w - L - 8, H = (g.h - 26) / 2, T = w.t[w.t.length - 1];
    const X = t => L + t / T * W, imax = Math.max(...w.i) * 1.1 || 1e-6, Yi = i => 4 + (1 - i / imax) * (H - 8);
    const vmax = Math.max(0.1, ...Object.values(w.v).flat()) * 1.05, Yv = v => H + 18 + (1 - v / vmax) * (H - 8);
    const tt = [0, .25, .5, .75, 1].map(a => [`${(a * T * 1e6).toFixed(0)}µs`, X(a * T)]);
    axes(g, L, 4, W, H - 4, 's', 'I µA', [], [[(imax * 1e6).toFixed(1), Yi(imax)], [0, Yi(0)]]);
    axes(g, L, H + 18, W, H - 8, '', 'V', tt, [[vmax.toFixed(2), Yv(vmax)], [0, Yv(0)]]);
    x.strokeStyle = cssv('--redline'); x.lineWidth = 1.8; x.beginPath(); w.t.forEach((t, i) => i ? x.lineTo(X(t), Yi(w.i[i])) : x.moveTo(X(t), Yi(w.i[i]))); x.stroke();
    const cols = [cssv('--text-1'), cssv('--text-3'), cssv('--accent'), cssv('--ok'), cssv('--near')];
    Object.entries(w.v).forEach(([n, vs], k2) => { x.strokeStyle = cols[k2 % cols.length]; x.lineWidth = 1.2; x.beginPath(); w.t.forEach((t, i) => i ? x.lineTo(X(t), Yv(vs[i])) : x.moveTo(X(t), Yv(vs[i]))); x.stroke();
      x.fillStyle = cols[k2 % cols.length]; x.fillText(n, L + W - 60, Yv(vs[vs.length - 1]) - 3) });
    $('#ev-read').textContent = `${row.case ? row.case + ' · ' : ''}${row.corner}, ${row.temp} °C, ×${row.vscale}: supply current settles at ${(w.i[w.i.length - 1] * 1e6).toFixed(3)} µA` +
      ` (its DC analysis says ${((row.i_op || 0) * 1e6).toFixed(2)} µA)`;
  };
  // sequence tests: one row per power-up case, one column per condition; a cell is red when the block ends dead or
  // oscillating there, amber when it settles in another state than the reference case (the first row) at that condition
  const seqGrid = (results, k, f) => {
    const cases = [...new Set(results.map(r => r.case))], conds = [...new Set(results.map(r => `${r.corner}|${r.temp}|${r.vscale}`))];
    const at = {}; results.forEach(r => at[`${r.case}#${r.corner}|${r.temp}|${r.vscale}`] = r);
    const cls = r => { if (!r || r.error) return 'na'; if (r.state === 'dead' || r.state === 'oscillates') return 'bad';
      const r0 = at[`${cases[0]}#${r.corner}|${r.temp}|${r.vscale}`];
      if (r !== r0 && r0 && r.state === 'settled' && r0.state === 'settled' &&
          Object.entries(r.nodes || {}).some(([n, v]) => r0.nodes[n] && v[1] != null && r0.nodes[n][1] != null && Math.abs(v[1] - r0.nodes[n][1]) > 0.1)) return 'warn';
      return r.state === 'settled' ? 'ok' : 'na' };
    const g = $('#ev-lat'); g.style.gridTemplateColumns = `minmax(0,2.4fr) repeat(${conds.length},minmax(0,1fr))`;
    g.innerHTML = '<span></span>' + conds.map(c => `<span class="hd">${c.split('|').slice(0, 2).join(' ')}°</span>`).join('') +
      cases.map(cs => `<span class="ck seqname" title="${cs}">${cs.replace(/^rails /, '').replace(/ ramps\)/, ')')}</span>` + conds.map(c => { const r = at[`${cs}#${c}`];
        return r ? `<button class="c ${cls(r)}" data-k="${cs}#${c}" title="${cs} · ${c.replace(/\|/g, ', ')}"></button>` : '<span></span>' }).join('')).join('');
    g.querySelectorAll('button').forEach(b => b.onclick = () => { g.querySelectorAll('.sel').forEach(x => x.classList.remove('sel')); b.classList.add('sel'); wavePlot(k, at[b.dataset.k]) });
    const w = f.detail && f.detail.worst, first = (w && at[`${f.detail.case}#${w[0]}|${w[1]}|${w[2]}`]) || results.find(r => cls(r) === 'bad') || results[0];
    if (first) { wavePlot(k, first); const b = g.querySelector(`[data-k="${CSS.escape(first.case + '#' + first.corner + '|' + first.temp + '|' + first.vscale)}"]`); b && b.classList.add('sel') }
  };
  const showEvidence = f => {
    const lp = f.detail && f.detail.loop, k = f.detail && f.detail.k;
    // a testbench loop carries its own results; shown as a stability test cut where the engine cut it
    const pr = lp ? {plan: {kind: 'stability', cell: f.detail.testbench, break: {net: lp.net}}, results: f.detail.results || []}
      : k != null && (lastLive.plan_results || [])[k];
    if (!pr) { evid.hidden = true; $('.pvt').hidden = false; return }
    evid.hidden = false; $('.pvt').hidden = true;
    const rows = (pr.results || []).filter(r => !r.error);
    // conditions the fine-step check could not reach are a gap in coverage: said next to the grid, never hidden
    const unc = (pr.results || []).filter(r => /^unconfirmed/.test(r.error || '')).length;
    const uncNote = () => { if (unc) $('#ev-hint').textContent += ` · ${unc} of ${pr.results.length} conditions not confirmed at a fine time step (grey: not tested)` };
    if (pr.plan.kind === 'sequence') {
      $('#ev-title').textContent = 'Power-up sequence · every order the chip can take';
      $('#ev-hint').textContent = `${pr.plan.cell} · rows: how the rails, enables and resets arrive · click a cell to simulate it`;
      seqGrid(pr.results, k, f); uncNote();
    } else if (pr.plan.kind === 'stability') {
      $('#ev-title').textContent = 'Loop gain · Bode'; $('#ev-hint').textContent = `${pr.plan.cell} · cut on ${pr.plan.break && pr.plan.break.net} · click a condition`;
      evGrid(pr.results, r => r.error ? 'na' : r.positive_dc || (r.pm != null && r.pm < 0) ? 'bad' : r.pm != null && r.pm < 45 ? 'warn' : 'ok',
        r => r.pm != null ? Math.round(r.pm) : '–', r => r.f && bode(rows, r));
      const worst = rows.filter(r => r.f).sort((a, b) => (a.pm ?? 999) - (b.pm ?? 999))[0]; if (worst) bode(rows, worst);
    } else {
      $('#ev-title').textContent = 'Power-up · waveform'; $('#ev-hint').textContent = `${pr.plan.cell} · from 0 V · click a condition to simulate it`;
      // a condition fails if it stays off, settles in a confirmed second state, or keeps swinging
      const bad = r => (r.i_end != null && r.i_end < 0.2 * r.i_op) || r.confirmed || (r.swing && Object.keys(r.swing).length);
      evGrid(pr.results, r => r.error ? 'na' : bad(r) ? 'bad' : 'ok', () => '', r => wavePlot(k, r)); uncNote();
      const w = f.detail && f.detail.worst, at = w && rows.find(r => r.corner === w[0] && r.temp === w[1] && r.vscale === w[2]);
      const first = at || rows.find(bad) || rows[0];
      if (first) { wavePlot(k, first); const b = $(`#ev-lat [data-k="${first.corner}|${first.temp}|${first.vscale}"]`); b && b.classList.add('sel') }
    }
  };

  const select = async (f, el) => {
    showEvidence(f);
    const at = whereIs(f.detail && f.detail.device), cell = f.detail && f.detail.plan && f.detail.plan.cell;
    const lp = f.detail && f.detail.loop;
    if (lp && f.detail.testbench) { await openSheet('', '', f.detail.testbench); f = Object.assign({}, f, {device: lp.inst}) }   // a testbench loop
    else if (cell && /\.sch$/.test(cell)) await openSheet('', '', cell);     // a planned test: show the cell it tested
    else if (at) { if (await openSheet(at.path, at.leaf)) f = Object.assign({}, f, {device: at.leaf}) } else toTop();
    flist.querySelectorAll('.card.sel').forEach(c => c.classList.remove('sel')); el.classList.add('sel');
    svg && svg.querySelectorAll('.dev.sel').forEach(g => g.classList.remove('sel'));
    Object.values(cellEls).forEach(c => c.classList.remove('hit', 'fail-hit'));
    // every condition where this finding fails, not only the worst one
    const key = (f.detail && f.detail.device) || f.device || '';
    let n = 0;
    // a PVT finding carries the conditions where it fails (whatever the rule); older runs fall back to the triode list
    const own = f.detail && Array.isArray(f.detail.conds) && f.detail.k == null && !f.detail.loop ? f.detail.conds : null;
    if (own) own.forEach(c => { const el2 = cellEls[`${c[0]}|${c[1]}|${c[2]}`]; if (el2) { el2.classList.add('fail-hit'); n++ } });
    else for (const c of lastCells) {
      const hitc = (c.devices || []).some(d => d === key || d.startsWith(key + ' '));
      if (hitc) { const el2 = cellEls[`${c.corner}|${c.temp}|${c.vscale}`]; if (el2) { el2.classList.add('fail-hit'); n++ } }
    }
    $('#pvt-n').innerHTML = `${seen.size} / 45<span class="selnote">${n ? '· this finding fails in ' + n + ' cell' + (n > 1 ? 's' : '') : ''}</span>`;
    const g = f.device && devEl(f.device);
    stage.classList.toggle('trail', !!g);
    if (g) { g.classList.add('sel'); const b = g.getBBox(), vb = svg.viewBox.baseVal;
      // getBBox is in the drawing's own coordinates; the drawing's origin (viewBox x/y) sits at the svg's top-left
      const cx = b.x + b.width / 2 - vb.x, cy = b.y + b.height / 2 - vb.y;
      view.k = Math.min(4, Math.max(view.k, 1.6)); view.x = cv.clientWidth / 2 - cx * view.k; view.y = cv.clientHeight / 2 - 40 - cy * view.k; apply(true);
      if (G) G.fromTo(g, {opacity: 0.2}, {opacity: 1, duration: 0.3, repeat: 2, yoyo: true}) }   // odd play count: ends lit
    const w = f.detail && f.detail.worst; if (w) { const c = cellEls[`${w[0]}|${w[1]}|${w[2]}`]; c && c.classList.add('hit') }
  };

  // ---------- walk-through: the finding explained on the bench, step by step (tour.js) ----------
  const wait = ms => new Promise(r => setTimeout(r, matchMedia('(prefers-reduced-motion: reduce)').matches ? 0 : ms));
  const union = els => { const rs = els.filter(Boolean).map(e => e.getBoundingClientRect()).filter(r => r.width || r.height);
    if (!rs.length) return null; const l = Math.min(...rs.map(r => r.left)), t = Math.min(...rs.map(r => r.top));
    return {left: l, top: t, width: Math.max(...rs.map(r => r.right)) - l, height: Math.max(...rs.map(r => r.bottom)) - t} };
  let walking = null;
  const tour = window.KaavalTour && new KaavalTour.Tour({
    show: async (f, st) => {
      const c = cards[f.id] && cards[f.id].el, t = st.target;
      if (walking !== f.id) { walking = f.id; tab('f'); await select(f, c); await wait(450) }
      if (t.kind === 'card') { c.scrollIntoView({block: 'nearest'}); return c.getBoundingClientRect() }
      if (t.kind === 'device' || t.kind === 'sheet') {
        await select(f, c); evid.hidden = true; $('.pvt').hidden = false;   // the canvas and grid, for the device
        await wait(500);
        const g = t.device && devEl(t.device);
        return g ? g.getBoundingClientRect() : cv.getBoundingClientRect() }
      if (t.kind === 'cells') { evid.hidden = true; $('.pvt').hidden = false;
        const hit = [...document.querySelectorAll('#matrix .fail-hit, #matrix .hit')];
        return union(hit.length ? hit : [$('#matrix')]) }
      if (t.kind === 'evidence-grid' || t.kind === 'evidence-plot') { showEvidence(f); await wait(300);
        return (t.kind === 'evidence-grid' ? $('#ev-lat') : $('.ev-plot')).getBoundingClientRect() }
      if (t.kind === 'actions') { c.scrollIntoView({block: 'nearest'});
        return union([c.querySelector('[data-fix]'), c.querySelector('.fixres'), c.querySelector('.evdl')]) || c.getBoundingClientRect() }
      return null },
    done: () => { walking = null } });
  const walk = f => tour && tour.start(f, PLAIN[f.rule]);

  // ---------- title block: what was reviewed, and the verdict once the review ends ----------
  const setTb = (j, lv, r) => {
    const fs = j.findings, sims = (lv.cells || []).filter(c => c.status !== 'err').length;
    $('#tb-dut').textContent = lv.dut || lv.source || r.repo || '…';
    $('#tb-tb').textContent = lv.testbench || '—';
    $('#tb-sims').textContent = sims + '/45';
    if (r.status !== 'done' || $('#tbar').dataset.done) return;
    $('#tbar').dataset.done = 1;
    const traps = fs.filter(f => f.kind === 'trap').length, risks = fs.filter(f => f.kind === 'risk').length;
    const secs = Math.round((r.finished - r.created) * 10) / 10;
    [['#tb-traps', traps, traps ? 'fail' : 'okc'], ['#tb-risks', risks, risks ? 'warn' : 'okc']].forEach(([id, n, c]) => {
      const el = $(id); el.className = c; const t0 = performance.now();
      const step = ts => { const p = Math.min(1, (ts - t0) / 700); el.textContent = Math.round(n * (1 - Math.pow(1 - p, 3))); if (p < 1) requestAnimationFrame(step) };
      requestAnimationFrame(step);
    });
    $('#tb-time').textContent = secs + ' s';
    $('#tbar').classList.add('done');
  };

  // ---------- poll ----------
  let svgLoaded = false, lastCells = [], linked = false;
  const tick = async () => {
    const j = await (await fetch(`/api/runs/${RID}?after=${after}`)).json();
    const r = j.run, lv = j.live || {}; lastLive = lv;
    $('#c-src').textContent = lv.source || r.repo; $('#c-sha').textContent = (r.commit_sha || '—').slice(0, 7);
    $('#c-tb').textContent = lv.testbench ? lv.testbench.split('/').pop() : '—';
    const st = $('#state');
    st.className = 'chip ' + (r.status === 'done' ? 'on' : r.status === 'error' ? 'off' : 'live');
    st.lastChild.textContent = r.status === 'done' ? 'Done' : r.status === 'error' ? 'Error' : (j.stage_names[r.stage] || 'Running');
    $('#elapsed').textContent = Math.round((r.finished || Date.now() / 1000) - r.created) + ' s';
    renderSteps(lv, j.stage_names, j.stages);
    if (lv.grid && !grid) buildMatrix(lv.grid);
    // retried on every poll until it succeeds: a slow or failed fetch can never leave the canvas on 'Preparing'
    if (!svgLoaded && lv.testbench) svgLoaded = await loadSvg().catch(() => false);
    if (!svgLoaded) $('#cv-msg').textContent = r.status === 'error' ? 'The review stopped; see the reviewer feed.' :
      ({fetch: 'Fetching the design…', audit: 'Reading every schematic as text…', testbench: 'Finding the testbench…'}[r.stage] ||
       (lv.stages && lv.stages.testbench && lv.stages.testbench.state === 'skipped' ? 'No testbench in this design: units checks only.' :
        lv.testbench ? 'Drawing the schematic…' : 'Preparing…'));
    if (r.status === 'error' || (lv.stages && lv.stages.testbench && lv.stages.testbench.state === 'skipped')) $('#cv-empty .spin') && ($('#cv-empty .spin').style.display = 'none');
    lastCells = lv.cells || []; addCells(lastCells); lastDevices = lv.devices; if (!sheet) colour(lv.devices);
    if (lv.kind === 'dynamic') { $('#legend').hidden = true;
      const st = (lv.stages || {}).pvt || {};
      if (st.state === 'skipped') { $('#pvt-n').textContent = 'not applicable · switching circuit'; $('#matrix').style.opacity = 0.35 }
      $('.pvt-h .hint').textContent = 'corner × temperature × supply · each cell is one transient run of the designer\'s testbench' }
    for (const e of j.events) { after = Math.max(after, e.ts);
      say(`<span class="ts">${new Date(e.ts * 1000).toTimeString().slice(0, 8)}</span>${esc(e.msg)}`,
          e.level !== 'info' ? e.level : /^Muse Spark (names|plans|'s reasoning)/.test(e.msg) ? 'muse' : '') }
    j.findings.forEach(f => byId[f.id] = f);
    for (const f of j.findings) { if (!shown.has(f.id)) { shown.add(f.id); card(f) } else updateCard(f) }
    // a link from the chip view (?f=<id>, &walk=1) opens that finding here, and its walk-through if asked
    if (!linked && (r.status === 'done' || r.status === 'error')) { linked = true;
      const q = new URLSearchParams(location.search), want = j.findings.find(f => String(f.id) === q.get('f'));
      if (want) { tab('f'); if (q.get('walk')) setTimeout(() => walk(want), 600); else select(want, cards[want.id].el) } }
    renderFams(j.findings, lv);
    $('#tab-fn').textContent = j.findings.filter(f => f.kind !== 'note').length + (j.findings.some(f => f.kind === 'note') ? ' + ' + j.findings.filter(f => f.kind === 'note').length : '');
    if (!switched && (r.status === 'done' || r.status === 'error')) { switched = true; if (j.findings.length) tab('f') }

    setTb(j, lv, r);
    if (r.status === 'done' && !feed.dataset.end && !j.findings.length) { flist.innerHTML = '<div class="msg">No findings.</div>' }
    if (r.status === 'done' && !feed.dataset.end) { feed.dataset.end = 1;
      say(j.findings.length ? `<b style="color:var(--text-1)">${j.findings.length} finding(s).</b> Select one to see the device and the condition that breaks it.`
        : lv.kind === 'dynamic' && ((lv.stages || {}).pvt || {}).state === 'done' ? '<b style="color:var(--text-1)">Nothing flagged.</b> Every output keeps doing what it does at nominal across all 45 conditions.'
        : lv.kind === 'dynamic' ? '<b style="color:var(--text-1)">No units traps.</b> This is a switching circuit; its outputs could not be measured, so its switching behaviour was not reviewed.'
        : '<b style="color:var(--text-1)">Nothing flagged by these checks.</b>') }
    const fixing = j.findings.some(f => f.fix && f.fix.state === 'running');
    if ((r.status !== 'done' && r.status !== 'error') || fixing || (lv.testbench && !svgLoaded)) setTimeout(tick, 900);
    else { polling = false; renderSteps(lv, j.stage_names, j.stages) }
  };
  if (G) G.from('.bench > *', {opacity: 0, y: 8, duration: 0.5, ease: 'expo.out', stagger: 0.06});
  tick();
})();
