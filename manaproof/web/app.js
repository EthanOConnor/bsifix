/* Manaproof UI — dependency-free. */
'use strict';
const $ = (s, r = document) => r.querySelector(s);
function h(tag, attrs, ...kids) {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v == null || v === false) continue;
    if (k === 'class') e.className = v;
    else if (k === 'html') e.innerHTML = v;
    else if (k.startsWith('on')) e.addEventListener(k.slice(2), v);
    else if (k === 'style' && typeof v === 'object') Object.assign(e.style, v);
    else if (k in e && k !== 'list') e[k] = v;
    else e.setAttribute(k, v);
  }
  for (const k of kids.flat(9)) if (k != null && k !== false) e.append(k.nodeType ? k : document.createTextNode(k));
  return e;
}
function fill(el, ...kids) { el.replaceChildren(...kids.flat(9).filter(k => k != null && k !== false)); }
const api = (p, body) => fetch(p, body === undefined ? {} : { method: 'POST', body: JSON.stringify(body) }).then(r => r.json());
const fmt = n => (n == null ? '–' : Number(n).toLocaleString());
const esc = s => s.replace(/[&<>]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;' }[c]));
const COL = ['W', 'U', 'B', 'R', 'G', 'C'];
const ACC = ['w', 'u', 'b', 'r', 'g', 'c', 'life', 'opp', 'draw', 'mill'];
const OUT = { mana: 'Infinite mana', life: 'Infinite life', damage: 'Infinite damage', draw: 'Infinite draw', mill: 'Infinite mill', tokens: 'Infinite tokens', counters: 'Infinite counters' };
const pip = c => h('span', { class: 'm ' + c }, c);
/** Render "{G}{2}" style text with mana pips. */
function rich(text) {
  const out = []; let last = 0;
  for (const m of String(text).matchAll(/\{([WUBRGCTQ]|\d+)\}/g)) {
    out.push(text.slice(last, m.index));
    out.push(/[WUBRGC]/.test(m[1]) ? pip(m[1]) : h('span', { class: 'm N' }, m[1]));
    last = m.index + m[0].length;
  }
  out.push(text.slice(last));
  return out;
}
const colorOf = cs => cs.length === 0 ? 'var(--C)' : cs.length > 1 ? 'var(--warn)' : `var(--${COL[cs[0]]})`;

const S = { status: {}, cards: [], combos: [], log: [], byName: {}, filters: { q: '', out: new Set(), size: 0, grade: '', status: '', win: false, sort: 'found', dir: -1 }, sandbox: { cards: [], float: { c: 0 }, actions: [] } };

/* ---------- data ---------- */
let comboTimer = null;
function refreshCombos() {
  clearTimeout(comboTimer);
  comboTimer = setTimeout(async () => {
    S.combos = await api('/api/combos');
    $('#nav-combos').textContent = S.combos.length || '';
    if (['combos', 'monitor'].includes(route().tab) && !route().arg) softRender();
  }, 350);
}
function connect() {
  const es = new EventSource('/api/events');
  es.onmessage = m => {
    const ev = JSON.parse(m.data);
    if (ev.kind === 'tick') { S.status = ev.state; renderSide(); if (route().tab === 'monitor') updateMonitor(); }
    else {
      if (ev.kind === 'log') { S.log.push(ev); if (S.log.length > 500) S.log.shift(); appendLog(ev); }
      if (ev.kind === 'combo' || (ev.kind === 'verify' && ev.status !== 'checking')) refreshCombos();
    }
  };
  es.onerror = () => { es.close(); setTimeout(connect, 2000); };
}
async function poll() {
  try { S.status = await api('/api/status'); renderSide(); if (route().tab === 'monitor') updateMonitor(); } catch (e) { }
  setTimeout(poll, 2500);
}
function renderSide() {
  const s = S.status, t = s.totals || {}, k = s.kernel || {};
  const el = $('#side-status'); fill(el, 
    h('div', {}, h('span', { class: 'chip ' + (k.built ? 'ok' : 'err') }, k.built ? '⊢ kernel ready' : '⊢ kernel offline')),
    h('div', {}, h('span', { class: 'chip ' + (s.running ? 'acc' : '') }, s.running ? '● ' + (s.phase || 'running') : '○ idle')),
    h('div', {}, h('b', {}, fmt(t.combos)), ' combos · ', h('b', {}, fmt(t.verified)), ' verified'),
    t.rejected ? h('div', { style: { color: 'var(--err)' } }, h('b', {}, t.rejected), ' rejected by kernel') : null);
}

/* ---------- routing ---------- */
function route() { const [, tab = 'monitor', arg] = location.hash.split('/'); return { tab, arg: arg && decodeURIComponent(arg) }; }
const views = {};
function render() {
  const { tab, arg } = route();
  document.querySelectorAll('nav a').forEach(a => a.classList.toggle('on', a.dataset.tab === tab));
  const v = $('#view'); fill(v); v.scrollTop = 0;
  (views[tab] || views.monitor)(v, arg);
}
function softRender() { const { tab } = route(); if (tab === 'combos') drawComboTable(); if (tab === 'monitor') drawRecent(); }
window.addEventListener('hashchange', render);

/* ---------- shared widgets ---------- */
function statusChip(st, tactic) {
  const m = { verified: ['ok', '✓ kernel-verified'], rejected: ['err', '✗ rejected'], checking: ['warn', '… checking'], queued: ['warn', '… queued'], pending: ['warn', '… pending'], unavailable: ['', 'unverified'] }[st] || ['', st];
  return h('span', { class: 'chip ' + m[0], title: tactic || '' }, m[1]);
}
const gradeChip = g => h('span', { class: 'chip ' + (g === 'A' ? 'acc' : ''), title: g === 'A' ? 'Inductive: proved for every number of iterations' : 'Bounded: board grows; six iterations checked by the kernel' }, g === 'A' ? 'A · ∀n proof' : 'B · bounded');
const namesEl = names => h('span', { class: 'names' }, names.flatMap((n, i) => [i ? h('span', {}, '+') : null, h('b', {}, n)]));
function permEl(p) {
  const bd = [];
  if (p.ctr) bd.push(h('span', { class: 'p' }, (p.creature ? '+1/+1 ×' : 'ctr ×') + p.ctr));
  if (p.neg) bd.push(h('span', { class: 'n' }, '-1/-1 ×' + p.neg));
  if (p.token) bd.push(h('span', {}, 'token'));
  if (p.tapped) bd.push(h('span', { class: 'k' }, 'tapped'));
  if (p.sick && p.creature && !p.haste) bd.push(h('span', {}, 'sick'));
  if (p.haste) bd.push(h('span', {}, 'haste'));
  if (p.link) bd.push(h('span', {}, 'lifelink'));
  if (p.used) bd.push(h('span', {}, 'used'));
  if (p.att >= 0) bd.push(h('span', {}, '→ #' + p.att));
  return h('div', { class: 'perm' + (p.tapped ? ' tapped' : ''), style: { borderTopColor: colorOf(p.colors) } },
    h('div', { class: 'nm' }, h('span', { class: 'dim mono' }, '#' + p.i + ' '), p.name), h('div', { class: 'ty' }, p.types), h('div', { class: 'bd' }, bd));
}
function stateEl(st, prev) {
  if (!st) return h('div', { class: 'banner err' }, 'Illegal action — the engine rejected this step.');
  const a = st.acc, pa = prev && prev.acc;
  const d = k => pa && a[k] !== pa[k] ? h('span', { style: { color: a[k] > pa[k] ? 'var(--ok)' : 'var(--err)', fontSize: '11px' } }, (a[k] > pa[k] ? '+' : '') + (a[k] - pa[k])) : null;
  const mana = COL.map((c, i) => (a[ACC[i]] || (pa && pa[ACC[i]])) ? h('div', {}, pip(c), h('b', {}, a[ACC[i]]), d(ACC[i])) : null);
  return h('div', { class: 'grid' },
    h('div', { class: 'res' }, h('div', { class: 'dim' }, 'pool'), mana.some(Boolean) ? mana : h('div', { class: 'dim' }, 'empty'),
      h('div', {}, '♥', h('b', {}, a.life), d('life')), h('div', {}, '⚔ opp. lost', h('b', {}, a.opp), d('opp')),
      a.draw ? h('div', {}, 'drawn', h('b', {}, a.draw), d('draw')) : null, a.mill ? h('div', {}, 'milled', h('b', {}, a.mill), d('mill')) : null),
    h('div', { class: 'bf' }, st.bf.map(permEl)),
    st.stack.length ? h('div', {}, h('div', { class: 'small dim' }, 'STACK (top first)'),
      h('ol', { class: 'stack', style: { margin: '4px 0', paddingLeft: '20px' } }, st.stack.map(t => h('li', {}, h('b', {}, t.source), ': ', rich(t.text), t.cost ? ` — pay {${t.cost}}` : '', t.optional ? h('span', { class: 'dim' }, ' (optional)') : null)))) : null);
}
function leanHL(src) {
  return esc(src).replace(/(--[^\n]*|\/-[\s\S]*?-\/)|("(?:[^"\\]|\\.)*")|\b(theorem|def|structure|inductive|namespace|end|import|open|by|match|with|if|then|else|let|fun|deriving|instance|where|some|none|true|false)\b|\b(Nat|Bool|List|Option|Acc|State|Cfg|Card|Cert|Action|Perm|Trig|Effect|Filter|Cost|Ability)\b/g,
    (m, c, s, k, t) => c ? `<span class="cm">${c}</span>` : s ? `<span class="str">${s}</span>` : k ? `<span class="kw">${k}</span>` : `<span class="ty2">${t}</span>`);
}
const codeEl = src => h('pre', { class: 'code', html: leanHL(src) });

