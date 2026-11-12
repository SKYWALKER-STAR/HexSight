import { useCallback, useEffect, useState } from 'react'
import { Activity, ArrowDown, ArrowUp, ChevronRight, CircleHelp, Clock3, Database, Hexagon, Play, Radio, Shield, Square, Swords, Target, Waves, Zap } from 'lucide-react'
import { api } from '../api/client'
import type { MonitorList, Player, Team } from '../api/types'
import { useMonitor } from '../hooks/useMonitor'
import { Trend } from '../components/Trend'

const format = (v: number | null | undefined) => v == null ? '—' : v.toLocaleString('zh-CN', { maximumFractionDigits: 0 })
const signed = (v: number | null | undefined) => v == null ? '—' : `${v > 0 ? '+' : ''}${format(v)}`
const clock = (v: string | null | undefined) => v ? new Date(v).toLocaleString('zh-CN', { hour12: false }) : '未知'
const roles: Record<string, string> = { TOP: '上路', JUNGLE: '打野', MID: '中路', BOT: '下路', SUPPORT: '辅助' }
const stateNames = { running: '监控中', stopped: '已停止', paused: '已暂停', error: '采集异常' }
const factors: Record<string, string> = { gold: '经济', towers: '防御塔', dragons: '小龙', barons: '大龙', inhibitors: '水晶' }
const confidence: Record<string, string> = { high: '高', medium: '中', low: '低', unknown: '未知' }
const emptyList: MonitorList = { items: [], requests_used: 0, request_budget: 0, demo_mode: false, warnings: [] }

