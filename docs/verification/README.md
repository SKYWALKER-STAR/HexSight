# 第一版验证记录

日期：2026-11-12（Asia/Shanghai）。

## 真实 Cito 请求

- `coverage.json`：`lol-match-117393592614464354` 的 coverage 请求，HTTP 200。
- `stats.json`：`lol-game-117393592614464355` 的 stats 请求，HTTP 200。返回赛后数组，已移除无关个人资料及媒体地址。
- 赛后统计没有 `frameTimestamp`，不能验证实时帧延迟；该小局已结束，程序应自动停止，不能把 match 级 coverage=true 当成小局仍在进行的证明。
- 进行中比赛连续更新 10 分钟的 P1 验收仍待可用的实时 gameId。

## 自动化验证

- 后端：52 项测试，包括优势方向、缺失字段、角色错配、401/403、404、429、5xx、超时、取消、请求预算、重复启动、旧帧/重复帧/未来帧、赛后结束、API/WebSocket、Redis 降级、ClickHouse 有界重试等。
- 前端：生产构建通过；3 项 Playwright 浏览器测试通过，覆盖手动开始/停止、刷新恢复、WebSocket 重连与 REST 补偿、过期数据、缺失字段和 390px 移动端布局。
- 依赖：Python `pip check` 通过；npm 安装完成后 audit 为 0 项漏洞。
- 部署：Docker Compose 默认与 storage profile 的配置校验通过。由于 Docker Hub 网络超时，未完成容器镜像构建/启动验证。
- 真实存储：使用本机 Redis 8.8.0、ClickHouse 26.3.4.11 启动隔离临时实例，验证最新快照/状态、重启改为 stopped、历史持久化、重复写入查询去重、缓存缺失后从 ClickHouse 回读。检查通过，临时服务已停止，临时数据库和测试 key 已清理。Compose 声明的 Redis 7 / ClickHouse 25.3 镜像尚未实测。

以上测试不代替进行中比赛的实时验收，也不证明评分公式具有统计预测能力。
