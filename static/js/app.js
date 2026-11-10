/* 见微 · 外壳：路由、导航、主题、快捷键 */
import { api } from './api.js';
import { closeSheet, detailContent, initSheet, openSheet, sheetIsOpen, toast } from './components.js';
import { fmtDateCN, h, shanghaiToday, weekdayCN } from './util.js';
import * as today from './views/today.js';
import * as feed from './views/feed.js';
import * as chat from './views/chat.js';
import * as insight from './views/insight.js';
import * as atlas from './views/atlas.js';
import * as companies from './views/companies.js';
import * as me from './views/me.js';

const ICONS = {
  today: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/></svg>',
  feed: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-linecap="round" stroke-linejoin="round"><path d="M4 11a9 9 0 0 1 9 9"/><path d="M4 4a16 16 0 0 1 16 16"/><circle cx="5" cy="19" r="1.6" fill="currentColor" stroke="none"/></svg>',
  insight: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-linecap="round" stroke-linejoin="round"><path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12z"/><circle cx="12" cy="12" r="3"/></svg>',
  atlas: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-linecap="round" stroke-linejoin="round"><circle cx="5" cy="6" r="2.2"/><circle cx="19" cy="5" r="2.2"/><circle cx="12" cy="19" r="2.2"/><path d="M6.8 7.2 10.8 17M17.3 6.2 13.3 17.3M7 6.4 17 5.4"/></svg>',
  companies: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-linecap="round" stroke-linejoin="round"><path d="M3 21h18"/><path d="M5 21V7h6v14"/><path d="M13 21V4h6v17"/><path d="M8 10h.01M8 14h.01M16 8h.01M16 12h.01M16 16h.01"/></svg>',
  me: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="8" r="4"/><path d="M4 21c0-4 3.6-6.5 8-6.5s8 2.5 8 6.5"/></svg>',
  chat: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-linecap="round" stroke-linejoin="round"><path d="M21 12a8 8 0 0 1-8 8H7l-4 3V12a8 8 0 1 1 18 0z"/></svg>',
};

const VIEWS = [
  { id: 'today', label: '今日', mod: today },
  { id: 'feed', label: '情报', mod: feed },
  { id: 'chat', label: '问', mod: chat },
  { id: 'insight', label: '洞察', mod: insight },
  { id: 'atlas', label: '图谱', mod: atlas },
  { id: 'companies', label: '公司', mod: companies },
  { id: 'me', label: '我的', mod: me },
];
const PRIMARY = ['today', 'feed', 'chat', 'companies', 'me'];
const GO = { t: 'today', f: 'feed', q: 'chat', c: 'companies', m: 'me', i: 'insight', a: 'atlas' };

let current = null;
let currentPath = '';
let cleanup = null;
let feedDetailPane = null;
let echoHash = null;
let goArmed = false;
let goTimer = 0;

const ctx = {
  lensNames: {},
  openItem,
  openEntity,
  setFeedDetailPane: (el) => { feedDetailPane = el; },
};

function themePref() {
  return localStorage.getItem('theme') || 'auto';
}
function themeWord(pref = themePref()) {
  return { auto: '自动', dark: '暗色', light: '亮色' }[pref] || '自动';
}

window.__applyTheme = () => {
  const pref = themePref();
  const dark = pref === 'dark' || (pref === 'auto' && matchMedia('(prefers-color-scheme: dark)').matches);
  document.documentElement.dataset.theme = dark ? 'dark' : 'light';
  document.documentElement.style.colorScheme = dark ? 'dark' : 'light';
  document.querySelector('meta[name=theme-color]')?.setAttribute('content', dark ? '#12110e' : '#f4f0e6');
  document.querySelectorAll('.js-theme').forEach((el) => { el.textContent = themeWord(pref); });
  document.querySelectorAll('[data-theme-choice]').forEach((el) => {
    el.classList.toggle('active', el.dataset.themeChoice === pref);
  });
};

function cycleTheme() {
  const order = ['auto', 'light', 'dark'];
  const next = order[(order.indexOf(themePref()) + 1) % order.length];
  localStorage.setItem('theme', next);
  window.__applyTheme();
  toast(`主题：${themeWord(next)}`);
}

async function openItem(id) {
  try {
    const d = await api.item(id);
    if (!d.user?.read) api.feedback(id, 'read').catch(() => {});
    const content = detailContent(d, { lensNames: ctx.lensNames, onOpenItem: openItem, onOpenEntity: openEntityByName });
    const desktop = matchMedia('(min-width: 1024px)').matches;
    if (desktop && current === 'feed' && feedDetailPane) {
      feedDetailPane.replaceChildren(content);
      feedDetailPane.scrollTop = 0;
      feedDetailPane.querySelectorAll('.intel-card').forEach(() => {});
    } else {
      openSheet(content);
    }
  } catch (e) {
    toast('这条没打开：' + e.message);
  }
}