/* ---------- Monitor ---------- */
views.monitor = v => {
  v.append(h('h1', {}, 'Discovery monitor'),
    h('p', { class: 'sub' }, 'Untrusted search proposes loops; the Lean kernel re-executes each one and either certifies it or throws it out. Watch the pipeline run, or start a new sweep.'),
    h('div', { class: 'grid' },
      h('div', { class: 'panel' }, h('div', { class: 'row', id: 'ctl' })),
      h('div', { class: 'funnel', id: 'funnel' }),
      h('div', { class: 'panel', id: 'sizes' }),
      h('div', { class: 'two' },
        h('div', { class: 'panel' }, h('div', { class: 'row' }, h('h2', {}, 'Live feed'), h('span', { class: 'sp' }), h('span', { class: 'dim small', id: 'rate' })), h('div', { class: 'feed', id: 'feed' })),
        h('div', { class: 'grid', style: { alignContent: 'start' } },
          h('div', { class: 'panel' }, h('h2', {}, 'Throughput (sets / second)'), h('canvas', { id: 'spark', height: 90 })),
          h('div', { class: 'panel' }, h('h2', {}, 'Latest discoveries'), h('div', { id: 'recent' }))))));
  drawControls(); S.log.forEach(appendLog); updateMonitor(); drawRecent();
};
function drawControls() {
  const c = $('#ctl'); if (!c) return;
  const run = S.status.running, cfg = (S.status.cfg || {});
  const size = h('select', {}, [2, 3, 4].map(n => h('option', { value: n, selected: n === (cfg.max_size || 3) }, `up to ${n} cards`)));
  const filt = h('select', {}, h('option', { value: 1 }, 'symbolic filter on'), h('option', { value: 0 }, 'exhaustive (no filter)'));
  const nodes = h('input', { type: 'number', value: cfg.max_nodes || 2000, min: 200, max: 20000, step: 500, style: { width: '90px' } });
  const inc = h('input', { type: 'text', placeholder: 'any', list: 'cardlist', style: { width: '210px' } });
  const dl = h('datalist', { id: 'cardlist' }, S.cards.filter(c => !c.token).map(c => h('option', { value: c.name })));
  fill(c, 
    h('label', { class: 'f' }, 'Set size', size), h('label', { class: 'f' }, 'Pruning', filt),
    h('label', { class: 'f' }, 'States per set', nodes), h('label', { class: 'f' }, 'Must contain card', inc), dl, h('span', { class: 'sp' }),
    h('button', { class: 'btn', onclick: () => api('/api/verify/all', {}) }, 'Re-verify all'),
    run ? h('button', { class: 'btn danger', onclick: () => api('/api/job/stop', {}).then(() => setTimeout(drawControls, 600)) }, '■ Stop run')
      : h('button', { class: 'btn primary', onclick: async () => { await api('/api/job/start', { max_size: +size.value, use_filter: !!+filt.value, max_nodes: +nodes.value, include: inc.value ? [inc.value] : [] }); setTimeout(() => { poll0(); }, 300); } }, '▶ Start discovery'));
}
async function poll0() { S.status = await api('/api/status'); drawControls(); updateMonitor(); }
let lastRun = null;
function updateMonitor() {
  const f = $('#funnel'); if (!f) return;
  if (lastRun !== S.status.running) { lastRun = S.status.running; drawControls(); }
  const st = S.status.stats || {}, tot = S.status.totals || {};
  const base = Math.max(1, st.enumerated || 0);
  const stage = (who, label, n, frac, cls) => h('div', { class: 'stage ' + (cls || '') }, h('div', { class: 'who' }, who), h('div', { class: 'n' }, fmt(n)), h('div', { class: 'l' }, label), h('div', { class: 'bar', style: { width: Math.min(100, 100 * frac) + '%' } }));
  fill(f, 
    stage('enumerate', 'card sets', st.enumerated, 1),
    stage('symbolic', 'pass resource filter', st.passed, (st.passed || 0) / base),
    stage('search', 'sets explored', st.searched, (st.searched || 0) / Math.max(1, st.passed || 0)),
    stage('search', 'game states visited', st.nodes, 1),
    stage('novelty', 'new combos proposed', st.novel, (st.novel || 0) / Math.max(1, st.loops || 0), 'find'),
    stage('lean kernel', `verified · ${st.rejected || 0} rejected`, st.verified, (st.verified || 0) / Math.max(1, st.novel || 0), 'ok'));
  const sz = S.status.sizes || {};
  fill($('#sizes'), h('div', { class: 'row' }, h('h2', { style: { margin: 0 } }, S.status.running ? 'Run in progress' : (S.status.phase ? 'Last run: ' + S.status.phase : 'No run yet')),
    h('span', { class: 'sp' }), h('span', { class: 'dim small mono' }, S.status.elapsed != null ? `elapsed ${S.status.elapsed}s` : '')),
    Object.entries(sz).map(([k, z]) => h('div', { style: { marginTop: '10px' } },
      h('div', { class: 'row small' }, h('b', {}, `${k}-card sets`), h('span', { class: 'dim' }, `${fmt(z.searched)} / ${fmt(z.passed)} searched · ${fmt(z.enumerated - z.passed)} pruned symbolically · ${z.novel} combos`)),
      h('div', { class: 'prog', style: { marginTop: '5px' } }, h('div', { style: { width: 100 * z.searched / Math.max(1, z.passed) + '%' } })))),
    Object.keys(sz).length ? null : h('div', { class: 'dim small', style: { marginTop: '8px' } }, `Library holds ${fmt(tot.combos)} combos (${fmt(tot.verified)} kernel-verified, ${fmt(tot.inductive)} with ∀n proofs, ${fmt(tot.wins)} winning).`));
  const hist = S.status.history || [];
  $('#rate').textContent = hist.length && S.status.running ? `${hist[hist.length - 1][1]} sets/s` : '';
  const cv = $('#spark'), W = cv.clientWidth, H = 90, dpr = devicePixelRatio || 1;
  cv.width = W * dpr; cv.height = H * dpr; const g = cv.getContext('2d'); g.scale(dpr, dpr); g.clearRect(0, 0, W, H);
  if (hist.length > 1) {
    const mx = Math.max(...hist.map(p => p[1]), 1), css = getComputedStyle(document.documentElement);
    g.beginPath(); hist.forEach((p, i) => { const x = i / (hist.length - 1) * W, y = H - 6 - p[1] / mx * (H - 22); i ? g.lineTo(x, y) : g.moveTo(x, y); });
    g.strokeStyle = css.getPropertyValue('--accent'); g.lineWidth = 1.8; g.stroke();
    g.lineTo(W, H); g.lineTo(0, H); g.closePath(); g.globalAlpha = .12; g.fillStyle = css.getPropertyValue('--accent'); g.fill(); g.globalAlpha = 1;
    g.fillStyle = css.getPropertyValue('--dim'); g.font = '11px ui-monospace,monospace'; g.fillText(`peak ${mx}/s`, 6, 12);
  }
}
function appendLog(ev) {
  const f = $('#feed'); if (!f) return;
  const stick = f.scrollTop + f.clientHeight >= f.scrollHeight - 30;
  f.append(h('div', { class: ev.level }, h('span', { class: 't' }, new Date(ev.t * 1000).toLocaleTimeString()), (ev.level === 'find' ? '∞ ' : '') + ev.msg));
  while (f.children.length > 400) f.firstChild.remove();
  if (stick) f.scrollTop = f.scrollHeight;
}
function drawRecent() {
  const r = $('#recent'); if (!r) return;
  const cs = [...S.combos].sort((a, b) => b.found - a.found).slice(0, 8);
  fill(r, cs.length ? h('table', {}, cs.map(c => h('tr', { class: 'click', onclick: () => location.hash = '#/combos/' + c.id },
    h('td', {}, namesEl(c.names), h('div', { class: 'small dim' }, c.claim)), h('td', { style: { textAlign: 'right' } }, statusChip(c.status, c.tactic))))) : h('div', { class: 'empty' }, 'Nothing yet — start a discovery run.'));
}

