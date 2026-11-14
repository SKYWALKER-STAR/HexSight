import assert from 'node:assert/strict'
import test from 'node:test'
import { readFile } from 'node:fs/promises'
import ts from 'typescript'

const source = await readFile(new URL('../src/api/items.ts', import.meta.url), 'utf8')
const { outputText } = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 } })
const { matchItemVersion, loadItemCatalog, itemIconUrl } = await import(`data:text/javascript;base64,${Buffer.from(outputText).toString('base64')}`)

test('matches exact or same patch without crossing patch boundaries', () => {
  const versions = ['16.22.2', '16.22.1', '16.2.1']
  assert.equal(matchItemVersion('16.22.1', versions), '16.22.1')
  assert.equal(matchItemVersion('16.22.456.789', versions), '16.22.2')
  assert.equal(matchItemVersion('16.2', versions), '16.2.1')
  assert.equal(matchItemVersion('16.21', versions), undefined)
  assert.equal(matchItemVersion('invalid', versions), undefined)
})

test('shares requests across players and patch aliases, separates locales, retries failures', async () => {
  const originalFetch = globalThis.fetch
  const calls = []
  let fail = true
  globalThis.fetch = async url => {
    calls.push(url)
    if (url.endsWith('versions.json')) return { ok: true, json: async () => ['16.22.1'] }
    if (url.includes('en_US') && fail) { fail = false; return { ok: false, status: 503 } }
    return { ok: true, json: async () => ({ data: { '2055': { name: '控制守卫', image: { full: '2055.png' } } } }) }
  }
  try {
    const catalogs = await Promise.all(Array.from({ length: 10 }, (_, index) => loadItemCatalog(index % 2 ? '16.22' : '16.22.123')))
    assert.equal(calls.length, 2)
    assert.ok(catalogs.every(catalog => catalog === catalogs[0]))
    assert.equal(itemIconUrl(catalogs[0], '2055'), 'https://ddragon.leagueoflegends.com/cdn/16.22.1/img/item/2055.png')
    assert.equal(itemIconUrl(catalogs[0], '99999'), undefined)
    await assert.rejects(loadItemCatalog('16.22', 'en_US'))
    assert.equal((await loadItemCatalog('16.22', 'en_US')).version, '16.22.1')
    assert.equal(calls.length, 4)
    await assert.rejects(loadItemCatalog('16.21'))
    assert.equal(calls.length, 4)
  } finally { globalThis.fetch = originalFetch }
})
