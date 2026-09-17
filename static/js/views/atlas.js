/* 图谱：大陆 AI 医药行业认知地图
   三分类知识图谱 + 代表公司深读 + 生物大模型讲解 */
import { h } from '../util.js';

const CATEGORIES = [
  {
    no: '①', key: 'biotech', name: 'AI + Biotech', cn: '自研管线',
    tag: '自己做药',
    def: 'AI 公司自己立项、自己持有药物管线，把 AI 直接变成"药"。',
    rep: '英矽智能（Insilico Medicine）',
    model: '自己研发新药 → 对外授权 / 自己推进临床，赚的是"药"的钱',
    accent: 'seal',
  },
  {
    no: '②', key: 'cro', name: 'AI + CRO', cn: '卖服务',
    tag: '给别人做药',
    def: 'AI 公司当"研发外包"，给大药企提供 AI 研发服务，一个个项目按订单收费。',
    rep: '晶泰科技（XtalPi）',
    model: '接药企研发订单 → 按 case 交付收费，赚的是"服务费"',
    accent: 'amber',
  },
  {
    no: '③', key: 'platform', name: 'AI + 平台', cn: '做大模型',
    tag: '造基础设施',
    def: 'AI 公司做生命科学基础大模型，开放给整个行业用，靠平台 + 战略合作变现。',
    rep: '百图生科（BioMap）',
    model: '卖大模型能力 / 平台 → 和大药企签战略合作，赚的是"平台"的钱',
    accent: 'azure',
  },
];

const COMPANIES = [
  {
    name: '英矽智能', en: 'Insilico Medicine', cat: 'AI + Biotech', accent: 'seal',
    stats: [
      ['成立', '2014 年'],
      ['估值', '超 13 亿美元（E 轮后）'],
      ['上市', '三闯港股 IPO（摩根士丹利、中金保荐）'],
      ['团队', '全球分布，AI 制药最老牌公司之一'],
    ],
    lines: [
      ['PandaOmics', '靶点发现引擎 —— 用 AI 从海量生物数据里找出"该打哪个靶点"'],
      ['Chemistry42', '分子生成平台 —— 让 AI 自己设计出候选药物分子'],
      ['inClinico', '临床试验预测 —— 提前判断一个药能不能成、会不会失败'],
    ],
    note: '代表作 ISM001-055（特发性肺纤维化）是全球第一个由 AI 从头发现、进入临床 II 期的药物。商业模式是"自研管线 + 对外授权"。',
  },
  {
    name: '晶泰科技', en: 'XtalPi · 2228.HK', cat: 'AI + CRO', accent: 'amber',
    stats: [
      ['成立', '2015 年'],
      ['上市', '港股上市，首日暴涨 173%，超额认购 6900 倍'],
      ['盈利', '2025 年度首次实现盈利'],
      ['特色', '量子物理 + AI + 机器人自动化实验'],
    ],
    lines: [
      ['晶型预测', '预测药物分子怎么"结晶"最稳定 —— 这是制药里最容易翻车的环节'],
      ['固态研发', 'AI + 自动化实验室，把枯燥的晶型筛选交给机器人'],
      ['药物发现 CRO', '给药企提供端到端的研发外包服务，按项目收费'],
    ],
    note: '本质是"AI 版 CRO"，卖的是研发服务订单。它的护城河是 AI+机器人湿实验闭环，不是单纯写代码。',
  },
  {
    name: '百图生科', en: 'BioMap', cat: 'AI + 平台', accent: 'azure',
    stats: [
      ['成立', '2020 年（李彦宏创立，个人大股东，百度占小股）'],
      ['团队', '北京约 100 人研发 + 苏州约 50 人湿实验室'],
      ['核心', 'xTrimo 生物大模型，2100 亿参数，全球最大'],
      ['合作', '赛诺菲 10 亿美元战略合作（2023）'],
      ['上市', '2026 年保密方式提交香港 IPO'],
    ],
    lines: [
      ['xTrimo 大模型', '生命科学基础大模型，覆盖蛋白质/DNA/RNA/细胞等 7 大模态'],
      ['AIGP 平台', 'AI Generated Protein，让 AI 直接生成目标蛋白质'],
      ['平台合作', '把大模型能力开放给药企，按战略合作收费'],
    ],
    note: '它不卖具体的药，卖的是"理解生命"的大模型能力。赛诺菲掏 10 亿美元，就是买它这个能力去做生物药研发。',
  },
];

