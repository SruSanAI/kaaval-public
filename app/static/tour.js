/* tour.js — "Walk me through it": a finding explained on the bench itself, step by step.

   steps(f, plain) turns one finding into the steps of its walk-through, from the finding's own data only (no number
   is made up here): the problem in plain words, where it is (the device circled on its sheet), when it fails (the
   conditions lit on the grid), the proof (the measured waveform or loop gain at the worst condition), and what to do.
   A step whose target the finding does not have is left out. Tour(hooks) plays them on the page: everything but
   the target is dimmed, a ring is drawn around it with a leader line to a callout, and a narration bar carries the
   words, Back / Next, the step dots and autoplay. The hooks are the bench's own: open the device's sheet, find a
   cell of the grid, show the evidence panel. Pure steps() runs under node for the tests (tests/test_tour_steps.py). */
(function (root) {
  const cond = c => c ? `${c[0]}, ${c[1]} °C, supply ×${c[2]}` : '';
  const eng = (v, u) => { if (v == null || !isFinite(v)) return '—'; const P = [[1e-12, 'p'], [1e-9, 'n'], [1e-6, 'µ'], [1e-3, 'm'], [1, ''], [1e3, 'k'], [1e6, 'M'], [1e9, 'G']];
    let s = P[0]; for (const p of P) if (Math.abs(v) >= p[0] * 0.9995) s = p; return (v / s[0]).toPrecision(3) + ' ' + s[1] + u };
  const first = t => String(t || '').split(/(?<=[.:])\s/)[0];
  const count = d => d && d.n_bad != null && d.n ? `${d.n_bad} of ${d.n} conditions` : '';

  // the number a finding is about, said at the device
  const reading = f => {
    const d = f.detail || {};
    if (f.rule === 'analog/headroom' && d.nominal_margin != null)
      return `margin ${(d.nominal_margin * 1e3).toFixed(0)} mV at nominal, ${(d.worst_margin * 1e3).toFixed(0)} mV at ${cond(d.worst)}`;
    if (f.rule === 'analog/bias_collapse' && d.nominal_id != null)
      return `${eng(d.nominal_id, 'A')} at nominal, ${eng(d.worst_id, 'A')} at ${cond(d.worst)}`;
    if (d.loop && d.margins) return (d.margins.pm != null ? `phase margin ${d.margins.pm.toFixed(0)}°` : 'no unity-gain crossing') +
      (d.margins.ugf ? ` at ${eng(d.margins.ugf, 'Hz')}` : '') + ` (${cond(d.worst)})`;
    if (d.states && d.states.length === 2) return `${eng(d.states[0].i, 'A')} by DC analysis, ${eng(d.states[1].i, 'A')} after power-up`;
    if (d.worst) return `worst at ${cond(d.worst)}`;
    return '';
  };

  // where the finding lives: a device on a sheet, an instance in the designer's testbench, or a cell's layout
  const where = f => {
    const d = f.detail || {};
    if (d.loop) return {kind: 'device', sheet: d.testbench, device: d.loop.inst,
      text: `${d.loop.inst} (${d.loop.subckt}) in the designer's testbench ${d.testbench}: its output ${d.loop.net} ${d.loop.via}. ` +
            `Kaaval cuts the loop there (${d.loop.pin}) and measures the gain around it.`};
    if (/^layout\//.test(f.rule)) return null;                     // the layout is not drawn on the bench
    const dev = f.device || d.device;
    if (!dev || dev === 'loop' || dev === 'supply') return d.plan && d.plan.cell ? {kind: 'sheet', sheet: d.plan.cell,
      text: `The cell is ${d.plan.cell}; the test Kaaval wrote for it powers it up from 0 V at every condition.`} : null;
    return {kind: 'device', sheet: d.plan && d.plan.cell, device: dev, text: `${dev} on ${d.plan && d.plan.cell || 'the reviewed schematic'}.`};
  };

  const steps = (f, plain) => {
    const d = f.detail || {}, out = [], r = reading(f);
    out.push({id: 'what', title: 'The problem', target: {kind: 'card'},
      text: (plain ? plain + ' ' : '') + first(f.title)});
    const w = where(f);
    if (w) out.push({id: 'where', title: 'Where it is', target: w, callout: r || null, text: w.text});
    if (d.k != null || d.loop) out.push({id: 'when', title: 'When it fails', target: {kind: 'evidence-grid'},
      text: `${count(d) ? 'It fails at ' + count(d) + '. ' : ''}Each square is one simulation: one corner, temperature and supply. ` +
            (d.worst ? `The worst is ${cond(d.worst)}.` : '')});
    else if (d.worst || d.n_bad != null) out.push({id: 'when', title: 'When it fails', target: {kind: 'cells', worst: d.worst || null, device: f.device || d.device},
      text: `${count(d) ? 'It fails at ' + count(d) + ' of the PVT sweep. ' : ''}${d.worst ? 'The worst is ' + cond(d.worst) + '.' : ''}`});
    if (d.k != null || d.loop) out.push({id: 'proof', title: 'The proof', target: {kind: 'evidence-plot'},
      text: d.loop ? 'The loop gain at the worst condition: where its magnitude crosses 0 dB, the phase says how close the loop is to oscillating. ' +
                     'Click any square to see another condition.'
                   : 'What the simulator measured at the worst condition. Click any square to simulate another condition.'});
    const act = f.kind === 'note' ? 'This is a note: something a test could not settle. Re-test it with the input biased as the chip biases it.'
      : /^analog\/headroom/.test(f.rule) ? 'Try a sizing fix: each candidate is re-simulated at all 45 conditions before it is shown.'
      : d.k != null || d.loop ? 'Download the evidence: the test, every condition, and an ngspice deck you can run without Kaaval.'
      : 'Check the device against the condition above in your own simulator.';
    out.push({id: 'next', title: 'What to do', target: {kind: 'actions'}, text: act});
    return out;
  };

  // ---------- the overlay ----------
  function Tour(hooks) { this.h = hooks; this.i = 0; this.s = []; this.f = null; this.auto = null; this.build() }
  Tour.prototype.build = function () {
    const el = this.el = document.createElement('div'); el.className = 'tour'; el.hidden = true;
    el.innerHTML = `<div class="tour-dim"></div><svg class="tour-ink" aria-hidden="true"><path class="tour-lead"/><rect class="tour-ring" rx="10"/></svg>
      <div class="tour-call mono" role="note"></div>
      <div class="tour-bar" role="dialog" aria-label="Walk-through">
        <div class="tour-tx"><div class="tour-k mono"></div><div class="tour-t"></div><div class="tour-p"></div></div>
        <div class="tour-nav"><div class="tour-dots"></div>
          <button class="btn" type="button" data-t="auto" aria-pressed="false">Play</button>
          <button class="btn" type="button" data-t="back">Back</button>
          <button class="btn primary" type="button" data-t="next">Next</button>
          <button class="btn icon" type="button" data-t="x" aria-label="Close the walk-through">×</button></div></div>`;
    document.body.appendChild(el);
    el.addEventListener('click', e => { const b = e.target.closest('[data-t]'); if (!b) return;
      ({back: () => this.go(this.i - 1), next: () => this.i < this.s.length - 1 ? this.go(this.i + 1) : this.close(), x: () => this.close(),
        auto: () => this.play(!this.auto)})[b.dataset.t]() });
    document.addEventListener('keydown', e => { if (el.hidden) return;
      if (e.key === 'Escape') this.close(); else if (e.key === 'ArrowRight') this.go(Math.min(this.s.length - 1, this.i + 1));
      else if (e.key === 'ArrowLeft') this.go(Math.max(0, this.i - 1)) });
    addEventListener('resize', () => { if (!el.hidden) this.place(this.rect) });
  };
  Tour.prototype.start = function (f, plain) {
    this.f = f; this.s = steps(f, plain); this.el.hidden = false; document.body.classList.add('touring');
    this.el.querySelector('.tour-dots').innerHTML = this.s.map((_, i) => `<i data-i="${i}"></i>`).join('');
    this.go(0);
  };
  Tour.prototype.close = function () { this.play(false); this.el.hidden = true; document.body.classList.remove('touring'); this.h.done && this.h.done() };
  Tour.prototype.play = function (on) {
    clearInterval(this.auto);
    if (on && this.i >= this.s.length - 1) this.go(0);     // Play on the last step plays it again from the start this.auto = on ? setInterval(() => this.i < this.s.length - 1 ? this.go(this.i + 1) : this.play(false), 5200) : null;
    const b = this.el.querySelector('[data-t="auto"]'); b.textContent = on ? 'Pause' : 'Play'; b.setAttribute('aria-pressed', !!on);
  };
  Tour.prototype.go = async function (i) {
    if (i < 0 || i >= this.s.length) return; this.i = i; const st = this.s[i], q = s => this.el.querySelector(s);
    q('.tour-k').textContent = `${i + 1} / ${this.s.length}`; q('.tour-t').textContent = st.title; q('.tour-p').textContent = st.text;
    q('[data-t="back"]').disabled = i === 0; q('[data-t="next"]').textContent = i === this.s.length - 1 ? 'Done' : 'Next';
    this.el.querySelectorAll('.tour-dots i').forEach((d, k) => d.classList.toggle('on', k <= i));
    const rect = await this.h.show(this.f, st);              // the bench moves to the target and says where it is on screen
    if (this.i !== i) return;                                // the user stepped on while the bench was moving
    this.rect = rect; q('.tour-call').textContent = st.callout || ''; this.place(rect);
  };
  Tour.prototype.place = function (r) {
    const q = s => this.el.querySelector(s), ring = q('.tour-ring'), lead = q('.tour-lead'), call = q('.tour-call'), dim = q('.tour-dim');
    if (!r) { dim.style.clipPath = 'none'; ring.style.display = 'none'; lead.style.display = 'none'; call.hidden = true; return }
    const p = 8, x = r.left - p, y = r.top - p, w = r.width + 2 * p, h = r.height + 2 * p;
    // dim everything but the target: a polygon with the target cut out (even-odd)
    dim.style.clipPath = `path(evenodd, "M0 0H${innerWidth}V${innerHeight}H0Z M${x} ${y}h${w}v${h}h${-w}Z")`;
    Object.entries({x, y, width: w, height: h}).forEach(([k, v]) => ring.setAttribute(k, v)); ring.style.display = '';
    const still = matchMedia('(prefers-reduced-motion: reduce)').matches;
    [ring, lead].forEach(e => { e.classList.remove('draw'); void e.getBBox(); if (!still) e.classList.add('draw') });
    call.hidden = !call.textContent;
    if (call.hidden) { lead.style.display = 'none'; return }
    // the callout sits beside the target, on the side with room, and a leader line runs to the ring
    const cw = Math.min(300, innerWidth - 32), right = x + w + 24 + cw < innerWidth;
    const cx = right ? x + w + 24 : Math.max(16, x - 24 - cw), cy = Math.max(16, Math.min(innerHeight - 160, y + h / 2 - 20));
    call.style.left = cx + 'px'; call.style.top = cy + 'px'; call.style.maxWidth = cw + 'px';
    const ax = right ? x + w : x, ay = y + h / 2, bx = right ? cx : cx + call.offsetWidth, by = cy + 16;
    lead.setAttribute('d', `M${ax} ${ay}C${(ax + bx) / 2} ${ay} ${(ax + bx) / 2} ${by} ${bx} ${by}`); lead.style.display = '';
  };

  const api = {steps, reading, where, Tour};
  if (typeof module !== 'undefined' && module.exports) module.exports = api; else root.KaavalTour = api;
})(typeof window !== 'undefined' ? window : globalThis);
