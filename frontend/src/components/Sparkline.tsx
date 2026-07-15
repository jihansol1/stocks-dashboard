import type { PricePoint } from "@/lib/api"

// Yahoo-style mini chart: green when up, red when down, soft area fill.
export function Sparkline({
  points,
  up,
  width = 96,
  height = 32,
}: {
  points: PricePoint[]
  up: boolean
  width?: number
  height?: number
}) {
  if (points.length < 2) {
    return <div style={{ width, height }} />
  }

  const values = points.map((p) => p.c)
  const min = Math.min(...values)
  const max = Math.max(...values)
  const span = max - min || 1
  const pad = 2

  const coords = points.map((p, i) => {
    const x = (i / (points.length - 1)) * (width - 2 * pad) + pad
    const y = height - pad - ((p.c - min) / span) * (height - 2 * pad)
    return `${x.toFixed(1)},${y.toFixed(1)}`
  })

  const line = `M ${coords.join(" L ")}`
  const area = `${line} L ${width - pad},${height} L ${pad},${height} Z`
  const color = up ? "#16a34a" : "#dc2626"

  return (
    <svg width={width} height={height} aria-hidden="true">
      <path d={area} fill={color} opacity="0.12" />
      <path d={line} fill="none" stroke={color} strokeWidth="1.5" />
    </svg>
  )
}
