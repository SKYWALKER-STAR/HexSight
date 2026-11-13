# HexSight

HexSight 是一个 LOL 职业赛事态势分析工具。手动输入 Cito `gameId`，即可开始采集、查看双方经济和资源差、五路对位及最近 30 分钟的优势趋势。

第一版依据仓库中的 `HexSight_desgin_v1.2_MVP.docx` 实现。优势分是可解释的启发式指标，**不是获胜概率**。数据缺失不补零，数据过期或时间戳未知时暂停判断。

## 已实现

- 手动添加比赛、开始/停止、多个任务切换；同一 gameId 的重复启动幂等。
- 蓝红双方经济、击杀、防御塔、小龙、大龙、水晶对比。
- 根据明确角色匹配五路，展示英雄、经济/CS/等级差、双方 KDA、装备 ID 和解释。
- 总体优势方向、强度、动态权重和可信度；打野/辅助仅展示基础发育差异。
- REST + WebSocket 实时刷新，浏览器断线指数退避重连并通过 REST 补偿。
- 30 分钟趋势、源时间戳、采集时间、延迟、过期提示、套餐延迟提示和错误原因。
- 连接/读取超时、429 Retry-After、5xx/网络退避、权限错误终止、连续失败/空数据阈值。
- 重复帧和旧帧过滤；比赛结束自动停止；赛后数组响应兼容。
- 内存历史窗口；可选 Redis 缓存/任务状态与 ClickHouse 历史持久化，故障时降级。
- 中文响应式页面、Docker Compose、离线演示、自动化测试。

本期不包含比赛自动发现、AI 胜率训练、赛前预测、英雄坐标、技能 CD 推断、Kafka、多节点采集和公网用户认证。

## 本次真实接口验证

2026-11-12（北京时间），使用以下用户提供的标识完成真实请求：

```text
gameId:  lol-game-117393592614464355
matchId: lol-match-117393592614464354
```

两个端点均返回 HTTP 200。比赛级 coverage 的 `numeric_live_state=true`，但该具体小局已经结束：stats 返回 10 名选手的最终统计数组，明确标记不是活动实时数据源，且没有 `frameTimestamp`。因此程序展示已知的赛后选手数据、暂停优势判断并自动停止采集；不会伪造当前经济、比赛时钟或实时优势。

真实验证记录位于 [docs/verification](docs/verification)，赛后脱敏响应固定在 [tests/fixtures/cito_completed.json](tests/fixtures/cito_completed.json)。**当前已验证鉴权和赛后响应适配，尚未完成进行中比赛连续更新 10 分钟的验收**。这需要另一个正在进行且有数值覆盖的 gameId。

## 快速启动

推荐 Linux/macOS、Python 3.11+、Node.js 22+。采集进程通过 POSIX 文件锁限制单机单实例；Windows 请使用 WSL 或 Docker。

