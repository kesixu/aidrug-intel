# AGENTS.md — 见微 · AI for Science 大陆情报系统

> 继承 `~/projects/AGENTS.md`。产品/架构全貌见 `README.md` 与 `docs/plans/2026-07-07-rebuild-v1.md`。

## 定位

私人 AI 情报分析师（单用户产品）。自动采集大陆 AI4S/生物医药政策与企业动态 → DeepSeek 按用户画像逐条深读打分 → 晨报/情报流/对话/进化。
服务用户三个决策：AZ 北京（亦庄）职业机会、TrustPathBot 市场定位、UK vs 大陆定居。

## 技术栈与硬约束

- FastAPI + SQLAlchemy 2.0 + SQLite（WAL + FTS5/jieba）；前端 Vanilla ES modules（**禁止引入 React/Vue/jQuery/构建工具**）
- LLM：DeepSeek `v4-flash`（批量分析）/ `v4-pro`（晨报/对话/进化），key 只放 `.env`（**绝不入 git**）
- 调度：APScheduler **进程内** → uvicorn **必须单 worker**，勿加 `--workers`
- 服务器是 UTC；所有调度显式 `Asia/Shanghai`，存储用 UTC ISO 字符串
- 部署：kumo VPS 端口 8010，systemd `aidrug`，nginx basic-auth 反代 `aidrug.kesixu.com`
- 依赖装在系统 python3（`pip3 install --user`），不用 venv

## 结构（改哪里）

```
config/sources.yml     加/改情报源（声明式；特殊结构→ app/ingest/parsers.py 加解析函数）
app/ingest/            抓取流水线（fetcher/parsers/registry/pipeline）
app/llm/               client(DeepSeek) / analyst(逐条深读) / briefing / chatsvc / evolver
app/api/               /api/v1 路由（feed/brief/chat/profile/system）
app/scheduler.py       定时任务（采集tick/补分析/晨报07:30/进化周日21:00）
app/seeds.py           决策维度/画像/实体种子 + v0.1 数据导入
static/                前端：css/app.css 设计令牌；js/views/* 五视图；js/app.js 路由外壳
tests/                 pytest（改核心逻辑必须跑：python3 -m pytest tests/ -q）
```

## 领域规则

- 条目评分：`final = 0.55·维度加权 + 0.25·importance + 0.20·来源权威`；分级阈值 75/60/45（改动要同步 analyst.py 与前端印章徽记语义）
- 去重：URL sha1 硬去重 + 标题实义词 Jaccard ≥0.7 软去重（`_TITLE_STOP` 剔除公文模板词，改前先看 tests/test_textutil.py 的校准样例）
- 媒体源必须 `gate: true`（画像关键词门控）；政府源不门控
- LLM 输出全部过 `_normalize` 钳制；进化建议只入 pending，**绝不静默改画像**
- 单源故障必须隔离（pipeline 已兜底），新代码不得破坏此性质

## 上线前检查

1. `python3 -m pytest tests/ -q` 全绿
2. 冒烟：`curl -s localhost:8010/healthz`、`/api/v1/feed?limit=1`、`/api/v1/system/status`
3. 重启后 `journalctl -u aidrug -n 20` 无异常、`scheduler.started` 事件在场
4. 涉及 auth/抓取行为的改动先跑 `/security-review`
