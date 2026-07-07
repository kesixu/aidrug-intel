/* 我的：兴趣画像 / 决策维度 / 关键词 / 进化 / 情报源 / 系统 */
import { api } from '../api.js';
import { mdRender, toast } from '../components.js';
import { h, relTime } from '../util.js';

export function render(container, ctx) {
  const profileBox = h('div', { class: 'me-section' });
  const lensBox = h('div', { class: 'me-section' });
  const kwBox = h('div', { class: 'me-section' });
  const evoBox = h('div', { class: 'me-section' });
  const srcBox = h('div', { class: 'me-section' });
  const sysBox = h('div', { class: 'me-section' });

  container.append(
    h('div', { class: 'section-title' }, '兴趣画像'), profileBox,
    h('div', { class: 'section-title' }, '决策维度权重'), lensBox,
    h('div', { class: 'section-title' }, '门控关键词'), kwBox,
    h('div', { class: 'section-title' }, '自进化'), evoBox,
    h('div', { class: 'section-title' }, '情报源健康'), srcBox,
    h('div', { class: 'section-title' }, '系统'), sysBox);

  /* 画像 + 维度 + 关键词 */
  api.profile().then((p) => {
    const ta = h('textarea', { class: 'narrative' }, p.narrative);
    profileBox.append(
      h('p', { class: 'muted', style: 'margin-bottom:8px' },
        'AI 分析每条情报时都会带着这段画像。写清楚你是谁、正在做什么决策、关心什么。'),
      ta,
      h('div', { style: 'text-align:right;margin-top:8px' },
        h('button', {
          class: 'btn small primary',
          onclick: async (e) => {
            e.currentTarget.disabled = true;
            try { await api.saveProfile({ narrative: ta.value }); toast('画像已更新，将影响后续所有分析'); } catch (err) { toast(err.message); }
            e.currentTarget.disabled = false;
          },
        }, '保存画像')));

    const rows = p.lenses.map((l) => {
      const val = h('span', { class: 'wv' }, l.weight.toFixed(2));
      const slider = h('input', { type: 'range', min: '0', max: '0.5', step: '0.05', value: l.weight });
      slider.addEventListener('input', () => { val.textContent = Number(slider.value).toFixed(2); });
      return { lens: l, slider, row: h('div', { class: 'weight-row' },
        h('div', {}, h('span', { class: 'wn' }, l.name), h('span', { class: 'wd' }, l.description.slice(0, 40) + '…')),
        slider, val) };
    });
    lensBox.append(
      ...rows.map((r) => r.row),
      h('div', { style: 'text-align:right;margin-top:10px' },
        h('button', {
          class: 'btn small',
          onclick: async (e) => {
            e.currentTarget.disabled = true;
            try {
              await api.saveLenses(rows.map((r) => ({ id: r.lens.id, weight: Number(r.slider.value), enabled: true })));
              toast('权重已保存，影响后续新条目评分');
            } catch (err) { toast(err.message); }
            e.currentTarget.disabled = false;
          },
        }, '保存权重')));

    const kws = [...p.keywords];
    const kwWrap = h('div', { class: 'kw-box' });
    const renderKws = () => {
      kwWrap.replaceChildren(...kws.map((k, i) => h('span', { class: 'kw-chip' }, k,
        h('button', { onclick: () => { kws.splice(i, 1); renderKws(); } }, '×'))));
    };
    renderKws();
    const newKw = h('input', { placeholder: '添加关键词…', style: 'flex:1;min-height:36px;background:var(--surface);border:1px solid var(--line);border-radius:10px;padding:0 12px;outline:none' });
    kwBox.append(
      h('p', { class: 'muted', style: 'margin-bottom:8px' }, '媒体源（36氪/量子位等）标题含任一关键词才会入库，政府源不受门控。'),
      kwWrap,
      h('div', { style: 'display:flex;gap:8px;margin-top:10px' },
        newKw,
        h('button', { class: 'btn small', onclick: () => { const v = newKw.value.trim(); if (v && !kws.includes(v)) { kws.push(v); renderKws(); newKw.value = ''; } } }, '添加'),
        h('button', {
          class: 'btn small primary',
          onclick: async (e) => {
            e.currentTarget.disabled = true;
            try { await api.saveProfile({ keywords: kws }); toast('关键词已保存'); } catch (err) { toast(err.message); }
            e.currentTarget.disabled = false;
          },
        }, '保存')));
  }).catch((e) => profileBox.append(h('p', { class: 'muted' }, '加载失败：' + e.message)));

  /* 进化 */
  function loadEvolution() {
    api.evolutionLog().then(({ runs }) => {
      evoBox.replaceChildren(
        h('p', { class: 'muted', style: 'margin-bottom:8px' },
          '每周日晚 AI 复盘你的反馈，提出画像/关键词/权重调整建议——采纳与否由你决定。'),
        h('button', {
          class: 'btn small', style: 'margin-bottom:10px',
          onclick: async (e) => {
            e.currentTarget.disabled = true; e.currentTarget.textContent = '进化中…约20秒';
            try { await api.evolutionRun(); toast('进化完成'); loadEvolution(); } catch (err) { toast(err.message); loadEvolution(); }
          },
        }, '立即运行一次进化'));
      if (!runs.length) { evoBox.append(h('p', { class: 'muted' }, '暂无进化记录')); return; }
      const latest = runs[0];
      evoBox.append(h('div', { class: 'card' },
        h('p', { class: 'muted mono', style: 'margin-bottom:6px' }, relTime(latest.ran_at)),
        h('div', { class: 'md', style: 'font-size:13.5px', html: mdRender(latest.report_md) }),
        ...latest.suggestions.map((s) => suggestionCard(s, loadEvolution))));
    }).catch(() => {});
  }
  loadEvolution();

  /* 情报源 */
  function loadSources() {
    api.sources().then(({ sources }) => {
      srcBox.replaceChildren(
        h('div', { style: 'display:flex;gap:8px;margin-bottom:6px' },
          h('button', {
            class: 'btn small',
            onclick: async (e) => {
              e.currentTarget.disabled = true; e.currentTarget.textContent = '抓取中…可能需要1-2分钟';
              try { const r = await api.ingestAll(); const n = r.results.reduce((x, y) => x + (y.new || 0), 0); toast(`抓取完成，新增 ${n} 条，正在后台分析`); } catch (err) { toast(err.message); }
              loadSources();
            },
          }, '↻ 全量抓取'),
          h('button', {
            class: 'btn small',
            onclick: async () => { try { const r = await api.analyzeNow(); toast(`补分析：成功 ${r.ok} 条`); } catch (err) { toast(err.message); } },
          }, '⚡ 补分析')),
        ...sources.map((s) => h('div', { class: 'src-row' },
          h('span', { class: `dot ${s.health}` }),
          h('div', { class: 'info' },
            h('div', {}, `${s.name} `, h('span', { class: 'muted' }, `T${s.tier}`)),
            h('div', { class: 'sub' },
              s.enabled
                ? `${s.item_count}条 · ${s.last_success_at ? '成功于' + relTime(s.last_success_at) : '未运行'}${s.last_run && !s.last_run.ok ? ' · ⚠' + (s.last_run.error || '').slice(0, 30) : ''}`
                : `已禁用 · ${s.note || ''}`)),
          s.enabled ? h('button', {
            class: 'btn small ghost',
            onclick: async (e) => {
              e.currentTarget.disabled = true;
              try { const r = await api.fetchSource(s.id); toast(`${s.name}：+${r.new || 0} 条`); } catch (err) { toast(err.message); }
              loadSources();
            },
          }, '抓取') : null)));
    }).catch(() => {});
  }
  loadSources();

  /* 系统 */
  api.status().then((s) => {
    const jobs = (s.scheduler || []).map((j) => `${j.name} → ${j.next_run ? new Date(j.next_run).toLocaleString('zh-CN', { hour12: false }).slice(5, 17) : '—'}`);
    sysBox.append(h('div', { class: 'card' },
      row('本月 LLM 费用（估算）', `¥${s.llm.cost_month}（${s.llm.calls_month} 次调用）`),
      row('今日费用', `¥${s.llm.cost_today}`),
      row('条目总量', `${s.items.total}（必读${s.items.by_tier?.red || 0} / 关注${s.items.by_tier?.orange || 0}）`),
      ...jobs.map((j) => row('调度', j)),
      row('主题', ''),
      h('div', { style: 'display:flex;gap:8px;margin-top:4px' },
        ['auto', 'dark', 'light'].map((m) => h('button', {
          class: `chip chip-btn ${(localStorage.getItem('theme') || 'auto') === m ? 'active' : ''}`,
          onclick: (e) => {
            localStorage.setItem('theme', m);
            window.__applyTheme();
            sysBox.querySelectorAll('.chip-btn').forEach((c) => c.classList.remove('active'));
            e.currentTarget.classList.add('active');
          },
        }, { auto: '跟随系统', dark: '暗色', light: '亮色' }[m]))),
    ));
  }).catch(() => {});

  function row(k, v) {
    return h('div', { style: 'display:flex;justify-content:space-between;gap:10px;padding:5px 0;font-size:13.5px' },
      h('span', { class: 'muted' }, k), h('span', { class: 'mono', style: 'text-align:right' }, v));
  }
}