/* ---------- Combos ---------- */
views.combos = (v, id) => {
  if (id) return comboDetail(v, id);
  const F = S.filters;
  const tog = (label, on, fn) => h('span', { class: 'chip tog' + (on ? ' on' : ''), onclick: () => { fn(); render(); } }, label);
  v.append(h('h1', {}, 'Combo library'),
    h('p', { class: 'sub' }, 'Every entry was found by search from the card programs alone and then replayed inside the Lean kernel. Supersets appear only when the extra card unlocks an outcome its subsets cannot reach.'),
    h('div', { class: 'panel', style: { marginBottom: '14px' } },
      h('div', { class: 'row' }, h('input', { type: 'text', placeholder: 'Search cards…', value: F.q, style: { width: '220px' }, oninput: e => { F.q = e.target.value; drawComboTable(); } }),
        Object.entries(OUT).map(([k, l]) => tog(l.replace('Infinite ', '∞ '), F.out.has(k), () => F.out.has(k) ? F.out.delete(k) : F.out.add(k)))),
      h('div', { class: 'row', style: { marginTop: '8px' } },
        [2, 3, 4].map(n => tog(n + ' cards', F.size === n, () => F.size = F.size === n ? 0 : n)),
        tog('∀n proofs', F.grade === 'A', () => F.grade = F.grade === 'A' ? '' : 'A'), tog('bounded', F.grade === 'B', () => F.grade = F.grade === 'B' ? '' : 'B'),
        tog('wins the game', F.win, () => F.win = !F.win), tog('✓ verified', F.status === 'verified', () => F.status = F.status === 'verified' ? '' : 'verified'),
        tog('✗ rejected', F.status === 'rejected', () => F.status = F.status === 'rejected' ? '' : 'rejected'),
        h('span', { class: 'sp' }), h('span', { class: 'dim small', id: 'count' }))),
    h('div', { class: 'panel', style: { padding: 0, overflow: 'hidden' } }, h('div', { id: 'ctable' })));
  drawComboTable();
};
function drawComboTable() {
  const el = $('#ctable'); if (!el) return;
  const F = S.filters, q = F.q.toLowerCase();
  let cs = S.combos.filter(c => (!q || c.names.join(' ').toLowerCase().includes(q)) && [...F.out].every(o => c.outcomes.includes(o)) && (!F.size || c.size === F.size) && (!F.grade || c.grade === F.grade) && (!F.win || c.win) && (!F.status || c.status === F.status));
  const key = { found: c => c.found, cards: c => c.names.join(), size: c => c.size, mv: c => c.mv, steps: c => c.steps, setup: c => c.setup_mana, claim: c => c.claim }[F.sort];
  cs.sort((a, b) => (key(a) > key(b) ? 1 : key(a) < key(b) ? -1 : 0) * F.dir);
  $('#count').textContent = `${cs.length} of ${S.combos.length}`;
  const th = (label, k) => h('th', { onclick: () => { F.dir = F.sort === k ? -F.dir : 1; F.sort = k; drawComboTable(); } }, label + (F.sort === k ? (F.dir > 0 ? ' ▲' : ' ▼') : ''));
  fill(el, cs.length ? h('table', {}, h('thead', {}, h('tr', {}, th('Cards', 'cards'), th('Result', 'claim'), th('Per iteration', 'claim'), th('Mana value', 'mv'), th('Setup mana', 'setup'), th('Loop', 'steps'), h('th', {}, 'Proof'), h('th', {}, 'Kernel'))),
    h('tbody', {}, cs.slice(0, 600).map(c => h('tr', { class: 'click', onclick: () => location.hash = '#/combos/' + c.id },
      h('td', {}, namesEl(c.names)), h('td', {}, c.outcomes.map(o => h('span', { class: 'chip ' + (o === 'damage' || o === 'mill' ? 'find' : ''), style: { marginRight: '4px' } }, OUT[o].replace('Infinite ', '∞ ')))),
      h('td', { class: 'small' }, rich(c.per_iter)), h('td', { class: 'mono' }, c.mv), h('td', { class: 'mono' }, c.setup_mana), h('td', { class: 'mono' }, c.steps + ' steps'), h('td', {}, gradeChip(c.grade)), h('td', {}, statusChip(c.status, c.tactic))))))
    : h('div', { class: 'empty' }, S.combos.length ? 'No combos match these filters.' : 'The library is empty — start a discovery run from the Monitor.'));
}
async function comboDetail(v, id) {
  const c = await api('/api/combo/' + id);
  if (c.error) return v.append(h('div', { class: 'empty' }, 'Combo not found.'));
  const vr = c.verify; let cur = 0, timer = null;
  const stepList = h('div', { class: 'steps' }), board = h('div', {});
  function show(i) {
    cur = Math.max(0, Math.min(c.frames.length - 1, i));
    stepList.querySelectorAll('.st').forEach(e => e.classList.toggle('on', +e.dataset.i === cur));
    const on = stepList.querySelector('.st.on'); if (on) on.scrollIntoView({ block: 'nearest' });
    const f = c.frames[cur];
    fill(board, h('div', { class: 'small dim', style: { marginBottom: '8px' } }, cur === 0 ? 'Starting position' : `After step ${cur} of ${c.frames.length - 1}` + (f.phase === 'loop' ? ` — loop iteration ${f.iter}` : ' — setup')), stateEl(f.state, cur ? c.frames[cur - 1].state : null));
  }
  let lastHd = '';
  c.frames.forEach((f, i) => {
    const hd = i === 0 ? '' : f.phase === 'setup' ? 'Setup' : 'Loop · iteration ' + f.iter;
    if (hd !== lastHd) { stepList.append(h('div', { class: 'hd' }, hd)); lastHd = hd; }
    stepList.append(h('div', { class: 'st', 'data-i': i, onclick: () => show(i) }, i === 0 ? 'Starting position' : [h('span', { class: 'dim mono' }, i + '. '), rich(f.action)]));
  });
  const play = h('button', { class: 'btn', onclick: () => { if (timer) { clearInterval(timer); timer = null; play.textContent = '▶ Play'; } else { play.textContent = '❚❚ Pause'; timer = setInterval(() => { if (cur >= c.frames.length - 1) show(0); else show(cur + 1); if (!document.body.contains(play)) clearInterval(timer); }, 900); } } }, '▶ Play');
  const sbx = () => { S.sandbox = { cards: c.cards.map(([k, a]) => ({ name: S.cards[k].name, att: a })), float: Object.fromEntries(ACC.map((n, i) => [n, c.float[i]])), actions: [...c.pre, ...c.loop] }; location.hash = '#/sandbox'; };
  v.append(h('div', { class: 'row' }, h('a', { href: '#/combos' }, '← Library'), h('span', { class: 'sp' }), h('button', { class: 'btn', onclick: sbx }, 'Open in sandbox'), h('button', { class: 'btn', onclick: () => api('/api/verify/' + id, {}).then(() => setTimeout(render, 2500)) }, 'Re-verify')),
    h('h1', { style: { marginTop: '10px' } }, c.claim), h('div', { class: 'row', style: { margin: '6px 0 16px' } }, statusChip(vr.status, vr.tactic), gradeChip(c.grade), c.win ? h('span', { class: 'chip find' }, 'wins the game') : null, h('span', { class: 'dim small' }, vr.tactic ? `checked by ${vr.tactic} in ${vr.seconds}s` : '')),
    h('div', { class: 'cards', style: { marginBottom: '14px' } }, c.cards.map(([k, a], i) => cardTile(S.cards[k], a >= 0 ? `attached to ${c.names[c.cards.findIndex((x, j) => j === a)] || '#' + a}` : null))),
    h('div', { class: 'two' },
      h('div', { class: 'grid', style: { alignContent: 'start' } },
        h('div', { class: 'panel' }, h('h2', {}, 'What is proved'),
          h('dl', { class: 'kv' }, h('dt', {}, 'Starts with'), h('dd', {}, 'the cards above on the battlefield, untapped', c.setup_mana ? [' and ', rich(c.requires), ' floating'] : ''),
            h('dt', {}, 'Each iteration'), h('dd', {}, rich(c.grade === 'A' ? c.delta_text : (c.per_iter || 'board grows'))),
            h('dt', {}, 'Guarantee'), h('dd', {}, c.grade === 'A' ? 'After the loop the board is identical and no resource is lower, so by the pumping theorem it can be repeated n times for every n.' : `The board grows every iteration, so it never repeats; the kernel checked ${6} consecutive iterations by evaluation.`),
            h('dt', {}, 'Trace'), h('dd', {}, `${c.pre.length} setup steps, ${c.loop.length} loop steps`),
            c.extends_full.length ? [h('dt', {}, 'Builds on'), h('dd', {}, c.extends_full.map(x => h('div', {}, h('a', { href: '#/combos/' + x.id }, x.names.join(' + ')), h('span', { class: 'dim' }, ' — ' + x.claim))))] : null)),
        vr.status === 'rejected' ? h('div', { class: 'banner err' }, h('b', {}, 'The kernel rejected this certificate. '), 'The fast engine and the formal semantics disagree — that is a bug the differential check just caught.', h('pre', { class: 'code', style: { marginTop: '8px' } }, vr.log)) : null,
        h('div', { class: 'panel' }, h('div', { class: 'row' }, h('h2', { style: { margin: 0 } }, 'Trace'), h('span', { class: 'sp' }), h('button', { class: 'btn', onclick: () => show(cur - 1) }, '‹'), play, h('button', { class: 'btn', onclick: () => show(cur + 1) }, '›')), stepList)),
      h('div', { class: 'grid', style: { alignContent: 'start' } },
        h('div', { class: 'panel' }, h('h2', {}, 'Board'), board),
        h('div', { class: 'panel' }, h('div', { class: 'row' }, h('h2', { style: { margin: 0 } }, 'Lean certificate'), h('span', { class: 'sp' }), h('button', { class: 'btn', onclick: e => { navigator.clipboard.writeText(c.lean); e.target.textContent = 'Copied'; } }, 'Copy')), h('div', { style: { marginTop: '10px' } }, codeEl(c.lean))))));
  show(0);
}