在仓库根目录执行：

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
cp -n .env.example .env
```

在 `.env` 中填写 `CITO_API_KEY`。如果本地已经配置好，请保留现有 `.env`。密钥只在后端使用，不要配置任何 `VITE_*` 密钥变量，也不要提交 `.env`。

启动后端：

```bash
uvicorn backend.app.main:app --host 127.0.0.1 --port 8000 --workers 1
```

另一个终端启动前端：

```bash
cd frontend
npm ci
npm run dev
```

打开 <http://127.0.0.1:5173>，输入 gameId；matchId 可选，用于采集前验证 `numeric_live_state`。点击「开始监控」。前端开发服务器代理 `/api` 和 `/ws` 到本机 8000 端口。

- API 交互文档：<http://127.0.0.1:8000/docs>
- 存活检查：<http://127.0.0.1:8000/health>
- 依赖就绪：<http://127.0.0.1:8000/ready>

服务启动后不会自动采集，需用户点击开始。**始终只运行一个采集 worker**，不要同时启用多个 uvicorn worker 或多个后端容器。`WEB_CONCURRENCY` 检查和本机文件锁用于防止重复采集，跨容器/跨机器仍需部署层限制为一个副本。

## 不消耗 API 配额的演示模式

无需密钥：

```bash
DEMO_MODE=true POLL_INTERVAL_SECONDS=3 uvicorn backend.app.main:app --host 127.0.0.1 --port 8000 --workers 1
```

前端输入 `demo-game` 等合法标识即可。页面会持续显示「演示模式」提示，数据来源为合成测试数据。真实 API 请求失败时不会自动切换演示模式。

## Docker 部署

先创建并配置根目录 `.env`，然后在仓库根目录运行：

```bash
docker compose --env-file .env -f deploy/docker-compose.yml up --build -d
```

访问 <http://127.0.0.1:8080>。默认只运行后端和 Nginx 前端，不需要数据库；端口仅绑定本机。

需要持久化时，修改 `.env`：

```dotenv
REDIS_URL=redis://redis:6379/0
CLICKHOUSE_URL=http://clickhouse:8123
CLICKHOUSE_USER=hexsight
CLICKHOUSE_PASSWORD=请替换为自己设置的密码
CLICKHOUSE_DATABASE=hexsight
```

然后启用存储 profile：

```bash
docker compose --env-file .env -f deploy/docker-compose.yml --profile storage up --build -d
```

Redis 和 ClickHouse 仅在 Compose 内网提供服务，数据保存在命名卷。首次初始化时后端可能短暂降级，存储恢复后后续写入会自动重试。不要在已有 ClickHouse 数据卷上直接更改账号而忽略数据库端的权限配置。

停止服务（保留存储卷）：

```bash
docker compose --env-file .env -f deploy/docker-compose.yml --profile storage down
```

## 配置说明

配置从根目录 `.env` 和进程环境变量读取，环境变量优先。完整默认值见 [.env.example](.env.example) 和 [backend/app/config.py](backend/app/config.py)。

| 配置 | 默认值 | 含义 |
| --- | --- | --- |
| `CITO_API_KEY` | 空 | 服务端密钥 |
| `CITO_BASE_URL` | `https://api.citoapi.com/api/v1` | Cito API 根路径 |
| `POLL_INTERVAL_SECONDS` | 30 | 每场正常采集间隔，最小 1 秒 |
| `CONNECT_TIMEOUT` / `READ_TIMEOUT` | 5 / 10 | 连接、读取超时，秒 |
| `MAX_RETRY_BACKOFF` | 30 | 网络/5xx 指数退避上限，含随机抖动 |
| `MAX_CONSECUTIVE_FAILURES` | 5 | 连续失败达到阈值后进入 error |
| `MAX_EMPTY_RESPONSES` | 3 | 连续空响应达到阈值后停止 |
| `STALE_THRESHOLD_SECONDS` | 120 | 超过阈值暂停当前优势判断 |
| `REQUEST_BUDGET` | 500 | 本进程累计调用上限，0 为不限；覆盖检查及失败重试也计数 |
| `MAX_MONITORS` | 10 | 同时运行任务上限 |
| `HISTORY_WINDOW_MINUTES` | 30 | 内存保留时长 |
| `HISTORY_MAX_POINTS` | 1800 | 每场历史点数上限 |
| `REDIS_URL` | 空 | 空表示禁用 |
| `REDIS_TTL_SECONDS` | 86400 | 最新快照和任务状态 TTL |
| `CLICKHOUSE_URL` | 空 | 空表示禁用；使用 HTTP 接口（通常 8123） |
| `CORS_ORIGINS` | 本机 5173、8080 | JSON 数组格式的来源白名单，也用于 WebSocket Origin 检查 |
| `DEMO_MODE` | false | 显式开启合成数据源 |

429 优先遵守 `Retry-After`（支持秒数和 HTTP 日期），即使它超过 30 秒也不会提前重试。连续 429 同样受失败次数上限约束。请求预算是进程级保护，重启清零，不等于 Cito 套餐剩余额度。多场每 30 秒轮询会叠加消耗。

## 评分与缺失字段

总体分数范围为 `[-100, 100]`：正数蓝方领先，负数红方领先，绝对值小于 10 为均势。页面中央展示优势强度的绝对值；趋势保留符号。

默认权重：经济 0.60、地图资源 0.25、防御塔 0.15。地图资源权重在已知的小龙、大龙、水晶差之间均分。每项差值除以量纲后截断到 `[-1,1]`，只使用双方都有值的分项，再归一化可用权重。

