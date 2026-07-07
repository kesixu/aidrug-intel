/* 情报流：过滤 chips + 搜索 + 无限滚动；桌面=列表+右栏详情 */
import { api } from '../api.js';
import { emptyState, intelCard, skeletons } from '../components.js';
import { debounce, h } from '../util.js';

const FILTERS = [
  { key: 'all', label: '全部' },
  { key: 'red', label: '必读', tier: 'red' },
  { key: 'orange', label: '关注', tier: 'orange' },
  { key: 'deadline', label: '⏰截止', collection: 'deadline' },
  { key: 'starred', label: '★收藏', collection: 'starred' },
  { key: 'followed', label: '🚩跟进', collection: 'followed' },
  { key: 'policy', label: '政策', category: '政策发布' },
  { key: 'funding', label: '资金申报', category: '资金申报' },
  { key: 'talent', label: '人才', category: '人才政策' },
  { key: 'company', label: '企业', category: '企业动态' },
  { key: 'invest', label: '融资', category: '融资并购' },
];

const state = { filter: 'all', q: '', cursor: null, items: [], loading: false, done: false, selectedId: null };

export function render(container, ctx) {
  state.cursor = null; state.items = []; state.done = false;
  const isDesktop = window.matchMedia('(min-width: 1024px)').matches;
  document.body.classList.toggle('split', isDesktop);

  const searchInput = h('input', {
    type: 'search', placeholder: '搜索情报（标题/正文/摘要）…', value: state.q,
    oninput: debounce((e) => { state.q = e.target.value.trim(); reload(); }, 350),
  });
  const filterBar = h('div', { class: 'filter-bar' },
    FILTERS.map((f) => h('button', {
      class: `chip chip-btn ${state.filter === f.key ? 'active' : ''}`,
      onclick: (e) => {
        state.filter = f.key;
        filterBar.querySelectorAll('.chip-btn').forEach((c) => c.classList.remove('active'));
        e.currentTarget.classList.add('active');
        reload();
      },
    }, f.label)));

  const list = h('div', { class: 'feed-list' });
  const sentinel = h('div', { style: 'height:1px' });

  let detailPane = null;
  if (isDesktop) {
    detailPane = h('div', { class: 'split-detail' },
      h('div', { class: 'detail-empty' }, '← 选择一条情报查看深读分析'));
    ctx.setFeedDetailPane(detailPane);
    container.append(h('div', { class: 'split-wrap' },
      h('div', { class: 'split-list' }, h('div', { class: 'search-row' }, searchInput), filterBar, list, sentinel),
      detailPane));
  } else {
    ctx.setFeedDetailPane(null);
    container.append(h('div', { class: 'search-row' }, searchInput), filterBar, list, sentinel);
  }

  const io = new IntersectionObserver((entries) => {
    if (entries[0].isIntersecting && !state.loading && !state.done && !state.q) loadMore();
  }, { rootMargin: '600px' });
  io.observe(sentinel);

  async function reload() {
    state.cursor = null; state.items = []; state.done = false;
    list.replaceChildren(...skeletons(5));
    await loadMore(true);
  }

  async function loadMore(fresh = false) {
    if (state.loading) return;
    state.loading = true;
    try {
      let items = [];
      if (state.q) {
        const r = await api.search(state.q);
        items = r.items; state.done = true;
      } else {
        const f = FILTERS.find((x) => x.key === state.filter) || {};
        const r = await api.feed({
          tier: f.tier, category: f.category, collection: f.collection,
          cursor: state.cursor, limit: 20,
        });
        items = r.items;
        state.cursor = r.next_cursor;
        state.done = !r.next_cursor;
      }
      if (fresh) list.replaceChildren();
      state.items.push(...items);
      if (!state.items.length) {
        list.replaceChildren(emptyState('档', '暂无匹配的情报', '调度器会按各源频率自动抓取'));
      } else {
        for (const it of items) {
          const card = intelCard(it, {
            lensNames: ctx.lensNames,
            onOpen: (item) => {
              list.querySelectorAll('.intel-card').forEach((c) => c.classList.remove('selected'));
              card.classList.add('selected');
              state.selectedId = item.id;
              ctx.openItem(item.id);
            },
          });
          list.append(card);
        }
      }
    } catch (e) {
      if (fresh) list.replaceChildren(emptyState('⚠', '加载失败', e.message));
    } finally {
      state.loading = false;
    }
  }

  reload();
  return () => { io.disconnect(); document.body.classList.remove('split'); ctx.setFeedDetailPane(null); };
}
