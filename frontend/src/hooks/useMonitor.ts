import { useEffect, useState } from 'react'
import { api, ApiError } from '../api/client'
import type { History, Monitor, MonitorList, Snapshot } from '../api/types'

export function mergeHistory(items: Snapshot[], value: Snapshot, now = Date.now()) {
  const map = new Map(items.map(s => [s.source_ts || s.ingest_ts, s]))
  map.set(value.source_ts || value.ingest_ts, value)
  return [...map.values()].filter(s => new Date(s.source_ts || s.ingest_ts).getTime() >= now - 30 * 60000)
    .sort((a, b) => (a.source_ts || a.ingest_ts).localeCompare(b.source_ts || b.ingest_ts)).slice(-1800)
}

export function useMonitor(gameId: string, refreshList: () => void) {
  const [snapshot, setSnapshot] = useState<Snapshot | null>(null)
  const [history, setHistory] = useState<Snapshot[]>([])
  const [status, setStatus] = useState<Monitor | null>(null)
  const [connection, setConnection] = useState('idle')
  const [error, setError] = useState('')
  const [warnings, setWarnings] = useState<string[]>([])
  useEffect(() => {
    setSnapshot(null); setHistory([]); setStatus(null); setError(''); setWarnings([])
    if (!gameId) { setConnection('idle'); return }
    let disposed = false, attempt = 0, socket: WebSocket | undefined, timer: ReturnType<typeof setTimeout>
    const abort = new AbortController()
    const accept = (s: Snapshot) => {
      if (disposed) return
      setSnapshot(old => old?.source_ts && (!s.source_ts || old.source_ts > s.source_ts) ? old : s)
      setHistory(old => mergeHistory(old, s))
    }
    const compensate = async () => {
      try {
        const s = await api<Snapshot>(`/api/games/${gameId}/latest`, { signal: abort.signal })
        accept(s)
      } catch (e) {
        if (!disposed && !(e instanceof ApiError && e.status === 404)) setError('快照同步失败，正在重试')
      }
      try {
        const h = await api<History>(`/api/games/${gameId}/history`, { signal: abort.signal })
        if (!disposed) {
          setHistory(old => old.reduce((items, s) => mergeHistory(items, s), h.items))
          setWarnings(h.warnings)
        }
      } catch { if (!disposed) setError('历史读取失败，实时采集不受影响') }
      try {
        const list = await api<MonitorList>('/api/monitors', { signal: abort.signal })
        if (!disposed) setStatus(list.items.find(m => m.game_id === gameId) || { game_id: gameId, match_id: null, state: 'stopped', reason: '服务中没有运行任务，请手动开始', error_code: null, consecutive_failures: 0, request_count: 0, next_retry_at: null })
      } catch { /* The list-level connection error is handled by refreshList. */ }
      if (!disposed) refreshList()
    }
    const connect = () => {
      if (disposed) return
      setConnection(attempt ? 'reconnecting' : 'connecting')
      socket = new WebSocket(`${location.protocol === 'https:' ? 'wss:' : 'ws:'}//${location.host}/ws/games/${gameId}`)
      socket.onopen = () => { if (!disposed) { attempt = 0; setConnection('connected'); setError(''); void compensate() } }
      socket.onmessage = event => {
        if (disposed) return
        try {
          const message = JSON.parse(event.data)
          if (message.type === 'snapshot') { accept(message.data); setError('') }
          if (message.type === 'status') { setStatus(message.data); refreshList() }
          if (message.type === 'warning') setError(message.data.message)
          if (message.type === 'heartbeat') setWarnings(message.data.warnings || [])
        } catch { setError('收到无法解析的推送消息') }
      }
      socket.onclose = () => {
        if (!disposed) {
          setConnection('reconnecting')
          timer = setTimeout(connect, Math.min(30000, 1000 * 2 ** attempt++) + Math.random() * 300)
        }
      }
      socket.onerror = () => socket?.close()
    }
    void compensate(); connect()
    // REST fallback also repairs gaps while WebSocket is unavailable.
    const fallback = setInterval(() => { if (socket?.readyState !== WebSocket.OPEN) void compensate() }, 15000)
    return () => { disposed = true; abort.abort(); clearTimeout(timer); clearInterval(fallback); socket?.close() }
  }, [gameId, refreshList])
  return { snapshot, history, status, connection, error, warnings }
}
