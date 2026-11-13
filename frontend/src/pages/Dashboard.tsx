import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  Activity,
  ChevronRight,
  CircleHelp,
  Clock3,
  Database,
  Gamepad2,
  Hexagon,
  Play,
  Radio,
  Shield,
  Signal,
  Square,
  Swords,
  Target,
  Timer,
  Waves,
  Zap,
} from 'lucide-react'
import { api } from '../api/client'
import type { MonitorList, Snapshot, Team } from '../api/types'
import { useMonitor } from '../hooks/useMonitor'
import { Trend } from '../components/Trend'

const format = (v: number | null | undefined) => (v == null ? '—' : v.toLocaleString('zh-CN', { maximumFractionDigits: 0 }))
const signed = (v: number | null | undefined) => (v == null ? '—' : `${v > 0 ? '+' : ''}${format(v)}`)
const clock = (v: string | null | undefined) => (v ? new Date(v).toLocaleString('zh-CN', { hour12: false }) : '未知')
const roles: Record<string, string> = { TOP: '上路', JUNGLE: '打野', MID: '中路', BOT: '下路', SUPPORT: '辅助' }
const stateNames = { running: '监控中', stopped: '已停止', paused: '已暂停', error: '采集异常' }
const factors: Record<string, string> = { gold: '经济', towers: '防御塔', dragons: '小龙', barons: '大龙', inhibitors: '水晶' }
const confidence: Record<string, string> = { high: '高', medium: '中', low: '低', unknown: '未知' }
const emptyList: MonitorList = { items: [], requests_used: 0, request_budget: 0, demo_mode: false, warnings: [] }

function formatClock(seconds: number | null | undefined) {
  if (seconds == null || !Number.isFinite(seconds)) return '—'
  const s = Math.max(0, Math.floor(seconds))
  const mm = String(Math.floor(s / 60)).padStart(2, '0')
  const ss = String(s % 60).padStart(2, '0')
  return `${mm}:${ss}`
}

function TeamPanel({ team, side }: { team?: Team; side: 'blue' | 'red' }) {
  return (
    <div className={`team-panel ${side}`}>
      <div className="team-heading">
        <span className="team-insignia">
          <Shield size={22} />
        </span>
        <div>
          <span className="eyebrow">{side === 'blue' ? 'BLUE SIDE' : 'RED SIDE'}</span>
          <h2>{team?.name || (side === 'blue' ? '蓝色方' : '红色方')}</h2>
        </div>
      </div>
      <div className="gold-number">
        {format(team?.gold)}
        <span>总经济</span>
      </div>
      <div className="team-metrics">
        <span>
          <Swords size={14} />
          <strong>{format(team?.kills)}</strong>击杀
        </span>
        <span>
          <Shield size={14} />
          <strong>{format(team?.towers)}</strong>防御塔
        </span>
      </div>
      <div className="objectives">
        <span>
          小龙 <b>{format(team?.dragons)}</b>
        </span>
        <span>
          大龙 <b>{format(team?.barons)}</b>
        </span>
        <span>
          水晶 <b>{format(team?.inhibitors)}</b>
        </span>
      </div>
    </div>
  )
}

function Metric({ label, value, hint, tone }: { label: string; value: string; hint?: string; tone?: string }) {
  return (
    <div className={`metric ${tone || ''}`.trim()}>
      <div className="metric-label">{label}</div>
      <div className="metric-value">{value}</div>
      {hint && <div className="metric-hint">{hint}</div>}
    </div>
  )
}

