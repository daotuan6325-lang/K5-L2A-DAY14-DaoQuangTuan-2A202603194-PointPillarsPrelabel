// ==UserScript==
// @name         CVAT D14: hop 3D tren camera
// @description  Bang noi trong job CVAT: chieu cuboid (da Save) len 7 camera, to vang hop dang chon. Can chay tools/d14_camserver.py.
// @match        http://localhost:8080/*
// @grant        none
// @version      1.7
// ==/UserScript==
// Chi DOC nhan qua API CVAT (phien dang nhap cua ban); khong ghi, khong sua nhan.
(() => {
  'use strict';
  const SERVER = 'http://127.0.0.1:8765';
  const COLORS = { Car: '#ff3b3b', Truck: '#ff9800', Bus: '#ffe600', Cyclist: '#3be36b', Pedestrian: '#3b9dff' };
  const S = { job: null, meta: null, specs: null, frame: null, data: null, sel: null, mode: 'all', busy: false, err: '' };

  // ---------------------------------------------------------------- panel
  const css = `
#d14p{position:fixed;top:60px;right:12px;width:560px;height:520px;z-index:99999;background:#14161b;color:#e6e6e6;
 font:12px/1.35 Segoe UI,Arial,sans-serif;border:1px solid #444;border-radius:8px;box-shadow:0 6px 24px #0008;
 display:flex;flex-direction:column;resize:both;overflow:hidden;min-width:300px;min-height:160px}
#d14p.min{height:34px!important;min-height:34px;resize:none}
#d14p header{display:flex;gap:6px;align-items:center;padding:5px 8px;background:#000;cursor:move;user-select:none}
#d14p header b{color:#ffd400}#d14p button{background:#262a33;color:#ddd;border:1px solid #444;border-radius:4px;padding:2px 7px;cursor:pointer}
#d14p button.on{border-color:#ffd400;color:#ffd400}#d14p input{width:70px;background:#262a33;color:#ddd;border:1px solid #444;border-radius:4px;padding:2px 5px}
#d14p .body{flex:1;overflow:auto;padding:6px}#d14p .info{padding:4px 6px;background:#1f232b;border-radius:5px;margin-bottom:6px}
#d14p .grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(250px,1fr));gap:6px}
#d14p .cam{position:relative}#d14p .cam span{position:absolute;left:4px;top:2px;color:#ff0;font-weight:600;text-shadow:0 0 3px #000}
#d14p svg{width:100%;display:block;background:#000;border-radius:4px}
#d14p .list{margin-top:6px;columns:2;font-size:11px}#d14p .list div{cursor:pointer;padding:1px 3px;border-radius:3px;break-inside:avoid}
#d14p .list div:hover{background:#2a2f3a}#d14p .err{color:#ff7b7b}`;
  const panel = document.createElement('div');
  panel.id = 'd14p';
  panel.innerHTML = `<style>${css}
#d14p .bar{display:flex;gap:6px;align-items:center;padding:5px 8px;background:#1b1e25;flex-wrap:wrap}
#d14p select{flex:1;min-width:160px;background:#262a33;color:#ddd;border:1px solid #444;border-radius:4px;padding:3px}
#d14p .big{font-size:14px;padding:3px 12px}
#d14p.pop{position:static;width:auto!important;height:100vh!important;border:0;border-radius:0;resize:none;box-shadow:none}
#d14p.pop header{cursor:default}</style>
   <header><b>D14 camera</b><span id="d14f"></span><span style="flex:1"></span>
   <button id="d14r" title="Tai lai tu CVAT (sau khi Save)">&#x21bb; Tai lai</button><button id="d14m" title="Thu nho / mo rong">_</button></header>
   <div class="bar"><button id="d14prev" class="big" title="Hop truoc">&#9664;</button><select id="d14s"></select>
   <button id="d14next" class="big" title="Hop sau">&#9654;</button>
   <button id="d14all" class="on">Tat ca cam</button><button id="d14foc">Phong to hop</button>
   <input id="d14q" placeholder="go pp_id"></div>
   <div class="body"><div class="info" id="d14i">Dang cho...</div><div class="grid" id="d14g"></div><div class="list" id="d14l"></div></div>`;
  const $ = (id) => panel.querySelector('#' + id);

  // Mac dinh: bang nam trong CUA SO RIENG (khong che CVAT, CVAT khong chan thao tac). Nut nho o goc trai duoi de mo.
  const launcher = document.createElement('button');
  launcher.textContent = '\u{1F4F7} D14 camera';
  launcher.title = 'Mo bang camera trong cua so rieng';
  launcher.style.cssText = 'position:fixed;left:70px;bottom:8px;z-index:99999;background:#000;color:#ffd400;border:1px solid #ffd400;' +
    'border-radius:6px;padding:6px 12px;font:600 13px Segoe UI,Arial;cursor:pointer;box-shadow:0 2px 8px #0008';
  let popup = null;
  function openPopup() {
    popup = window.open('', 'd14cam', 'width=1050,height=880');
    if (!popup) { alert('Trinh duyet chan cua so bat len. Cho phep popup cho localhost:8080 roi bam lai.'); return; }
    const d = popup.document;
    d.title = 'D14 camera';
    d.body.style.cssText = 'margin:0;background:#14161b';
    panel.classList.add('pop');
    panel.classList.remove('min');
    d.body.innerHTML = '';
    d.body.appendChild(d.adoptNode(panel));
    S.data = null; refresh(true);
  }
  launcher.onclick = openPopup;
  const popped = () => popup && !popup.closed;

  function mount() {
    if (!document.body.contains(launcher)) document.body.appendChild(launcher);
    launcher.style.display = popped() ? 'none' : '';
  }
  (function drag() {
    let sx, sy, ox, oy;
    panel.addEventListener('mousedown', (e) => {
      if (e.target.closest('header') && !e.target.closest('button,input')) {
        sx = e.clientX; sy = e.clientY; const r = panel.getBoundingClientRect(); ox = r.left; oy = r.top;
        const mv = (ev) => { panel.style.left = ox + ev.clientX - sx + 'px'; panel.style.top = oy + ev.clientY - sy + 'px'; panel.style.right = 'auto'; };
        const up = () => { document.removeEventListener('mousemove', mv); document.removeEventListener('mouseup', up); };
        document.addEventListener('mousemove', mv); document.addEventListener('mouseup', up);
      }
    });
  })();
  ['keydown', 'keyup', 'keypress', 'wheel', 'contextmenu'].forEach((t) => panel.addEventListener(t, (e) => e.stopPropagation()));
  $('d14m').onclick = () => panel.classList.toggle('min');
  $('d14all').onclick = () => { S.mode = 'all'; render(); };
  $('d14foc').onclick = () => { if (S.sel == null) step(1); S.mode = 'focus'; render(); };
  $('d14r').onclick = () => refresh(true);
  $('d14q').onkeydown = (e) => { if (e.key === 'Enter') { select(e.target.value.trim(), true); } };
  $('d14prev').onclick = () => step(-1);
  $('d14next').onclick = () => step(1);
  $('d14s').onchange = (e) => { if (e.target.value) select(e.target.value, true); };
  const ordered = () => (S.data ? S.data.boxes.slice().sort((a, b) => a.sev - b.sev || a.dist - b.dist) : []);
  function step(dir) {
    const list = ordered(); if (!list.length) return;
    const i = list.findIndex((b) => b.id === S.sel);
    const n = i < 0 ? (dir > 0 ? 0 : list.length - 1) : (i + dir + list.length) % list.length;
    choose(list[n].id, true);
  }

  // ---------------------------------------------------------------- CVAT API (chi doc)
  const api = async (path) => {
    const r = await fetch(path, { credentials: 'include' });
    if (!r.ok) throw new Error(`${path}: HTTP ${r.status}`);
    return r.json();
  };
  async function loadJob(job) {
    S.job = job; S.meta = null; S.specs = null; S.data = null; S.frame = null;
    S.meta = await api(`/api/jobs/${job}/data/meta`);
    const labels = [];
    let url = `/api/labels?job_id=${job}&page_size=100`;
    while (url) { const p = await api(url); labels.push(...p.results); url = p.next ? p.next.replace(/^https?:\/\/[^/]+/, '') : null; }
    S.specs = {};
    for (const l of labels) S.specs[l.id] = { name: l.name, attrs: Object.fromEntries((l.attributes || []).map((a) => [a.id, a.name])) };
  }
  const frameNames = () => (S.meta.frames || []).map((f) => (f.name.match(/s\d{2}f\d{2}/) || [''])[0]);

  let nameEl = null; // phan tu hien "pointcloud/sNNfNN.pcd" duoi thanh frame cua CVAT (tim 1 lan, giu lai)
  function currentFrameName() {
    const re = /(s\d{2}f\d{2})\.pcd/;
    if (!(nameEl && nameEl.isConnected && re.test(nameEl.textContent))) {
      nameEl = null;
      for (const el of document.querySelectorAll('span,div,p')) {
        if (el.children.length === 0 && re.test(el.textContent) && el.textContent.length < 80) { nameEl = el; break; }
      }
    }
    const m = nameEl && nameEl.textContent.match(re);
    return m ? m[1] : null;
  }

  async function refresh(force) {
    const jm = location.pathname.match(/\/tasks\/\d+\/jobs\/(\d+)/);
    if (!jm) { launcher.remove(); return; }
    mount();
    if (!popped()) return; // cua so camera chua mo: khong lam gi, CVAT khong bi nang
    if (S.busy) return;
    S.busy = true;
    try {
      const job = Number(jm[1]);
      if (S.job !== job || !S.meta) await loadJob(job);
      const name = currentFrameName();
      if (!name) { info('Chua doc duoc ten frame (sNNfNN.pcd).'); return; }
      if (!force && name === S.frame && S.data) return;
      S.frame = name;
      $('d14f').textContent = name;
      const names = frameNames();
      const idx = names.indexOf(name) + (S.meta.start_frame || 0);
      const ann = await api(`/api/jobs/${job}/annotations`);
      const shapes = (ann.shapes || []).filter((s) => s.frame === idx && s.type === 'cuboid').map((s) => {
        const sp = S.specs[s.label_id] || { name: '?', attrs: {} };
        const av = Object.fromEntries((s.attributes || []).map((a) => [sp.attrs[a.spec_id], a.value]));
        return { id: s.id, label: sp.name, points: s.points, pp_id: av.pp_id || '', score: av.score || '' };
      });
      const r = await fetch(SERVER + '/project', { method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ frame: name, shapes }) });
      const d = await r.json();
      if (d.error) throw new Error(d.error);
      S.data = d; S.err = ''; S.order = shapes.map((s) => s.id);
      render();
    } catch (e) {
      S.err = String(e.message || e).includes('Failed to fetch')
        ? 'Khong ket noi duoc camera server. Chay: python tools/d14_camserver.py --data "<Data-VF>"'
        : String(e.message || e);
      info(`<span class="err">${S.err}</span>`);
    } finally { S.busy = false; }
  }

  // ---------------------------------------------------------------- chon hop
  const keyOf = (b) => (b.pp_id !== '' ? String(b.pp_id) : 'moi' + b.id);
  function select(k, manual) {
    if (!S.data) return;
    const b = S.data.boxes.find((x) => keyOf(x) === k || String(x.pp_id) === k);
    choose(b ? b.id : null, manual);
  }
  function choose(id, manual) {
    S.sel = id;
    if (manual && id != null) S.mode = 'focus';
    render();
    if (manual && id != null) pushToCvat(id);
  }

  // ---- noi voi sidebar Objects cua CVAT.
  // CVAT danh so object (clientID) theo thu tu nap tu server; hop cung frame tren sidebar (sap theo clientID)
  // tuong ung 1-1 voi danh sach shape server (cung thu tu) mien la da Save va khong con thay doi chua luu.
  const ITEM = 'cvat-objects-sidebar-state-item-';
  function uiItems() {
    return Array.from(document.querySelectorAll(`[id^="${ITEM}"]`))
      .map((el) => ({ el, cid: Number(el.id.slice(ITEM.length)) }))
      .filter((x) => Number.isFinite(x.cid)).sort((a, b) => a.cid - b.cid);
  }
  function mapping() {
    const items = uiItems(); const order = S.order || [];
    if (!S.data || !items.length || items.length < order.length) return null; // CVAT co it hon: con thay doi chua Save
    const byId = new Map(), byCid = new Map();
    order.forEach((sid, i) => {
      const box = S.data.boxes.find((b) => b.id === sid);
      const it = items[i];
      if (box && it && (it.el.textContent || '').includes(box.label)) { byId.set(sid, it); byCid.set(it.cid, sid); }
    });
    return { byId, byCid };
  }
  let pushedCid = null;
  function pushToCvat(sid) {
    const m = mapping();
    const it = m && m.byId.get(sid);
    if (!it) { info('<span class="err">Chua chon duoc tren CVAT: bam Save tren CVAT roi bam &#x21bb; Tai lai.</span>'); return; }
    pushedCid = it.cid;
    it.el.scrollIntoView({ block: 'center' });
    // CVAT 2.8x: o object tren sidebar kich hoat bang mousedown (nut trai, khong phim phu) hoac mouseenter,
    // nhap dup = "focus and expand" (dua khung nhin toi object, mo DETAILS).
    const r = it.el.getBoundingClientRect();
    const opts = { bubbles: true, cancelable: true, view: window, button: 0, buttons: 1,
      clientX: r.left + 8, clientY: r.top + 8, relatedTarget: document.body };
    it.el.dispatchEvent(new MouseEvent('mouseover', opts));
    it.el.dispatchEvent(new MouseEvent('mousedown', opts));
    it.el.dispatchEvent(new MouseEvent('mouseup', { ...opts, buttons: 0 }));
    it.el.dispatchEvent(new MouseEvent('dblclick', { ...opts, buttons: 0, detail: 2 }));
    setTimeout(() => {
      const on = it.el.classList.contains('cvat-objects-sidebar-state-active-item');
      const msg = `[chan doan] sidebar ${uiItems().length} o, server ${(S.order || []).length} hop, ghep ${m.byId.size}; ` +
        `gui toi o #${it.cid} (${it.el.className.slice(0, 60)}); sau 0.4s: ${on ? 'DA KICH HOAT' : 'CHUA kich hoat'}`;
      console.log('D14', msg, it.el);
      $('d14i').insertAdjacentHTML('beforeend', `<br><span style="color:#8cf">${msg}</span>`);
    }, 400);
  }
  function activeServerId() {
    const act = Array.from(document.querySelectorAll('.cvat-objects-sidebar-state-active-item'))
      .find((el) => el.id && el.id.startsWith(ITEM));
    if (!act) return null;
    const cid = Number(act.id.slice(ITEM.length));
    const m = mapping();
    return m && m.byCid.has(cid) ? { cid, sid: m.byCid.get(cid) } : null;
  }

  // ---------------------------------------------------------------- ve
  function info(html) { $('d14i').innerHTML = html; }
  function render() {
    $('d14all').classList.toggle('on', S.mode === 'all');
    $('d14foc').classList.toggle('on', S.mode === 'focus');
    const d = S.data; if (!d) return;
    const sel = d.boxes.find((b) => b.id === S.sel);
    const mp = mapping();
    const cvatNo = (b) => { const it = mp && mp.byId.get(b.id); return it ? it.cid : null; };
    S.cvatNo = cvatNo;
    const selNo = sel ? cvatNo(sel) : null;
    info(sel
      ? `<span style="font-size:18px;color:#0ff;font-weight:700">Tren CVAT: object so ${selNo ?? '? (Save + F5 CVAT)'}</span>` +
        ` &nbsp;(pp_id <b style="color:#ffd400">${keyOf(sel)}</b>)<br>${sel.label} &middot; cach ${sel.dist} m &middot; ${sel.dims} &middot; ${sel.npts} diem<br>${sel.hint}`
      : `${d.boxes.length} hop da Save o frame nay. Chon hop o sidebar CVAT, bam ten hop ben duoi, hoac go pp_id. Hop moi ve: Save roi bam &#x21bb;.`);
    const g = $('d14g'); g.innerHTML = '';
    for (const c of d.cams) {
      const mine = c.boxes.find((b) => b.id === S.sel);
      if (S.mode === 'focus' && sel && !mine) continue;
      let vb = null;
      if (S.mode === 'focus' && mine) {
        const pts = mine.lines.flat();
        const us = pts.map((p) => p[0]), vs = pts.map((p) => p[1]);
        const u0 = Math.min(...us), u1 = Math.max(...us), v0 = Math.min(...vs), v1 = Math.max(...vs);
        const w = Math.max((u1 - u0) * 2.4, 260), h = Math.max((v1 - v0) * 2.4, 170);
        vb = [(u0 + u1) / 2 - w / 2, (v0 + v1) / 2 - h / 2, w, h];
      }
      const div = document.createElement('div'); div.className = 'cam';
      const ns = 'http://www.w3.org/2000/svg';
      const svg = document.createElementNS(ns, 'svg');
      const img = document.createElementNS(ns, 'image');
      img.setAttribute('href', SERVER + c.url);
      img.setAttribute('x', 0); img.setAttribute('y', 0);
      svg.appendChild(img);
      const probe = new Image();
      probe.onload = () => {
        img.setAttribute('width', probe.naturalWidth); img.setAttribute('height', probe.naturalHeight);
        svg.setAttribute('viewBox', (vb || [0, 0, probe.naturalWidth, probe.naturalHeight]).join(' '));
      };
      probe.src = SERVER + c.url;
      for (const b of c.boxes) {
        const box = d.boxes.find((x) => x.id === b.id); const on = b.id === S.sel;
        const col = on ? '#ffd400' : (COLORS[box.label] || '#fff');
        for (const ln of b.lines) {
          const pl = document.createElementNS(ns, 'polyline');
          pl.setAttribute('points', ln.map((p) => p.join(',')).join(' '));
          pl.setAttribute('fill', 'none'); pl.setAttribute('stroke', col);
          pl.setAttribute('stroke-width', on ? 4 : 1.6); pl.setAttribute('vector-effect', 'non-scaling-stroke');
          svg.appendChild(pl);
        }
        const top = b.lines.flat().reduce((a, p) => (p[1] < a[1] ? p : a), [0, 1e9]);
        const t = document.createElementNS(ns, 'text');
        t.setAttribute('x', top[0] + 3); t.setAttribute('y', top[1] - 4); t.setAttribute('fill', col);
        t.setAttribute('font-size', vb ? Math.max(vb[2] / 28, 8) : 22); t.setAttribute('font-weight', 700);
        t.setAttribute('style', 'cursor:pointer;paint-order:stroke;stroke:#000;stroke-width:3px');
        { const no = S.cvatNo && S.cvatNo(box); t.textContent = no != null ? String(no) : keyOf(box); }
        svg.appendChild(t);
      }
      // bam vao bat ky dau trong hop (khung bao 2D) de chon; hop nho nhat chua diem bam duoc uu tien
      svg.style.cursor = 'pointer';
      svg.addEventListener('click', (ev) => {
        const m = svg.getScreenCTM(); if (!m) return;
        const p = svg.createSVGPoint(); p.x = ev.clientX; p.y = ev.clientY;
        const q = p.matrixTransform(m.inverse());
        let best = null;
        for (const b of c.boxes) {
          const pts = b.lines.flat(); const us = pts.map((z) => z[0]), vs = pts.map((z) => z[1]);
          const u0 = Math.min(...us) - 6, u1 = Math.max(...us) + 6, v0 = Math.min(...vs) - 6, v1 = Math.max(...vs) + 6;
          if (q.x >= u0 && q.x <= u1 && q.y >= v0 && q.y <= v1) {
            const area = (u1 - u0) * (v1 - v0);
            if (!best || area < best.area) best = { id: b.id, area };
          }
        }
        if (best) choose(best.id, true);
      });
      div.appendChild(svg);
      const lab = document.createElement('span'); lab.textContent = c.cam; div.appendChild(lab);
      g.appendChild(div);
    }
    if (S.mode === 'focus' && sel && !g.children.length) g.innerHTML = '<div class="info">Khong camera nao thay hop nay.</div>';
    const ord = ordered();
    $('d14s').innerHTML = '<option value="">-- chon hop (' + ord.length + ') --</option>' + ord.map((b) =>
      `<option value="${keyOf(b)}" ${b.id === S.sel ? 'selected' : ''}>[CVAT ${cvatNo(b) ?? '?'}] pp ${keyOf(b)} ${b.label} ${b.dist}m - ${b.hint}</option>`).join('');
    $('d14l').innerHTML = ord
      .map((b) => `<div data-k="${keyOf(b)}" style="color:${b.id === S.sel ? '#ffd400' : (COLORS[b.label] || '#ddd')}">${keyOf(b)} ${b.label} ${b.dist}m &middot; ${b.hint}</div>`).join('');
    $('d14l').querySelectorAll('div').forEach((el) => { el.onclick = () => select(el.dataset.k, true); });
  }

  // ---------------------------------------------------------------- vong lap
  let lastCid = null;
  setInterval(() => {
    refresh(false);
    if (!popped()) return;
    const a = activeServerId(); // ban chon object tren CVAT -> bang camera to vang hop do
    if (a && a.cid !== lastCid) { lastCid = a.cid; if (a.cid !== pushedCid && a.sid !== S.sel) choose(a.sid, false); pushedCid = null; }
  }, 700);
  document.addEventListener('keydown', (e) => { if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 's') setTimeout(() => refresh(true), 1800); }, true);
  document.addEventListener('click', (e) => {
    const b = e.target && e.target.closest ? e.target.closest('button,[role="button"]') : null;
    if (b && /save/i.test(b.textContent || '')) setTimeout(() => refresh(true), 1800);
  }, true);
  window.addEventListener('beforeunload', () => { if (popped()) popup.close(); });
})();
