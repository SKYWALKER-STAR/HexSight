import { useEffect, useState } from 'react'
import { SiteHeader } from '../components/SiteHeader'
import { api } from '../api/client'
import './tournaments.css'

type Tournament = { tournamentId: string; name: string; slug: string; tier: string; league: { name: string; shortName: string; region: string; imageUrl: string | null }; startDate: string | null; endDate: string | null; prizePool: string | null; prizePoolUsd: number | null; isCompleted: boolean; isInternational: boolean }
type Data = { tournaments: Tournament[]; meta: { total: number; limit: number; offset: number; hasMore: boolean }; demo_mode: boolean }
const date = (s: string | null) => s ? s.slice(0, 10) : '待定'
export function Tournaments() {
  const [data, setData] = useState<Data | null>(null)
  const [offset, setOffset] = useState(0)
  const [revision, setRevision] = useState(0)
  const [busy, setBusy] = useState(true)
  const [error, setError] = useState('')
  const [query, setQuery] = useState('')
  const [tier, setTier] = useState('all')
  const [region, setRegion] = useState('all')
  const [status, setStatus] = useState('all')
  const [intl, setIntl] = useState(false)
  useEffect(() => {
    const controller = new AbortController()
    setBusy(true); setError(''); setData(null)
    api<Data>(`/api/tournaments?limit=50&offset=${offset}`, { signal: controller.signal }).then(result => { if (!controller.signal.aborted) setData(result) }).catch(e => { if (!controller.signal.aborted) setError(e.message) }).finally(() => { if (!controller.signal.aborted) setBusy(false) })
    return () => controller.abort()
  }, [offset, revision])
  const all = data?.tournaments || []
  const rows = all.filter(t => (tier === 'all' || t.tier === tier) && (region === 'all' || t.league?.region === region) && (status === 'all' || t.isCompleted === (status === 'completed')) && (!intl || t.isInternational) && `${t.name} ${t.tournamentId} ${t.slug}`.toLowerCase().includes(query.toLowerCase()))
  const badge = (t: Tournament) => <span className={`tm-badge ${t.isCompleted ? '' : 'tm-active live-blink'}`}>{t.isCompleted ? '✓ 已完赛' : '● 未完赛'}</span>
  const tierBadge = (t: Tournament) => <span className={`tm-tier tier-${t.tier.toLowerCase()}`}>{t.tier.toUpperCase()}</span>
  const focus = [...rows].sort((a,b) => Number(['s','a'].includes(b.tier.toLowerCase())) - Number(['s','a'].includes(a.tier.toLowerCase()))).slice(0,3)
  return <div className="tm-page"><SiteHeader current="/tournaments" status="REST / TOURNAMENTS"/><main>
    <section className="tm-intro"><small className="tm-kicker">STAGE 03 // MATRIX</small><h1>🏆 全球职业赛事矩阵 <span>(GLOBAL TOURNAMENTS)</span></h1><div className="tm-stats">
      <article><small>赛事总量 // TOTAL</small><strong>{data?.meta.total ?? '—'} 场</strong><p>当前加载 {all.length} 场</p></article>
      <article><small>S 级巅峰赛事 // TIER S</small><strong>{all.filter(t => t.tier.toLowerCase() === 's').length}</strong><p>当前页顶级职业联赛</p></article>
      <article><small>未完赛 // ACTIVE</small><strong className={all.some(t => !t.isCompleted) ? 'live-blink' : ''}>{all.filter(t => !t.isCompleted).length} 场</strong><p>当前页 · 包含尚未开赛的赛事</p></article>
      <article><small>国际赛事 // INTERNATIONAL</small><strong>{all.filter(t => t.isInternational).length} INTL</strong><p>当前页跨赛区赛事</p></article>
    </div></section>
    <section className="tm-filters"><p>筛选范围：当前加载页（最多 50 场）</p><div>TIER: {['all', ...new Set(all.map(t => t.tier))].map(v => <button key={v} aria-pressed={tier===v} onClick={() => setTier(v)}>{v === 'all' ? '全部' : v.toUpperCase()}</button>)}</div><input aria-label="搜索赛事" placeholder="搜索赛事名称 / tournamentId / slug…" value={query} onChange={e => setQuery(e.target.value)}/><div>REGION: <select aria-label="赛区" value={region} onChange={e => setRegion(e.target.value)}><option value="all">全部赛区</option>{[...new Set(all.map(t => t.league?.region).filter(Boolean))].map(r => <option key={r}>{r}</option>)}</select><select aria-label="赛事状态" value={status} onChange={e => setStatus(e.target.value)}><option value="all">全部状态</option><option value="active">仅看未完赛</option><option value="completed">仅看已完赛</option></select><label><input type="checkbox" checked={intl} onChange={e => setIntl(e.target.checked)}/> 仅看国际赛事</label><button onClick={() => {setTier('all');setRegion('all');setStatus('all');setIntl(false);setQuery('')}}>重置筛选</button></div></section>
    {busy && <p role="status">正在加载赛事矩阵…</p>}{error && <p role="alert">{error} <button onClick={() => setRevision(r => r+1)}>重试</button></p>}{data?.demo_mode && <p>演示模式未提供赛事数据；请配置 Cito 后切换到真实数据模式。</p>}
    <section><h2>■ 重点赛事推荐 // FEATURED HIGHLIGHTS</h2><div className="tm-featured">{focus.map(t => <article key={t.tournamentId}>{tierBadge(t)} {t.isInternational && <span className="tm-intl">INTL</span>}<h3>{t.name}</h3>{badge(t)}<p>{t.league?.region} · {date(t.startDate)} ～ {date(t.endDate)}</p><small>{t.tournamentId}</small></article>)}</div></section>
    <section><h2>■ 全球赛事全量矩阵列表</h2><p>当前页匹配 {rows.length} 场 · 全部 {data?.meta.total ?? '—'} 场</p><div className="tm-table"><table><thead><tr>{['联赛','赛事名称与 ID','级别','赛区','赛程日期','奖金池','状态'].map(h => <th key={h}>{h}</th>)}</tr></thead><tbody>{rows.map(t => <tr key={t.tournamentId}><td><b className="tm-logo">{t.league?.shortName || 'LOL'}</b></td><td><strong>{t.name}</strong><small>{t.tournamentId}</small></td><td>{tierBadge(t)}</td><td>{t.league?.region || '—'} {t.isInternational && <span className="tm-intl">INTL</span>}</td><td>{date(t.startDate)}<br/>～ {date(t.endDate)}</td><td className="tm-prize">{t.prizePoolUsd != null ? `$${t.prizePoolUsd.toLocaleString()} USD` : t.prizePool || '官方未披露'}</td><td>{badge(t)}</td></tr>)}</tbody></table></div>{data && !rows.length && <p>没有符合条件的赛事</p>}</section>
    <footer><span>当前第 {Math.floor(offset/50)+1} 页 · {data ? `${data.meta.offset + (all.length ? 1 : 0)}–${data.meta.offset+all.length} / ${data.meta.total}` : '—'}</span><button disabled={busy || offset===0} onClick={() => setOffset(n => Math.max(0,n-50))}>◀ 上一页</button><button disabled={busy || !data?.meta.hasMore} onClick={() => setOffset(n => n+50)}>下一页 ▶</button><button disabled={busy} onClick={() => setRevision(r => r+1)}>刷新</button></footer>
  </main></div>
}
