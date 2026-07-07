/* 见微 · 外壳：路由、导航、主题、详情打开策略（抽屉 vs 右栏） */
import { api } from './api.js';
import { closeSheet, detailContent, initSheet, openSheet, toast } from './components.js';
import { fmtDateCN, h } from './util.js';
import * as today from './views/today.js';
import * as feed from './views/feed.js';
import * as chat from './views/chat.js';
import * as insight from './views/insight.js';
import * as me from './views/me.js';

const ICONS = {
  today: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/></svg>',
  feed: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-linecap="round" stroke-linejoin="round"><path d="M4 11a9 9 0 0 1 9 9"/><path d="M4 4a16 16 0 0 1 16 16"/><circle cx="5" cy="19" r="1.6" fill="currentColor" stroke="none"/></svg>',
  insight: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-linecap="round" stroke-linejoin="round"><path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12z"/><circle cx="12" cy="12" r="3"/></svg>',
  me: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="8" r="4"/><path d="M4 21c0-4 3.6-6.5 8-6.5s8 2.5 8 6.5"/></svg>',
};

const VIEWS = [
  { id: 'today', label: '今日', mod: today },
  { id: 'feed', label: '情报', mod: feed },
  { id: 'chat', label: '问', mod: chat, ask: true },
  { id: 'insight', label: '洞察', mod: insight },
  { id: 'me', label: '我的', mod: me },
];

let current = null;
let cleanup = null;
let feedDetailPane = null;

const ctx = {
  lensNames: {},
  openItem,
  openEntity,
  setFeedDetailPane: (el) => { feedDetailPane = el; },
};

/* ── 主题 ── */
window.__applyTheme = () => {
  const pref = localStorage.getItem('theme') || 'auto';
  const dark = pref === 'dark' || (pref === 'auto' && matchMedia('(prefers-color-scheme: dark)').matches);
  document.documentElement.dataset.theme = dark ? 'dark' : 'light';
  document.querySelector('meta[name=theme-color]')?.setAttribute('content', dark ? '#0a0c10' : '#f5f3ee');
};

/* ── 详情打开 ── */
async function openItem(id) {
  try {
    const d = await api.item(id);
    if (!d.user?.read) api.feedback(id, 'read').catch(() => {});
    const content = detailContent(d, { lensNames: ctx.lensNames, onOpenItem: openItem, onOpenEntity: openEntityByName });
    const desktop = matchMedia('(min-width: 1024px)').matches;
    if (desktop && current === 'feed' && feedDetailPane) {
      feedDetailPane.replaceChildren(content);
      feedDetailPane.scrollTop = 0;
    } else {
      openSheet(content);
    }
  } catch (e) {
    toast('加载条目失败：' + e.message);
  }
}

async function openEntity(entityId) {
  try {
    const { entity, items } = await api.entityTimeline(entityId);
    const list = h('div', {},
      h('div', { class: 'detail-title', style: 'font-size:17px' }, `${entity.name} · 时间线`),
      h('div', { style: 'margin-bottom:10px' },
        h('button', {
          class: 'chip chip-btn' + (entity.watch ? ' active' : ''),
          onclick: async (e) => {
            const w = !entity.watch;
            await api.watchEntity(entity.id, w);
            entity.watch = w;
            e.currentTarget.classList.toggle('active', w);
            toast(w ? '已关注' : '已取消关注');
          },
        }, entity.watch ? '✓ 已关注' : '＋ 关注')),
      items.length
        ? items.map((it) => h('div', { class: 'lineage-entry', onclick: () => openItem(it.id) },
            h('span', { class: 'dt' }, it.published_at),
            h('span', {}, it.title)))
        : h('p', { class: 'muted' }, '暂无相关条目'));
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
    toast(`已创建并关注「${name}」`);
    return openEntity(created.id);
  } catch (e) {
    toast(e.message);
  }
}

/* ── 路由 ── */
function navigate(viewId, { push = true } = {}) {
  const view = VIEWS.find((v) => v.id === viewId) || VIEWS[0];
  if (current === view.id) return;
  cleanup?.();
  cleanup = null;
  closeSheet(true);
  current = view.id;
  if (push) location.hash = `#/${view.id}`;

  document.querySelectorAll('[data-nav]').forEach((el) => {
    el.classList.toggle('active', el.dataset.nav === view.id);
  });
  document.getElementById('top-title').textContent = view.label === '问' ? '问 · 情报分析师' : view.label;

  const container = document.getElementById('view');
  container.className = '';
  container.id = 'view';
  container.replaceChildren();
  const ret = view.mod.render(container, ctx);
  if (typeof ret === 'function') cleanup = ret;
  window.scrollTo(0, 0);
}

function buildNav() {
  const tabbar = document.getElementById('tabbar');
  const sidenav = document.getElementById('side-nav');
  for (const v of VIEWS) {
    if (v.ask) {
      tabbar.append(h('button', { class: 'tab tab-ask', 'data-nav': v.id, onclick: () => navigate(v.id) },
        h('span', { class: 'ask-btn' }, '问')));
    } else {
      tabbar.append(h('button', { class: 'tab', 'data-nav': v.id, onclick: () => navigate(v.id) },
        h('span', { html: ICONS[v.id] || '' }), v.label));
    }
    sidenav.append(h('button', { class: 'nav-item', 'data-nav': v.id, onclick: () => navigate(v.id) },
      v.ask ? h('span', { class: 'brand-seal', style: 'width:19px;height:19px;font-size:11px;border-radius:5px' }, '问')
            : h('span', { html: ICONS[v.id] || '' }),
      v.label === '问' ? '问 · 分析师' : v.label));
  }
}

async function loadSidebarFoot() {
  try {
    const s = await api.status();
    const dot = document.getElementById('health-dot');
    const down = s.sources.down || 0;
    dot.className = 'health-dot' + (down > 1 ? ' bad' : (s.sources.degraded || down ? ' warn' : ''));
    dot.title = `情报源：正常${s.sources.ok} 异常${(s.sources.degraded || 0) + down}`;
    const foot = document.getElementById('side-foot');
    if (foot) {
      foot.replaceChildren(
        h('div', { class: 'row' }, h('span', {}, '今日新增'), h('span', { class: 'mono' }, String(s.items.new_today))),
        h('div', { class: 'row' }, h('span', {}, '本月费用'), h('span', { class: 'mono' }, `¥${s.llm.cost_month}`)),
        h('div', { class: 'row' }, h('span', {}, '情报源'), h('span', { class: 'mono' }, `${s.sources.ok}✓ ${(s.sources.degraded || 0) + (s.sources.down || 0)}⚠`)));
    }
  } catch { /* 静默 */ }
}

async function boot() {
  window.__applyTheme();
  matchMedia('(prefers-color-scheme: dark)').addEventListener('change', window.__applyTheme);
  initSheet();
  buildNav();
  document.getElementById('top-date').textContent = fmtDateCN();

  try {
    const p = await api.profile();
    for (const l of p.lenses) ctx.lensNames[l.id] = l.name;
  } catch { /* 首屏容错 */ }

  const start = (location.hash.match(/^#\/(\w+)/) || [])[1];
  navigate(VIEWS.some((v) => v.id === start) ? start : 'today', { push: false });
  window.addEventListener('hashchange', () => {
    const id = (location.hash.match(/^#\/(\w+)/) || [])[1];
    if (id && id !== current) navigate(id, { push: false });
  });

  loadSidebarFoot();
  setInterval(loadSidebarFoot, 120000);
}

boot();
