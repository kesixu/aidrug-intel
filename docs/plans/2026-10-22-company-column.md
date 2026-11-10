# 药企深读专栏（2026-10-22）

**目标**：在「见微」里开一个常设专栏，存放各家药企的深度档案，替代散落在聊天和公众号里的分析。

**改动文件**
- 新增 `static/js/data/companies.js`（档案数据，加公司=加一条对象）
- 新增 `static/js/views/companies.js`（列表 + 详情，移动优先）
- 改 `static/js/app.js`（import、ICONS、VIEWS 各加一项）
- 改 `static/css/app.css`（追加 `.co-*` 样式）
- 新增本计划文件

**不动的**：后端、数据库、抓取流水线、调度器。专栏是编辑内容，不走采集分析链路。

**风险**：低。唯一影响面是前端导航多一个 tab（7 个），tabbar 用 `flex:1` 自适应，无需改布局规则。
每条结论带证据分级（A 官方 / C 主流媒体 / D 自媒体待核），页面顶部有图例。

**验收**：`python3 -m pytest tests/ -q` 全绿；`uvicorn` 起本地实例，`curl` 首页与新 JS 资源 200；浏览器打开 `#/companies` 列表与详情可切换。
