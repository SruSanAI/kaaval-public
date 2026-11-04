// Layout 3D: a cell's committed Magic layout as stacked layers (three.js). Everything drawn comes from
// /api/runs/<id>/layout3d (kaaval_engine.layout3d: the .mag files read as text); nothing here is invented.
(() => {
  const $ = s => document.querySelector(s);
  const esc = s => String(s).replace(/[&<>"]/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;'}[c]));
  const rid = location.pathname.split('/')[2], root = document.documentElement;
  const q = new URLSearchParams(location.search);
  $('#c-run').href = '/runs/' + rid; $('#c-chip').href = `/runs/${rid}/chip`;
  // one colour per layer group, the same in both themes (a layout's colours are its legend)
  const COL = {well: 0x6b7280, diffusion: 0x2f9e6b, gate: 0xd9483b, poly: 0xe0604f, contact: 0xcfcfcf, li: 0x8b5cf6,
    mcon: 0xd4d4d4, metal1: 0x3b82f6, via1: 0xbfbfbf, metal2: 0xec4899, via2: 0xbfbfbf, metal3: 0x22c3c3, via3: 0xbfbfbf,
    metal4: 0xf59e0b, via4: 0xbfbfbf, metal5: 0xa3a3a3};
  const OPA = {well: 0.16, diffusion: 0.85, gate: 0.95, poly: 0.9, contact: 0.95, li: 0.8, mcon: 0.95, metal1: 0.72,
    metal2: 0.66, metal3: 0.62, metal4: 0.58, metal5: 0.55};
  const cssv = n => getComputedStyle(root).getPropertyValue(n).trim();
  $('#theme').onclick = () => {
    const dark = root.dataset.theme ? root.dataset.theme === 'dark' : matchMedia('(prefers-color-scheme: dark)').matches;
    root.dataset.theme = dark ? 'light' : 'dark'; try { localStorage.setItem('kv-theme', root.dataset.theme) } catch (e) {}
  };

  const view = $('#view');
  const renderer = new THREE.WebGLRenderer({antialias: true, alpha: true});
  renderer.setPixelRatio(Math.min(devicePixelRatio || 1, 2));
  view.appendChild(renderer.domElement);
  const scene = new THREE.Scene(), cam = new THREE.PerspectiveCamera(40, 1, 0.1, 1e6);
  const ctl = new THREE.OrbitControls(cam, renderer.domElement); ctl.enableDamping = true; ctl.dampingFactor = 0.08;
  scene.add(new THREE.AmbientLight(0xffffff, 0.75));
  const sun = new THREE.DirectionalLight(0xffffff, 0.55); sun.position.set(1, -1.2, 2); scene.add(sun);
  const size = () => { const r = view.getBoundingClientRect(); renderer.setSize(r.width, r.height, false); cam.aspect = r.width / Math.max(r.height, 1); cam.updateProjectionMatrix() };
  new ResizeObserver(size).observe(view);

  let data = null, meshes = [], span = 1, still = matchMedia('(prefers-reduced-motion: reduce)').matches;
  const unit = () => data.unit_um;
  const place = () => {                      // heights: nominal stack x zscale, plus explode gaps between groups
    const k = +$('#zscale').value * span / 400, gap = +$('#explode').value / 100 * span * 0.04;
    const groups = [...new Set(data.layers.map(l => l.group))];
    meshes.forEach(m => { const l = m.userData.layer, gi = groups.indexOf(l.group);
      m.position.z = l.z * k + gi * gap; m.scale.z = Math.max(l.h * k, span * 0.0008) });
  };
  const build = d => {
    meshes.forEach(m => { scene.remove(m); m.geometry.dispose(); m.material.dispose() }); meshes = [];
    data = d; const u = d.unit_um, [x0, y0, x1, y1] = d.bbox, cx = (x0 + x1) / 2, cy = (y0 + y1) / 2;
    span = Math.max(x1 - x0, y1 - y0) * u;
    const geo = new THREE.BoxGeometry(1, 1, 1); geo.translate(0, 0, 0.5);
    const M = new THREE.Matrix4(), Q = new THREE.Quaternion(), P = new THREE.Vector3(), S = new THREE.Vector3();
    d.layers.forEach(l => {
      const mat = new THREE.MeshLambertMaterial({color: COL[l.group] || 0x999999, transparent: true, opacity: OPA[l.group] ?? 0.8,
        depthWrite: (OPA[l.group] ?? 0.8) > 0.6});
      const inst = new THREE.InstancedMesh(geo, mat, l.rects.length);
      l.rects.forEach((r, i) => {
        P.set(((r[0] + r[2]) / 2 - cx) * u, ((r[1] + r[3]) / 2 - cy) * u, 0);
        S.set(Math.max((r[2] - r[0]) * u, 1e-3), Math.max((r[3] - r[1]) * u, 1e-3), 1);
        inst.setMatrixAt(i, M.compose(P, Q, S));
      });
      // each layer is one mesh whose z position and thickness the sliders move together
      const holder = new THREE.Group(); holder.add(inst); holder.userData.layer = l; holder.geometry = geo; holder.material = mat;
      scene.add(holder); meshes.push(holder);
    });
    place();
    cam.position.set(span * 0.55, -span * 0.95, span * 0.75); cam.up.set(0, 0, 1); ctl.target.set(0, 0, 0); ctl.update();
    $('#l3-meta').textContent = `${d.cell} · ${(span).toFixed(1)} µm across · ${d.layers.reduce((n, l) => n + l.rects.length, 0).toLocaleString()} rectangles` +
      ` · ${d.cells.length} cell(s)${d.truncated ? ' · capped' : ''}`;
    $('#c-cell').textContent = d.cell;
    const byG = {}; d.layers.forEach(l => (byG[l.group] = byG[l.group] || []).push(l));
    $('#l3-n').textContent = `${Object.keys(byG).length} groups`;
    $('#layers').innerHTML = Object.entries(byG).reverse().map(([g, ls]) => `<div class="l3-row" data-g="${esc(g)}">` +
      `<i style="background:#${(COL[g] || 0x999999).toString(16).padStart(6, '0')}"></i>${esc(g)}` +
      `<span class="n">${ls.reduce((n, l) => n + l.rects.length, 0)}</span></div>`).join('');
    $('#layers').querySelectorAll('.l3-row').forEach(r => r.onclick = () => {
      r.classList.toggle('off'); meshes.filter(m => m.userData.layer.group === r.dataset.g).forEach(m => m.visible = !r.classList.contains('off')) });
    if (!still) { $('#explode').value = 60; place(); animateExplode(60, 8, 1400) }       // the stack settles together on arrival
  };
  const animateExplode = (from, to, ms) => { const t0 = performance.now();
    const step = t => { const p = Math.min(1, (t - t0) / ms), e = 1 - Math.pow(1 - p, 3); $('#explode').value = from + (to - from) * e; place();
      if (p < 1) requestAnimationFrame(step) }; requestAnimationFrame(step) };
  $('#explode').oninput = place; $('#zscale').oninput = place;

  // hover: which layer is under the pointer
  const ray = new THREE.Raycaster(), mouse = new THREE.Vector2(), tip = $('#l3-tip');
  renderer.domElement.addEventListener('pointermove', e => {
    const r = renderer.domElement.getBoundingClientRect(); mouse.set((e.clientX - r.left) / r.width * 2 - 1, -(e.clientY - r.top) / r.height * 2 + 1);
    ray.setFromCamera(mouse, cam);
    const hit = ray.intersectObjects(meshes.filter(m => m.visible), true)[0];
    if (!hit) { tip.hidden = true; return }
    const l = hit.object.parent.userData.layer; tip.hidden = false;
    tip.textContent = `${l.name} (${l.group}) · ${(hit.point.x).toFixed(1)}, ${(hit.point.y).toFixed(1)} µm`;
    tip.style.left = (e.clientX - r.left) + 'px'; tip.style.top = (e.clientY - r.top) + 'px';
  });
  renderer.domElement.addEventListener('pointerleave', () => tip.hidden = true);
  const loop = () => { ctl.update(); renderer.render(scene, cam); requestAnimationFrame(loop) }; size(); loop();

  const load = mag => fetch(`/api/runs/${rid}/layout3d?mag=${encodeURIComponent(mag)}`).then(r => r.json()).then(d => {
    if (!d.ok || !d.bbox) { $('#l3-meta').textContent = d.error || 'this layout holds no drawn layers'; return }
    build(d); history.replaceState(null, '', `?mag=${encodeURIComponent(mag)}`) });
  fetch(`/api/runs/${rid}/layout3d`).then(r => r.json()).then(j => {
    const base = m => m.split('/').pop().replace(/\.mag$/, '');
    // an analog block first (a whole tile is standard cells and pads), then the top cell
    const mags = j.mags || [], want = q.get('mag') || (j.analog || [])[0] || (j.top && mags.find(m => base(m) === j.top)) || mags[0];
    $('#pick').innerHTML = mags.map(m => `<option${m === want ? ' selected' : ''}>${esc(m)}</option>`).join('');
    $('#pick').onchange = () => load($('#pick').value);
    if (want) load(want); else $('#l3-meta').textContent = 'no Magic layout (.mag) in this repository';
  });
})();
