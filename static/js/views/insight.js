/* 洞察：关注实体 + 政策脉络 */
import { api } from '../api.js';
import { emptyState, errorState, skeletons } from '../components.js';
import { h as el } from '../util.js';

const KIND_LABEL = { company: '公司', agency: '机构', park: '园区', program: '计划', person: '人物', other: '其他' };
const STAGES = ['征求意见', '发布', '解读', '配套细则', '申报窗口', '结果公示'];

export function render(container, ctx) {
  const entityBox = el('div', {});
  const lineageBox = el('div', {});
  const filter = el('input', {
    class: 'entity-filter', type: 'search', placeholder: '筛选关注的名字', 'aria-label': '筛选实体',
  });
  container.append(
    el('div', { class: 'section-title' }, '关注实体'),
    el('p', { class: 'muted section-note' }, '按相关情报多少排列。点开看时间线。'),
    filter,
    entityBox,
    el('div', { class: 'section-title' }, '政策脉络'),
    lineageBox);
  entityBox.replaceChildren(...skeletons(4));
  lineageBox.replaceChildren(...skeletons(2));

  const loadEntities = () => {
    api.entities({ watch: 'true' }).then(({ entities }) => {
      const rows = entities.slice().sort((a, b) => b.item_count - a.item_count || a.name.localeCompare(b.name, 'zh'));
      const paint = () => {
        const q = filter.value.trim();
        const shown = q ? rows.filter((e) => e.name.includes(q)) : rows;
        if (!rows.length) {
          entityBox.replaceChildren(emptyState('观', '还没有关注的实体', '在一条情报里点实体名字即可关注'));
          return;
        }
        if (!shown.length) {
          entityBox.replaceChildren(emptyState('观', '没有匹配的名字', '换个词，或清空筛选'));
          return;
        }
        entityBox.replaceChildren(el('div', { class: 'entity-grid' },
          shown.map((e) => el('button', { type: 'button', class: 'entity-card', onclick: () => ctx.openEntity(e.id) },
            el('div', { class: 'n' }, e.name),
            el('div', { class: 'k' }, KIND_LABEL[e.kind] || e.kind),
            el('div', { class: 'c' }, e.item_count ? `${e.item_count} 条情报` : '还没有情报')))));
      };
      filter.oninput = paint;
      paint();
    }).catch((e) => entityBox.replaceChildren(errorState('实体没加载出来', e.message, loadEntities)));
  };
  loadEntities();

  api.lineages().then(({ data }) => {
    if (!data.length) {
      lineageBox.replaceChildren(emptyState('策', '暂无政策脉络', 'AI 会自动把同族政策串成生命线'));
      return;
    }
    lineageBox.replaceChildren(...data.slice(0, 12).map((fam) =>
      el('div', { class: 'lineage-card' },
        el('h3', {}, fam.name),
        el('div', { class: 'stage-track' }, STAGES.map((s) =>
          el('span', { class: `stage-pill ${fam.stages.includes(s) ? 'done' : ''}` }, s))),
        fam.entries.slice(-5).reverse().map((e) =>
          el('div', { class: 'lineage-entry', onclick: () => ctx.openItem(e.id) },
            el('span', { class: 'dt' }, e.date),
            el('span', {}, e.title))))));
  }).catch((e) => lineageBox.replaceChildren(errorState('脉络没加载出来', e.message, () => location.reload())));
}