/* ---------- Cards ---------- */
function cardTile(c, extra) {
  return h('div', { class: 'card', style: { borderTopColor: colorOf(c.colors) }, onclick: () => location.hash = '#/cards/' + encodeURIComponent(c.name) },
    h('div', { class: 'nm' }, c.name, h('small', {}, c.pt ? c.pt.join('/') : '')), h('div', { class: 'ty' }, c.types + (c.token ? ' · token' : ` · MV ${c.mv}`)), h('div', { class: 'tx' }, rich(c.text)), extra ? h('div', { class: 'small', style: { color: 'var(--warn)', marginTop: '4px' } }, extra) : null);
}
views.cards = (v, name) => {
  if (name) return cardDetail(v, name);
  const grid = h('div', { class: 'cards' });
  const draw = q => fill(grid, ...S.cards.filter(c => !q || (c.name + c.types + c.text).toLowerCase().includes(q.toLowerCase())).map(c => cardTile(c)));
  v.append(h('h1', {}, 'Card pool'), h('p', { class: 'sub' }, 'Each card is a program in a small typed DSL. The same definitions are compiled into the Lean kernel and the fast search engine, so there is exactly one source of truth to audit.'),
    h('div', { class: 'row', style: { marginBottom: '14px' } }, h('input', { type: 'text', placeholder: 'Filter cards…', style: { width: '260px' }, oninput: e => draw(e.target.value) }), h('span', { class: 'dim small' }, `${S.cards.filter(c => !c.token).length} cards · ${S.cards.filter(c => c.token).length} token definitions`)), grid);
  draw('');
};
function cardDetail(v, name) {
  const c = S.byName[name]; if (!c) return v.append(h('div', { class: 'empty' }, 'Unknown card.'));
  const mine = S.combos.filter(x => x.ids.includes(c.id));
  v.append(h('a', { href: '#/cards' }, '← Card pool'), h('h1', { style: { marginTop: '10px' } }, c.name), h('p', { class: 'sub' }, c.types + (c.pt ? ' · ' + c.pt.join('/') : '') + (c.token ? ' · token' : ' · mana value ' + c.mv)),
    h('div', { class: 'two' },
      h('div', { class: 'grid', style: { alignContent: 'start' } },
        h('div', { class: 'panel' }, h('h2', {}, 'Program'), c.dsl.length ? c.dsl.map(a => h('div', { style: { margin: '6px 0' } }, h('span', { class: 'chip', style: { marginRight: '8px' } }, a.kind), rich(a.text))) : h('div', { class: 'dim' }, 'No abilities.')),
        h('div', { class: 'panel' }, h('h2', {}, 'Symbolic signature'), h('div', { class: 'row' }, h('span', { class: 'dim small' }, 'produces'), c.produces.map(r => h('span', { class: 'chip ok' }, r))), h('div', { class: 'row', style: { marginTop: '8px' } }, h('span', { class: 'dim small' }, 'needs'), c.needs.length ? c.needs.map(r => h('span', { class: 'chip warn' }, r)) : h('span', { class: 'dim small' }, 'nothing'))),
        h('div', { class: 'panel' }, h('h2', {}, 'Lean term'), codeEl(c.lean))),
      h('div', { class: 'panel', style: { alignSelf: 'start' } }, h('h2', {}, `Combos using this card (${mine.length})`), mine.length ? h('table', {}, mine.map(x => h('tr', { class: 'click', onclick: () => location.hash = '#/combos/' + x.id }, h('td', {}, namesEl(x.names.filter(n => n !== c.name)), h('div', { class: 'small dim' }, x.claim)), h('td', {}, statusChip(x.status))))) : h('div', { class: 'dim' }, 'None found yet.'))));
}