function LaneCard({ role, name, lane, fresh }: { role: string; name: string; lane: Snapshot['lanes'][number] | undefined; fresh: boolean }) {
  const diffGold = lane?.differences.gold
  const diffCs = lane?.differences.cs
  const diffLevel = lane?.differences.level
  const score = fresh ? lane?.advantage.score ?? null : null
  const direction = lane?.reason ? 'unknown' : lane?.advantage.direction
  const statusLabel = lane?.reason
    ? (role === 'JUNGLE' || role === 'SUPPORT') && lane?.blue && lane?.red
      ? '仅展示差异'
      : '无法匹配'
    : score == null
      ? '—'
      : signed(score)
  const tone = lane?.reason ? '' : direction
  const icon = role === 'JUNGLE' ? <Waves size={14} /> : role === 'SUPPORT' ? <Shield size={14} /> : <Target size={14} />
  const blue = lane?.blue || null
  const red = lane?.red || null
  const blueKda = [blue?.kills, blue?.deaths, blue?.assists].map(format).join(' / ')
  const redKda = [red?.kills, red?.deaths, red?.assists].map(format).join(' / ')
  return (
    <div className={`lane-card ${tone}`}>
      <div className="lane-card-head">
        <div className="lane-role">
          <span className="lane-role-icon">{icon}</span>
          <div>
            <div className="lane-role-name">{name}</div>
            <div className="lane-role-en">{role}</div>
          </div>
        </div>

        <div className="lane-sides">
          <div className="lane-side blue">
            <div className="lane-player">{blue?.name || '—'}</div>
            <div className="lane-champion">{blue?.champion || '英雄未知'}</div>
          </div>
          <div className="lane-mid">
            <div className="lane-badge">
              <span className="lane-badge-title">经济差</span>
              <span className="lane-badge-value">{signed(diffGold)}</span>
            </div>
            <div className="lane-badge-sub">
              CS {signed(diffCs)} · 等级 {signed(diffLevel)}
            </div>
          </div>
          <div className="lane-side red">
            <div className="lane-player">{red?.name || '—'}</div>
            <div className="lane-champion">{red?.champion || '英雄未知'}</div>
          </div>
        </div>
      </div>

      <div className="lane-card-body">
        <div className="lane-stat">
          <span className="lane-stat-key">KDA</span>
          <span className="lane-stat-val blue">{blueKda}</span>
          <span className="lane-stat-val red">{redKda}</span>
        </div>
        <div className="lane-stat">
          <span className="lane-stat-key">经济</span>
          <span className="lane-stat-val blue">{format(blue?.gold)}</span>
          <span className="lane-stat-val red">{format(red?.gold)}</span>
        </div>
        <div className="lane-stat">
          <span className="lane-stat-key">补刀</span>
          <span className="lane-stat-val blue">{format(blue?.cs)}</span>
          <span className="lane-stat-val red">{format(red?.cs)}</span>
        </div>
        <div className="lane-stat">
          <span className="lane-stat-key">等级</span>
          <span className="lane-stat-val blue">{format(blue?.level)}</span>
          <span className="lane-stat-val red">{format(red?.level)}</span>
        </div>
      </div>

      <div className="lane-card-foot">
        <span className={`lane-score ${tone}`} title={lane?.reason || lane?.advantage.note}>
          {statusLabel}
        </span>
        {lane && (
          <details>
            <summary>详情</summary>
            <div>
              蓝方经济 / CS / 等级：{[blue?.gold, blue?.cs, blue?.level].map(format).join(' / ')}
              <br />
              红方经济 / CS / 等级：{[red?.gold, red?.cs, red?.level].map(format).join(' / ')}
              <br />
              蓝方装备：{blue?.items?.join('、') || '—'}
              <br />
              红方装备：{red?.items?.join('、') || '—'}
              <br />
              {lane.reason || lane.advantage.note}
            </div>
          </details>
        )}
      </div>
    </div>
  )
}

function SnapshotFeed({ items, now }: { items: Snapshot[]; now: number }) {
  const rows = useMemo(() => {
    const recent = items
      .filter(s => s.source_ts)
      .slice(-12)
      .reverse()
    return recent.map(s => {
      const ts = s.source_ts || s.ingest_ts
      const age = ts ? (now - new Date(ts).getTime()) / 1000 : null
      const score = s.advantage.score
      const direction = score == null ? 'unknown' : s.advantage.direction
      return {
        key: ts,
        ts,
        age,
        direction,
        score,
        label: ts ? new Date(ts).toLocaleTimeString('zh-CN', { hour12: false }) : '未知',
      }
    })
  }, [items, now])

  return (
    <div className="snapshot-feed" aria-label="快照列表">
      {!rows.length && <div className="empty">等待快照写入，开始绘制与回放</div>}
      {rows.map(r => (
        <div key={r.key} className={`snapshot-row ${r.direction}`}>
          <span className="snapshot-time">{r.label}</span>
          <span className="snapshot-score">{r.score == null ? '—' : r.score.toFixed(1)}</span>
          <span className="snapshot-age">{r.age == null ? '—' : `${Math.max(0, r.age).toFixed(0)}s`}</span>
        </div>
      ))}
    </div>
  )
}

