/* AI for Science 大陆情报系统 — 前端逻辑 */
const API = '/api';
let currentView = 'timeline';
let currentData = [];
let stats = {};

// ─── Init ───
document.addEventListener('DOMContentLoaded', () => {
  loadStats();
  loadTimeline();
  setupEventListeners();
});

function setupEventListeners() {
  document.querySelectorAll('.tab-btn').forEach(btn => {
    btn.addEventListener('click', () => switchView(btn.dataset.view));
  });
  document.getElementById('search-input').addEventListener('input', debounce(loadTimeline, 300));
  document.getElementById('filter-category').addEventListener('change', loadTimeline);
  document.getElementById('filter-region').addEventListener('change', loadTimeline);
  document.getElementById('filter-score').addEventListener('change', loadTimeline);
}

// ─── View Switching ───
function switchView(view) {
  currentView = view;
  document.querySelectorAll('.tab-btn').forEach(b => b.classList.toggle('active', b.dataset.view === view));
  document.querySelectorAll('.view').forEach(v => v.style.display = 'none');
  document.getElementById('view-' + view).style.display = 'block';
  if (view === 'timeline') loadTimeline();
  else if (view === 'lineages') loadLineages();
  else if (view === 'sources') loadSources();
}

// ─── Stats ───
async function loadStats() {
  try {
    const r = await fetch(API + '/stats');
    stats = await r.json();
    document.getElementById('stats-bar').innerHTML = `
      <span>总计 <strong>${stats.total}</strong> 条</span>
      <span class="highlight">高优先级 <strong>${stats.high_priority}</strong></span>
      <span>需跟进 <strong>${stats.need_followup}</strong></span>
    `;
  } catch(e) { console.error(e); }
}

// ─── Timeline ───
async function loadTimeline() {
  const container = document.getElementById('timeline-container');
  container.innerHTML = '<div class="loading">加载中...</div>';

  const params = new URLSearchParams();
  const search = document.getElementById('search-input').value.trim();
  const category = document.getElementById('filter-category').value;
  const region = document.getElementById('filter-region').value;
  const score = document.getElementById('filter-score').value;

  if (search) params.set('search', search);
  if (category) params.set('category', category);
  if (region) params.set('region_tier', region);
  if (score) params.set('min_score', score);
  params.set('limit', '100');

  try {
    const r = await fetch(API + '/intel?' + params.toString());
    const j = await r.json();
    currentData = j.data;
    if (j.data.length === 0) {
      container.innerHTML = '<div class="empty-state"><div class="icon">📭</div><p>暂无情报条目</p><p style="font-size:12px">系统将每日自动抓取新情报</p></div>';
      return;
    }
    container.innerHTML = j.data.map(e => renderCard(e)).join('');
    bindCardClicks();
  } catch(e) {
    container.innerHTML = '<div class="empty-state"><div class="icon">⚠️</div><p>加载失败</p></div>';
  }
}

