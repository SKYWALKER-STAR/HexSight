import { useEffect, useRef, useState } from 'react'
import type { Snapshot } from '../api/types'
export function Trend({ items, now }: { items: Snapshot[]; now: number }) {
  const container = useRef<HTMLDivElement>(null)
  const [width, setWidth] = useState(980)
  useEffect(() => {
    const observer = new ResizeObserver(entries => setWidth(Math.max(280, entries[0].contentRect.width)))
    if (container.current) observer.observe(container.current)
    return () => observer.disconnect()
  }, [])
  const start = now - 30 * 60000
  const points = items.filter(s => s.source_ts && new Date(s.source_ts).getTime() >= start)
  const x = (s: Snapshot) => 48 + (new Date(s.source_ts!).getTime() - start) / (30 * 60000) * (width - 80)
  const y = (score: number) => 110 - score * .8
  const segments: { sign: 'blue' | 'red'; d: string }[] = []
	let currentSign: 'blue' | 'red' | null = null
	let currentPath = ''
	let currentConnected = false
	const flush = () => {
		if (currentSign && currentPath) segments.push({ sign: currentSign, d: currentPath })
		currentSign = null
		currentPath = ''
		currentConnected = false
	}

  points.forEach(s => {
    if (s.advantage.score == null) {
			flush()
      return
    }
    const sign = s.advantage.score >= 0 ? 'blue' : 'red'
		if (!currentSign || currentSign !== sign) {
			flush()
			currentSign = sign
    }
		currentPath += `${currentConnected ? 'L' : 'M'}${x(s)},${y(s.advantage.score)} `
		currentConnected = true
  })
	flush()
  return <div className="trend-plot" ref={container}>
    {!segments.length && <div className="chart-empty">等待有效快照，开始绘制趋势</div>}
    <svg viewBox={`0 0 ${width} 240`} role="img" aria-label="最近30分钟优势趋势，正值为蓝方领先，负值为红方领先">
      {[100, 50, 0, -50, -100].map(v => <g key={v}><line x1="48" x2={width - 32} y1={y(v)} y2={y(v)} className={v === 0 ? 'zero-line' : 'grid-line'}/><text x="32" y={y(v) + 4} textAnchor="end">{v > 0 ? `+${v}` : v}</text></g>)}
      {segments.map(seg => (
        <path
          key={seg.d}
          d={seg.d}
          fill="none"
          stroke={seg.sign === 'blue' ? '#00f59b' : '#ffb3b5'}
          strokeWidth="2.5"
          strokeLinejoin="round"
        />
      ))}
      {points.filter(s => s.advantage.score != null).map(s => (
        <circle
          key={s.source_ts}
          cx={x(s)}
          cy={y(s.advantage.score!)}
          r="3"
          fill={s.advantage.score! >= 0 ? '#00f59b' : '#ffb3b5'}
        >
          <title>
            {new Date(s.source_ts!).toLocaleTimeString()} · {s.advantage.score}
          </title>
        </circle>
      ))}
      {(width < 500 ? [0, 15, 30] : [0, 5, 10, 15, 20, 25, 30]).map(m => <text key={m} x={48 + m / 30 * (width - 80)} y="226" textAnchor="middle">{m === 30 ? '现在' : `${30 - m} 分钟前`}</text>)}
    </svg>
  </div>
}