export function Dashboard() {
  const [gameInput, setGameInput] = useState(() => localStorage.getItem('hexsight.game') || '')
  const [matchInput, setMatchInput] = useState('')
  const [gameId, setGameId] = useState(() => localStorage.getItem('hexsight.game') || '')
  const [list, setList] = useState<MonitorList>(emptyList)
  const [requestError, setRequestError] = useState('')
  const [busy, setBusy] = useState(false)
  const [now, setNow] = useState(Date.now())

  const refreshList = useCallback(() => {
    void api<MonitorList>('/api/monitors')
      .then(setList)
      .catch(() => setRequestError('后端连接失败，请检查服务是否启动'))
  }, [])

  const { snapshot, history, status: pushStatus, connection, error, warnings } = useMonitor(gameId, refreshList)
  const status = pushStatus || list.items.find(m => m.game_id === gameId)

  useEffect(() => {
    refreshList()
    const t = setInterval(refreshList, 10000)
    return () => clearInterval(t)
  }, [refreshList])

  useEffect(() => {
    const t = setInterval(() => setNow(Date.now()), 1000)
    return () => clearInterval(t)
  }, [])

  useEffect(() => {
    if (gameId) localStorage.setItem('hexsight.game', gameId)
  }, [gameId])

  const age = snapshot?.source_ts ? (now - new Date(snapshot.source_ts).getTime()) / 1000 : null
  const fresh =
    age != null &&
    age >= -5 &&
    age <= (snapshot?.stale_threshold_seconds || 120) &&
    snapshot?.freshness === 'fresh'
  const score = fresh ? snapshot?.advantage.score ?? null : null
  const direction = score == null ? 'unknown' : snapshot!.advantage.direction
  const label = { blue: '蓝方领先', red: '红方领先', even: '双方均势', unknown: snapshot ? '暂停判断' : '等待比赛数据' }[direction]
  const active = status?.state === 'running'
  const allWarnings = [...new Set([...list.warnings, ...warnings])]

  const select = (id: string) => {
    setGameId(id)
    setGameInput(id)
    setRequestError('')
  }

  async function start(event: React.FormEvent) {
    event.preventDefault()
    const id = gameInput.trim(), match = matchInput.trim()
    if (
      !/^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$/.test(id) ||
      (match && !/^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$/.test(match))
    ) {
      setRequestError('ID 仅允许 1–64 位字母、数字、下划线或短横线，并以字母或数字开头')
      return
    }
    setBusy(true)
    setRequestError('')
    try {
      await api('/api/monitors', {
        method: 'POST',
        body: JSON.stringify({ gameId: id, matchId: match || null }),
      })
      select(id)
      setMatchInput('')
      refreshList()
    } catch {
      setRequestError('启动失败，请检查 gameId 或后端日志')
    } finally {
      setBusy(false)
    }
  }

  async function stop() {
    if (!gameId) return
    setBusy(true)
    setRequestError('')
    try {
      await api(`/api/monitors/${gameId}`, { method: 'DELETE' })
      refreshList()
    } catch {
      setRequestError('停止失败，请稍后重试')
    } finally {
      setBusy(false)
    }
  }

  const connectionText = ({
    idle: '未连接',
    connecting: '连接中',
    connected: '推送已连接',
    reconnecting: '连接中断 · 自动重连',
  } as Record<string, string>)[connection]

  const gameClock = formatClock(snapshot?.game_seconds)
  const lag = snapshot?.lag_seconds ?? snapshot?.delayed_seconds ?? null
  const lagLabel = lag == null ? '—' : `${Math.max(0, lag).toFixed(0)}s`
  const dataAge = age == null ? '—' : `${Math.max(0, age).toFixed(0)}s`

  const headerState = status?.state ? stateNames[status.state] : '未选择比赛'
  const requestBudget = list.request_budget || '不限'

  return (
    <div className="app-shell crt-mesh">
      <aside className="rail" aria-label="导航">
        <div className="brand-icon" aria-hidden="true">
          <Hexagon />
          <span />
        </div>
        <div className="rail-active" aria-hidden="true">
          <Activity />
        </div>
        <div className="rail-bottom" aria-hidden="true">
          <CircleHelp />
        </div>
      </aside>

      <div className="workspace">
        <header className="topbar">
          <div className="brand">
            HexSight<span>赛事态势分析</span>
          </div>
          <div className="top-meta">
            <a href="/schedule">赛程与即将开赛 →</a>
            <span className="pill">LEAGUE OF LEGENDS</span>
            {list.demo_mode && <span className="pill pill-demo">演示模式</span>}
            <span className="version">MVP / 0.1</span>
          </div>
        </header>

        <main>
          <div className="page-heading">
            <div>
              <div className="eyebrow">
                <Radio size={14} /> LIVE INTELLIGENCE <ChevronRight size={14} /> MATCH OVERVIEW
              </div>
              <h1>
                把握赛场的每一次变化<span className="heading-dot">.</span>
              </h1>
              <p>经济、资源与五路对位，在同一个视野里。</p>
            </div>
            <div className={`live-tag ${active ? 'on' : ''}`} aria-label="监控状态">
              <span className={`status-dot ${status?.state || ''}`} />
              {headerState}
            </div>
          </div>

          {!!allWarnings.length && (
            <div className="notice" role="status">
              {allWarnings.join(' · ')}
            </div>
          )}
          {list.demo_mode && (
            <div className="notice demo" role="status">
              演示模式：当前为合成测试数据，不连接真实赛事，不消耗 Cito 配额
            </div>
          )}
          {(requestError || error) && (
            <div className="notice error" role="alert">
              {requestError || error}
            </div>
          )}

          <section className="panel control-panel" aria-label="监控控制">
            <form className="monitor-form" onSubmit={start}>
              <div className="form-label">
                <Signal size={18} />
                <div>
                  <span>监控一场比赛</span>
                  <small>输入 Cito 比赛标识</small>
                </div>
              </div>
              <label>
                <span>
                  Game ID <em>必填</em>
                </span>
                <input
                  aria-label="Game ID"
                  value={gameInput}
                  placeholder="例如 demo-game"
                  onChange={e => setGameInput(e.target.value)}
                />
              </label>
              <label>
                <span>
                  Match ID <em>可选</em>
                </span>
                <input
                  aria-label="Match ID"
                  value={matchInput}
                  placeholder="用于验证数值覆盖"
                  onChange={e => setMatchInput(e.target.value)}
                />
              </label>
              <button className="primary" type="submit" disabled={busy}>
                <Play size={16} />开始监控
              </button>
              <button className="stop" type="button" onClick={stop} disabled={!active || busy}>
                <Square size={16} />停止
              </button>
            </form>

            <div className="monitor-tabs" aria-label="历史任务">
              {list.items.map(m => (
                <button
                  key={m.game_id}
                  className={m.game_id === gameId ? 'selected' : ''}
                  type="button"
                  onClick={() => select(m.game_id)}
                >
                  <span className={`status-dot ${m.state}`} />
                  {m.game_id}
                  <small>{stateNames[m.state]}</small>
                </button>
              ))}
            </div>
          </section>

          <section className="panel hud" aria-label="态势总览">
            <div className="metric-strip" aria-label="关键指标">
              <Metric label="GAME" value={gameId || '—'} hint={status?.match_id || 'matchId —'} tone="mono" />
              <Metric label="CLOCK" value={gameClock} hint={snapshot?.game_state || '—'} tone="mono" />
              <Metric label="ADV" value={label} hint={`可信度 ${confidence[fresh ? snapshot?.advantage.confidence || 'unknown' : 'unknown']}`} tone={direction} />
              <Metric label="SCORE" value={score == null ? '—' : Math.abs(score).toFixed(1)} hint="强度 / 100" tone={direction} />
              <Metric label="LAG" value={lagLabel} hint="源端延迟" tone="mono" />
              <Metric label="AGE" value={dataAge} hint={fresh ? 'fresh' : snapshot ? '数据过期' : '—'} tone={snapshot && !fresh ? 'amber' : 'mono'} />
              <Metric label="REQ" value={`${list.requests_used}`} hint={`预算 ${requestBudget}`} tone="mono" />
              <Metric label="WS" value={connectionText} hint={error ? '有告警' : '—'} tone={connection === 'connected' ? 'good' : 'mono'} />
            </div>

            <div className="versus">
              <TeamPanel team={snapshot?.blue} side="blue" />
              <div className="advantage-panel">
                <span className="eyebrow">
                  <Zap size={14} /> ADVANTAGE INDEX
                </span>
                <div className={`advantage-title ${direction}`}>{label}</div>
                <div className="score-number">
                  {score == null ? '—' : Math.abs(score).toFixed(1)}
                  <span>/ 100</span>
                </div>
                <div className="score-track" aria-label="优势强度">
                  <div className="track-center" />
                  {score != null && (
                    <div
                      className={`score-fill ${direction}`}
                      style={{ left: `${score < 0 ? 50 + score / 2 : 50}%`, width: `${Math.abs(score) / 2}%` }}
                    />
                  )}
                </div>
                <div className="track-labels">
                  <span>红方</span>
                  <span>均势</span>
                  <span>蓝方</span>
                </div>
                <p className="advantage-note">
                  <CircleHelp size={13} />优势强度，不代表获胜概率
                </p>
                <div className="score-meta">
                  <span>
                    <Timer size={13} />
                    {snapshot?.game_state || '—'}
                  </span>
                  <span>
                    <Clock3 size={13} />
                    源端 {clock(snapshot?.source_ts)}
                  </span>
                </div>
              </div>
              <TeamPanel team={snapshot?.red} side="red" />
            </div>

            <div className="factor-strip" aria-label="判断依据">
              <span>
                <Zap size={14} />判断依据
              </span>
              {fresh && snapshot?.advantage.factors.length ? (
                snapshot.advantage.factors.map(f => (
                  <span key={f.name} className="factor">
                    {factors[f.name] || f.name}差 <b>{signed(f.difference)}</b>
                    <small>权重 {Math.round(f.weight * 100)}%</small>
                  </span>
                ))
              ) : (
                <span className="factor empty">有效数据到达后显示各项差值与实际权重</span>
              )}
            </div>
          </section>

          <div className="main-grid">
            <div className="main-left">
              <section className="panel trend" aria-label="优势走势">
              <div className="section-heading">
                <h2>
                  <Activity size={16} />优势走势
                </h2>
                <span>
                  <span className="legend-dot" />优势分<span className="subtle-tag">最近 30 分钟</span>
                </span>
              </div>
              <Trend items={history} now={now} />
              <div className="trend-bottom">
                <div className="trend-note">
                  <Gamepad2 size={14} />
                  正值为蓝方领先，负值为红方领先
                </div>
                <SnapshotFeed items={history} now={now} />
              </div>
              </section>

              <section className="panel stability" aria-label="系统稳定性">
                <div className="section-heading">
                  <h2>
                    <Zap size={16} />系统韧性链路
                  </h2>
                  <span>
                    <span className="legend-dot" />超时 / 重试 / 限流 / 恢复 / 去重
                  </span>
                </div>
                <div className="stability-grid">
                  <div className="stability-item">
                    <div className="stability-title">任务状态</div>
                    <div className="stability-value">{status?.state ? stateNames[status.state] : '—'}</div>
                    <div className="stability-hint">连续失败 {status?.consecutive_failures ?? '—'} 次</div>
                  </div>
                  <div className="stability-item">
                    <div className="stability-title">下次重试</div>
                    <div className="stability-value">{clock(status?.next_retry_at)}</div>
                    <div className="stability-hint">错误码 {status?.error_code || '—'}</div>
                  </div>
                  <div className="stability-item">
                    <div className="stability-title">WebSocket</div>
                    <div className="stability-value">{connectionText}</div>
                    <div className="stability-hint">告警 {error ? '存在' : '—'}</div>
                  </div>
                  <div className="stability-item">
                    <div className="stability-title">请求计数</div>
                    <div className="stability-value">{list.requests_used}</div>
                    <div className="stability-hint">预算 {requestBudget}</div>
                  </div>
                </div>
              </section>
            </div>

            <section className="panel lanes" aria-label="五路对位">
              <div className="section-heading">
                <h2>
                  <Swords size={16} />五路对位
                </h2>
                <span>
                  经济差额 · 补刀 · 等级 · KDA<span className="subtle-tag">字段缺失显示 —</span>
                </span>
              </div>
              <div className="lane-cards">
                {Object.entries(roles).map(([role, name]) => (
                  <LaneCard
                    key={role}
                    role={role}
                    name={name}
                    lane={snapshot?.lanes.find(l => l.role === role)}
                    fresh={fresh}
                  />
                ))}
              </div>
              <div className="table-note">缺失字段显示「—」；角色无法可靠匹配时禁用评分。打野与辅助只展示发育维度差异。</div>
            </section>
          </div>

          <footer>
            <span className={connection === 'connected' ? 'connected' : ''}>
              <span className="status-dot" />
              {connectionText}
            </span>
            <span>
              <Clock3 size={13} />数据源 {clock(snapshot?.source_ts)}
            </span>
            <span>采集 {clock(snapshot?.ingest_ts)}</span>
            <span className={snapshot && !fresh ? 'amber' : ''}>延迟 {age == null ? '未知' : `${Math.max(0, age).toFixed(0)} 秒`}</span>
            <span>
              <Database size={13} />请求 {list.requests_used} / {requestBudget}
            </span>
          </footer>

          {status?.reason && !status.error_code && <p className="status-reason">{status.reason}</p>}
          {snapshot && snapshot.quality.length > 0 && (
            <details className="quality">
              <summary>数据质量 · {snapshot.quality.length} 项提示</summary>
              <p>{snapshot.quality.join(' · ')}</p>
            </details>
          )}

          <div className="page-bottom">
            <span>
              <Hexagon size={13} /> HEXSIGHT
            </span>
            <span>
              看见优势，理解变化。<span className="bottom-divider">/</span>数据来自 {list.demo_mode ? '离线演示' : 'Cito API'}
            </span>
          </div>
        </main>
      </div>
    </div>
  )
}

