/* 洞察：关注实体 + 政策脉络 */
import { api } from '../api.js';
import { emptyState } from '../components.js';
import { h as el } from '../util.js';

const KIND_LABEL = { company: '公司', agency: '机构', park: '园区', program: '计划', person: '人物', other: '其他' };
const STAGES = ['征求意见', '发布', '解读', '配套细则', '申报窗口', '结果公示'];

export function render(container, ctx) {
  const entityBox = el('div', {});
  const lineageBox = el('div', {});
  container.append(
    el('div', { class: 'section-title' }, '关注实体'),
    entityBox,
    el('div', { class: 'section-title' }, '政策脉络'),
    lineageBox);

  api.entities({ watch: 'true' }).then(({ entities }) => {
    if (!entities.length) {
      entityBox.replaceChildren(emptyState('观', '暂无关注实体', '在条目详情里点实体即可关注'));
      return;
    }
    entityBox.replaceChildren(el('div', { class: 'entity-grid' },
      entities.map((e) => el('div', { class: 'entity-card', onclick: () => ctx.openEntity(e.id) },
        el('div', { class: 'n' }, e.name),
        el('div', { class: 'k' }, KIND_LABEL[e.kind] || e.kind),
        el('div', { class: 'c' }, `${e.item_count} 条情报`)))));
  }).catch((e) => entityBox.replaceChildren(emptyState('⚠', '加载失败', e.message)));

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
  }).catch((e) => lineageBox.replaceChildren(emptyState('⚠', '加载失败', e.message)));
}
