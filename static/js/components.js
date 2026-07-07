/* 共享组件：toast、抽屉/面板、情报卡片、详情渲染 */
import { api } from './api.js';
import { daysUntil, esc, h, mdRender } from './util.js';

/* ── toast ── */
let toastTimer;
export function toast(msg) {
  const el = document.getElementById('toast');
  el.textContent = msg;
  el.classList.add('show');
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => el.classList.remove('show'), 2200);
}

/* ── 抽屉（手机）/居中面板（桌面）；返回键可关 ── */
const overlay = () => document.getElementById('overlay');
const sheet = () => document.getElementById('sheet');
let sheetOpen = false;

export function openSheet(contentEl) {
  const body = sheet().querySelector('.sheet-body');
  body.replaceChildren(contentEl);
  body.scrollTop = 0;
  overlay().classList.add('show');
  sheet().classList.add('show');
  if (!sheetOpen) {
    sheetOpen = true;
    history.pushState({ sheet: true }, '');
  }
}

export function closeSheet(fromPop = false) {
  overlay().classList.remove('show');
  sheet().classList.remove('show');
  if (sheetOpen && !fromPop) history.back();
  sheetOpen = false;
}

export function initSheet() {
  overlay().addEventListener('click', () => closeSheet());
  window.addEventListener('popstate', () => { if (sheetOpen) closeSheet(true); });
  // 手机下滑关闭
  let startY = null;
  const s = sheet();
  s.querySelector('.sheet-handle').addEventListener('touchstart', (e) => { startY = e.touches[0].clientY; }, { passive: true });
  s.querySelector('.sheet-handle').addEventListener('touchmove', (e) => {
    if (startY !== null && e.touches[0].clientY - startY > 70) { startY = null; closeSheet(); }
  }, { passive: true });
}

/* ── 分级印章 ── */
const SEAL_CHAR = { red: '必', orange: '关', blue: '阅', gray: '档' };
export function sealBadge(analysis) {
  if (!analysis) return h('div', { class: 'seal-badge pending', title: '分析中' }, '…');
  const t = analysis.tier || 'gray';
  return h('div', { class: `seal-badge ${t}`, title: `综合分 ${analysis.final_score}` }, SEAL_CHAR[t] || '档');
}

/* ── 情报卡片 ── */
export function intelCard(item, { onOpen, lensNames = {} } = {}) {
  const a = item.analysis;
  const meta = [];
  meta.push(h('span', { class: 'src' }, item.source?.name || ''));
  meta.push(h('span', {}, item.published_at || ''));
  if (a?.category) meta.push(h('span', { class: 'chip', style: 'padding:1px 8px;font-size:10.5px' }, a.category));
  if (a?.deadline) {
    const d = daysUntil(a.deadline);
    if (d !== null && d >= 0) meta.push(h('span', { class: 'deadline-tag' }, `⏳${d === 0 ? '今日截止' : `${d}天后截止`}`));
  }
  const topLens = (a?.lens_scores || []).filter((s) => s.score >= 55).sort((x, y) => y.score - x.score)[0];
  if (topLens) meta.push(h('span', { class: 'lens-tag' }, `${lensNames[topLens.lens_id] || topLens.lens_id} ${topLens.score}`));
  if (item.user?.starred) meta.push(h('span', { class: 'star-mark' }, '★'));

  return h('article', { class: 'intel-card', 'data-id': item.id, onclick: () => onOpen?.(item) },
    sealBadge(a),
    h('div', { class: 'ic-body' },
      h('h3', {}, item.title),
      a?.summary ? h('p', { class: 'ic-summary' }, a.summary) : null,
      h('div', { class: 'ic-meta' }, meta)));
}

export function skeletons(n = 4) {
  return Array.from({ length: n }, () => h('div', { class: 'skeleton' }));
}

export function emptyState(glyph, text, sub) {
  return h('div', { class: 'empty' },
    h('span', { class: 'glyph' }, glyph),
    h('p', {}, text),
    sub ? h('p', { class: 'muted', style: 'margin-top:6px' }, sub) : null);
}

/* ── 详情渲染（抽屉与桌面右栏共用） ── */
const FB_DEFS = [
  ['useful', '👍', '有用'], ['irrelevant', '👎', '无关'],
  ['star', '⭐', '收藏'], ['follow_up', '🚩', '跟进'],
];

