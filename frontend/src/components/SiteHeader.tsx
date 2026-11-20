import './SiteHeader.css'
type Props = { current: string; status: string }
const links = [['/', "监控总览大屏"], ['/schedule', "赛程与即将开赛"], ['/winrate', "选手胜率榜"]]
export function SiteHeader({current, status}: Props) {
return <header className="site-header"><a className="site-brand" href="/">■ HEXSIGHT <small>// LOL ESPORTS HUD</small></a><nav aria-label="主导航">{links.map(([href,label]) => <a key={href} href={href} aria-current={current === href ? 'page' : undefined}>{label}</a>)}</nav><span className="site-online">{status}</span></header>
}
