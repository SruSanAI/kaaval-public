// Kaaval Zoom: the whole Tiny Tapeout tile -> one block -> its schematic and the tests run on it.
// Everything drawn comes from /api/runs/<id>/chip (the project's top module and info.yaml, read as text) and the
// review's own test results; nothing here is invented.
(() => {
  const $ = s => document.querySelector(s);
  const esc = s => String(s).replace(/[&<>"]/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;'}[c]));
  const rid = location.pathname.split('/')[2];
  const root = document.documentElement;
  $('#theme').onclick = () => {
    const dark = root.dataset.theme ? root.dataset.theme === 'dark' : matchMedia('(prefers-color-scheme: dark)').matches;
    root.dataset.theme = dark ? 'light' : 'dark'; try { localStorage.setItem('kv-theme', root.dataset.theme) } catch (e) {}
  };
  $('#c-run').href = '/runs/' + rid;

  const PLAIN = {
    'analog/no_startup': 'stays off after power-up', 'analog/two_states': 'has a second operating point',
    'analog/marginal_startup': 'start-up depends on numerical detail', 'analog/oscillates': 'never settles',
    'analog/sequence_dependent': 'depends on the power-up order', 'analog/overstress': 'a 1.8 V device sees more',
    'analog/weak_output': 'cannot drive its pad', 'analog/low_phase_margin': 'thin phase margin', 'analog/unstable': 'unstable loop'};
  const SIDE = {rail: 'top', analog_pad: 'bottom', digital_in: 'left', clock: 'left', reset: 'left', enable: 'left',
    digital_out: 'right', constant: 'left'};

  fetch(`/api/runs/${rid}/chip`).then(r => r.json()).then(t => {
    if (!t.ok) { $('#insp').innerHTML = `<p class="z-empty">${esc(t.error || 'no tile')}</p>`; return }
    $('#c-top').textContent = t.top || 'tile';
    $('#z-meta').textContent = `${t.instances.length} blocks · ${t.uses_3v3 ? '3.3 V + 1.8 V' : '1.8 V'} · analog pads ${t.analog_pads.join(' ') || 'none'}`;
    draw(t);
  });

  function draw(t) {
    const S = $('#tile'), W = 960, H = 600, L = 120, R = W - 120, top = 56, bot = H - 96;
    const blocks = [...t.instances].sort((a, b) => (a.analog - b.analog) || a.name.localeCompare(b.name));
    // columns: digital blocks left, analog right
    const cols = [blocks.filter(b => !b.analog), blocks.filter(b => b.analog)].filter(c => c.length);
    const cw = (R - L) / Math.max(cols.length, 1);
    const pos = new Map();
    cols.forEach((col, ci) => {
      const gap = (bot - top - 40) / col.length;
      col.forEach((b, i) => {
        const pins = b.pins.length, h = Math.min(gap - 24, Math.max(70, 14 * Math.max(...['left', 'right'].map(s =>
          b.pins.filter(p => side(p, b) === s).length)) + 30));
        pos.set(b.name, {x: L + ci * cw + cw * 0.18, y: top + 40 + i * gap + (gap - h) / 2, w: cw * 0.64, h});
      });
    });
    function side(p, b) {
      if (SIDE[p.kind]) return SIDE[p.kind];
      return b.analog ? 'left' : 'right';          // internal nets face the other column
    }
    // pads along the edges, only the ones in use (all six analog pads drawn, the paid ones marked)
    const used = k => [...new Set(t.instances.flatMap(b => b.pins.filter(p => p.kind === k || (k === 'digital_in' && ['clock', 'reset', 'enable'].includes(p.kind))).map(p => p.pad)))];
    const ins = used('digital_in'), outs = used('digital_out');
    const padY = (list, i) => top + 40 + (i + 0.5) * (bot - top - 40) / Math.max(list.length, 1);
    const uaX = i => L + (i + 0.5) * (R - L) / 6;
    let g = '';
    // rails
    const rails = [['VDPWR', '1.8 V', top - 30], ['VAPWR', '3.3 V', top - 12]];
    rails.forEach(([n, v, y]) => {
      const on = t.rails.includes(n);
      g += `<line class="rail${on ? '' : ' off'}" x1="${L - 40}" x2="${R + 40}" y1="${y}" y2="${y}"/><text class="rl" x="${L - 46}" y="${y + 3}" text-anchor="end">${n} ${v}${on ? '' : ' (unused)'}</text>`;
    });
    g += `<line class="rail" x1="${L - 40}" x2="${R + 40}" y1="${H - 20}" y2="${H - 20}"/><text class="rl" x="${L - 46}" y="${H - 17}" text-anchor="end">VGND</text>`;
    // analog pads
    for (let i = 0; i < 6; i++) {
      const p = `ua[${i}]`, on = t.analog_pads.includes(p), paid = t.analog_pins != null && i < t.analog_pins;
      g += `<g class="pad${on ? ' on' : ''}" data-pad="${p}"><rect x="${uaX(i) - 26}" y="${H - 66}" width="52" height="26" rx="3"/><text x="${uaX(i)}" y="${H - 49}" text-anchor="middle">${p}</text>` +
        (t.analog_pins != null ? `<text class="sub" x="${uaX(i)}" y="${H - 72}" text-anchor="middle">${paid ? 'paid' : ''}</text>` : '') + '</g>';
    }
    ins.forEach((p, i) => g += `<g class="pad on" data-pad="${esc(p)}"><rect x="${L - 108}" y="${padY(ins, i) - 11}" width="64" height="22" rx="3"/><text x="${L - 76}" y="${padY(ins, i) + 4}" text-anchor="middle">${esc(p)}</text></g>`);
    outs.forEach((p, i) => g += `<g class="pad on" data-pad="${esc(p)}"><rect x="${R + 44}" y="${padY(outs, i) - 11}" width="64" height="22" rx="3"/><text x="${R + 76}" y="${padY(outs, i) + 4}" text-anchor="middle">${esc(p)}</text></g>`);
    // blocks, their pins and wires
    const netPins = {};
    let wires = '', boxes = '';
    blocks.forEach(b => {
      const P = pos.get(b.name), bad = (b.tests || []).some(x => x.findings.length);
      const by = {top: [], bottom: [], left: [], right: []};
      b.pins.forEach(p => by[side(p, b)].push(p));
      const at = (s, i, n) => s === 'top' ? [P.x + (i + 1) * P.w / (n + 1), P.y] : s === 'bottom' ? [P.x + (i + 1) * P.w / (n + 1), P.y + P.h]
        : s === 'left' ? [P.x, P.y + 22 + i * (P.h - 30) / Math.max(n, 1)] : [P.x + P.w, P.y + 22 + i * (P.h - 30) / Math.max(n, 1)];
      let pins = '';
      Object.entries(by).forEach(([s, ps]) => ps.forEach((p, i) => {
        const [x, y] = at(s, i, ps.length), id = `${b.name}.${p.port}`;
        pins += `<circle class="pin" cx="${x}" cy="${y}" r="3" data-pin="${esc(id)}"><title>${esc(p.port)} → ${esc(p.pad || p.rail || p.net)}</title></circle>`;
        const lx = s === 'left' ? x + 6 : s === 'right' ? x - 6 : x, ly = s === 'top' ? y + 12 : s === 'bottom' ? y - 6 : y + 3;
        pins += `<text class="pn" x="${lx}" y="${ly}" text-anchor="${s === 'left' ? 'start' : s === 'right' ? 'end' : 'middle'}">${esc(p.port)}</text>`;
        let d = '';
        if (p.kind === 'rail') { const ry = (rails.find(r => r[0] === p.rail) || [0, 0, H - 20])[2]; d = `M${x} ${y}V${p.rail === 'VGND' ? H - 20 : ry}` }
        else if (p.kind === 'analog_pad') { const i2 = +p.pad.slice(3, -1); d = `M${x} ${y}V${H - 86}H${uaX(i2)}V${H - 66}` }
        else if (p.pad && ins.includes(p.pad)) d = `M${x} ${y}H${(L - 44 + x) / 2}V${padY(ins, ins.indexOf(p.pad))}H${L - 44}`;
        else if (p.pad && outs.includes(p.pad)) d = `M${x} ${y}H${(R + 44 + x) / 2}V${padY(outs, outs.indexOf(p.pad))}H${R + 44}`;
        else if (p.kind === 'internal') (netPins[p.net.toLowerCase()] = netPins[p.net.toLowerCase()] || []).push([x, y, id]);
        if (d) wires += `<path class="w ${p.kind}" d="${d}" data-pin="${esc(id)}"/>`;
      }));
      boxes += `<g class="blk${b.analog ? ' a' : b.digital ? ' d' : ''}${bad ? ' bad' : ''}" data-b="${esc(b.name)}" tabindex="0" role="button" aria-label="${esc(b.name)}">` +
        `<rect x="${P.x}" y="${P.y}" width="${P.w}" height="${P.h}" rx="4"/>` +
        `<text class="bn" x="${P.x + P.w / 2}" y="${P.y + P.h / 2 - 2}" text-anchor="middle">${esc(b.name)}</text>` +
        `<text class="bt" x="${P.x + P.w / 2}" y="${P.y + P.h / 2 + 13}" text-anchor="middle">${esc(b.type)}${bad ? ' · finding' : ''}</text>${pins}</g>`;
    });
    // internal nets: pins sharing a net are wired together through a midpoint bus
    Object.entries(netPins).forEach(([n, ps]) => {
      if (ps.length < 2) return;
      const mx = ps.reduce((s, p) => s + p[0], 0) / ps.length;
      ps.forEach(([x, y, id]) => wires += `<path class="w internal" d="M${x} ${y}H${mx}" data-pin="${esc(id)}"/>`);
      wires += `<path class="w internal" d="M${mx} ${Math.min(...ps.map(p => p[1]))}V${Math.max(...ps.map(p => p[1]))}"/><text class="nn" x="${mx + 4}" y="${Math.min(...ps.map(p => p[1])) - 4}">${esc(n)}</text>`;
    });
    S.setAttribute('viewBox', `0 0 ${W} ${H}`);
    S.innerHTML = g + wires + boxes;
    S.querySelectorAll('.blk').forEach(e => {
      const go = () => open(t.instances.find(b => b.name === e.dataset.b), e);
      e.onclick = go; e.onkeydown = k => { if (k.key === 'Enter' || k.key === ' ') { k.preventDefault(); go() } };
    });
    S.querySelectorAll('.pin').forEach(e => e.onclick = ev => { ev.stopPropagation(); trace(e.dataset.pin) });
    const first = blocks.find(b => (b.tests || []).some(x => x.findings.length)) || blocks.find(b => b.analog);
    if (first) open(first, S.querySelector(`.blk[data-b="${CSS.escape(first.name)}"]`));
  }

  function trace(id) {
    const S = $('#tile');
    S.querySelectorAll('.w').forEach(w => w.classList.toggle('hl', w.dataset.pin === id));
  }

  function open(b, el) {
    document.querySelectorAll('.blk').forEach(x => x.classList.toggle('sel', x === el));
    $('#c-sel').textContent = b.name;
    $('#i-kind').textContent = b.analog ? 'ANALOG BLOCK' : b.digital ? 'DIGITAL BLOCK' : 'BLOCK';
    $('#i-cell').textContent = b.cell || b.type;
    const where = p => p.kind === 'rail' ? `${p.rail}` : p.pad ? p.pad : p.kind === 'internal' ? `net ${p.net} (to another block)` : p.kind === 'constant' ? `tied ${p.net}` : p.net || '—';
    const pins = `<table class="z-pins mono"><tbody>${b.pins.map(p => `<tr data-pin="${esc(b.name + '.' + p.port)}"><td>${esc(p.port)}</td><td class="k">${esc(p.kind.replace('_', ' '))}</td><td>${esc(where(p))}</td></tr>`).join('')}</tbody></table>`;
    const tests = (b.tests || []).length ? b.tests.map(x => `<div class="z-test${x.findings.length ? ' bad' : ''}"><b class="mono">${esc(x.kind)}</b>` +
      (x.findings.length ? x.findings.map(f => `<p><span class="mono r">${esc(PLAIN[f.rule] || f.rule)}</span> ${esc(f.message)}</p>`).join('') : '<p class="ok">no finding</p>') +
      `<p class="why">${esc(x.why || '')}</p></div>`).join('') :
      `<p class="z-empty">${b.analog ? 'This review ran no test on this block.' : 'Digital block: its timing and logic are shown, not simulated here.'}</p>`;
    $('#insp').innerHTML = `<h3>Pins</h3>${pins}<h3>Tests on this block</h3>${tests}` +
      (b.cell && b.cell.endsWith('.sch') ? `<h3>Schematic</h3><div class="z-sch" id="sch"><p class="z-empty">drawing…</p></div>` : '');
    $('#insp').querySelectorAll('tr[data-pin]').forEach(r => r.onclick = () => trace(r.dataset.pin));
    if (b.cell && b.cell.endsWith('.sch'))
      fetch(`/api/runs/${rid}/sheet?cell=${encodeURIComponent(b.cell)}`).then(r => r.json()).then(j => {
        $('#sch').innerHTML = j.ok ? j.svg : `<p class="z-empty">${esc(j.error || 'no drawing')}</p>`;
      });
  }
})();