function renderCard(e) {
  const rs = e.relevance_score || {};
  const highPrio = rs.overall >= 4;
  const midPrio = rs.overall >= 2 && rs.overall < 4;
  const priorityClass = highPrio ? 'high-priority' : (midPrio ? 'medium-priority' : '');

  const tagClass = {
    '政策发布': 'tag-policy', '实施细则': 'tag-policy',
    '资金申报': 'tag-funding', '人才政策': 'tag-talent',
    '监管动态': 'tag-regulatory', '企业动态': 'tag-enterprise',
    '学术会议': 'tag-academic', '产业数据': 'tag-industry',
  };

  const scores = [
    { label: '综合', val: rs.overall },
    { label: 'AZ', val: rs.az_beijing },
    { label: 'TPB', val: rs.trustpathbot },
    { label: '人才', val: rs.talent_program },
    { label: '资金', val: rs.funding_opportunity },
  ];

  const scoreDots = scores.map(s => {
    const cls = s.val >= 4 ? 'high' : (s.val >= 2 ? 'mid' : 'low');
    const filled = Array(Math.min(s.val || 0, 5)).fill(0).map(() => `<span class="score-dot filled ${cls}"></span>`).join('');
    const empty = Array(Math.max(5 - (s.val || 0), 0)).fill(0).map(() => `<span class="score-dot"></span>`).join('');
    return `<span title="${s.label}: ${s.val || 0}/5" style="display:flex;gap:2px">${filled}${empty}</span>`;
  }).join('');

  const summary = e.ai_interpretation ? e.ai_interpretation.slice(0, 120) + (e.ai_interpretation.length > 120 ? '...' : '') : '';

  const statusBadge = e.user_status ? `<span style="font-size:11px;background:#eee;padding:2px 6px;border-radius:10px">${e.user_status}</span>` : '';
  const noteIcon = e.user_note ? ' 📝' : '';

  return `
<div class="intel-card ${priorityClass}" id="card-${e.id}">
  <div class="card-header">
    <div>
      <div class="card-title" data-id="${e.id}">${escHtml(e.title)}${noteIcon}</div>
      <div class="tag-row">
        <span class="tag ${tagClass[e.category] || 'tag-policy'}">${e.category || '未分类'}</span>
        <span class="tag tag-region">${e.region_tier || '未知'}</span>
        ${statusBadge}
      </div>
    </div>
    <div class="card-meta">
      <div>${e.date_published || ''}</div>
      <div style="margin-top:4px">${scoreDots}</div>
    </div>
  </div>
  <div class="card-summary">${escHtml(summary)}</div>
  <div class="card-expanded" id="expand-${e.id}">
    ${e.original_excerpt ? '<h4>原文摘要</h4><p>' + escHtml(e.original_excerpt) + '</p>' : ''}
    ${e.ai_interpretation ? '<h4>解读</h4><p>' + escHtml(e.ai_interpretation) + '</p>' : ''}
    ${e.relevance_reasoning ? '<h4>关联分析</h4><p>' + escHtml(e.relevance_reasoning) + '</p>' : ''}
    ${e.forecast ? '<h4>预判</h4><p>' + escHtml(e.forecast) + '</p>' : ''}
    ${e.recommended_action ? '<div class="action-box"><strong>建议行动：</strong>' + escHtml(e.recommended_action) + '</div>' : ''}
    ${e.source_url ? '<p style="font-size:11px;margin-top:4px">📎 <a href="' + escHtml(e.source_url) + '" target="_blank" rel="noopener">' + escHtml(e.source_url) + '</a></p>' : ''}
    <div class="card-actions">
      <select onchange="updateStatus('${e.id}', this.value)" style="font-size:12px">
        <option value="">标记状态...</option>
        <option value="已读" ${e.user_status === '已读' ? 'selected' : ''}>已读</option>
        <option value="需跟进" ${e.user_status === '需跟进' ? 'selected' : ''}>需跟进</option>
        <option value="已过时" ${e.user_status === '已过时' ? 'selected' : ''}>已过时</option>
      </select>
      <button onclick="addNote('${e.id}')">备注</button>
    </div>
  </div>
</div>`;
}

function bindCardClicks() {
  document.querySelectorAll('.card-title').forEach(el => {
    el.addEventListener('click', () => {
      const id = el.dataset.id;
      const expand = document.getElementById('expand-' + id);
      if (expand) expand.classList.toggle('show');
    });
  });
}

// ─── Status & Notes ───
async function updateStatus(id, status) {
  if (!status) return;
  await fetch(API + '/intel/' + id, {
    method: 'PUT',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({user_status: status})
  });
  loadTimeline();
  loadStats();
}

function addNote(id) {
  const note = prompt('添加备注：');
  if (note === null) return;
  fetch(API + '/intel/' + id, {
    method: 'PUT',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({user_note: note})
  }).then(() => loadTimeline());
}