function PlayerCell({ player, side }: { player: Player | null; side: string }) {
  return <div className={`player-cell ${side}`}><span className="champion-mark">{player?.champion?.slice(0, 2).toUpperCase() || '—'}</span><div><strong>{player?.champion || '英雄未知'}</strong><small>{player?.name || '选手未知'}</small></div></div>
}
function TeamPanel({ team, side }: { team?: Team; side: 'blue' | 'red' }) {
  return <div className={`team-panel ${side}`}>
    <div className="team-heading"><span className="team-insignia"><Shield size={24}/></span><div><span className="eyebrow">{side === 'blue' ? 'BLUE SIDE' : 'RED SIDE'}</span><h2>{team?.name || (side === 'blue' ? '蓝色方' : '红色方')}</h2></div></div>
    <div className="gold-number">{format(team?.gold)}<span>总经济</span></div>
    <div className="team-metrics"><span><Swords size={15}/><strong>{format(team?.kills)}</strong>击杀</span><span><Shield size={15}/><strong>{format(team?.towers)}</strong>防御塔</span></div>
    <div className="objectives"><span>小龙 <b>{format(team?.dragons)}</b></span><span>大龙 <b>{format(team?.barons)}</b></span><span>水晶 <b>{format(team?.inhibitors)}</b></span></div>
  </div>
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
    void api<MonitorList>('/api/monitors').then(setList).catch(() => setRequestError('后端连接失败，请检查服务是否启动'))
  }, [])
  const { snapshot, history, status: pushStatus, connection, error, warnings } = useMonitor(gameId, refreshList)
  const status = pushStatus || list.items.find(m => m.game_id === gameId)
  useEffect(() => { refreshList(); const t = setInterval(refreshList, 10000); return () => clearInterval(t) }, [refreshList])
  useEffect(() => { const t = setInterval(() => setNow(Date.now()), 1000); return () => clearInterval(t) }, [])
  useEffect(() => { if (gameId) localStorage.setItem('hexsight.game', gameId) }, [gameId])
  const age = snapshot?.source_ts ? (now - new Date(snapshot.source_ts).getTime()) / 1000 : null
  const fresh = age != null && age >= -5 && age <= (snapshot?.stale_threshold_seconds || 120) && snapshot?.freshness === 'fresh'
  const score = fresh ? snapshot?.advantage.score ?? null : null
  const direction = score == null ? 'unknown' : snapshot!.advantage.direction
  const label = { blue: '蓝方领先', red: '红方领先', even: '双方均势', unknown: snapshot ? '暂停判断' : '等待比赛数据' }[direction]
  const active = status?.state === 'running'
  const allWarnings = [...new Set([...list.warnings, ...warnings])]
  const select = (id: string) => { setGameId(id); setGameInput(id); setRequestError('') }
  async function start(event: React.FormEvent) {
    event.preventDefault()
    const id = gameInput.trim(), match = matchInput.trim()
    if (!/^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$/.test(id) || (match && !/^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$/.test(match))) {
      setRequestError('ID 仅允许 1–64 位字母、数字、下划线或短横线，并以字母或数字开头'); return
    }
    setBusy(true); setRequestError('')
    try { await api('/api/monitors', { method: 'POST', body: JSON.stringify({ gameId: id, matchId: match || null }) }); select(id); refreshList() }
    catch (e) { setRequestError((e as Error).message) } finally { setBusy(false) }
  }
  async function stop() {
    setBusy(true); setRequestError('')
    try { await api(`/api/monitors/${gameId}`, { method: 'DELETE' }); refreshList() }
    catch (e) { setRequestError((e as Error).message) } finally { setBusy(false) }
  }
  return <div className="app-shell">
    <aside className="rail"><a href="/" className="brand-icon" aria-label="HexSight 首页"><Hexagon size={29}/><span/></a><div className="rail-active" title="赛事态势"><Activity size={23}/></div><span className="rail-bottom" title="LOL"><Swords size={20}/></span></aside>
    <div className="workspace"><header className="topbar"><div className="brand">HexSight <span>赛事态势分析</span></div><div className="top-meta"><span className="pill">LEAGUE OF LEGENDS</span><span className="version">MVP / 0.1</span></div></header>
      <main><div className="page-heading"><div><div className="eyebrow">LIVE INTELLIGENCE <ChevronRight size={12}/> MATCH OVERVIEW</div><h1>把握赛场的每一次变化<span className="heading-dot">.</span></h1><p>经济、资源与五路对位，在同一个视野里。</p></div><div className={`live-tag ${active ? 'on' : ''}`}><span/>{status ? stateNames[status.state] : '尚未监控'}</div></div>
      {list.demo_mode && <div className="notice demo" role="status">演示模式 · 当前为合成测试数据，不连接真实赛事，不消耗 Cito 配额。</div>}
      <form className="monitor-form" onSubmit={start}><div className="form-label"><Radio size={20}/><span>监控一场比赛<small>输入 Cito 比赛标识</small></span></div><label><span>GAME ID</span><input aria-label="Game ID" placeholder="输入 gameId" value={gameInput} onChange={e => setGameInput(e.target.value)} maxLength={64} required/></label><label className="match-field"><span>MATCH ID <em>可选</em></span><input aria-label="Match ID（可选）" placeholder="用于验证数据覆盖" value={matchInput} onChange={e => setMatchInput(e.target.value)} maxLength={64}/></label><button className="primary" disabled={busy} type="submit"><Play size={15}/>{busy ? '处理中' : '开始监控'}</button><button className="stop" type="button" disabled={busy || !active} onClick={() => void stop()}><Square size={14}/>停止</button></form>
      {list.items.length > 0 && <nav className="monitor-tabs" aria-label="已添加的比赛">{list.items.map(m => <button key={m.game_id} className={m.game_id === gameId ? 'selected' : ''} onClick={() => select(m.game_id)}><span className={`status-dot ${m.state}`}/>{m.game_id}<small>{stateNames[m.state]}</small></button>)}</nav>}
      {(requestError || error || status?.error_code) && <div className="notice error" role="alert">{requestError || status?.reason || error}{status?.next_retry_at && ` · 下次重试 ${clock(status.next_retry_at)}`}</div>}
      {allWarnings.map(w => <div className="notice" key={w}>{w}</div>)}
      {snapshot && !fresh && <div className="notice" role="status">{age == null ? '数据源时间戳未知' : age < -5 ? '数据源时间异常' : '数据过期'} · 已暂停态势判断，保留最后一帧供参考。</div>}
      {snapshot?.delayed_seconds != null && snapshot.delayed_seconds > 0 && <div className="notice">套餐延迟数据 · Cito 标记延迟 {snapshot.delayed_seconds} 秒，并非即时赛况。</div>}
      <section className="overview panel"><div className="section-heading"><h2><Activity size={16}/>全局态势</h2><span>{gameId ? `GAME ${gameId}` : '等待添加比赛'}<i/>比赛时间 {snapshot?.game_seconds != null ? `${Math.floor(snapshot.game_seconds / 60)}:${String(Math.floor(snapshot.game_seconds % 60)).padStart(2, '0')}` : '—'}</span></div><div className="versus"><TeamPanel team={snapshot?.blue} side="blue"/><div className="advantage-panel"><span className="eyebrow">ADVANTAGE INDEX</span><div className={`advantage-title ${direction}`}>{label}</div><div className="score-number">{score == null ? '—' : Math.abs(score).toFixed(1)}<span>/ 100</span></div><div className="score-track"><div className="track-center"/>{score != null && <div className={`score-fill ${direction}`} style={{ left: `${score < 0 ? 50 + score / 2 : 50}%`, width: `${Math.abs(score) / 2}%` }}/>}</div><div className="track-labels"><span>红方</span><span>均势</span><span>蓝方</span></div><span className="confidence">可信度 {confidence[fresh ? snapshot?.advantage.confidence || 'unknown' : 'unknown']}</span><p><CircleHelp size={13}/>优势强度，不代表获胜概率</p></div><TeamPanel team={snapshot?.red} side="red"/></div><div className="factor-strip"><span><Zap size={14}/>判断依据</span>{fresh && snapshot?.advantage.factors.length ? snapshot.advantage.factors.map(f => <span key={f.name}>{factors[f.name] || f.name}差 <b>{signed(f.difference)}</b><small>权重 {Math.round(f.weight * 100)}%</small></span>) : <span>有效数据到达后显示各项差值与实际权重</span>}</div></section>
      <section className="panel lanes"><div className="section-heading"><h2><Swords size={16}/>五路对位</h2><span>蓝方 − 红方<span className="subtle-tag">基础发育优势</span></span></div><div className="table-scroll"><table><thead><tr><th>位置</th><th>蓝方选手</th><th>经济差</th><th>CS 差</th><th>等级差</th><th>K / D / A（蓝 · 红）</th><th>红方选手</th><th>对位判断</th></tr></thead><tbody>{Object.entries(roles).map(([role, name]) => { const lane = snapshot?.lanes.find(l => l.role === role); const diff = lane?.differences.gold; return <tr key={role}><td><span className="role-icon">{role === 'JUNGLE' ? <Waves size={15}/> : role === 'SUPPORT' ? <Shield size={15}/> : <Target size={15}/>}</span>{name}<small className="role-en">{role}</small></td><td><PlayerCell player={lane?.blue || null} side="blue"/></td><td className={diff != null && diff !== 0 ? diff > 0 ? 'blue' : 'red' : ''}>{diff != null && diff !== 0 && (diff > 0 ? <ArrowUp size={12}/> : <ArrowDown size={12}/>)}{signed(diff)}</td><td>{signed(lane?.differences.cs)}</td><td>{signed(lane?.differences.level)}</td><td className="kda"><span>{[lane?.blue?.kills, lane?.blue?.deaths, lane?.blue?.assists].map(format).join(' / ')}</span><small>{[lane?.red?.kills, lane?.red?.deaths, lane?.red?.assists].map(format).join(' / ')}</small></td><td><PlayerCell player={lane?.red || null} side="red"/></td><td><span className={`lane-score ${fresh ? lane?.advantage.direction : ''}`} title={lane?.reason || lane?.advantage.note}>{lane?.reason ? (role === 'JUNGLE' || role === 'SUPPORT') && lane.blue && lane.red ? '仅展示差异' : '无法匹配' : !fresh || lane?.advantage.score == null ? '—' : signed(lane.advantage.score)}</span>{lane && <details><summary>详情</summary><div>蓝方经济 / CS / 等级：{[lane.blue?.gold, lane.blue?.cs, lane.blue?.level].map(format).join(' / ')}<br/>红方经济 / CS / 等级：{[lane.red?.gold, lane.red?.cs, lane.red?.level].map(format).join(' / ')}<br/>蓝方装备：{lane.blue?.items?.join('、') || '—'}<br/>红方装备：{lane.red?.items?.join('、') || '—'}<br/>{lane.reason || lane.advantage.note}</div></details>}</td></tr> })}</tbody></table></div><div className="table-note">缺失字段显示「—」；角色无法可靠匹配时禁用评分。打野与辅助只展示发育维度差异。</div></section>
      <section className="panel trend"><div className="section-heading"><h2><Activity size={16}/>优势走势</h2><span><span className="legend-dot"/>优势分<span className="subtle-tag">最近 30 分钟</span></span></div><Trend items={history} now={now}/></section>
      <footer><span className={connection === 'connected' ? 'connected' : ''}><span className="status-dot"/>{({ idle: '未连接', connecting: '连接中', connected: '推送已连接', reconnecting: '连接中断 · 自动重连' } as Record<string, string>)[connection]}</span><span><Clock3 size={13}/>数据源 {clock(snapshot?.source_ts)}</span><span>采集 {clock(snapshot?.ingest_ts)}</span><span className={snapshot && !fresh ? 'amber' : ''}>延迟 {age == null ? '未知' : `${Math.max(0, age).toFixed(0)} 秒`}</span><span><Database size={13}/>请求 {list.requests_used} / {list.request_budget || '不限'}</span></footer>
      {status?.reason && !status.error_code && <p className="status-reason">{status.reason}</p>}
      {snapshot && snapshot.quality.length > 0 && <details className="quality"><summary>数据质量 · {snapshot.quality.length} 项提示</summary><p>{snapshot.quality.join(' · ')}</p></details>}
      <div className="page-bottom"><span><Hexagon size={13}/> HEXSIGHT</span><span>看见优势，理解变化。<span className="bottom-divider">/</span>数据来自 {list.demo_mode ? '离线演示' : 'Cito API'}</span></div>
    </main></div>
  </div>
}
