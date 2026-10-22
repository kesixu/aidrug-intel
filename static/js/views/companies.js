/* 公司：药企深读档案（阿斯利康 / GSK / …）
   列表 → 点开进入详情；详情页顶部有返回。数据在 ../data/companies.js。 */
import { h } from '../util.js';
import { COMPANIES, GRADES, companyBySlug } from '../data/companies.js';

function gradeBadge(g) {
  return h('span', { class: `co-grade g-${g.toLowerCase()}`, title: GRADES[g] || '' }, g);
}

function metricRow([k, v, g]) {
  return h('div', { class: 'co-metric' },
    h('span', { class: 'co-metric-k' }, k),
    h('span', { class: 'co-metric-v' }, v),
    gradeBadge(g));
}

function sourceRow(s) {
  return h('div', { class: 'co-source' },
    h('span', { class: 'co-source-n' }, String(s.n)),
    h('a', { class: 'co-source-t', href: s.u, target: '_blank', rel: 'noopener' }, s.t),
    gradeBadge(s.g));
}

function sectionBlock(sec) {
  const parts = [h('div', { class: 'co-sec-title' }, sec.t)];
  for (const p of sec.p || []) parts.push(h('p', { class: 'co-p' }, p));
  if (sec.table) {
    const { head, rows, note } = sec.table;
    parts.push(h('div', { class: 'co-table-wrap' },
      h('table', { class: 'co-table' },
        h('thead', {}, h('tr', {}, head.map((c) => h('th', {}, c)))),
        h('tbody', {}, rows.map((r) => h('tr', {},
          r.map((c, i) => h('td', {}, i === r.length - 1 && /^[ACD]$/.test(c) ? gradeBadge(c) : c))))))));
    if (note) parts.push(h('div', { class: 'co-note' }, note));
  }
  return h('div', { class: 'co-sec' }, ...parts);
}

function listCard(c) {
  return h('div', {
    class: `co-card accent-${c.accent}`,
    onclick: () => { location.hash = `#/companies/${c.slug}`; },
  },
    h('div', { class: 'co-card-head' },
      h('div', {},
        h('div', { class: 'co-card-name' }, c.name),
        h('div', { class: 'co-card-en' }, `${c.en} · ${c.ticker}`)),
      h('div', { class: 'co-card-arrow' }, '›')),
    h('div', { class: 'co-card-tag' }, c.tagline),
    h('div', { class: 'co-card-metrics' }, c.metrics.slice(0, 3).map(metricRow)),
    h('div', { class: 'co-card-foot' }, `更新 ${c.updated} · 点开看完整档案`));
}

function listView(container) {
  container.append(
    h('div', { class: 'co-hero' },
      h('div', { class: 'co-hero-kicker' }, '药企深读 · 巨头档案'),
      h('h1', { class: 'co-hero-title' }, '各家药企在发生什么'),
      h('div', { class: 'co-hero-sub' },
        '一手财报、官方公告加三方报道，按证据分级整理。不是新闻摘要，是能直接拿去做判断的底稿。')),
    h('div', { class: 'co-legend' },
      h('span', { class: 'co-legend-label' }, '证据分级'),
      ...Object.entries(GRADES).map(([g, d]) => h('span', { class: 'co-legend-item' }, gradeBadge(g), d))),
    h('div', { class: 'co-list' }, COMPANIES.map(listCard)),
    h('div', { class: 'co-foot' },
      `共 ${COMPANIES.length} 家 · 加一家公司只需在 static/js/data/companies.js 里加一条对象`),
  );
}

function detailView(container, c) {
  container.append(
    h('div', { class: 'co-detail-head' },
      h('button', {
        class: 'chip chip-btn',
        onclick: () => { location.hash = '#/companies'; },
      }, '‹ 返回'),
      h('div', { class: 'co-detail-title' }, c.name),
      h('div', { class: 'co-detail-en' }, `${c.en} · ${c.ticker} · 更新 ${c.updated}`)),

    h('div', { class: 'co-verdict' }, c.verdict),

    h('div', { class: 'co-section-title' }, '关键数字'),
    h('div', { class: 'co-metrics' }, c.metrics.map(metricRow)),

    ...c.sections.map(sectionBlock),

    h('div', { class: 'co-section-title' }, '对 Oliver 的意义'),
    h('div', { class: 'co-toyou' },
      h('div', { class: 'co-toyou-level' }, `相关度：${c.toYou.level}`),
      ...c.toYou.points.map((p) => h('div', { class: 'co-toyou-p' }, p))),

    h('div', { class: 'co-section-title' }, '来源'),
    h('div', { class: 'co-sources' }, c.sources.map(sourceRow)),

    h('div', { class: 'co-foot' },
      '档案是编辑判断，不构成投资建议。标记 D 的条目在引用前请自行二次核实。'),
  );
}

export function render(container) {
  const slug = (location.hash.match(/^#\/companies\/([\w-]+)/) || [])[1];
  const c = slug ? companyBySlug(slug) : null;
  if (c) detailView(container, c);
  else listView(container);
}
