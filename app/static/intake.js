// Kaaval intake: a design review you can watch. The drawing is Kaaval's own test reference; every mark, number and
// lattice cell comes from its real simulation (static/hero.json, ngspice + sky130).
(() => {
  const $ = s => document.querySelector(s);
  const esc = s => String(s).replace(/[&<>"]/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;'}[c]));
  const reduce = matchMedia('(prefers-reduced-motion: reduce)').matches;
  const root = document.documentElement;
  $('#theme').onclick = () => {
    const dark = root.dataset.theme ? root.dataset.theme === 'dark' : matchMedia('(prefers-color-scheme: dark)').matches;
    root.dataset.theme = dark ? 'light' : 'dark'; try { localStorage.setItem('kv-theme', root.dataset.theme) } catch (e) {}
  };

  // ---------- boot: the engine's real steps, once per visit ----------
  const STEPS = ['load sky130 models · 5 corners', 'netlist schematics as text', 'check units against silicon',
    'find testbenches and cells', 'label pin roles · Muse Spark', 'plan tests · Muse Spark', 'power up from 0 V',
    'every rail order and speed', 'cut loops · measure margin', 'start the review'];
  const boot = $('#boot');
  let booted = false; try { booted = sessionStorage.getItem('kv-boot') === '1' } catch (e) {}
  if (reduce || booted) boot.remove();
  else {
    const ol = $('#boot-list'); ol.innerHTML = STEPS.map((s, i) => `<li><b>${String(i + 1).padStart(3, '0')}</b>${s}</li>`).join('');
    const lis = [...ol.children], t0 = performance.now(), D = 1700;
    const step = ts => { const p = Math.min(1, (ts - t0) / D);
      $('#boot-pc').textContent = Math.round(p * 100); lis.forEach((li, i) => li.classList.toggle('on', p >= i / lis.length));
      if (p < 1) requestAnimationFrame(step);
      else { setTimeout(() => boot.classList.add('done'), 160); setTimeout(() => boot.remove(), 1100); try { sessionStorage.setItem('kv-boot', '1') } catch (e) {} } };
    requestAnimationFrame(step);
  }

  // ---------- the drawing under review ----------
  const S = $('#draw');
  const P = (d, c = 'ink') => `<path class="${c}" d="${d}"/>`, T = (x, y, s, c = '') => `<text x="${x}" y="${y}" class="${c}">${s}</text>`;
  // MOS at (x, y): channel vertical, terminals up/down; gate plate on side g (-1 left / +1 right); p: bubble
  const mos = (x, y, g, p, name, cls = 'ink') => {
    const gp = x + g * 8, end = x + g * 26;
    return P(`M${x} ${y - 18}V${y + 18}M${x} ${y - 14}H${x + 0.01}M${gp} ${y - 14}V${y + 14}M${x} ${y - 18}V${y - 30}M${x} ${y + 18}V${y + 30}` +
      `M${x} ${y - 12}h-${0}M${p ? gp + g * 6 : gp} ${y}H${end}`, cls) + (p ? `<circle class="${cls}" cx="${gp + g * 3}" cy="${y}" r="3"/>` : '') +
      T(x + (g < 0 ? 8 : -30), y - 22, name, 'n');
  };
  const res = (x, y1, y2, name) => { let d = `M${x} ${y1}v8`; const n = 6, h = (y2 - y1 - 16) / n;
    for (let i = 0; i < n; i++) d += `l${i % 2 ? -7 : 7} ${h / 2}l${i % 2 ? 7 : -7} ${h / 2}`; return P(d + 'v8') + T(x + 12, (y1 + y2) / 2 + 3, name) };
  const gnd = (x, y, c = 'ink') => P(`M${x} ${y}v6M${x - 8} ${y + 6}h16M${x - 5} ${y + 10}h10M${x - 2} ${y + 14}h4`, c);
  const base = [
    P('M40 40H600'), T(44, 32, 'VDD 1.8 V', 'n'), P('M40 360H600'), T(44, 378, 'VSS', 'n'),
    mos(170, 110, -1, 1, 'M3'), mos(330, 110, -1, 1, 'M4'), mos(490, 110, -1, 1, 'M5'),
    P('M170 80V40M330 80V40M490 80V40'),
    P('M144 110V60H464V110'), P('M304 110V165H330'),
    mos(170, 250, 1, 0, 'M1'), mos(330, 250, -1, 0, 'M2'),
    P('M170 140V220M330 140V220'), P('M196 250H304'), P('M196 250V200H170'),
    P('M170 280V360'), res(330, 280, 340, 'R1 20k'), P('M330 340V360'),
    P('M490 140V180'), res(490, 180, 300, 'R2 50k'), P('M490 300V360'),
    `<circle class="dot" cx="170" cy="200" r="3"/><circle class="dot" cx="330" cy="165" r="3"/><circle class="dot" cx="490" cy="170" r="3"/>`,
    T(150, 196, 'n1', 'n'), T(338, 160, 'n2', 'n'), T(500, 166, 'iout', 'n'),
  ].join('');
  // the reviewer's marks, revealed only under the probe
  const MARKS = [
    {x: 250, y: 185, r: 120, tag: 'c', label: '1', html: () => `<b>No start-up path.</b> This self-biased loop has a second solution at 0 A.
      Powered up from 0 V it stays at <b>0.000 µA at ${H.dead}/45 conditions</b>, every −40 °C and 27 °C one, while its DC analysis
      reports ${H.ex.i_op.toFixed(2)} µA.<small>ss · −40 °C · supply ×0.9 · held 300 µs · confirmed steady</small>`},
    {x: 92, y: 150, r: 46, tag: 'p', label: '2', html: () => `<b>Proposal:</b> a weak always-on PMOS into n1 kicks the loop out of the 0 A
      state. Re-simulated: <b>0/45 dead</b>.<small>S.05 · a proposal, never a merge</small>`},
    {x: 490, y: 240, r: 60, tag: 'n', label: '3', html: () => `<b>Output, once running:</b> ${H.lo.toFixed(1)}–${H.hi.toFixed(1)} µA across the
      45 conditions with the start-up device.<small>supply current of V_DD, settled</small>`},
    {x: 250, y: 60, r: 44, tag: 'n', label: '4', html: () => `<b>The ${45 - H.dead} that start</b> are all at 125 °C, carried by leakage alone:
      not a start-up circuit.<small>tt / ss / ff / sf / fs · 125 °C · ×0.9–×1.1</small>`},
  ];
  const cloud = (x, y, r) => { let d = ''; const n = 14; for (let i = 0; i <= n; i++) { const a = i / n * 2 * Math.PI, rr = r * (1 + 0.06 * Math.sin(i * 2.7));
    const px = x + rr * Math.cos(a), py = y + rr * Math.sin(a) * 0.72; d += (i ? `Q${(x + (rr + 10) * Math.cos(a - Math.PI / n)).toFixed(1)} ${(y + (rr + 10) * Math.sin(a - Math.PI / n) * 0.72).toFixed(1)} ` : 'M') + `${px.toFixed(1)} ${py.toFixed(1)}` } return d };
  const marks = MARKS.map(m => `<path d="${cloud(m.x, m.y, m.r)}"/><circle class="fillr" cx="${m.x - m.r * 0.72}" cy="${m.y - m.r * 0.55}" r="9"/>` +
    `<text x="${m.x - m.r * 0.72 - 3.2}" y="${m.y - m.r * 0.55 + 3.5}" style="fill:var(--bg-0)">${m.label}</text>`).join('') +
    mos(92, 110, 1, 1, 'M6?', '') + P('M92 80V40M92 140V200H144M118 110H130V122', '') + gnd(130, 122, '');
  S.innerHTML = `<defs><clipPath id="lensclip"><circle id="lc" cx="-200" cy="-200" r="78"/></clipPath></defs>${base}
    <g class="mark" clip-path="url(#lensclip)">${marks}</g>
    <circle class="lens" id="lens" cx="-200" cy="-200" r="78"/><path class="cross" id="cross" d=""/>`;
  const lc = $('#lc'), lens = $('#lens'), cross = $('#cross');
  let H = null, touched = false;
  const at = (x, y) => {
    lc.setAttribute('cx', x); lc.setAttribute('cy', y); lens.setAttribute('cx', x); lens.setAttribute('cy', y);
    cross.setAttribute('d', `M${x - 6} ${y}h12M${x} ${y - 6}v12`);
    if (!H) return;
    const m = MARKS.map(m => ({m, d: Math.hypot(m.x - x, (m.y - y) / 0.72) - m.r})).sort((a, b) => a.d - b.d)[0];
    const note = $('#note');
    if (m.d < 70) note.innerHTML = `<span class="tag mono ${m.m.tag === 'c' ? 'c' : ''}">${{c: 'caught', p: 'proposal', n: 'note'}[m.m.tag]} ${m.m.label}</span><p>${m.m.html()}</p>`;
  };
  const toSvg = e => { const r = S.getBoundingClientRect(); return [(e.clientX - r.left) / r.width * 640, (e.clientY - r.top) / r.height * 400] };
  S.addEventListener('pointermove', e => { touched = true; at(...toSvg(e)) });
  S.addEventListener('pointerdown', e => { touched = true; S.setPointerCapture(e.pointerId); at(...toSvg(e)) });

  // ---------- data ----------
  const dead = x => x.i_end != null && x.i_end < 0.2 * x.i_op;
  fetch('/static/hero.json').then(r => r.json()).then(j => {
    const w = j.without.cells, ok = j.with.cells.map(x => x.i_end);
    H = {dead: w.filter(dead).length, ex: w.find(x => x.c === 'ss' && x.t === -40 && x.v === 0.9), lo: Math.min(...ok), hi: Math.max(...ok)};
    // until someone takes the probe, it walks the findings by itself
    if (reduce) { at(MARKS[0].x, MARKS[0].y) }
    else { const path = MARKS.map(m => [m.x, m.y]), t0 = performance.now();
      const walk = ts => { if (touched) return; const u = ((ts - t0) / 2600) % path.length, i = Math.floor(u), f = u - i, a = path[i], b = path[(i + 1) % path.length],
        e = f < .7 ? 0 : (f - .7) / .3, s = e * e * (3 - 2 * e); at(a[0] + (b[0] - a[0]) * s, a[1] + (b[1] - a[1]) * s); requestAnimationFrame(walk) };
      requestAnimationFrame(walk) }
    lattice(j);
    transcript(j);
  });

  // ---------- S.01: the review transcript ----------
  const transcript = j => {
    const ex = H.ex;
    const lines = [
      ['$', 'kaaval review ./ref        <span class="d"># Kaaval reviewing its own test reference</span>'],
      ['netlist', '5 transistors · 2 resistors · 6 nets · parsed as text'],
      ['bench', 'no testbench in the design · 1 cell with ports VDD VSS iout'],
      ['plan', 'powerup · 5 corners × 3 temperatures × 3 supplies = 45'],
      ['run', '45 conditions · ngspice · sky130 models'],
      ['caught', `no_startup · <span class="k">${H.dead}/45 stay at 0 µA</span> · DC says ${ex.i_op.toFixed(2)} µA (ss, −40 °C, ×0.9)`],
      ['confirm', 'supply current steady at 0.000 µA over the hold'],
      ['propose', '+ XM6 start-up PMOS · re-simulated: <span class="k">0/45 dead</span>'],
    ];
    const el = $('#term'); let shown = false;
    const render = n => el.innerHTML = lines.slice(0, n).map(([k, v]) => `${k === '$' ? '<span class="k">$</span>' : k.padEnd(8)} ${v}`).join('\n');
    new IntersectionObserver(es => es.forEach(e => { if (!e.isIntersecting || shown) return; shown = true;
      if (reduce) return render(lines.length); let n = 0; const tick = () => { render(++n); if (n < lines.length) setTimeout(tick, 260) }; tick() }), {threshold: 0.3}).observe(el);
  };

  // ---------- S.03 / S.04: the lattice and the proposal ----------
  const lattice = j => {
    const lat = $('#lat'), CORN = ['tt', 'ss', 'ff', 'sf', 'fs'], TEMPS = [-40, 27, 125], VS = [0.9, 1.0, 1.1];
    lat.innerHTML = '<span></span>' + TEMPS.map(t => `<span class="hd">${t} °C</span>`).join('') +
      CORN.map(c => `<span class="ck">${c}</span>` + TEMPS.map(t => `<span class="tg">${VS.map(v =>
        `<span class="c" data-k="${c}|${t}|${v}" title="${c}, ${t} °C, supply ×${v}"></span>`).join('')}</span>`).join('')).join('');
    const el = {}; lat.querySelectorAll('.c').forEach(e => el[e.dataset.k] = e);
    let timers = [];
    const show = (which, animate) => {
      timers.forEach(clearTimeout); timers = [];
      const cells = j[which].cells, nd = cells.filter(dead).length;
      $('#ro-big').innerHTML = `${nd}<small>/45 dead</small>`; $('#ro-big').classList.toggle('good', nd === 0);
      cells.forEach((x, i) => { const e = el[`${x.c}|${x.t}|${x.v}`]; if (!e) return;
        const go = () => e.className = 'c ' + (x.err ? '' : dead(x) ? 'bad' : 'ok');
        animate && !reduce ? timers.push(setTimeout(go, i * 22)) : go() });
      return nd;
    };
    let seen = false;
    new IntersectionObserver(es => es.forEach(e => { if (e.isIntersecting && !seen) { seen = true; show('without', true) } }), {threshold: 0.3}).observe(lat);
    $('#tog').onclick = () => {
      const on = $('#tog').getAttribute('aria-checked') !== 'true'; $('#tog').setAttribute('aria-checked', on); $('#tog-s').textContent = on ? 'on' : 'off';
      const nd = show(on ? 'with' : 'without', true);
      $('#fix-res').textContent = on ? `before: ${H.dead}/45 dead · after: ${nd}/45 dead · re-simulated at all 45 conditions` : `before: ${H.dead}/45 dead · after: re-simulate to see`;
      $('#s3').scrollIntoView({behavior: reduce ? 'auto' : 'smooth', block: 'center'});
    };
  };

  // ---------- S.04: the block in its chip (static/chip.json, real runs of our own circuits) ----------
  const CORNERS = ['tt', 'ss', 'ff'];
  const us = t => t >= 1e-3 ? `${+(t * 1e3).toFixed(2)} ms` : `${+(t * 1e6).toFixed(1)} µs`;
  const label = (r, sc) => {
    const m = r.meta, o = m.lead == null ? 'rails together' : `${m.lead} first, +${us(m.gap)}`;
    const c = !sc.controls.length ? '' : m.late === 'logic' ? ` · ${sc.controls.join('/')} by the logic` :
      m.late ? ` · ${sc.controls.join('/')} +20 µs` : ` · ${sc.controls.join('/')} with rails`;
    return `${o}<span>${m.speed === 'fast' ? '2 µs ramps' : '1 ms ramps'}${c}</span>`;
  };
  const chip = j => {
    const seq = $('#seq'), tl = $('#tl');
    let sc = null, sel = 0;
    const lanes = () => [...Object.entries(sc.supplies).map(([p, v], i) => [`vplan${i}`, `${p} ${v} V`]),
      ...sc.controls.map((p, i) => [`vctl${i}`, p])];
    const draw = () => {
      const r = sc.rows[sel], L = lanes(), W = 420, X0 = 78, X1 = W - 8, top = 12, lh = Math.min(44, 150 / L.length);
      const T = Math.max(...sc.rows.map(q => Math.max(...Object.values(q.schedule).map(s => s[0] === 'wave' ? s[1][s[1].length - 1][0] : s[0] + s[1])))) * 1.08;
      const x = t => X0 + (X1 - X0) * Math.sqrt(Math.max(0, t) / T);      // square-root time: 10 µs and 2 ms both visible
      let g = '';
      [0, 10e-6, 100e-6, 1e-3, 2e-3].filter(t => t <= T).forEach(t => {
        g += `<line class="gr" x1="${x(t)}" x2="${x(t)}" y1="${top - 4}" y2="${top + lh * L.length}"/>` +
          (t ? `<text class="ax" x="${x(t)}" y="${top + lh * L.length + 14}" text-anchor="middle">${us(t)}</text>` : '');
      });
      L.forEach(([k, name], i) => {
        const s = r.schedule[k], y0 = top + lh * (i + 1) - 8, y1 = top + lh * i + 8;
        let pts = [[0, 0]];
        if (s[0] === 'wave') { let lv = 0; s[1].forEach(([t, b]) => { if (b !== lv) { pts.push([t, lv], [t, b]); lv = b } }) }
        else pts.push([s[0], 0], [s[0] + s[1], 1]);
        pts.push([T, pts[pts.length - 1][1]]);
        const d = pts.map(([t, v], n) => `${n ? 'L' : 'M'}${x(t).toFixed(1)} ${(v ? y1 : y0).toFixed(1)}`).join('');
        g += `<text class="ln" x="0" y="${(y0 + y1) / 2 + 3}">${esc(name)}</text><path class="${k.startsWith('vctl') ? 'ctl' : 'rail'}" d="${d}"/>`;
      });
      tl.setAttribute('viewBox', `0 0 ${W} ${top + lh * L.length + 22}`); tl.innerHTML = g;
      const bad = CORNERS.filter(c => ['dead', 'oscillates'].includes((r.cells[c] || {}).state));
      $('#tl-cap').innerHTML = bad.length ? `<b class="bad">stays off</b> at ${bad.join(', ')} · ` +
        `${(Math.min(...bad.map(c => r.cells[c].i_end)) * 1e9).toFixed(2)} nA` : `<b>comes up</b> at tt, ss, ff · ` +
        `${(r.cells.tt.i_end * 1e6).toFixed(1)} µA`;
      seq.querySelectorAll('.row').forEach((e, i) => e.classList.toggle('sel', i === sel));
    };
    const show = key => {
      sc = j[key]; sel = 0;
      seq.innerHTML = `<div class="hd"><span></span>${CORNERS.map(c => `<span>${c}</span>`).join('')}</div>` + sc.rows.map((r, i) =>
        `<button class="row" type="button" data-i="${i}"><span class="nm">${label(r, sc)}</span>${CORNERS.map(c => {
          const st = (r.cells[c] || {}).state; return `<i class="${st === 'dead' || st === 'oscillates' ? 'bad' : st === 'settled' ? 'ok' : ''}" title="${c}: ${st || 'did not run'}"></i>` }).join('')}</button>`).join('');
      seq.querySelectorAll('.row').forEach(e => e.onclick = () => { sel = +e.dataset.i; draw() });
      const release = () => {      // when the logic lets go, counted from the end of the rail ramps (from the VCD)
        const lr = sc.rows.find(r => r.meta.late === 'logic'); if (!lr) return 0;
        const end = Math.max(...Object.entries(lr.schedule).filter(([k]) => k.startsWith('vplan')).map(([, v]) => v[0] + v[1]));
        return (lr.schedule.vctl0[1].find(p => p[1] === 1) || [end])[0] - end;
      };
      const f = sc.findings.find(f => f.rule === 'analog/sequence_dependent'), q = f && f.sequence;
      const nbad = sc.rows.filter(r => CORNERS.some(c => (r.cells[c] || {}).state === 'dead')).length;
      $('#verdict').innerHTML = !f ? '' : q && q.lead ?
        `<div class="big">${us(q.fail_gap)}</div><p><b>${esc(q.lead)} first by ${us(q.fail_gap)} or more: the block stays off.</b> At ${us(q.pass_gap)} it starts. With every rail together the plain power-up check passes, so nothing else catches this.</p>` :
        `<div class="big">${nbad}<small>/${sc.rows.length}</small></div><p><b>sequences where it stays off.</b> Released with the rails it starts; our logic releases ${esc(sc.controls.join('/'))} ${us(release())} after the rails (its VCD), when the start-up kick is long gone.</p>`;
      // first failing row selected, so the timeline opens on the finding
      const fails = r => CORNERS.some(c => (r.cells[c] || {}).state === 'dead');
      const fl = sc.rows.findIndex(r => r.meta.late === 'logic' && fails(r)), fi = fl >= 0 ? fl : sc.rows.findIndex(fails);
      sel = fi < 0 ? 0 : fi; draw();
    };
    document.querySelectorAll('.r-tabs button').forEach(b => b.onclick = () => {
      document.querySelectorAll('.r-tabs button').forEach(x => x.setAttribute('aria-selected', x === b)); show(b.dataset.s) });
    show('rails');
  };
  fetch('/static/chip.json').then(r => r.json()).then(chip);

  // ---------- intake field ----------
  const src = $('#src'), und = $('#und'), go = $('#go');
  let file = null, t = null;
  const showParse = d => {
    if (!d) { und.innerHTML = ''; go.disabled = true; return }
    if (!d.ok) { und.innerHTML = `<span class="bad">${esc(d.error)}</span>`; go.disabled = true; return }
    const bits = [[d.kind === 'git' ? 'git' : 'GitHub', d.label]];
    if (d.ref) bits.push([d.ref.startsWith('refs/pull/') ? 'pull request' : 'ref', d.ref.replace(/^refs\/pull\/(\d+)\/head$/, '#$1')]);
    if (d.path) bits.push(['folder', d.path]);
    if (d.focus) bits.push(['file', d.focus]);
    und.innerHTML = 'Reviewing ' + bits.map(([k, v]) => `<span class="tag"><b>${esc(k)}</b>${esc(v)}</span>`).join('');
    go.disabled = false;
  };
  src.addEventListener('input', () => {
    file = null; clearTimeout(t);
    const v = src.value.trim(); if (!v) return showParse(null);
    t = setTimeout(async () => showParse(await (await fetch('/api/parse', {method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({text: v})})).json()), 180);
  });
  const pickZip = f => {
    if (!f) return; if (!/\.zip$/i.test(f.name)) { showParse({ok: false, error: 'Drop a .zip of the project folder.'}); return }
    file = f; src.value = '';
    und.innerHTML = `Reviewing <span class="tag"><b>zip</b>${esc(f.name)}</span><span class="tag"><b>size</b>${(f.size / 1e6).toFixed(1)} MB</span>`;
    go.disabled = false;
  };
  $('#pick').onclick = () => $('#zip').click();
  $('#zip').onchange = e => pickZip(e.target.files[0]);
  const drop = $('#drop');
  ['dragenter', 'dragover'].forEach(ev => drop.addEventListener(ev, e => { e.preventDefault(); drop.classList.add('over') }));
  ['dragleave', 'drop'].forEach(ev => drop.addEventListener(ev, e => { e.preventDefault(); drop.classList.remove('over') }));
  drop.addEventListener('drop', e => pickZip(e.dataTransfer.files[0]));
  $('#ask').onsubmit = async e => {
    e.preventDefault(); go.disabled = true; go.textContent = 'Starting';
    let r, code = ''; try { code = sessionStorage.getItem('kv-code') || '' } catch (e3) {}
    const send = () => file ? (() => { const fd = new FormData(); fd.append('file', file); fd.append('code', code); return fetch('/api/runs', {method: 'POST', body: fd}) })()
      : fetch('/api/runs', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({text: src.value, code})});
    r = await send();
    let j = await r.json();
    if (r.status === 403 && j.need_code) {          // a hosted Kaaval with an access code: ask once per visit
      code = (prompt('Access code for this Kaaval (from the submission page):') || '').trim();
      if (code) { try { sessionStorage.setItem('kv-code', code) } catch (e4) {} r = await send(); j = await r.json() }
    }
    if (!r.ok) { showParse({ok: false, error: j.error}); go.textContent = 'Review'; return }
    try { const mine = JSON.parse(localStorage.getItem('kv-runs') || '[]'); localStorage.setItem('kv-runs', JSON.stringify([j.id, ...mine.filter(x => x !== j.id)].slice(0, 20))) } catch (e2) {}
    const nav = () => location.href = '/runs/' + j.id;
    !reduce && document.startViewTransition ? document.startViewTransition(nav) : nav();
  };

  // figures count up once in view; chapters reveal once
  const count = el => {
    const to = +el.dataset.to, dec = +(el.dataset.dec || 0), suf = el.dataset.suffix || '';
    const fmt = v => v.toLocaleString('en-US', {minimumFractionDigits: dec, maximumFractionDigits: dec}) + suf;
    if (reduce) { el.textContent = fmt(to); return }
    const t0 = performance.now(); const step = ts => { const p = Math.min(1, (ts - t0) / 1400); el.textContent = fmt(to * (1 - Math.pow(1 - p, 3))); if (p < 1) requestAnimationFrame(step) };
    requestAnimationFrame(step);
  };
  document.querySelectorAll('.r-sec, .r-facts').forEach(s => s.classList.add('reveal'));
  const io = new IntersectionObserver(es => es.forEach(e => { if (!e.isIntersecting) return; e.target.classList.add('in'); io.unobserve(e.target);
    e.target.querySelectorAll('.v[data-to]').forEach(count) }), {threshold: 0.12});
  document.querySelectorAll('.reveal').forEach(el => io.observe(el));

  // the visitor's own recent reviews
  const ago = s => { const d = Date.now() / 1000 - s; return d < 60 ? Math.round(d) + ' s ago' : d < 3600 ? Math.round(d / 60) + ' min ago' : d < 86400 ? Math.round(d / 3600) + ' h ago' : Math.round(d / 86400) + ' d ago' };
  let mine = []; try { mine = JSON.parse(localStorage.getItem('kv-runs') || '[]') } catch (e) {}
  if (mine.length) fetch('/api/runs?ids=' + mine.join(',')).then(r => r.json()).then(rs => {
    if (!rs.length) return; $('#recent').hidden = false;
    $('#runs').innerHTML = rs.slice(0, 6).map(r => {
      const nf = (r.summary && JSON.parse(r.summary).findings) || 0;
      const st = r.status === 'done' ? (nf ? `${nf} finding${nf > 1 ? 's' : ''}` : 'clean') : r.status === 'error' ? 'error' : 'running';
      return `<a class="row" href="/runs/${r.id}"><span>${esc(r.repo)}</span><span class="mono" style="color:var(--text-3)">${esc((r.commit_sha || '').slice(0, 7))}</span><span class="mono">${st}</span><span class="when mono">${ago(r.created)}</span></a>`;
    }).join('');
  });
})();
