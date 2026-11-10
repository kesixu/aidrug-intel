/* 情报流：级别 / 分类 / 收藏 / 跟进可叠加，桌面键盘可扫。 */
import { api } from '../api.js';
import { emptyState, errorState, intelCard, skeletons, toast } from '../components.js';
import { debounce, h } from '../util.js';

const TIERS = [['', '全部'], ['red', '必读'], ['orange', '关注'], ['blue', '扫一眼'], ['gray', '归档']];
const COLLS = [['starred', '收藏'], ['followed', '跟进'], ['deadline', '临期']];
const CATS = [['政策发布', '政策'], ['资金申报', '资金'], ['人才政策', '人才'], ['企业动态', '企业'], ['融资并购', '融资']];
const TIER_KEY = { '1': '', '2': 'red', '3': 'orange', '4': 'blue', '5': 'gray' };
const COLL_KEY = { '6': 'starred', '7': 'followed', '8': 'deadline' };

const state = { tier: '', category: '', collection: '', q: '', selectedId: null };

export function render(container, ctx) {
  const isDesktop = window.matchMedia('(min-width: 1024px)').matches;
  document.body.classList.toggle('split', isDesktop);

  let token = 0;
  let busy = false;
  let cursor = null;
  let done = false;
  let items = [];

  const searchInput = h('input', {
    type: 'search',
    placeholder: '搜索标题、正文、摘要',
    value: state.q,
    'aria-label': '搜索情报',
    oninput: debounce((e) => { state.q = e.target.value.trim(); reload(); }, 300),
  });
  const tierBar = chipBar('tier', TIERS);
  const collBar = chipBar('collection', COLLS);
  const catBar = chipBar('category', CATS);
  const countEl = h('span', { class: 'feed-count' }, '');
  const list = h('div', { class: 'feed-list' });
  const moreBtn = h('button', {
    type: 'button', class: 'btn ghost more-btn', hidden: true,
    onclick: () => fetchPage(false),
  }, '继续加载');
  const sentinel = h('div', { class: 'feed-sentinel' });

  const tools = h('div', { class: 'feed-tools' },
    h('div', { class: 'search-row' }, searchInput),
    tierBar, collBar, catBar,
    h('div', { class: 'feed-meta-row' },
      countEl,
      h('span', { class: 'kbd-hint' }, 'j k 选择 · 回车打开 · s 收藏 · / 搜索 · ? 帮助')));

  let detailPane = null;
  const listCol = h('div', { class: 'split-list' }, tools, list, moreBtn, sentinel);
  if (isDesktop) {
    detailPane = h('div', { class: 'split-detail' },
      h('div', { class: 'detail-empty' },
        h('p', { class: 'empty-title' }, '选一条看深读'),
        h('p', { class: 'muted' }, '方向键移动，回车打开')));
    ctx.setFeedDetailPane(detailPane);
    container.append(h('div', { class: 'split-wrap' }, listCol, detailPane));
  } else {
    ctx.setFeedDetailPane(null);
    container.append(tools, list, moreBtn, sentinel);
  }

  function chipBar(kind, options) {
    return h('div', { class: 'filter-bar', role: 'toolbar', 'aria-label': kind },
      options.map(([value, label]) => h('button', {
        type: 'button',
        class: 'chip chip-btn',
        'data-kind': kind,
        'data-value': value,
        onclick: () => setFilter(kind, value),
      }, label)));
  }

  function paintChips() {
    container.querySelectorAll('.filter-bar .chip-btn').forEach((btn) => {
      const kind = btn.dataset.kind;
      const value = btn.dataset.value;
      const cur = state[kind] || '';
      btn.classList.toggle('active', cur === value);
    });
  }

  function setFilter(kind, value) {
    if (kind === 'tier') state.tier = value;
    else state[kind] = state[kind] === value ? '' : value;
    paintChips();
    reload();
  }

  function describe() {
    const bits = [];
    const tier = TIERS.find(([v]) => v === state.tier);
    if (state.tier && tier) bits.push(tier[1]);
    const coll = COLLS.find(([v]) => v === state.collection);
    if (coll) bits.push(coll[1]);
    if (state.category) bits.push(CATS.find(([v]) => v === state.category)?.[1] || state.category);
    if (state.q) bits.push(state.q);
    return bits.join(' · ') || '全部';
  }

  function paintCount() {
    const tail = done ? `${items.length} 条` : `${items.length} 条，还可以继续`;
    countEl.textContent = `${describe()} · ${tail}`;
    moreBtn.hidden = done || !items.length;
  }

  function applyUser(card, user) {
    if (!card || !user) return;
    card.dataset.starred = user.starred ? '1' : '0';
    card.dataset.followed = user.followed ? '1' : '0';
    const meta = card.querySelector('.ic-meta');
    if (!meta) return;
    meta.querySelector('.star-mark')?.remove();
    meta.querySelector('.follow-mark')?.remove();
    if (user.starred) meta.append(h('span', { class: 'star-mark' }, '已收藏'));
    if (user.followed) meta.append(h('span', { class: 'follow-mark' }, '跟进'));
  }

  function selectCard(card, { open = false } = {}) {
    list.querySelectorAll('.intel-card').forEach((c) => c.classList.remove('selected'));
    if (!card) return;
    card.classList.add('selected');
    state.selectedId = Number(card.dataset.id);
    card.scrollIntoView({ block: 'nearest' });
    if (open) ctx.openItem(state.selectedId);
  }

  function appendCards(batch, fresh) {
    if (fresh) list.replaceChildren();
    if (!items.length) {
      const filtered = state.tier || state.category || state.collection || state.q;
      list.replaceChildren(emptyState(
        '档',
        filtered ? '这个条件下没有情报' : '还没有情报',
        filtered ? '换个筛选，或等下一轮抓取' : '到点会按各源的频率自己抓',
        filtered ? h('button', { type: 'button', class: 'btn small', onclick: clearAll }, '清除筛选') : null));
      return;
    }
    for (const it of batch) {
      const card = intelCard(it, {
        lensNames: ctx.lensNames,
        onOpen: () => selectCard(card, { open: true }),
      });
      if (it.id === state.selectedId) card.classList.add('selected');
      list.append(card);
    }
  }

  function clearAll() {
    state.tier = '';
    state.category = '';
    state.collection = '';
    state.q = '';
    searchInput.value = '';
    paintChips();
    reload();
  }

  async function fetchPage(fresh) {
    if (!fresh && (busy || done)) return;
    const my = token;
    busy = true;
    try {
      const r = await api.feed({
        tier: state.tier || undefined,
        category: state.category || undefined,
        collection: state.collection || undefined,
        q: state.q || undefined,
        cursor: fresh ? undefined : cursor,
        limit: 20,
      });
      if (my !== token) return;
      const batch = r.items || [];
      cursor = r.next_cursor;
      done = !r.next_cursor;
      if (fresh) items = [];
      items = items.concat(batch);
      appendCards(batch, fresh);
      paintCount();
    } catch (e) {
      if (my !== token) return;
      if (fresh || !items.length) {
        list.replaceChildren(errorState('情报没有加载出来', e.message, () => reload()));
      } else toast(e.message);
    } finally {
      if (my === token) busy = false;
    }
  }

  function reload() {
    token += 1;
    busy = false;
    cursor = null;
    done = false;
    items = [];
    moreBtn.hidden = true;
    list.replaceChildren(...skeletons(5));
    countEl.textContent = '加载中…';
    fetchPage(true);
  }

  const io = new IntersectionObserver((entries) => {
    if (entries[0].isIntersecting) fetchPage(false);
  }, { root: isDesktop ? listCol : null, rootMargin: '400px' });
  io.observe(sentinel);

  function onFeedback(e) {
    const card = list.querySelector(`.intel-card[data-id="${e.detail.id}"]`);
    applyUser(card, e.detail.state);
  }
  window.addEventListener('intel-feedback', onFeedback);

  async function toggleSelected(which) {
    const card = list.querySelector('.intel-card.selected') || list.querySelector('.intel-card');
    if (!card) return;
    selectCard(card);
    const id = Number(card.dataset.id);
    const on = card.dataset[which === 'star' ? 'starred' : 'followed'] === '1';
    const send = which === 'star' ? (on ? 'unstar' : 'star') : (on ? 'unfollow' : 'follow_up');
    try {
      const r = await api.feedback(id, send);
      applyUser(card, r.state);
      toast(which === 'star' ? (r.state.starred ? '已收藏' : '已取消收藏') : (r.state.followed ? '已标为跟进' : '已取消跟进'));
    } catch (err) { toast(err.message); }
  }

  function move(delta) {
    const all = [...list.querySelectorAll('.intel-card')];
    if (!all.length) return;
    let i = all.findIndex((c) => c.classList.contains('selected'));
    i = i < 0 ? (delta > 0 ? 0 : all.length - 1) : Math.max(0, Math.min(all.length - 1, i + delta));
    selectCard(all[i]);
  }

  window.__feedKeys = (e) => {
    if (e.target.closest('button, a') && e.key === 'Enter') return false;
    if (TIER_KEY[e.key] !== undefined) { setFilter('tier', TIER_KEY[e.key]); return true; }
    if (COLL_KEY[e.key]) { setFilter('collection', COLL_KEY[e.key]); return true; }
    if (e.key === '/' ) { searchInput.focus(); return true; }
    if (e.key === 'j' || e.key === 'ArrowDown') { move(1); return true; }
    if (e.key === 'k' || e.key === 'ArrowUp') { move(-1); return true; }
    if (e.key === 'Enter') {
      let c = list.querySelector('.intel-card.selected');
      if (!c) c = list.querySelector('.intel-card');
      if (c) { selectCard(c); ctx.openItem(Number(c.dataset.id)); }
      return true;
    }
    if (e.key === 's') { toggleSelected('star'); return true; }
    if (e.key === 'f') { toggleSelected('follow'); return true; }
    return false;
  };

  paintChips();
  reload();
  return () => {
    token += 1;
    io.disconnect();
    window.removeEventListener('intel-feedback', onFeedback);
    if (window.__feedKeys) window.__feedKeys = null;
    document.body.classList.remove('split');
    ctx.setFeedDetailPane(null);
  };
}
