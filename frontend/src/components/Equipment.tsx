import { useEffect, useState } from 'react'
import { itemIconUrl, loadItemCatalog, type ItemCatalog } from '../api/items'

type CatalogState = { patch: string; catalog?: ItemCatalog; failed?: boolean }

export function Equipment({ items, patchVersion }: { items?: (string | number)[] | null; patchVersion?: string | null }) {
  const patch = patchVersion?.trim() || ''
  const [state, setState] = useState<CatalogState>()
  const [retry, setRetry] = useState(0)
  const hasItems = Boolean(items?.some(id => String(id) !== '0'))
  useEffect(() => {
    if (!patch || !hasItems) return
    let active = true
    setState({ patch })
    loadItemCatalog(patch).then(
      catalog => { if (active) setState({ patch, catalog }) },
      () => { if (active) setState({ patch, failed: true }) },
    )
    return () => { active = false }
  }, [patch, hasItems, retry])

  const current = state?.patch === patch ? state : undefined
  const catalog = current?.catalog
  return (
    <div className="equipment" aria-label="装备">
      <div className="equipment-slots">
        {items == null ? <span className="equipment-note">装备数据未知</span> : items.length === 0 ? <span className="equipment-note">暂无装备</span> : items.map((id, index) => {
          const key = String(id)
          const empty = key === '0'
          const item = catalog?.data[key]
          const label = empty ? '空装备槽' : item ? `${item.name} (${key})` : `未知装备 (${key})`
          const url = catalog && !empty ? itemIconUrl(catalog, key) : undefined
          return (
            <span className="equipment-slot" key={`${index}:${key}`} title={label} aria-label={label} tabIndex={0}>
              <span className="equipment-placeholder">{empty ? '—' : '?'}</span>
              {url && <img key={url} src={url} alt={item?.name || label} loading="lazy" onError={event => { event.currentTarget.style.display = 'none' }} />}
              <span className="equipment-tooltip" role="tooltip">{label}</span>
            </span>
          )
        })}
      </div>
      {hasItems && !patch && <span className="equipment-note">版本未知</span>}
      {hasItems && patch && !catalog && !current?.failed && <span className="equipment-note">装备加载中…</span>}
      {hasItems && current?.failed && <button className="equipment-retry" onClick={() => setRetry(value => value + 1)}>装备加载失败，重试</button>}
    </div>
  )
}
