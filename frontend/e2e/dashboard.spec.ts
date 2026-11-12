import { test, expect } from '@playwright/test'

test('手动开始停止、五路展示、刷新恢复与窄屏布局', async ({ page }) => {
  const errors: string[] = []
  page.on('pageerror', error => errors.push(error.message))
  await page.goto('/')
  await expect(page.getByText('把握赛场的每一次变化', { exact: false })).toBeVisible()
  await expect(page.getByText('演示模式', { exact: false })).toBeVisible()
  await page.getByRole('textbox', { name: 'Game ID', exact: true }).fill('e2e-game')
  await page.getByRole('button', { name: '开始监控' }).click()
  await expect(page.getByText('DEMO BLUE', { exact: true })).toBeVisible()
  await expect(page.getByText('推送已连接', { exact: true })).toBeVisible()
  await expect(page.getByText('Gnar', { exact: true })).toHaveCount(2)
  await expect(page.getByText('仅展示差异', { exact: true })).toHaveCount(2)
  await page.screenshot({ path: 'test-results/dashboard-desktop.png', fullPage: true })
  await page.reload()
  await expect(page.getByText('DEMO BLUE', { exact: true })).toBeVisible()
  await expect(page.getByRole('button', { name: '停止', exact: true })).toBeEnabled()
  await page.getByRole('button', { name: '停止', exact: true }).click()
  await expect(page.getByRole('button', { name: '停止', exact: true })).toBeDisabled()
  await expect(page.getByText('用户已停止监控', { exact: true })).toBeVisible()
  await page.setViewportSize({ width: 390, height: 844 })
  await page.screenshot({ path: 'test-results/dashboard-mobile.png', fullPage: true })
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
  expect(errors).toEqual([])
})

test('WebSocket 断线自动重连并用 REST 补偿', async ({ page }) => {
  let sockets = 0
  await page.routeWebSocket('**/ws/games/**', ws => {
    sockets++
    if (sockets === 1) setTimeout(() => ws.close(), 100)
    else ws.connectToServer()
  })
  let latestCalls = 0
  page.on('request', req => { if (req.url().includes('/latest')) latestCalls++ })
  await page.goto('/')
  await page.getByRole('textbox', { name: 'Game ID', exact: true }).fill('reconnect-game')
  await page.getByRole('button', { name: '开始监控' }).click()
  await expect(page.getByText('推送已连接', { exact: true })).toBeVisible({ timeout: 10000 })
  await expect.poll(() => sockets).toBeGreaterThan(1)
  await expect.poll(() => latestCalls).toBeGreaterThan(1)
  await expect(page.getByText('DEMO BLUE', { exact: true })).toBeVisible()
  await page.getByRole('button', { name: '停止', exact: true }).click()
})

test('过期数据暂停判断、缺失字段显示横线', async ({ page }) => {
  const snapshot = { game_id: 'stale-game', source_ts: new Date(Date.now() - 300000).toISOString(), ingest_ts: new Date().toISOString(), game_seconds: null, freshness: 'stale', stale_threshold_seconds: 120, quality: ['game_time_unknown'], blue: { name: 'OLD BLUE', gold: 5000 }, red: { name: 'OLD RED', gold: null }, advantage: { score: null, direction: 'unknown', confidence: 'unknown', factors: [] }, lanes: [], source: 'cito' }
  await page.addInitScript(() => localStorage.setItem('hexsight.game', 'stale-game'))
  await page.route('**/api/games/stale-game/latest', route => route.fulfill({ json: snapshot }))
  await page.route('**/api/games/stale-game/history', route => route.fulfill({ json: { items: [], warnings: [] } }))
  await page.goto('/')
  await expect(page.getByText('暂停判断', { exact: true })).toBeVisible()
  await expect(page.getByText('数据过期', { exact: false })).toBeVisible()
  await expect(page.locator('.team-panel.red .gold-number')).toContainText('—')
})
