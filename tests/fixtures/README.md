# 测试数据来源

- `board.json`：依据 Cito 官方 LOL scoreboard 字段手工构造的**合成** fixture，gameId 为 `test-1`；pytest 在每个测试中注入当前时间戳。不是任何真实比赛的实时快照。
- `cito_completed.json`：2026-11-12 对用户提供的 `lol-game-117393592614464355` 实际请求返回的赛后统计，删去实名、图片、UUID、符文等与 MVP 无关字段。保留字段值未修改。不存在实时帧时间戳，因此不能用于证明实时采集或延迟。

测试不使用 `.env` 中的真实密钥，也不调用付费 Cito 端点。真实验证概况见 `docs/verification/`。
