/* 今日：晨报 + 统计 + 临期提醒 + 历史晨报 */
import { api } from '../api.js';
import { bindMdRefs, emptyState, mdRender, toast } from '../components.js';
import { daysUntil, fmtDateCN, h, weekdayCN } from '../util.js';

export function render(container, ctx) {
  const head = h('div', { class: 'today-head' },
    h('span', { class: 'd' }, fmtDateCN()),
    h('span', { class: 'w' }, weekdayCN()));
  const statStrip = h('div', { class: 'stat-strip' });
  const dlStrip = h('div', { class: 'deadline-strip' });
  const briefBox = h('div', {});
  const historyBox = h('div', { style: 'margin-top:14px' });

  const grid = h('div', { class: 'today-grid' },
    h('div', {}, briefBox, historyBox),
    h('div', {}, statStrip, dlStrip));
  container.append(head, grid);

  api.status().then((s) => {
    statStrip.replaceChildren(
      stat(s.items.new_today, '今日新增'),
      stat(s.items.by_tier?.red || 0, '必读', 'red'),
      stat(s.items.by_tier?.orange || 0, '关注', 'amber'),
      stat(s.items.by_status?.new || 0, '待分析'));
  }).catch(() => {});

  api.feed({ collection: 'deadline', limit: 10 }).then((r) => {
    const upcoming = r.items
      .filter((it) => it.analysis?.deadline && daysUntil(it.analysis.deadline) >= 0)
      .sort((a, b) => a.analysis.deadline.localeCompare(b.analysis.deadline));
    if (!upcoming.length) return;
    dlStrip.replaceChildren(
      ...upcoming.slice(0, 8).map((it) => {
        const d = daysUntil(it.analysis.deadline);
        return h('div', { class: 'dl-chip', onclick: () => ctx.openItem(it.id) },
          h('div', { class: 'd' }, `${it.analysis.deadline} · 剩${d}天`),
          h('div', { class: 't' }, it.title));
      }));
  }).catch(() => {});

  async function loadBrief() {
    briefBox.replaceChildren(h('div', { class: 'skeleton', style: 'height:220px' }));
    try {
      const { brief } = await api.briefToday();
      renderBrief(brief);
    } catch (e) {
      briefBox.replaceChildren(emptyState('⚠', '晨报加载失败', e.message));
    }
  }

  function renderBrief(brief) {
    if (!brief) {
      briefBox.replaceChildren(
        emptyState('晨', '还没有晨报', '每天早上 7:30 自动生成；也可以现在手动生成'),
        h('div', { style: 'text-align:center' },
          h('button', { class: 'btn primary', onclick: generate }, '立即生成晨报')));
      return;
    }
    const md = h('div', { class: 'md', html: mdRender(brief.content_md) });
    bindMdRefs(md, { onOpenItem: ctx.openItem });
    const foot = h('div', { style: 'display:flex;gap:8px;margin-top:14px;align-items:center' },
      h('span', { class: 'muted mono' }, brief.date === todayStr() ? `${brief.model}` : `⚠ 这是 ${brief.date} 的晨报`),
      h('span', { style: 'flex:1' }),
      h('button', { class: 'btn small', onclick: generate }, brief.date === todayStr() ? '重新生成' : '生成今日晨报'));
    briefBox.replaceChildren(h('div', { class: 'brief-card' }, md, foot));
  }

  async function generate(e) {
    const btn = e?.currentTarget;
    if (btn) { btn.disabled = true; btn.textContent = '生成中…约30秒'; }
    try {
      let s = await api.briefGenerate();
      for (let i = 0; s.running && i < 100; i++) {
        await new Promise((r) => setTimeout(r, 3000));
        s = await api.briefGenerateStatus();
      }
      if (s.running) {
        toast('还在后台生成，稍后刷新查看');
        if (btn) { btn.disabled = false; btn.textContent = '重新生成'; }
        return;
      }
      if (s.error) throw new Error(s.error);
      toast('晨报已生成');
      await loadBrief();
    } catch (err) {
      toast('生成失败：' + err.message);
      if (btn) { btn.disabled = false; btn.textContent = '重试'; }
    }
  }

  api.briefs(10).then(({ briefs }) => {
    if (briefs.length < 2) return;
    historyBox.append(
      h('div', { class: 'section-title' }, '历史晨报'),
      h('div', { class: 'deadline-strip' },
        briefs.slice(1).map((b) => h('button', {
          class: 'chip chip-btn',
          onclick: () => { renderBrief(b); window.scrollTo({ top: 0, behavior: 'smooth' }); },
        }, b.date))));
  }).catch(() => {});

  loadBrief();
}

function stat(n, label, cls = '') {
  return h('div', { class: `stat ${cls}` }, h('span', { class: 'n' }, String(n)), h('span', { class: 'l' }, label));
}
function todayStr() {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
}