/* ---------- Graph ---------- */
views.graph = async v => {
  const g = await api('/api/graph');
  const cv = h('canvas', { style: { height: '640px', cursor: 'grab' } }), info = h('div', { class: 'panel', style: { alignSelf: 'start' } });
  let mode = 'combos';
  const modeBtn = h('div', { class: 'row' });
  v.append(h('h1', {}, 'Interaction graph'), h('p', { class: 'sub' }, 'Cards as nodes. Combo edges join cards that appear together in a verified loop; resource edges show the symbolic abstraction the pre-filter reasons about (who produces what someone else needs).'),
    modeBtn, h('div', { style: { display: 'grid', gridTemplateColumns: 'minmax(0,1fr) 300px', gap: '14px', marginTop: '12px' } }, h('div', { class: 'panel', style: { padding: 0, overflow: 'hidden' } }, cv), info));
  const N = g.nodes.map((n, i) => ({ ...n, x: Math.cos(i * 2.4) * (120 + i * 3), y: Math.sin(i * 2.4) * (120 + i * 3), vx: 0, vy: 0 }));
  const idx = Object.fromEntries(N.map((n, i) => [n.id, i]));
  let sel = null, hover = null, drag = null, edges = [], sc = 1;
  const setMode = m => { mode = m; fill(modeBtn, ['combos', 'flows'].map(k => h('span', { class: 'chip tog' + (mode === k ? ' on' : ''), onclick: () => setMode(k) }, k === 'combos' ? 'Verified combo edges' : 'Symbolic resource flows')), h('span', { class: 'dim small' }, 'drag nodes · click to inspect'));
    edges = mode === 'combos' ? g.combo_edges.map(e => ({ s: idx[e.a], t: idx[e.b], w: e.pair ? 2.4 : 1, win: e.win, pair: e.pair })) : g.flows.map(e => ({ s: idx[e.a], t: idx[e.b], w: .6, r: e.r })); heat = 1; };
  let heat = 1; setMode('combos');
  const css = getComputedStyle(document.documentElement), col = n => css.getPropertyValue(n.colors.length === 0 ? '--C' : n.colors.length > 1 ? '--warn' : '--' + COL[n.colors[0]]);
  function tick() {
    if (!document.body.contains(cv)) return;
    if (heat > .02) {
      for (const a of N) for (const b of N) if (a !== b) { const dx = a.x - b.x, dy = a.y - b.y, d2 = dx * dx + dy * dy + 40; a.vx += dx / d2 * 7000 * heat; a.vy += dy / d2 * 7000 * heat; }
      const k = mode === 'combos' ? .05 : .0005, L = mode === 'combos' ? 110 : 200;
      for (const e of edges) { const a = N[e.s], b = N[e.t], dx = b.x - a.x, dy = b.y - a.y, d = Math.hypot(dx, dy) + .01, f = k * (e.pair === false ? .12 : 1) * (d - L) / d * heat; a.vx += dx * f; a.vy += dy * f; b.vx -= dx * f; b.vy -= dy * f; }
      for (const n of N) { n.vx -= n.x * .03 * heat; n.vy -= n.y * .03 * heat; if (n !== drag) { n.x += n.vx; n.y += n.vy; } n.vx *= .6; n.vy *= .6; }
      heat *= .992;
    }
    const W = cv.clientWidth, H = cv.clientHeight, dpr = devicePixelRatio || 1; cv.width = W * dpr; cv.height = H * dpr;
    const ext = N.reduce((m, n) => (mode === 'combos' && !n.combos) ? m : Math.max(m, Math.abs(n.x) / (W / 2 - 70), Math.abs(n.y) / (H / 2 - 30)), .01); sc += (Math.min(1.5, 1 / ext) - sc) * .15;
    const c = cv.getContext('2d'); c.scale(dpr, dpr); c.translate(W / 2, H / 2); c.scale(sc, sc);
    const focus = sel ?? hover, nb = new Set();
    for (const e of edges) if (e.s === focus || e.t === focus) { nb.add(e.s); nb.add(e.t); }
    for (const e of edges) { const on = focus != null && (e.s === focus || e.t === focus); if (mode === 'flows' && !on) continue;
      c.beginPath(); c.moveTo(N[e.s].x, N[e.s].y); c.lineTo(N[e.t].x, N[e.t].y); c.lineWidth = e.w * (on ? 1.6 : 1) / sc;
      c.strokeStyle = css.getPropertyValue(e.win ? '--find' : on ? '--accent' : '--line'); c.globalAlpha = focus == null || on ? (e.pair || on ? .95 : .5) : .12; c.stroke(); }
    c.globalAlpha = 1; c.font = (11 / sc) + 'px system-ui'; c.textAlign = 'center';
    N.forEach((n, i) => { if (mode === 'combos' && !n.combos) return; const r = (4.5 + Math.sqrt(n.combos) * 1.1) / sc, dimd = focus != null && !nb.has(i) && i !== focus; c.globalAlpha = dimd ? .25 : 1;
      c.beginPath(); c.arc(n.x, n.y, r, 0, 7); c.fillStyle = col(n); c.fill(); if (i === sel) { c.lineWidth = 2.5; c.strokeStyle = css.getPropertyValue('--text'); c.stroke(); }
      if (n.combos > 2 || i === focus || nb.has(i)) { c.fillStyle = css.getPropertyValue('--text'); c.fillText(n.name, n.x, n.y - r - 4); } });
    c.globalAlpha = 1; requestAnimationFrame(tick);
  }
  const at = ev => { const r = cv.getBoundingClientRect(), x = (ev.clientX - r.left - r.width / 2) / sc, y = (ev.clientY - r.top - r.height / 2) / sc; let best = null, bd = 260 / (sc * sc); N.forEach((n, i) => { if (mode === 'combos' && !n.combos) return; const d = (n.x - x) ** 2 + (n.y - y) ** 2; if (d < bd) { bd = d; best = i; } }); return [best, x, y]; };
  cv.onmousemove = ev => { const [i, x, y] = at(ev); hover = i; if (drag) { drag.x = x; drag.y = y; heat = Math.max(heat, .3); } };
  cv.onmousedown = ev => { const [i] = at(ev); if (i != null) drag = N[i]; };
  cv.onmouseup = ev => { const [i] = at(ev); drag = null; sel = i; showInfo(); };
  cv.onmouseleave = () => { hover = null; drag = null; };
  function showInfo() {
    if (sel == null) return fill(info, h('h2', {}, 'Select a card'), h('div', { class: 'dim small' }, `${N.length} cards · ${g.combo_edges.length} combo edges · ${g.flows.length} resource flows. Node size reflects how many verified combos include the card; cards in no combo are shown only in the resource-flow view.`));
    const n = N[sel], card = S.cards[n.id], mine = S.combos.filter(x => x.ids.includes(n.id));
    fill(info, h('h2', {}, h('a', { href: '#/cards/' + encodeURIComponent(n.name) }, n.name)), h('div', { class: 'small' }, rich(card.text)),
      h('div', { class: 'row', style: { margin: '10px 0 4px' } }, card.produces.map(r => h('span', { class: 'chip ok' }, '+' + r)), card.needs.map(r => h('span', { class: 'chip warn' }, '−' + r))),
      h('div', { class: 'small dim', style: { margin: '10px 0 4px' } }, `${mine.length} combos`), h('div', { style: { maxHeight: '380px', overflow: 'auto' } }, mine.map(x => h('div', { style: { margin: '6px 0' } }, h('a', { href: '#/combos/' + x.id }, x.names.filter(y => y !== n.name).join(' + ')), h('div', { class: 'small dim' }, x.claim)))));
  }
  showInfo(); tick();
};

