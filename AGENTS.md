# AGENTS.md — AI for Science 大陆情报系统

> 继承 `~/projects/AGENTS.md`

## 定位

AI for Science 大陆情报追踪看板。Phase 1 聚焦北京 · 亦庄 BioPark。
为 AstraZeneca Beijing 职业决策 + TrustPathBot 市场定位 + UK vs 大陆定居决策提供持续情报支持。

## 技术栈

- 后端：FastAPI + SQLite（`app/main.py`）
- 前端：Vanilla JS SPA（`static/index.html` + `static/js/app.js`）
- 部署：kumo VPS，端口 8010，nginx 反代
- 域名：`aidrug.kesixu.com`

## 文件结构

```
app/main.py          — FastAPI 路由
app/models.py        — SQLAlchemy 模型
static/index.html    — 前端入口
static/css/style.css — 样式
static/js/app.js     — 前端逻辑
data/aidrug.db       — SQLite 数据库（gitignored）
```

## 启动

```bash
# 生产环境用 systemd
sudo systemctl start aidrug

# 开发环境
cd /home/oliver/projects/aidrug
/usr/bin/python3 -m uvicorn app.main:app --host 127.0.0.1 --port 8010 --reload
```

注意：Python 依赖安装在系统 python3（`/usr/bin/python3`），不在 Hermes venv 中。

## 数据 Schema

见 `app/models.py` 的 `IntelEntry`。核心字段：
- id: intel_YYYYMMDD_NNN
- relevance_score: {overall, az_beijing, trustpathbot, talent_program, funding_opportunity}
- policy_family + policy_stage 用于生命周期追踪

## 禁止

- 不要引入 React/Vue/jQuery
- 不要在 git tracked 文件里写 API key
- 部署前跑冒烟测试
