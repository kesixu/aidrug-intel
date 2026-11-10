# 见微 · AI for Science 大陆情报系统

> 见微知著 —— 系统看见微弱信号，你得到大局判断。

私人 AI 情报分析师：自动追踪中国大陆 AI for Science / 生物医药领域的**政策更新**与**企业动态**，用 DeepSeek 逐条深读并按你的决策维度打分，每天早晨给你一份 3 分钟晨报，随时可对话追问（带引用溯源），并根据你的反馈每周自进化。

线上：`aidrug.kesixu.com`（nginx basic-auth）· 手机/桌面自适应双形态

## 它怎么工作

```
sources.yml（分层情报源）
   │  每30分钟检查到期源（各源独立频率）
   ▼
采集流水线  抓取(ETag) → 解析(RSS/HTML/JSON) → 关键词门控 → Jaccard去重 → 入库
   ▼
AI 分析师（deepseek-flash）
   携带你的兴趣画像逐条深读 → 摘要/分类/实体/申报截止日
   + 五个决策维度各打 0-100 分并给理由
   → final = 0.55·个性化 + 0.25·行业重要性 + 0.20·来源权威
   → 🔴必读 ≥75 · 🟠关注 ≥60 · 🔵扫一眼 ≥45 · ⚪归档
   ▼
产品面
   今日：晨报（07:30 生成）+ 临期申报提醒
   情报：个性化情报流（过滤/检索/收藏/跟进）
   问　：对话分析师（FTS 检索增强 + [n] 引用，SSE 流式）
   洞察：实体时间线 + 政策脉络生命周期
   我的：画像/权重/关键词编辑 + 进化建议一键采纳 + 源健康 + 费用
   ▼
反馈闭环   👍👎⭐🚩 → 每周日 21:00 AI 复盘 → 建议（用户确认制，绝不静默改画像）
```

## 快速开始

```bash
# 依赖（系统 python3，本项目约定不用 venv）
pip3 install --user -r requirements.txt

# 配置（.env 已 gitignore）
echo 'DEEPSEEK_API_KEY=sk-...' > .env

# 开发
python3 -m uvicorn app.main:app --host 127.0.0.1 --port 8010 --reload

# 测试（含无头浏览器冒烟；本机有 Chrome，或先 python3 -m playwright install chromium）
python3 -m pytest tests/ -q

# 手动采集/分析（不经 Web）
python3 -m app.ingest.pipeline --all
python3 -m app.llm.analyst
```

生产（在 Kumo 上）：

```bash
cd /home/oliver/projects/aidrug
git pull
sudo systemctl restart aidrug
```

unit 见 `aidrug.service`。**必须单 worker**，调度器在进程内，不要加 `--workers`。nginx 配置见 `nginx-aidrug.conf`：整站 basic auth，`/api/v1/chat/stream` 单独关掉 `proxy_buffering`，避免 SSE 被攒住。

## 关键文件

| 路径 | 职责 |
|---|---|
| `config/sources.yml` | 情报源注册表（加源=改这里） |
| `app/ingest/` | 抓取/解析/去重流水线 |
| `app/llm/` | DeepSeek 客户端、分析师、晨报、对话、进化 |
| `app/api/` | REST API（/api/v1，文档 /api/docs） |
| `app/scheduler.py` | 进程内调度（Asia/Shanghai） |
| `static/` | 前端（无构建 Vanilla ES modules，设计令牌在 `static/css/app.css`） |
| `static/js/data/companies.js` | 药企深读档案（「公司」专栏数据源，加一家公司=加一条对象） |
| `docs/plans/2026-07-07-rebuild-v1.md` | 完整设计文档 |
| `docs/research/` | 外部技术报告/论文的深度分析（含原件索引） |
| `data/raw/` | 外部原件（PDF/文本，gitignored） |

## 界面

2026-11 这一轮只改阅读体验，API 形状没变。

- 今日按北京时间。先放临期，再放必读卡片，晨报正文在下面，不用先翻完长文才看见截止日。
- 情报可以同时按级别、分类、收藏、跟进、临期筛，搜索和筛选叠在一起。桌面用 `j` `k` 移动、回车打开、`s` 收藏、`f` 跟进、`/` 搜索，`g` 再加一个字母换页，`?` 看全部快捷键。
- 问是 SSE。`[n]` 一出现就能点。换会话不刷新整页。
- 手机底部五个键：今日、情报、问、公司、我的。洞察和图谱在顶栏「更多」里，桌面侧栏仍是全部入口。
- 颜色、字号、间距都是 `app.css` 里的变量。暗色默认，亮色跟系统或在「我的」里切换。没有构建步骤。

本地看界面（不调用 DeepSeek）：

```bash
AIDRUG_DB_PATH=/tmp/aidrug-demo.db AIDRUG_SCHEDULER_ENABLED=false \
  DEEPSEEK_API_KEY=sk-demo python3 scripts/seed_fixture.py
AIDRUG_DB_PATH=/tmp/aidrug-demo.db AIDRUG_SCHEDULER_ENABLED=false \
  DEEPSEEK_API_KEY=sk-demo python3 -m uvicorn app.main:app --host 127.0.0.1 --port 8010
```

## 运维速查

- 健康：`curl -s localhost:8010/healthz`；源健康与费用看「我的」页或 `GET /api/v1/system/status`
- 日志：`journalctl -u aidrug -f` + `workspace/logs/YYYY-MM-DD.jsonl`
- 数据：`data/aidrug.db`（SQLite WAL，备份=拷文件；旧版 `intel_entries` 表原样保留）
- 费用：flash 做批量分析、pro 只做晨报/对话/进化；「我的→系统」有月度估算