/* ---------- Sandbox ---------- */
views.sandbox = async v => {
  const sb = S.sandbox, pick = h('input', { type: 'text', placeholder: 'Add a card…', list: 'cardlist2', style: { width: '240px' } });
  const add = () => { if (S.byName[pick.value] && sb.cards.length < 8) { sb.cards.push({ name: pick.value, att: -1 }); sb.actions = []; pick.value = ''; draw(); } };
  pick.onchange = add;
  const setupEl = h('div', {}), playEl = h('div', {}), searchEl = h('div', {});
  v.append(h('h1', {}, 'Sandbox'), h('p', { class: 'sub' }, 'Put cards on the battlefield and drive the same interpreter the search uses. The engine lists every legal action; a banner appears the moment your line of play closes a loop.'),
    h('div', { class: 'panel', style: { marginBottom: '14px' } }, h('div', { class: 'row' }, pick, h('datalist', { id: 'cardlist2' }, S.cards.map(c => h('option', { value: c.name }))), h('button', { class: 'btn', onclick: add }, 'Add'),
      h('span', { class: 'sp' }), h('button', { class: 'btn', onclick: () => { sb.cards = []; sb.actions = []; fill(searchEl, ); draw(); } }, 'Clear'), h('button', { class: 'btn primary', onclick: runSearch }, '⌕ Search this set for loops')), setupEl, searchEl), playEl);
  async function runSearch() {
    fill(searchEl, h('div', { class: 'dim', style: { marginTop: '10px' } }, 'Searching…'));
    const r = await api('/api/sandbox/search', { cards: sb.cards });
    if (r.error) return fill(searchEl, h('div', { class: 'banner err', style: { marginTop: '10px' } }, r.error));
    fill(searchEl, h('div', { class: 'small dim', style: { margin: '10px 0 6px' } }, `${r.results.length} loop(s) · ${fmt(r.nodes)} states in ${r.seconds}s`),
      r.results.map(x => h('div', { class: 'row', style: { margin: '4px 0' } }, gradeChip(x.grade), h('b', {}, x.claim), h('span', { class: 'dim small' }, rich(x.gain)), h('span', { class: 'dim small' }, `${x.pre.length}+${x.loop.length} steps`),
        h('button', { class: 'btn', onclick: () => { sb.cards = x.cards; sb.float = x.float; sb.actions = [...x.pre, ...x.loop]; draw(); } }, 'Load line'))));
  }
  async function draw() {
    fill(setupEl, h('div', { class: 'row', style: { marginTop: '12px' } }, sb.cards.map((c, i) => { const cd = S.byName[c.name];
      return h('span', { class: 'chip', style: { padding: '4px 10px' } }, h('span', { class: 'dim mono' }, '#' + i), h('b', {}, c.name),
        cd.attach ? h('select', { style: { padding: '1px 4px' }, onchange: e => { c.att = +e.target.value; sb.actions = []; draw(); } }, h('option', { value: -1 }, 'unattached'), sb.cards.map((o, j) => j === i ? null : h('option', { value: j, selected: c.att === j }, '→ ' + o.name))) : null,
        h('a', { href: 'javascript:void 0', onclick: () => { sb.cards.splice(i, 1); sb.cards.forEach(x => { if (x.att === i) x.att = -1; else if (x.att > i) x.att--; }); sb.actions = []; draw(); } }, '✕')); }),
      sb.cards.length ? null : h('span', { class: 'dim' }, 'No cards yet. Try Devoted Druid + Vizier of Remedies.')),
      h('div', { class: 'row', style: { marginTop: '10px' } }, h('span', { class: 'dim small' }, 'Floating mana'), COL.map((c, i) => h('label', { class: 'row', style: { gap: '3px' } }, pip(c), h('input', { type: 'number', min: 0, max: 30, value: sb.float[ACC[i]] || 0, style: { width: '52px', padding: '3px 5px' }, onchange: e => { sb.float[ACC[i]] = +e.target.value; sb.actions = []; draw(); } })))));
    if (!sb.cards.length) return fill(playEl, );
    const r = await api('/api/sandbox', sb);
    if (r.error) return fill(playEl, h('div', { class: 'banner err' }, r.error));
    const fr = r.frames, last = fr[fr.length - 1];
    fill(playEl, h('div', { class: 'two' },
      h('div', { class: 'grid', style: { alignContent: 'start' } },
        r.loop ? h('div', { class: 'banner' }, h('b', {}, r.loop.grade === 'A' ? '∞ Loop closed. ' : '∞ Growing loop. '), `Steps ${r.loop.from + 1}–${fr.length - 1} return to ${r.loop.grade === 'A' ? 'the same board' : 'a strictly larger board'} with `, rich(r.loop.gain), ' gained.') : null,
        h('div', { class: 'panel' }, h('h2', {}, 'Board'), stateEl(last.state, fr.length > 1 ? fr[fr.length - 2].state : null)),
        h('div', { class: 'panel' }, h('div', { class: 'row' }, h('h2', { style: { margin: 0 } }, `History (${sb.actions.length})`), h('span', { class: 'sp' }), h('button', { class: 'btn', disabled: !sb.actions.length, onclick: () => { sb.actions.pop(); draw(); } }, '↶ Undo'), h('button', { class: 'btn', disabled: !sb.actions.length, onclick: () => { sb.actions = []; draw(); } }, 'Reset')),
          h('div', { class: 'steps', style: { marginTop: '8px' } }, fr.slice(1).map((f, i) => h('div', { class: 'st', onclick: () => { sb.actions = sb.actions.slice(0, i + 1); draw(); } }, h('span', { class: 'dim mono' }, (i + 1) + '. '), rich(f.action)))))),
      h('div', { class: 'panel', style: { alignSelf: 'start' } }, h('h2', {}, `Legal actions (${r.legal.length})`), r.legal.length ? h('div', { class: 'legal' }, r.legal.map(a => h('button', { class: 'btn', onclick: () => { sb.actions.push(a.a); draw(); } }, rich(a.text)))) : h('div', { class: 'dim' }, 'No legal actions in this position.'))));
  }
  draw();
};