async function openEntity(entityId) {
  try {
    const { entity, items } = await api.entityTimeline(entityId);
    const list = h('div', {},
      h('h2', { class: 'detail-title' }, `${entity.name}`),
      h('p', { class: 'muted' }, '时间线'),
      h('div', { class: 'detail-actions' },
        h('button', {
          type: 'button',
          class: 'chip chip-btn' + (entity.watch ? ' active' : ''),
          onclick: async (e) => {
            const w = !entity.watch;
            await api.watchEntity(entity.id, w);
            entity.watch = w;
            e.currentTarget.classList.toggle('active', w);
            e.currentTarget.textContent = w ? '已关注' : '关注';
            toast(w ? '已关注' : '已取消关注');
          },
        }, entity.watch ? '已关注' : '关注')),
      items.length
        ? items.map((it) => h('div', { class: 'lineage-entry', onclick: () => openItem(it.id) },
            h('span', { class: 'dt' }, it.published_at),
            h('span', {}, it.title)))
        : h('p', { class: 'muted' }, '还没有相关条目'));
    openSheet(list);
  } catch (e) {
    toast(e.message);
  }
}

async function openEntityByName(name) {
  try {
    const { entities } = await api.entities({ q: name });
    const hit = entities.find((e) => e.name === name) || entities[0];
    if (hit) return openEntity(hit.id);
    const created = await api.createEntity({ name, kind: 'other' });
    toast(`已关注「${name}」`);
    return openEntity(created.id);
  } catch (e) {
    toast(e.message);
  }
}

function closeMore() {
  const pop = document.getElementById('more-pop');
  const btn = document.getElementById('more-toggle');
  pop?.setAttribute('hidden', '');
  btn?.setAttribute('aria-expanded', 'false');
}

function toggleMore() {
  const pop = document.getElementById('more-pop');
  const btn = document.getElementById('more-toggle');
  const open = pop.hasAttribute('hidden');
  if (open) pop.removeAttribute('hidden');
  else pop.setAttribute('hidden', '');
  btn.setAttribute('aria-expanded', open ? 'true' : 'false');
}

function setHelp(open) {
  document.getElementById('help').toggleAttribute('hidden', !open);
}

function navigate(viewId, { push = true } = {}) {
  const view = VIEWS.find((v) => v.id === viewId) || VIEWS[0];
  const hash = location.hash;
  const target = push
    ? `#/${view.id}`
    : (hash.startsWith(`#/${view.id}`) ? hash : `#/${view.id}`);
  if (current === view.id && currentPath === target) return;

  cleanup?.();
  cleanup = null;
  closeSheet(true);
  closeMore();
  current = view.id;
  currentPath = target;
  if (location.hash !== target) {
    echoHash = target;
    location.hash = target;
  }

  document.querySelectorAll('[data-nav]').forEach((el) => {
    const on = el.dataset.nav === view.id;
    el.classList.toggle('active', on);
    if (on) el.setAttribute('aria-current', 'page');
    else el.removeAttribute('aria-current');
  });
  document.getElementById('more-toggle')?.classList.toggle('active', view.id === 'insight' || view.id === 'atlas');
  document.getElementById('top-title').textContent = view.label;

  const container = document.getElementById('view');
  container.className = '';
  container.dataset.view = view.id;
  container.replaceChildren();
  container.scrollTop = 0;
  const ret = view.mod.render(container, ctx);
  if (typeof ret === 'function') cleanup = ret;
}

function buildNav() {
  const tabbar = document.getElementById('tabbar');
  const sidenav = document.getElementById('side-nav');
  for (const v of VIEWS) {
    sidenav.append(h('button', {
      type: 'button', class: 'nav-item', 'data-nav': v.id,
      onclick: () => navigate(v.id),
    }, h('span', { html: ICONS[v.id] || ICONS.chat }), v.label));
  }
  for (const id of PRIMARY) {
    const v = VIEWS.find((x) => x.id === id);
    tabbar.append(h('button', {
      type: 'button', class: 'tab', 'data-nav': v.id,
      onclick: () => navigate(v.id),
    }, h('span', { html: ICONS[v.id] || ICONS.chat }), v.label));
  }
  document.querySelectorAll('#more-pop [data-nav]').forEach((el) => {
    el.addEventListener('click', () => navigate(el.dataset.nav));
  });
}