// ─── Policy Lineages ───
async function loadLineages() {
  const container = document.getElementById('lineages-container');
  container.innerHTML = '<div class="loading">加载中...</div>';
  try {
    const r = await fetch(API + '/policy-lineages');
    const j = await r.json();
    if (j.data.length === 0) {
      container.innerHTML = '<div class="empty-state"><div class="icon">📋</div><p>暂无政策家族追踪</p></div>';
      return;
    }
    container.innerHTML = j.data.map(fam => {
      const stages = ['发布', '官方解读', '配套细则', '资金申报', '结果产出'];
      const doneStages = fam.stages || [];
      const entriesHtml = fam.entries.map(e => `<div style="font-size:12px;margin-left:12px">• ${e.date} — ${escHtml(e.title)} [${e.stage}]</div>`).join('');
      return `
<div class="lineage-bar">
  <h3>${escHtml(fam.name)}</h3>
  <div class="lifecycle-track">
    ${stages.map(s => {
      const isDone = doneStages.includes(s) || doneStages.has(s);
      return `<div class="lifecycle-step ${isDone ? 'done' : ''}"><div class="step-label">${s}</div></div>`;
    }).join('')}
  </div>
  ${entriesHtml}
</div>`;
    }).join('');
  } catch(e) {
    container.innerHTML = '<div class="empty-state"><div class="icon">⚠️</div><p>加载失败</p></div>';
  }
}

// ─── Source Map ───
function loadSources() {
  const container = document.getElementById('sources-container');
  const sources = {
    'Tier 1 — 亦庄/BioPark 最高优先级': [
      {name:'北京亦庄工作动态', url:'https://open.beijing.gov.cn/html/yizhuang/gzdt/', desc:'镜像亦庄微信公众号内容'},
      {name:'开发区管委会政务公开', url:'https://kfqgw.beijing.gov.cn/zwgkkfq/', desc:'政策发布与公告'},
      {name:'国际科创中心-亦庄专栏', url:'https://www.ncsti.gov.cn/kjdt/scyq/bjjjjskfq/jkdt/', desc:'科技动态'},
      {name:'国家药监局 NMPA', url:'https://www.nmpa.gov.cn', desc:'关注京津冀分中心公告'},
      {name:'AstraZeneca 中国', url:'https://www.astrazeneca.com.cn', desc:'AZ 中国 newsroom'},
    ],
    'Tier 2 — 市级（科委中关村）': [
      {name:'北京市科委-政策文件', url:'https://kw.beijing.gov.cn/zwgk/zcwj/', desc:'核心政策来源'},
      {name:'北京市科委-政策解读', url:'https://kw.beijing.gov.cn/zwgk/zcjd/', desc:'官方解读文件'},
      {name:'国际科创中心-政策法规', url:'https://www.ncsti.gov.cn/zcfg/', desc:'政策总栏'},
      {name:'首都之窗', url:'https://www.beijing.gov.cn', desc:'北京市政府门户'},
    ],
    'Tier 3 — 行业/媒体/学术': [
      {name:'动脉网', url:'https://vcbeat.net', desc:'医药/医疗AI产业新闻'},
      {name:'医药魔方', url:'https://pharmcube.com', desc:'医药行业数据'},
      {name:'MICCAI', url:'https://conferences.miccai.org', desc:'医学影像AI顶会'},
      {name:'ISBI', url:'https://biomedicalimaging.org', desc:'生物医学成像'},
    ],
    'Tier 4 — 全国背景（低频监控）': [
      {name:'科技部', url:'https://www.most.gov.cn', desc:'国家科技政策'},
      {name:'国家卫健委', url:'https://www.nhc.gov.cn', desc:'医疗卫生政策'},
    ],
  };

  container.innerHTML = Object.entries(sources).map(([tier, items]) => {
    const tierNum = tier.split(' ')[0].replace('Tier', 't');
    return `
<div class="source-tier ${tierNum}">
  <h3>${tier}</h3>
  <div class="source-grid">
    ${items.map(s => `
      <div class="source-card">
        <div class="src-name">${escHtml(s.name)}</div>
        <div class="src-url"><a href="${escHtml(s.url)}" target="_blank" rel="noopener">${escHtml(s.url)}</a></div>
        <div class="src-desc">${escHtml(s.desc)}</div>
      </div>
    `).join('')}
  </div>
</div>`;
  }).join('');
}

// ─── Utils ───
function escHtml(s) {
  if (!s) return '';
  return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}
function debounce(fn, ms) {
  let timer;
  return function(...args) {
    clearTimeout(timer);
    timer = setTimeout(() => fn.apply(this, args), ms);
  };
}