/* ---------- Kernel ---------- */
views.kernel = async v => {
  const k = await api('/api/kernel'); let cur = 'Theorems.lean';
  const src = h('div', {}), tabs = h('div', { class: 'tabs' });
  const draw = () => { fill(tabs, k.files.map(f => h('span', { class: 'chip tog' + (f.name === cur ? ' on' : ''), onclick: () => { cur = f.name; draw(); } }, f.name, h('span', { class: 'dim' }, f.lines + ' lines')))); fill(src, codeEl(k.files.find(f => f.name === cur).source)); src.firstChild.style.maxHeight = '720px'; };
  v.append(h('h1', {}, 'Lean kernel'), h('p', { class: 'sub' }, 'The trusted core: a small-step semantics of the modelled game fragment and the theorems that turn one checked loop into a statement about every number of iterations. Everything outside this page — search, pruning, this UI — is untrusted.'),
    h('div', { class: 'two', style: { gridTemplateColumns: 'minmax(0,1fr) minmax(0,1.6fr)' } },
      h('div', { class: 'grid', style: { alignContent: 'start' } },
        h('div', { class: 'panel' }, h('h2', {}, 'Toolchain'), h('dl', { class: 'kv' }, h('dt', {}, 'Lean'), h('dd', { class: 'small' }, k.kernel.lean || 'not found'), h('dt', {}, 'Library'), h('dd', {}, h('span', { class: 'chip ' + (k.kernel.built ? 'ok' : 'err') }, k.kernel.built ? 'built — all proofs checked' : 'not built'))),
          h('div', { class: 'row', style: { marginTop: '10px' } }, h('button', { class: 'btn', onclick: e => { e.target.textContent = 'Building…'; api('/api/kernel/build', {}).then(() => setTimeout(render, 6000)); } }, 'Rebuild kernel'))),
        h('div', { class: 'panel' }, h('h2', {}, 'Trust model'), h('dl', { class: 'kv' },
          h('dt', {}, 'Trusted'), h('dd', {}, 'Lean’s kernel; the semantics in Step.lean; the card encodings in Cards.lean (hand-written translations of real cards, with stated simplifications).'),
          h('dt', {}, 'Proved'), h('dd', {}, 'Resources are a frame (step_shift); a loop that returns to the same board with no resource lower can be pumped forever (pump, checkA_sound).'),
          h('dt', {}, 'Checked per combo'), h('dd', {}, 'The exact trace, re-executed by kernel reduction (decide +kernel). No compiler or search code is trusted.'),
          h('dt', {}, 'Untrusted'), h('dd', {}, 'The Python engine, symbolic filter, loop search and acceleration. A bug there can only produce a certificate the kernel rejects.'))),
        h('div', { class: 'panel' }, h('h2', {}, `Theorems (${k.theorems.length})`), k.theorems.map(t => h('div', { style: { margin: '8px 0' } }, h('div', { class: 'mono' }, h('span', { class: 'kw' }, 'theorem '), t.name, h('span', { class: 'dim small' }, '  ' + t.file)), t.doc ? h('div', { class: 'small dim' }, t.doc) : null)))),
      h('div', { class: 'panel' }, tabs, src)));
  draw();
};

/* ---------- boot ---------- */
(async () => {
  [S.cards, S.combos, S.status] = await Promise.all([api('/api/cards'), api('/api/combos'), api('/api/status')]);
  S.cards.forEach(c => S.byName[c.name] = c);
  $('#nav-cards').textContent = S.cards.filter(c => !c.token).length; $('#nav-combos').textContent = S.combos.length || '';
  renderSide(); render(); connect(); poll();
})();
