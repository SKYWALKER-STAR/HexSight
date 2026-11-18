import { useEffect, useState } from 'react'
import { api } from '../api/client'
import './winrate.css'

type Player = { rank: number; playerId: string; playerName: string; nationality: string | null; role: string | null; currentTeam: string | null; value: number; gamesPlayed: number }
type Board = { items: Player[]; fetchedAt: string | null; stale: boolean; demo_mode: boolean }
const roles = ['Mid', 'ADC', 'Jungle', 'Top', 'Support']
const roleNames: Record<string, string> = { Mid: '中单 MID', ADC: '下路 ADC', Jungle: '打野 JGL', Top: '上单 TOP', Support: '辅助 SUP' }
const pct = (n: number) => `${n.toFixed(1)}%`
const tier = (n: number) => n >= 80 ? 'elite' : n >= 75 ? 'gold' : 'silver'
function Rate({ value }: { value: number }) { return <span className={`wr-rate ${tier(value)}`}><b>{pct(value)}</b><span className="wr-track"><i style={{ width: `${value}%` }} /></span></span> }

export function Winrate() {
  const [data, setData] = useState<Board | null>(null)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)
  const [reload, setReload] = useState(0)
  const [role, setRole] = useState('all')
  const [query, setQuery] = useState('')
  const [minimum, setMinimum] = useState(0)
  const [copied, setCopied] = useState('')
  useEffect(() => {
    const abort = new AbortController()
    setLoading(true); setError('')
    api<Board>('/api/leaderboards/winrate', { signal: abort.signal }).then(setData).catch(e => {
      if (!abort.signal.aborted) setError(e instanceof Error ? e.message : '榜单加载失败')
    }).finally(() => { if (!abort.signal.aborted) setLoading(false) })
    return () => abort.abort()
  }, [reload])
  const all = data?.items || []
  const filtered = all.filter(p => (role === 'all' || p.role === role) && p.gamesPlayed >= minimum && `${p.playerName} ${p.currentTeam || ''} ${p.playerId} ${p.nationality || ''}`.toLowerCase().includes(query.trim().toLowerCase()))
  const mostGames = [...all].sort((a, b) => b.gamesPlayed - a.gamesPlayed)[0]
  const teams = [...new Set(all.map(p => p.currentTeam).filter((t): t is string => !!t))].map(name => ({ name, players: all.filter(p => p.currentTeam === name) })).sort((a, b) => b.players.length - a.players.length).slice(0, 4)
  const average = all.length ? all.reduce((sum, p) => sum + p.value, 0) / all.length : null
  async function copy(id: string) { try { await navigator.clipboard.writeText(id); setCopied(`已复制 ${id}`) } catch { setCopied('复制失败，请选中完整 ID 手动复制') } }
  function exportCsv() {
    const cell = (v: unknown) => `"${String(v ?? '').replace(/^[=+@-]/, "'$&").replaceAll('"', '""')}"`
    const rows = [['排名', '选手', '位置', '国籍', '战队', '场次', '胜率', 'ID'], ...filtered.map(p => [p.rank, p.playerName, p.role, p.nationality, p.currentTeam, p.gamesPlayed, p.value, p.playerId])]
    const url = URL.createObjectURL(new Blob(['\uFEFF' + rows.map(r => r.map(cell).join(',')).join('\r\n')], { type: 'text/csv;charset=utf-8' }))
    const a = document.createElement('a'); a.href = url; a.download = 'hexsight-winrate.csv'; a.click(); URL.revokeObjectURL(url)
  }
  return <div className="wr-page">
    <header className="wr-nav"><a className="wr-brand" href="/">▣ PIXEL HUD <small>// HEXSIGHT · LOL ESPORTS</small></a><nav><a href="/">实时对局</a><a href="/schedule">即将开赛</a><a href="/winrate" aria-current="page">选手胜率榜</a></nav><span className="wr-source">CITO / 排行快照</span></header>
    <div className="wr-ticker"><b>■ PLAYER WINRATE RADAR</b><span>已载入 {all.length} 位选手 · 榜内平均 {average == null ? '—' : pct(average)}</span><span>北京时间 {data?.fetchedAt ? new Date(data.fetchedAt).toLocaleString('zh-CN', { timeZone: 'Asia/Shanghai', hour12: false }) : '—'}</span></div>
    <main className="wr-main">
      <section className="wr-intro wr-panel"><div><span className="wr-kicker">ARCADE ESPORTS RADAR</span><h1>🏆 职业选手胜率雷达榜</h1><p>从胜率、比赛场次和位置，查看上榜选手的表现。<br />排名保留官方顺序；统计范围以接口返回榜单为准。</p></div><div className="wr-highlights"><div><small>♛ 榜首胜率</small><strong>{all[0] ? pct(all[0].value) : '—'}</strong><span>{all[0]?.playerName || '等待数据'}</span></div><div><small>▣ 最多比赛场次</small><strong>{mostGames?.gamesPlayed ?? '—'}</strong><span>{mostGames?.playerName || '—'}</span></div><div><small>◈ 上榜战队</small><strong>{new Set(all.map(p => p.currentTeam).filter(Boolean)).size}</strong><span>仅统计已知战队</span></div></div></section>
      {loading && <p role="status" className="wr-panel wr-message">正在读取胜率榜…</p>}
      {error && <div role="alert" className="wr-panel wr-message">加载失败：{error} <button onClick={() => setReload(n => n + 1)}>重试</button></div>}
      {data?.stale && <p role="status" className="wr-message">上游暂不可用，当前展示上次成功获取的缓存快照。</p>}
      {data?.demo_mode && <p className="wr-message">当前为演示模式，胜率榜不调用真实接口。关闭演示模式后可查看真实排行。</p>}
      {!!all.length && <section className="wr-podium" aria-label="榜单前三名">{[all[1], all[0], all[2]].filter((p): p is Player => !!p).map(p => <article key={p.playerId} className={`wr-winner wr-panel place-${p.rank}`}><span className="wr-rank-ribbon">{p.rank === 1 ? '♛ GLOBAL NO.1' : `RANK #0${p.rank}`}</span><small>{p.rank === 1 ? '🏆' : '◆'} {p.role?.toUpperCase()} / {p.nationality || '地区未知'}</small><h2>{p.playerName}</h2><p>{p.currentTeam || '战队未提供'}</p><div className="wr-podium-rate"><small>WIN RATE // 胜率</small><strong>{pct(p.value)}</strong></div><Rate value={p.value}/><footer>{p.gamesPlayed} 场比赛 <span>#{p.rank} 官方排名</span></footer></article>)}</section>}
      <section className="wr-panel wr-filters"><div className="wr-tabs">{['all', ...roles].map(r => <button key={r} aria-pressed={role === r} onClick={() => setRole(r)}>{r === 'all' ? '全部位置' : roleNames[r]} [{all.filter(p => r === 'all' || p.role === r).length}]</button>)}</div><div className="wr-search"><input aria-label="搜索选手、战队或 ID" placeholder="⌕ 搜索选手、战队、国籍或 playerId…" value={query} onChange={e => setQuery(e.target.value)}/><label>最低场次 <select value={minimum} onChange={e => setMinimum(Number(e.target.value))}><option value={0}>不限</option><option value={50}>50 场</option><option value={100}>100 场</option><option value={300}>300 场</option></select></label><span>显示 {filtered.length} / {all.length}</span><button disabled={loading} onClick={() => setReload(n => n + 1)}>刷新</button></div></section>
      <div className="wr-columns"><section className="wr-panel wr-matrix"><div className="wr-section-title">▣ LEADERBOARD MATRIX / 胜率排行 <small>绿 ≥80% · 金 ≥75%</small></div><div className="wr-table-scroll"><table><thead><tr>{['排名', '选手 PLAYER', '位置', '国籍', '当前战队', '场次', '胜率 WIN RATE', '选手 ID'].map(t => <th key={t}>{t}</th>)}</tr></thead><tbody>{filtered.map(p => <tr key={p.playerId}><td><span className={p.rank <= 3 ? 'wr-top-rank' : ''}>#{String(p.rank).padStart(2, '0')}</span></td><td><b>{p.playerName}</b></td><td><span className={`wr-role role-${p.role?.toLowerCase()}`}>{p.role || '—'}</span></td><td>{p.nationality || '—'}</td><td>{p.currentTeam || <span className="wr-muted">未提供</span>}</td><td className="wr-numeric">{p.gamesPlayed}</td><td><Rate value={p.value}/></td><td><button className="wr-id" title={p.playerId} aria-label={`复制 ${p.playerName} 的 ID`} onClick={() => copy(p.playerId)}>{p.playerId.slice(0, 8)}… ▣</button></td></tr>)}</tbody></table></div>{!loading && !error && !filtered.length && <p className="wr-message">{all.length ? '没有符合筛选条件的选手。' : '暂无胜率排行数据。'}</p>}<footer className="wr-table-footer"><span>官方排名 · 本地筛选不额外请求接口</span><button disabled={!filtered.length} onClick={exportCsv}>导出当前结果 CSV ↓</button></footer><p className="wr-copy-status" aria-live="polite">{copied}</p></section>
      <aside className="wr-aside"><section className="wr-panel"><h3>♧ 榜单观察</h3><p>最高胜率：<b>{all[0]?.playerName || '—'}</b></p><p>最多比赛：<b>{mostGames?.playerName || '—'}</b> · {mostGames?.gamesPlayed ?? '—'} 场</p><p className="wr-muted">小样本胜率容易波动，请结合比赛场次比较。接口未提供统计时间范围。</p></section><section className="wr-panel"><h3>⚑ 上榜战队分布</h3>{teams.map(t => <div className="wr-squad" key={t.name}><b>{t.name}</b><span>{t.players.length} 位</span><p>{t.players.map(p => `${p.playerName} (${pct(p.value)})`).join(' · ')}</p></div>)}</section><section className="wr-panel"><h3>▥ 各位置平均胜率</h3>{roles.map(r => { const rows = all.filter(p => p.role === r); return <div className="wr-role-average" key={r}><span>{roleNames[r]} · {rows.length} 位</span>{rows.length ? <Rate value={rows.reduce((sum, p) => sum + p.value, 0) / rows.length}/> : <span>—</span>}</div> })}<p className="wr-muted">仅对当前榜单按选手等权平均，并非全体选手或战队胜率。</p></section><section className="wr-panel"><h3>◉ SNAPSHOT NOTES</h3><p>榜单每小时按需更新。多个浏览器共享缓存，刷新按钮不会绕过缓存。</p><p>战队、国籍缺失显示“未提供”，不推断自由人身份。</p></section></aside></div>
      <footer className="wr-footer">★ HEXSIGHT / PLAYER WINRATE RADAR <span>CITO DATA · 每小时缓存</span></footer>
    </main>
  </div>
}
