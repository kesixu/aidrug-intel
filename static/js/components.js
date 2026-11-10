/* 共享组件：toast、抽屉、情报卡片、详情、空态与骨架 */
import { api } from './api.js';
import { daysUntil, esc, h, mdRender } from './util.js';

let toastTimer;
export function toast(msg) {
  const el = document.getElementById('toast');
  el.textContent = msg;
  el.classList.add('show');
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => el.classList.remove('show'), 2200);
}

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

export function sheetIsOpen() {
  return sheetOpen;
}

export function initSheet() {
  overlay().addEventListener('click', () => closeSheet());
  window.addEventListener('popstate', () => { if (sheetOpen) closeSheet(true); });
  let startY = null;
  const handle = sheet().querySelector('.sheet-handle');
  handle.addEventListener('touchstart', (e) => { startY = e.touches[0].clientY; }, { passive: true });
  handle.addEventListener('touchmove', (e) => {
    if (startY !== null && e.touches[0].clientY - startY > 70) { startY = null; closeSheet(); }
  }, { passive: true });
  window.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && sheetOpen && !e.target.closest('input, textarea')) closeSheet();
  });
}

const SEAL_CHAR = { red: '必', orange: '关', blue: '阅', gray: '档' };
const SEAL_NAME = { red: '必读', orange: '关注', blue: '扫一眼', gray: '归档' };

export function sealBadge(analysis) {
  if (!analysis) return h('div', { class: 'seal-badge pending', title: '分析中' }, '…');
  const t = analysis.tier || 'gray';
  const name = SEAL_NAME[t] || '归档';
  return h('div', {
    class: `seal-badge ${t}`,
    title: `${name} · ${analysis.final_score}`,
    'aria-label': `${name} ${analysis.final_score}`,
  }, SEAL_CHAR[t] || '档');
}

export function intelCard(item, { onOpen, lensNames = {} } = {}) {
  const a = item.analysis;
  const meta = [];
  meta.push(h('span', { class: 'src' }, item.source?.name || ''));
  if (item.published_at) meta.push(h('span', {}, item.published_at));
  if (a?.category) meta.push(h('span', { class: 'chip chip-mini' }, a.category));
  if (a?.deadline) {
    const d = daysUntil(a.deadline);
    if (d !== null && d >= 0) {
      const label = d === 0 ? '今天截止' : d === 1 ? '明天截止' : `${d}天后截止`;
      meta.push(h('span', { class: 'deadline-tag' }, label));
    }
  }
  const topLens = (a?.lens_scores || []).filter((s) => s.score >= 55).sort((x, y) => y.score - x.score)[0];
  if (topLens) meta.push(h('span', { class: 'lens-tag' }, `${lensNames[topLens.lens_id] || topLens.lens_id} ${topLens.score}`));
  if (a?.final_score) meta.push(h('span', { class: 'score-tag' }, String(Math.round(a.final_score))));
  if (item.user?.starred) meta.push(h('span', { class: 'star-mark' }, '已收藏'));
  if (item.user?.followed) meta.push(h('span', { class: 'follow-mark' }, '跟进'));

  return h('article', {
    class: `intel-card tier-${a?.tier || 'pending'}`,
    'data-id': item.id,
    'data-starred': item.user?.starred ? '1' : '0',
    'data-followed': item.user?.followed ? '1' : '0',
    onclick: () => onOpen?.(item),
  },
    sealBadge(a),
    h('div', { class: 'ic-body' },
      h('h3', {}, item.title),
      a?.summary ? h('p', { class: 'ic-summary' }, a.summary) : null,
      h('div', { class: 'ic-meta' }, meta)));
}

export function skeletons(n = 4) {
  return Array.from({ length: n }, () => h('div', { class: 'skeleton', 'aria-hidden': 'true' },
    h('i'), h('i'), h('i', { class: 'short' })));
}

export function emptyState(glyph, text, sub, action) {
  return h('div', { class: 'empty' },
    h('span', { class: 'glyph' }, glyph),
    h('p', { class: 'empty-title' }, text),
    sub ? h('p', { class: 'muted' }, sub) : null,
    action || null);
}

export function errorState(title, detail, onRetry) {
  return h('div', { class: 'error-box' },
    h('p', { class: 'empty-title' }, title),
    detail ? h('p', { class: 'muted' }, detail) : null,
    onRetry ? h('button', { type: 'button', class: 'btn small', onclick: onRetry }, '重试') : null);
}

const FB_DEFS = [
  ['useful', '有用'], ['irrelevant', '无关'],
  ['star', '收藏'], ['follow_up', '跟进'],
];

