/* 今日：临期提醒 + 必读 + 晨报正文。顺序固定，手机上不用先翻过长文。 */
import { api } from '../api.js';
import { bindMdRefs, emptyState, errorState, intelCard, mdRender, skeletons, toast } from '../components.js';
import { daysUntil, fmtDateCN, h, shanghaiToday, weekdayCN } from '../util.js';

export function render(container, ctx) {
  const head = h('header', { class: 'today-head' },
    h('p', { class: 'kicker' }, '三分钟 · 北京时间'),
    h('h1', {},
      h('span', { class: 'd' }, fmtDateCN()),
      h('span', { class: 'w' }, weekdayCN())));
  const stats = h('p', { class: 'quiet-stats' }, '正在汇总今天的数字…');
  const deadlines = h('section', { class: 'deadline-block' });
  const must = h('section', { class: 'must-block' });
  const briefBox = h('div', { class: 'brief-wrap' });
  const historyBox = h('div', { class: 'history-block' });
  container.append(head, stats, deadlines, must, briefBox, historyBox);

  const loadStats = () => {
    api.status().then((s) => {
      const tier = s.items.by_tier || {};
      stats.replaceChildren(
        statBit(s.items.new_today, '今日新增'),
        ' · ',
        statBit(tier.red || 0, '必读', 'num-seal'),
        ' · ',
        statBit(tier.orange || 0, '关注', 'num-amber'),
        ' · ',
        statBit(s.items.by_status?.new || 0, '待分析'));
    }).catch(() => { stats.textContent = '统计暂时没拿到'; });
  };

  const loadDeadlines = () => {
    api.feed({ collection: 'deadline', limit: 12 }).then((r) => {
      const upcoming = r.items
        .filter((it) => it.analysis?.deadline && daysUntil(it.analysis.deadline) >= 0)
        .sort((a, b) => daysUntil(a.analysis.deadline) - daysUntil(b.analysis.deadline));
      if (!upcoming.length) { deadlines.replaceChildren(); return; }
      deadlines.replaceChildren(
        h('h2', { class: 'section-title' }, `临期 · ${upcoming.length}`),
        h('div', { class: 'deadline-list' }, upcoming.slice(0, 4).map((it) => {
          const d = daysUntil(it.analysis.deadline);
          const urgent = d <= 3;
          const when = d === 0 ? '今天截止' : d === 1 ? '明天截止' : `还剩 ${d} 天`;
          return h('button', {
            type: 'button',
            class: 'dl-row' + (urgent ? ' urgent' : ''),
            onclick: () => ctx.openItem(it.id),
          },
            h('span', { class: 'dl-when' }, when),
            h('span', { class: 'dl-date' }, it.analysis.deadline.slice(5)),
            h('span', { class: 'dl-title' }, it.title));
        })));
    }).catch((e) => {
      deadlines.replaceChildren(errorState('临期提醒没加载出来', e.message, loadDeadlines));
    });
  };

  const loadMust = () => {
    must.replaceChildren(h('h2', { class: 'section-title' }, '必读'), ...skeletons(3));
    api.feed({ tier: 'red', limit: 5 }).then((r) => {
      const items = r.items || [];
      if (!items.length) {
        must.replaceChildren(
          h('h2', { class: 'section-title' }, '必读'),
          emptyState('阅', '今天没有必读', '低于 75 分的会留在情报流里'));
        return;
      }
      must.replaceChildren(
        h('h2', { class: 'section-title' }, `必读 · ${items.length}`),
        h('div', { class: 'must-list' }, items.map((it) => intelCard(it, {
          lensNames: ctx.lensNames,
          onOpen: (item) => ctx.openItem(item.id),
        }))));
    }).catch((e) => {
      must.replaceChildren(errorState('必读没加载出来', e.message, loadMust));
    });
  };

  function renderBrief(brief) {
    if (!brief) {
      briefBox.replaceChildren(
        h('h2', { class: 'section-title' }, '晨报'),
        emptyState('晨', '还没有晨报', '每天 7:30（北京时间）自动写；也可以现在生成'),
        h('div', { class: 'center-actions' },
          h('button', { type: 'button', class: 'btn primary', onclick: generate }, '生成晨报')));
      return;
    }
    const today = shanghaiToday();
    const md = h('div', { class: 'md', html: mdRender(brief.content_md) });
    bindMdRefs(md, { onOpenItem: ctx.openItem });
    const note = brief.date === today
      ? brief.model
      : `最新一份是 ${brief.date}，今天的还没生成`;
    briefBox.replaceChildren(
      h('h2', { class: 'section-title' }, '晨报正文'),
      h('article', { class: 'brief-card' },
        md,
        h('div', { class: 'brief-foot' },
          h('span', { class: 'muted' }, note),
          h('button', {
            type: 'button', class: 'btn small',
            onclick: generate,
          }, brief.date === today ? '重新生成' : '生成今日'))));
  }

  async function loadBrief() {
    briefBox.replaceChildren(h('div', { class: 'skeleton skeleton-tall', 'aria-hidden': 'true' }, h('i'), h('i'), h('i'), h('i')));
    try {
      const { brief } = await api.briefToday();
      renderBrief(brief);
    } catch (e) {
      briefBox.replaceChildren(errorState('晨报没加载出来', e.message, loadBrief));
    }
  }

  async function generate(e) {
    const btn = e?.currentTarget;
    if (btn) { btn.disabled = true; btn.textContent = '正在写…'; }
    try {
      let s = await api.briefGenerate();
      for (let i = 0; s.running && i < 100; i++) {
        await new Promise((r) => setTimeout(r, 3000));
        s = await api.briefGenerateStatus();
      }
      if (s.running) {
        toast('还在写，过一会刷新');
        if (btn) { btn.disabled = false; btn.textContent = '重新生成'; }
        return;
      }
      if (s.error) throw new Error(s.error);
      toast('晨报好了');
      await loadBrief();
    } catch (err) {
      toast('没写成：' + err.message);
      if (btn) { btn.disabled = false; btn.textContent = '重试'; }
    }
  }

  api.briefs(10).then(({ briefs }) => {
    if (briefs.length < 2) return;
    historyBox.replaceChildren(
      h('h2', { class: 'section-title' }, '以前的晨报'),
      h('div', { class: 'history-row' },
        briefs.slice(1, 8).map((b) => h('button', {
          type: 'button', class: 'chip chip-btn',
          onclick: () => {
            renderBrief(b);
            container.scrollTo({ top: 0, behavior: 'smooth' });
          },
        }, b.date.slice(5)))));
  }).catch(() => {});

  loadStats();
  loadDeadlines();
  loadMust();
  loadBrief();
}

function statBit(n, label, cls = '') {
  return h('span', { class: 'qstat' }, h('b', { class: cls }, String(n)), ' ' + label);
}