/* 生物大模型讲解 —— 用最直白的话 */
const BIO_MODEL = [
  { t: '先理解一个核心思想：把"生命"当成一门语言', body: [
    '蛋白质是由 20 种氨基酸首尾相连串成的"句子"；DNA 是由 4 种碱基（A/C/G/T）写成的"文章"。',
    '既然它们是"一串字母"，那理论上就可以像教 AI 学英语、学中文一样，教 AI 学"生命的语言"。',
    '生物大模型，就是这样一个"学会了读蛋白质、读 DNA"的超大 AI。',
  ]},
  { t: '它到底怎么训出来的？', body: [
    '训练方法其实和 ChatGPT 一模一样，叫"掩码预测"（Masked Language Modeling）：把一串蛋白质序列里随机遮住几个氨基酸，让模型猜被遮住的是什么。',
    '猜得多了，模型就自己悟出了蛋白质的"语法"——哪些氨基酸喜欢挨在一起、什么顺序容易折叠成稳定结构、什么序列可能是功能位点。',
    '百图生科的 xTrimo V3 用了"专家混合"（MoE）架构，参数堆到 2100 亿，喂进去海量的蛋白质、DNA、RNA、细胞数据，覆盖 7 大模态。',
  ]},
  { t: '它跟 AlphaFold 到底差在哪？', body: [
    'AlphaFold 是"专用翻译机"：只干一件事——输入一段蛋白质序列，输出它的 3D 折叠结构。',
    'xTrimo 是"会这门语言的大模型"：一个模型能干很多事——预测结构、预测功能、预测蛋白质怎么相互作用、辅助设计新药。',
    '打个比方：AlphaFold 是"英汉词典"（查一个词翻一个词），xTrimo 是"英语母语者"（会英语之后，写作、翻译、对话都能干）。',
    '百图生科对标的其实不是 AlphaFold 这一个模型，而是 Google DeepMind 旗下 Isomorphic Labs 的"生命科学基础模型"这条更大的路线。',
  ]},
  { t: '它跟病理基础模型（pathology foundation model）的区别', body: [
    '输入不同：病理基础模型学的是"图片"——数字病理切片（WSI）长什么样；生物大模型学的是"序列"——分子字母怎么排列。',
    '训练不同：病理模型多用"对比学习"（同一张切片的两个小图块应该长得像）；生物大模型用"掩码预测"（遮住序列猜字母）。',
    '输出不同：病理模型输出的是"这张切片像不像癌"这类诊断表征；生物大模型输出的是"这个蛋白会折成什么形状、会不会和某个药结合"这类分子层面的预测。',
    '一句话：一个是"看懂细胞长什么样"，一个是"读懂生命怎么写"。',
  ]},
];

function statRow(k, v) {
  return h('div', { class: 'at-stat' },
    h('span', { class: 'at-stat-k' }, k),
    h('span', { class: 'at-stat-v' }, v));
}

function companyCard(c) {
  return h('div', { class: `at-company accent-${c.accent}` },
    h('div', { class: 'at-company-head' },
      h('div', { class: 'at-company-name' }, c.name),
      h('div', { class: 'at-company-en' }, c.en),
      h('span', { class: 'at-tag' }, c.cat)),
    h('div', { class: 'at-company-stats' }, c.stats.map(([k, v]) => statRow(k, v))),
    h('div', { class: 'at-section-sub' }, '核心产品线'),
    ...c.lines.map(([n, d]) => h('div', { class: 'at-line' },
      h('div', { class: 'at-line-n' }, n),
      h('div', { class: 'at-line-d' }, d))),
    h('div', { class: 'at-note' }, c.note));
}

export function render(container) {
  container.append(
    /* 头图 */
    h('div', { class: 'at-hero' },
      h('div', { class: 'at-hero-kicker' }, '行业认知图谱 · 2026'),
      h('h1', { class: 'at-hero-title' }, '中国大陆 AI 医药（AI DD）三分类'),
      h('div', { class: 'at-hero-sub' }, 'AI 到底在医药行业里当"药企""外包"还是"平台"，决定了它赚什么钱、怎么活。')),
    h('div', { class: 'section-title' }, '三种活法'),

    /* 三分类 */
    h('div', { class: 'at-cat-grid' },
      CATEGORIES.map((c) => h('div', { class: `at-cat accent-${c.accent}` },
        h('div', { class: 'at-cat-no' }, c.no),
        h('div', { class: 'at-cat-name' }, c.name),
        h('span', { class: 'at-tag' }, c.tag),
        h('div', { class: 'at-cat-def' }, c.def),
        h('div', { class: 'at-cat-rep' }, `代表：${c.rep}`),
        h('div', { class: 'at-cat-model' }, c.model)))),
    h('div', { class: 'at-hint' }, '三类不是非此即彼——很多公司会横跨两类，但每个公司的主叙事总落在其中一类。'),

    /* 公司深读 */
    h('div', { class: 'section-title' }, '代表公司深读'),
    h('div', { class: 'at-company-list' }, COMPANIES.map(companyCard)),

    /* 生物大模型 */
    h('div', { class: 'section-title' }, '重点：生物大模型是什么'),
    h('div', { class: 'at-bio' },
      BIO_MODEL.map((s, i) => h('div', { class: 'at-bio-sec' },
        h('div', { class: 'at-bio-q' }, `${i + 1}. ${s.t}`),
        ...s.body.map((p) => h('p', { class: 'at-bio-p' }, p))))),

    h('div', { class: 'at-foot' }, '认知更新：2026-08 · 数据来自公开报道，融资/估值以官方披露为准'));
}