function typingTarget(e) {
  const t = e.target;
  if (!t || !t.tagName) return false;
  return t.tagName === 'INPUT' || t.tagName === 'TEXTAREA' || t.isContentEditable;
}

function onKey(e) {
  if (e.metaKey || e.ctrlKey || e.altKey || e.isComposing) return;
  if (e.key === 'Escape') {
    const help = document.getElementById('help');
    if (help && !help.hasAttribute('hidden')) { setHelp(false); return; }
    const pop = document.getElementById('more-pop');
    if (pop && !pop.hasAttribute('hidden')) { closeMore(); return; }
    if (sheetIsOpen()) { closeSheet(); return; }
    return;
  }
  if (typingTarget(e)) return;
  if (e.key === '?') { e.preventDefault(); setHelp(true); return; }
  if (goArmed) {
    goArmed = false;
    clearTimeout(goTimer);
    const dest = GO[e.key.toLowerCase()];
    if (dest) { e.preventDefault(); navigate(dest); }
    return;
  }
  if (e.key === 'g') {
    goArmed = true;
    clearTimeout(goTimer);
    goTimer = setTimeout(() => { goArmed = false; }, 1200);
    return;
  }
  if (current === 'feed' && window.__feedKeys?.(e)) e.preventDefault();
}

async function loadSidebarFoot() {
  try {
    const s = await api.status();
    const dot = document.getElementById('health-dot');
    const down = s.sources.down || 0;
    dot.className = 'health-dot' + (down > 1 ? ' bad' : (s.sources.degraded || down ? ' warn' : ''));
    dot.title = `情报源：正常 ${s.sources.ok}，异常 ${(s.sources.degraded || 0) + down}`;
    const foot = document.getElementById('side-foot');
    if (foot) {
      foot.replaceChildren(
        h('button', { type: 'button', class: 'btn small ghost js-theme', onclick: cycleTheme }, themeWord()),
        h('div', { class: 'row' }, h('span', {}, fmtDateCN().replace(/^\d+年/, '') + ' ' + weekdayCN()), h('span', { class: 'mono' }, shanghaiToday().slice(5))),
        h('div', { class: 'row' }, h('span', {}, '今日新增'), h('span', { class: 'mono' }, String(s.items.new_today))),
        h('div', { class: 'row' }, h('span', {}, '本月费用'), h('span', { class: 'mono' }, `¥${s.llm.cost_month}`)),
        h('div', { class: 'row' }, h('span', {}, '情报源'), h('span', { class: 'mono' }, `${s.sources.ok} 正常`)));
    }
  } catch { /* 顶栏状态失败不挡阅读 */ }
}

async function boot() {
  window.__applyTheme();
  matchMedia('(prefers-color-scheme: dark)').addEventListener('change', window.__applyTheme);
  initSheet();
  buildNav();
  document.getElementById('top-date').textContent = `${fmtDateCN().slice(5)} ${weekdayCN()}`;
  document.getElementById('theme-toggle').addEventListener('click', cycleTheme);
  document.getElementById('more-toggle').addEventListener('click', (e) => { e.stopPropagation(); toggleMore(); });
  document.getElementById('help-close').addEventListener('click', () => setHelp(false));
  document.getElementById('help').addEventListener('click', (e) => { if (e.target.id === 'help') setHelp(false); });
  document.getElementById('health-dot').addEventListener('click', () => navigate('me'));
  document.getElementById('health-dot').addEventListener('keydown', (e) => {
    if (e.key === 'Enter') navigate('me');
  });
  document.addEventListener('click', (e) => {
    if (!e.target.closest('#more-pop, #more-toggle')) closeMore();
  });
  window.addEventListener('keydown', onKey);

  try {
    const p = await api.profile();
    for (const l of p.lenses) ctx.lensNames[l.id] = l.name;
  } catch { /* 首屏没有画像也不白屏 */ }

  const start = (location.hash.match(/^#\/([\w-]+)/) || [])[1];
  navigate(VIEWS.some((v) => v.id === start) ? start : 'today', { push: !start });
  window.addEventListener('hashchange', () => {
    if (echoHash && location.hash === echoHash) { echoHash = null; return; }
    echoHash = null;
    const id = (location.hash.match(/^#\/([\w-]+)/) || [])[1];
    if (id) navigate(id, { push: false });
  });

  loadSidebarFoot();
  setInterval(loadSidebarFoot, 120000);
}

boot();
