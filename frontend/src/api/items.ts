const origin = 'https://ddragon.leagueoflegends.com'
export type ItemCatalog = { version: string; data: Record<string, { name: string; image?: { full?: string } }> }
let versionsRequest: Promise<string[]> | undefined
const catalogs = new Map<string, Promise<ItemCatalog>>()

async function getJson(url: string) {
  const response = await fetch(url, { signal: AbortSignal.timeout(15000) })
  if (!response.ok) throw new Error(`HTTP ${response.status}`)
  return response.json()
}

export function matchItemVersion(patch: string, versions: string[]): string | undefined {
  if (versions.includes(patch)) return patch
  const parts = /^(\d+)\.(\d+)(?:\.|$)/.exec(patch)
  if (!parts) return undefined
  const prefix = `${parts[1]}.${parts[2]}.`
  return versions.find(version => version.startsWith(prefix))
}

export async function loadItemCatalog(patch: string, locale = 'zh_CN'): Promise<ItemCatalog> {
  versionsRequest ??= getJson(`${origin}/api/versions.json`).catch(error => {
    versionsRequest = undefined
    throw error
  })
  const version = matchItemVersion(patch, await versionsRequest!)
  if (!version) throw new Error('没有匹配的装备版本')
  const key = `${version}/${locale}`
  let request = catalogs.get(key)
  if (!request) {
    request = getJson(`${origin}/cdn/${version}/data/${locale}/item.json`)
      .then(body => {
        if (!body.data || typeof body.data !== 'object') throw new Error('装备字典无效')
        return { version, data: body.data } as ItemCatalog
      })
      .catch(error => { catalogs.delete(key); throw error })
    catalogs.set(key, request)
  }
  return request
}

export function itemIconUrl(catalog: ItemCatalog, id: string): string | undefined {
  const file = catalog.data[id]?.image?.full
  return file ? `${origin}/cdn/${catalog.version}/img/item/${encodeURIComponent(file)}` : undefined
}