- 经济量纲：`max(3000, 比赛分钟数 × 300)`；比赛时间缺失时使用 3000 并降低可信度，标记 `game_time_unknown`。
- 防御塔 / 小龙 / 大龙 / 水晶量纲：5 / 3 / 2 / 3。
- 击杀只展示解释，不重复加入高权重计分。
- TOP/MID/BOT 的个人经济、CS、等级默认权重 0.65 / 0.25 / 0.10；量纲 2000 / 50 / 3。个人经济缺失时降低可信度。
- JUNGLE/SUPPORT 仅展示差值与 KDA、装备，不使用线上补刀评分。
- 缺失、非数值、负值和非有限数值视为未知；不能依据选手数组顺序猜测角色。
- 时间戳必须为带时区的 ISO 格式。缺失、异常未来时间、过期数据都暂停当前判断。
- `confidence` 表示已知输入的完整程度，不是统计校准过的置信概率。

权重、量纲和均势阈值集中在 `Settings` 中，均可通过同名大写环境变量调整。公式尚未经过历史回测。

## Cito 契约和验证工具

基于 [Cito 官方 LOL 文档](https://citoapi.com/docs/api/league-of-legends/) 实现：

- `GET /lol/live/{gameId}/stats`：核心采集；不调用 `/lol/live` 自动搜索赛事。
- `GET /lol/matches/{matchId}/coverage`：填写 matchId 时，要求 `numeric_live_state` 明确为 true。
- 实时 scoreboard：顶层 `frameTimestamp`，`data.gameId`、`data.state`、`blueTeam/redTeam` 和 `players`。
- 总经济/击杀：`totalGold/totalKills`；选手 CS：`creepScore`；角色：`side + role`。
- 小龙可以是类型数组，取明确返回的数组长度；缺失不等同于空数组。
- `data.gameTimeSeconds` 仅在明确存在时使用；官方样例及本次赛后响应均不保证该字段存在。
- 已验证的赛后分支：顶层 gameId、`coverage.numeric_live_state=false`、选手数组内 `final=true`。此时仅转换明确字段，不汇总推测团队总量或伪造帧时间。
- 原始响应留在服务端内存；可写入 ClickHouse 的快照保存 `raw_json`，不通过前端 API 暴露。

只做一次验证（最多 2 个请求）：

```bash
python -m scripts.probe_cito lol-game-117393592614464355 \
  --match-id lol-match-117393592614464354 \
  --output docs/verification/probe.json
```

工具只输出状态、字段完整度和延迟，不打印密钥。保存的响应移除密钥类字段及无关个人资料。401/403、404、无数值覆盖、非预期 schema 都会明确报错。

## 后端接口

| 方法 | 路径 | 用途 |
| --- | --- | --- |
| POST | `/api/monitors` | `{"gameId":"...","matchId":"..."}`，异步启动；返回 202 |
| DELETE | `/api/monitors/{gameId}` | 取消并等待任务清理，返回 stopped |
| GET | `/api/monitors` | 任务、请求计数、演示标志、存储告警 |
| GET | `/api/games/{gameId}/latest` | 最新态势；没有快照返回 404；读取时重新计算新鲜度 |
| GET | `/api/games/{gameId}/history?minutes=30` | 按源时间排序的历史，最大 1440 分钟和配置点数上限 |
| WS | `/ws/games/{gameId}` | snapshot/status/warning/heartbeat 消息；15 秒心跳 |
| GET | `/health` | 进程存活 |
| GET | `/ready` | 密钥配置及可选存储检查；依赖降级返回 503 |

输入 ID 为 1–64 位字母、数字、短横线、下划线，以字母或数字开头。前后端均校验。`/ready` 不会为检查健康自动消耗付费 API 请求，因此“就绪”不代表该套餐对每场比赛都有权限。

## 存储与恢复

- **内存**：默认启用；每场最多保留指定时间与点数。进程退出后丢失。
- **Redis**：`hexsight:game:{id}:latest` / `hexsight:game:{id}:status`。重启读取任务列表并一律改为 stopped，必须手动恢复采集。Redis 不可用时以内存继续运行并提示降级。
- **ClickHouse**：`game_snapshots` 使用 `ReplacingMergeTree(ingest_ts)`，以 `(game_id, frame_ts)` 排序，查询使用 `FINAL` 去重，并与当前内存数据合并。保存原始 JSON、规范化快照 JSON、经济、优势分和质量标志。
- 写入采用有界后台队列，每条最多尝试 2 次；存储故障不阻塞实时广播。队列满或写入失败会提示部分历史没有持久化，不做无限积压。
- 缺失 `source_ts` 的快照不会伪造时间写入 ClickHouse，只保留在内存和 Redis；赛后数组属于这一情况。
- 未启用 Redis 时，任务列表不会跨进程重启保留；仍可用已知 gameId 查询 ClickHouse 保存的快照与历史。
- 已知时间戳按 gameId + source_ts 去重，拒绝旧帧；无时间戳时只做内容摘要去重且不评分。无时间戳帧不能覆盖已有时间戳的最新帧。

这是单进程 MVP；没有多节点自动接管和历史无损补录承诺。

## 测试与验收

后端测试使用固定合成 fixture 和脱敏真实赛后 fixture，不持续调用 Cito：

```bash
pytest -q
```

前端生产构建与浏览器测试：

```bash
cd frontend
npm ci
npm run build
npx playwright install chromium
npm run test:e2e
```

如本机已有 Chrome，可省去下载：

```bash
CHROME_PATH=/opt/google/chrome/chrome npm run test:e2e
```

浏览器测试会自行启动**演示模式**后端（8000）和前端（5173），请先停止占用这两个端口的开发服务。测试覆盖开始/停止、页面刷新恢复、WebSocket 断线重连及 REST 补偿、过期数据、移动端布局。

可选存储集成检查：只对专用测试实例执行，会创建并删除临时 `hexsight_test_*` 数据库和随机 Redis key，不要指向共享生产实例。

```bash
TEST_REDIS_URL=redis://127.0.0.1:16379/15 \
TEST_CLICKHOUSE_URL=http://127.0.0.1:18123 \
TEST_CLICKHOUSE_USER=default TEST_CLICKHOUSE_PASSWORD=测试密码 \
python -m scripts.check_storage
```

实时验收流程：使用进行中的 gameId，开始监控至少 10 分钟，确认源时间戳连续变化、延迟可接受、趋势不断追加；测试断网恢复后，点击停止并核对请求计数不再增长。不能用已结束比赛或演示数据替代此验收。

## 目录

```text
backend/app/
  api/routes.py             REST 与 WebSocket
  clients/cito.py           鉴权、HTTP 错误分类与预算
  clients/demo.py           显式离线演示数据源
  services/monitor.py       任务去重、重试、停止与清理
  services/normalizer.py    官方 scoreboard 与已验证赛后响应适配
  services/advantage.py     可解释优势评分
  services/events.py        有界客户端消息队列
  models/domain.py         数据结构、新鲜度规则
  storage/repository.py    内存、Redis、ClickHouse
  config.py / main.py       配置、启动与依赖生命周期
frontend/src/
  pages/Dashboard.tsx       中文单页监控面板
  components/Trend.tsx      最近 30 分钟趋势
  hooks/useMonitor.ts      推送、重连、REST 补偿
  api/                     类型与请求封装
tests/                     后端单元及集成测试
frontend/e2e/              浏览器端验收测试
deploy/                    Docker Compose、Nginx
scripts/                   真实 API 验证、存储检查
docs/verification/         本次真实接口脱敏验证记录
```

## 部署边界

默认设计为本机或可信内网使用，已限制端口绑定、CORS 和 WebSocket Origin。公网部署前应增加统一认证、入口限流和 TLS，并同步修改来源白名单；CORS 本身不是认证。当前依赖仓库配置提供的服务端凭证，不在浏览器存储密钥或记录敏感响应日志。


## REST + webhook ????????

?????? REST stats ?????? Cito ?? Live WebSocket?
?? `/ws/games/{game_id}` ?????????????????????
???? Cito ?? WebSocket ??????????????

????????? `CITO_WEBHOOK_SECRET` ? Cito ?????????????
???? HTTPS ???? `POST /api/webhooks/cito`????????? 503?
??? `lol.live.state`?`lol.live.game_started`?`lol.score.updated`?
`lol.game.completed`?`lol.match.completed`?? matchId ????????????
? Cito ????????????????????

????????? gameId ????? matchId??????? webhook ???
??????? REST????????????????????? webhook
???? scoreboard???????????????? 10000 ? ID???????
????????????????????????? 5 ?????????
5 ??????????????? POLL_INTERVAL_SECONDS ???
429 Retry-After ???????? webhook ???????? REQUEST_BUDGET?
???????? REST ????????????????

??????????? Linux ? worker ????????????????
????????????????????????? numeric_live_state ???
?????https://citoapi.com/docs/webhooks/