export function detailContent(d, { lensNames = {}, onOpenItem, onOpenEntity } = {}) {
  const a = d.analysis;
  const root = h('div', {});
  root.append(h('div', { class: 'detail-title' }, d.title));

  const metaRow = h('div', { class: 'detail-meta' },
    sealBadge(a),
    h('span', { class: 'chip' }, d.source?.name || ''),
    h('span', { class: 'muted mono' }, d.published_at || ''),
    a?.signal ? h('span', { class: 'chip' }, `信号·${a.signal}`) : null,
    a ? h('span', { class: 'muted mono' }, `综合 ${a.final_score}`) : null);
  root.append(metaRow);

  if (a?.summary) {
    root.append(section('AI 摘要', h('p', { class: 'detail-summary' }, a.summary)));
  } else if (d.status === 'new') {
    root.append(section('AI 摘要', h('p', { class: 'muted' }, '⏳ 等待分析（新条目会在数分钟内完成深读）')));
  }

  if (a?.action_hint) {
    root.append(h('div', { class: 'action-box', html: `<b>建议行动</b>　${esc(a.action_hint)}` }));
  }
  if (a?.deadline) {
    const days = daysUntil(a.deadline);
    root.append(h('div', { class: 'action-box', style: 'margin-top:8px' },
      h('b', {}, '⏰ 截止 '), `${a.deadline}`,
      days !== null && days >= 0 ? `（还剩 ${days} 天）` : '（已过期）'));
  }

  if (a?.lens_scores?.length) {
    const rows = a.lens_scores.slice().sort((x, y) => y.score - x.score).map((s) => {
      const row = h('div', { class: `lens-row ${s.score >= 70 ? 'hot' : ''}` },
        h('span', { class: 'name' }, lensNames[s.lens_id] || s.lens_id),
        h('div', { class: 'bar' }, h('i', { style: `width:${s.score}%` })),
        h('span', { class: 'val' }, String(s.score)));
      const frag = document.createDocumentFragment();
      frag.append(row);
      if (s.reason && s.score >= 40) frag.append(h('div', { class: 'lens-reason' }, s.reason));
      return frag;
    });
    root.append(section('对你的相关度', h('div', {}, rows)));
  }

  if (a?.policy_family) {
    root.append(section('政策脉络', h('div', { class: 'stage-track' },
      h('span', { class: 'chip jade' }, a.policy_family),
      a.policy_stage ? h('span', { class: 'stage-pill done' }, a.policy_stage) : null)));
  }

  const ents = a?.entities || [];
  if (ents.length) {
    root.append(section('涉及实体', h('div', { class: 'kw-box' },
      ents.map((e) => h('button', {
        class: 'chip chip-btn',
        onclick: () => onOpenEntity?.(e.name),
      }, e.name)))));
  }

  if (d.content_preview) {
    const p = h('p', { class: 'muted', style: 'font-size:13px;line-height:1.7;max-height:130px;overflow:hidden' }, d.content_preview);
    const more = h('button', { class: 'btn small ghost', style: 'margin-top:6px', onclick: () => { p.style.maxHeight = 'none'; more.remove(); } }, '展开全文');
    root.append(section('原文节选', h('div', {}, p, d.content_preview.length > 200 ? more : null)));
  }

  if (d.url) {
    root.append(h('a', {
      class: 'btn', style: 'margin-top:14px;width:100%',
      href: d.url, target: '_blank', rel: 'noopener',
      onclick: () => api.feedback(d.id, 'open_url').catch(() => {}),
    }, '打开原文 ↗'));
  }

  if (d.related?.length) {
    root.append(section('相关条目', h('div', {}, d.related.map((r) =>
      h('div', { class: 'lineage-entry', onclick: () => onOpenItem?.(r.id) },
        h('span', { class: 'dt' }, r.date || r.published_at || ''),
        h('span', {}, r.title))))));
  }

  // 反馈条
  const state = d.user || {};
  const bar = h('div', { class: 'feedback-bar' });
  for (const [action, icon, label] of FB_DEFS) {
    const isOn = () => (action === 'useful' || action === 'irrelevant')
      ? state.voted === action
      : (action === 'star' ? state.starred : state.followed);
    const btn = h('button', { class: `fb-btn ${isOn() ? 'on' : ''}` }, `${icon} ${label}`);
    btn.addEventListener('click', async () => {
      let send = action;
      if (action === 'star' && state.starred) send = 'unstar';
      if (action === 'follow_up' && state.followed) send = 'unfollow';
      try {
        const r = await api.feedback(d.id, send);
        Object.assign(state, r.state);
        bar.querySelectorAll('.fb-btn').forEach((b, i) => {
          const [act] = FB_DEFS[i];
          const on = (act === 'useful' || act === 'irrelevant') ? state.voted === act
            : act === 'star' ? state.starred : state.followed;
          b.classList.toggle('on', on);
        });
        if (send === 'useful' || send === 'irrelevant') toast('已记录，见微会学习你的偏好');
      } catch (e) { toast('操作失败：' + e.message); }
    });
    bar.append(btn);
  }
  root.append(bar);
  return root;
}

function section(title, content) {
  return h('div', { class: 'detail-section' }, h('h4', {}, title), content);
}

/* 绑定 markdown 中 [#id] / 引用 chip 的点击 */
export function bindMdRefs(container, { onOpenItem, citations = [] } = {}) {
  container.querySelectorAll('.item-ref').forEach((el) => {
    el.addEventListener('click', () => onOpenItem?.(parseInt(el.dataset.item, 10)));
  });
  container.querySelectorAll('.cite-ref').forEach((el) => {
    const c = citations.find((x) => x.n === parseInt(el.dataset.cite, 10));
    if (c) el.addEventListener('click', () => onOpenItem?.(c.item_id));
  });
}

export { mdRender };
