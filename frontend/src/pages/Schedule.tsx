import { useEffect, useState } from 'react'
import { api } from '../api/client'
import './schedule.css'

type Team = { name: string | null; code: string | null }
type Match = { matchId: string; gameId: string | null; startTime: string | null; leagueName: string; leagueSlug: string; tournamentName: string; blockName: string | null; strategy: string | null; team1: Team; team2: Team }
type ScheduleData = { refreshSeconds: number; items: Match[]; fetchedAt: string; demo_mode: boolean }
const date = (value: string | null) => value ? new Date(value).toLocaleString('zh-CN', { timeZone: 'Asia/Shanghai', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hour12: false }) : '时间待定'
function countdown(value: string | null, now: number) {
  if (!value) return '时间待定'
  const seconds = Math.floor((Date.parse(value) - now) / 1000)
  if (seconds <= 0) return '等待开赛确认'
  const hours = Math.floor(seconds / 3600)
  return `${String(hours).padStart(2, '0')}:${String(Math.floor(seconds / 60) % 60).padStart(2, '0')}:${String(seconds % 60).padStart(2, '0')}`
}
export function Schedule() {
  const [data, setData] = useState<ScheduleData | null>(null)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [query, setQuery] = useState('')
  const [league, setLeague] = useState('all')
  const [format, setFormat] = useState('all')
  const [now, setNow] = useState(Date.now())
  const [revision, setRevision] = useState(0)
  useEffect(() => {
    const controller = new AbortController()
    let running = false
    let timer: ReturnType<typeof setTimeout> | undefined
    let refreshSeconds = 86400
    async function refresh() {
      if (running) return
      running = true; setBusy(true)
      try { const result = await api<ScheduleData>('/api/schedule', { signal: controller.signal }); setData(result); refreshSeconds = result.refreshSeconds || 86400; setError('') }
      catch (e) { if (!controller.signal.aborted) setError(e instanceof Error ? e.message : '赛程获取失败') }
      finally { running = false; if (!controller.signal.aborted) { setBusy(false); timer = setTimeout(refresh, refreshSeconds * 1000) } }
    }
    void refresh()
    return () => { controller.abort(); clearTimeout(timer) }
  }, [revision])
  useEffect(() => { const timer = setInterval(() => setNow(Date.now()), 1000); return () => clearInterval(timer) }, [])
  const all = data?.items || []
  const matches = all.filter(m => (league === 'all' || m.leagueSlug === league) && (format === 'all' || m.strategy?.toLowerCase() === format) && `${m.team1.name} ${m.team1.code} ${m.team2.name} ${m.team2.code} ${m.matchId} ${m.gameId || ''}`.toLowerCase().includes(query.toLowerCase()))
  const focus = matches[0]
  async function monitor(m: Match) {
    if (!m.gameId || busy) return
    setBusy(true)
    try { await api('/api/monitors', { method: 'POST', body: JSON.stringify({ gameId: m.gameId, matchId: m.matchId }) }); localStorage.setItem('hexsight.game', m.gameId); window.location.href = '/' }
    catch (e) { setError(e instanceof Error ? e.message : '启动失败'); setBusy(false) }
  }
  const team = (t: Team, side: string) => <div className={`sc-team ${side}`}><span className="sc-label">{side === 'blue' ? 'TEAM 01' : 'TEAM 02'}</span><div className="sc-team-name"><b>{t.code || '?'}</b><h2>{t.name || '战队待定'}</h2></div><p>首发阵容 · 等待官方公布</p><div className="sc-roles">{['TOP', 'JUG', 'MID', 'ADC', 'SUP'].map(r => <span key={r}>{r}<strong>—</strong></span>)}</div></div>
  const action = (m: Match) => <button className="sc-launch" disabled={!m.gameId || busy} onClick={() => void monitor(m)}>{m.gameId ? '⚡ 接入本场监控' : '等待小局 gameId 公布'}</button>
  const today = new Date(now).toLocaleDateString('en-CA', { timeZone: 'Asia/Shanghai' })
  return <div className="schedule-page">
    <header className="sc-header"><a className="sc-brand" href="/">■ HEXSIGHT <small>// LOL ESPORTS HUD</small></a><nav><a href="/">监控总览大屏</a><a href="/schedule" aria-current="page">赛程与即将开赛</a></nav><span className="sc-online">{data?.demo_mode ? 'DEMO / 合成数据' : 'REST / SCHEDULE'}</span></header>
    <main className="sc-main"><section className="sc-intro"><span className="sc-label">RADAR ACTIVE</span><span className="sc-kicker"> // UPCOMING 14 DAYS</span><div className="sc-title"><div><h1>待开赛程与雷达预警</h1><p>未来两周职业赛事 · 北京时间 UTC+8 · 自动同步 Cito 赛程</p></div><div className="sc-metrics"><span>今日待开 <b>{all.filter(m => m.startTime && new Date(m.startTime).toLocaleDateString('en-CA', { timeZone: 'Asia/Shanghai' }) === today).length}</b></span><span>1小时内 <b>{all.filter(m => m.startTime && Date.parse(m.startTime) > now && Date.parse(m.startTime) - now <= 3600000).length}</b></span><span>刷新 <b>{(data?.refreshSeconds || 86400) >= 3600 ? `${(data?.refreshSeconds || 86400) / 3600}h` : `${data?.refreshSeconds}s`}</b></span></div></div><div className="sc-filters"><div><button className={league === 'all' ? 'active' : ''} onClick={() => setLeague('all')}>全部赛事 (ALL)</button>{Array.from(new Set(all.map(m => m.leagueSlug))).map(l => <button key={l} className={league === l ? 'active' : ''} onClick={() => setLeague(l)}>{all.find(m => m.leagueSlug === l)?.leagueName || l}</button>)}</div><select aria-label="赛制" value={format} onChange={e => setFormat(e.target.value)}><option value="all">全部赛制</option><option value="bo5">BO5</option><option value="bo3">BO3</option><option value="bo1">BO1</option></select><input aria-label="搜索赛程" placeholder="搜索战队、matchId 或 gameId…" value={query} onChange={e => setQuery(e.target.value)} /></div></section>
    {error && <div className="sc-error" role="alert">{error} {data && '· 以下为上次成功获取的赛程'} <button disabled={busy} onClick={() => setRevision(r => r + 1)}>重试</button></div>}
    {!data && busy && <div className="sc-empty" role="status">正在扫描赛事日历…</div>}
    {data?.demo_mode && <p className="sc-demo">演示模式：以下为合成赛程，不代表真实比赛。</p>}
    {focus && <section className="sc-focus"><div className="sc-focus-heading"><span className="sc-label">◆ 下一场焦点对阵</span><span>{focus.tournamentName} · {focus.strategy || '赛制待定'}</span><span className="sc-countdown">◷ {countdown(focus.startTime, now)}</span></div><div className="sc-arena">{team(focus.team1, 'blue')}<div className="sc-versus"><p>{date(focus.startTime)} CST</p><strong>VS</strong><p>{focus.blockName || '赛程阶段待定'}</p>{action(focus)}<small>gameId: {focus.gameId || '尚未公布'}</small></div>{team(focus.team2, 'red')}</div><div className="sc-facts"><div><b>赛事信息</b><p>{focus.leagueName} · {focus.tournamentName}</p></div><div><b>比赛标识</b><p>{focus.matchId}</p></div><div><b>赛前数据</b><p>胜率、对位分析将在数据可用后展示</p></div></div></section>}
    <div className="sc-queue-title"><h2>■ 接续赛程雷达表</h2><span>{matches.length} 场 · 按开赛时间排序</span></div>
    {data && !matches.length && <div className="sc-empty">{all.length ? '没有符合筛选条件的比赛' : '未来两周暂无已公布赛程'}<p>赛程将自动刷新，也可以调整筛选条件。</p></div>}
    <div className="sc-grid">{matches.map(m => <article className="sc-card" key={m.matchId}><div className="sc-card-heading"><span>{date(m.startTime)}</span><b>{m.leagueName} / {m.strategy || '待定'}</b></div><div className="sc-card-teams"><div><strong>{m.team1.code || '?'}</strong><h3>{m.team1.name || '待定'}</h3></div><b>VS</b><div><strong>{m.team2.code || '?'}</strong><h3>{m.team2.name || '待定'}</h3></div></div><p>{m.tournamentName}</p><p className="sc-clock">◷ {countdown(m.startTime, now)}</p><div className="sc-id">matchId: {m.matchId}<br/>gameId: {m.gameId || '尚未公布'}</div>{action(m)}</article>)}</div>
    <footer className="sc-footer"><span>■ {busy ? '正在同步…' : error ? '同步异常' : '赛程就绪'} · {all.length} MATCHES LOADED</span><span>上次同步：{data ? date(data.fetchedAt) : '—'}</span><button disabled={busy} onClick={() => setRevision(r => r + 1)}>↻ 刷新赛程</button><a href="/">手动输入 gameId →</a></footer></main>
  </div>
}