const KIND_TEXT = { keyword_add: '新增关键词', keyword_remove: '移除关键词', weight: '调整权重', entity_watch: '关注实体', narrative_append: '补充画像' };

function suggestionCard(s, refresh) {
  const desc = `${KIND_TEXT[s.kind] || s.kind}：${JSON.stringify(s.payload).slice(0, 60)}`;
  const card = h('div', { class: 'sug-card' },
    h('div', {}, h('b', {}, KIND_TEXT[s.kind] || s.kind), ' ', h('span', { class: 'mono muted', style: 'font-size:11.5px' }, JSON.stringify(s.payload))),
    h('div', { class: 'muted', style: 'margin-top:4px' }, s.reason));
  if (s.status === 'pending') {
    card.append(h('div', { class: 'actions' },
      h('button', {
        class: 'btn small primary',
        onclick: async () => { try { const r = await api.decideSuggestion(s.id, 'accept'); toast(r.detail || '已采纳'); refresh(); } catch (e) { toast(e.message); } },
      }, '采纳'),
      h('button', {
        class: 'btn small',
        onclick: async () => { try { await api.decideSuggestion(s.id, 'reject'); refresh(); } catch (e) { toast(e.message); } },
      }, '忽略')));
  } else {
    card.append(h('div', { class: 'muted', style: 'margin-top:6px' }, s.status === 'accepted' ? '✓ 已采纳' : '已忽略'));
  }
  return card;
}