export function detailContent(d, { lensNames = {}, onOpenItem, onOpenEntity } = {}) {
  const a = d.analysis;
  const root = h('div', { class: 'detail-root' });
  root.append(h('h2', { class: 'detail-title' }, d.title));

  const metaRow = h('div', { class: 'detail-meta' },
    sealBadge(a),
    h('span', { class: 'chip' }, d.source?.name || ''),
    h('span', { class: 'muted mono' }, d.published_at || ''),
    a?.signal ? h('span', { class: 'chip' }, `信号·${a.signal}`) : null,
    a ? h('span', { class: 'muted mono' }, `${SEAL_NAME[a.tier] || ''} ${a.final_score}`) : null);
  root.append(metaRow);

  if (a?.summary) {
    root.append(section('AI 摘要', h('p', { class: 'detail-summary' }, a.summary)));
  } else if (d.status === 'new') {
    root.append(section('AI 摘要', h('p', { class: 'muted' }, '还在分析，新条目通常几分钟内会有深读')));
  }

  if (a?.action_hint) {
    root.append(h('div', { class: 'action-box', html: `<b>建议</b>　${esc(a.action_hint)}` }));
  }
  if (a?.deadline) {
    const days = daysUntil(a.deadline);
    const left = days === null ? '' : days < 0 ? '（已过期）' : days === 0 ? '（今天截止）' : `（还剩 ${days} 天）`;
    root.append(h('div', { class: 'action-box deadline-box' },
      h('b', {}, '截止 '), a.deadline, left));
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
    root.append(section('和你的关系', h('div', {}, rows)));
  }

  if (a?.policy_family) {
    root.append(section('政策脉络', h('div', { class: 'stage-track' },
      h('span', { class: 'chip jade' }, a.policy_family),
      a.policy_stage ? h('span', { class: 'stage-pill done' }, a.policy_stage) : null)));
  }

  const ents = a?.entities || [];
  if (ents.length) {
    root.append(section('涉及', h('div', { class: 'kw-box' },
      ents.map((e) => h('button', {
        type: 'button', class: 'chip chip-btn',
        onclick: () => onOpenEntity?.(e.name),
      }, e.name)))));
  }

  if (d.content_preview) {
    const p = h('p', { class: 'preview' }, d.content_preview);
    const more = h('button', {
      type: 'button', class: 'btn small ghost',
      onclick: () => { p.classList.add('open'); more.remove(); },
    }, '展开节选');
    root.append(section('原文节选', h('div', {}, p, d.content_preview.length > 180 ? more : null)));
  }

  if (d.url) {
    root.append(h('a', {
      class: 'btn', href: d.url, target: '_blank', rel: 'noopener',
      onclick: () => api.feedback(d.id, 'open_url').catch(() => {}),
    }, '打开原文'));
  }

  if (d.related?.length) {
    root.append(section('相关', h('div', {}, d.related.map((r) =>
      h('div', { class: 'lineage-entry', onclick: () => onOpenItem?.(r.id) },
        h('span', { class: 'dt' }, r.date || r.published_at || ''),
        h('span', {}, r.title))))));
  }

  const state = { ...(d.user || {}) };
  const bar = h('div', { class: 'feedback-bar' });
  const paint = () => {
    bar.querySelectorAll('.fb-btn').forEach((b) => {
      const act = b.dataset.act;
      const on = (act === 'useful' || act === 'irrelevant') ? state.voted === act
        : act === 'star' ? state.starred : state.followed;
      b.classList.toggle('on', on);
      b.setAttribute('aria-pressed', on ? 'true' : 'false');
    });
  };
  for (const [action, label] of FB_DEFS) {
    const btn = h('button', { type: 'button', class: 'fb-btn', 'data-act': action }, label);
    btn.addEventListener('click', async () => {
      let send = action;
      if (action === 'star' && state.starred) send = 'unstar';
      if (action === 'follow_up' && state.followed) send = 'unfollow';
      try {
        const r = await api.feedback(d.id, send);
        Object.assign(state, r.state);
        paint();
        window.dispatchEvent(new CustomEvent('intel-feedback', { detail: { id: d.id, state: { ...state } } }));
        if (send === 'useful' || send === 'irrelevant') toast('记下了，之后的排序会参考这个');
        else if (send === 'star' || send === 'unstar') toast(state.starred ? '已收藏' : '已取消收藏');
        else toast(state.followed ? '已标为跟进' : '已取消跟进');
      } catch (e) { toast('操作失败：' + e.message); }
    });
    bar.append(btn);
  }
  paint();
  root.append(bar);
  return root;
}

function section(title, content) {
  return h('div', { class: 'detail-section' }, h('h4', {}, title), content);
}

export function bindMdRefs(container, { onOpenItem, citations = [] } = {}) {
  container.querySelectorAll('.item-ref').forEach((el) => {
    el.addEventListener('click', () => onOpenItem?.(parseInt(el.dataset.item, 10)));
  });
  container.querySelectorAll('.cite-ref').forEach((el) => {
    const c = citations.find((x) => x.n === parseInt(el.dataset.cite, 10));
    if (c) el.addEventListener('click', () => onOpenItem?.(c.item_id));
  });
}

/* 流式输出会反复 innerHTML，用事件委托，[n] 一出现就能点。 */
export function delegateRefs(container, { onOpenItem, citationsOf } = {}) {
  container.addEventListener('click', (e) => {
    const el = e.target.closest?.('.item-ref, .cite-ref');
    if (!el || !container.contains(el)) return;
    if (el.classList.contains('item-ref')) {
      onOpenItem?.(parseInt(el.dataset.item, 10));
      return;
    }
    const host = el.closest('[data-cite-host]') || el.closest('.msg');
    const citations = citationsOf?.(host) || [];
    const c = citations.find((x) => x.n === parseInt(el.dataset.cite, 10));
    if (c) onOpenItem?.(c.item_id);
  });
}

export { mdRender };
