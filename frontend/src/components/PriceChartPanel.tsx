import { useEffect, useState } from "react"
import { AreaSeries, ColorType, createChart } from "lightweight-charts"
import type { IChartApi, UTCTimestamp } from "lightweight-charts"

import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { getPrices } from "@/lib/api"
import type { PriceRange, PriceSeries } from "@/lib/api"

const RANGES: PriceRange[] = ["1d", "5d", "1mo", "6mo", "1y"]
const RANGE_LABELS: Record<PriceRange, string> = {
  "1d": "1D",
  "5d": "5D",
  "1mo": "1M",
  "6mo": "6M",
  "1y": "1Y",
}

export function PriceChartPanel({
  initial,
  companyName,
  onClose,
}: {
  initial: PriceSeries
  companyName: string | null
  onClose: () => void
}) {
  // State, not a ref: the dialog mounts its content in a portal one render
  // late, so we need a re-render (and effect re-run) when the node attaches.
  const [container, setContainer] = useState<HTMLDivElement | null>(null)
  const [range, setRange] = useState<PriceRange>(initial.range)
  const [series, setSeries] = useState<PriceSeries>(initial)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (range === initial.range) {
      setSeries(initial)
      return
    }
    let cancelled = false
    getPrices(initial.ticker, range)
      .then((data) => {
        if (!cancelled) {
          setSeries(data)
          setError(null)
        }
      })
      .catch((e) => {
        if (!cancelled) setError(e instanceof Error ? e.message : "Failed to load prices")
      })
    return () => {
      cancelled = true
    }
  }, [range, initial])

  useEffect(() => {
    if (!container) return

    let chart: IChartApi | null = null
    let disposed = false
    let frame = 0

    const create = () => {
      if (disposed) return
      // The dialog is still animating open; wait until the container has
      // real dimensions before creating the chart, then let autoSize track
      // any further changes.
      if (container.clientWidth === 0 || container.clientHeight === 0) {
        frame = requestAnimationFrame(create)
        return
      }
      const up = (series.change ?? 0) >= 0
      const color = up ? "#16a34a" : "#dc2626"
      const isDark = document.documentElement.classList.contains("dark")
      chart = createChart(container, {
        autoSize: true,
        layout: {
          background: { type: ColorType.Solid, color: "transparent" },
          textColor: isDark ? "#a3a3a3" : "#525252",
          attributionLogo: false,
        },
        grid: {
          vertLines: { visible: false },
          horzLines: { color: isDark ? "rgba(255,255,255,0.07)" : "rgba(0,0,0,0.06)" },
        },
        timeScale: {
          timeVisible: series.range === "1d" || series.range === "5d",
          borderVisible: false,
        },
        rightPriceScale: { borderVisible: false },
      })
      const area = chart.addSeries(AreaSeries, {
        lineColor: color,
        lineWidth: 2,
        topColor: up ? "rgba(22,163,74,0.25)" : "rgba(220,38,38,0.25)",
        bottomColor: "rgba(0,0,0,0)",
      })
      area.setData(
        series.points.map((p) => ({ time: p.t as UTCTimestamp, value: p.c })),
      )
      chart.timeScale().fitContent()
    }

    // Give the dialog's open animation a couple of frames before measuring.
    frame = requestAnimationFrame(() => {
      frame = requestAnimationFrame(create)
    })

    return () => {
      disposed = true
      cancelAnimationFrame(frame)
      chart?.remove()
    }
  }, [container, series])

  const up = (series.change ?? 0) >= 0

  return (
    <Dialog open onOpenChange={(next) => !next && onClose()}>
      <DialogContent className="sm:max-w-3xl">
        <DialogHeader>
          <DialogTitle>
            {series.ticker}
            {companyName && (
              <span className="ml-2 text-base font-normal text-muted-foreground">
                {companyName}
              </span>
            )}
          </DialogTitle>
          <DialogDescription>
            <span className="text-lg font-semibold text-foreground tabular-nums">
              {series.price?.toFixed(2)} {series.currency}
            </span>
            {series.change !== null && series.change_percent !== null && (
              <span
                className={`ml-2 tabular-nums ${up ? "text-green-600" : "text-red-600"}`}
              >
                {up ? "+" : ""}
                {series.change.toFixed(2)} ({up ? "+" : ""}
                {series.change_percent.toFixed(2)}%) today
              </span>
            )}
          </DialogDescription>
        </DialogHeader>
        <div className="flex gap-1">
          {RANGES.map((r) => (
            <Button
              key={r}
              size="sm"
              variant={r === range ? "default" : "ghost"}
              onClick={() => setRange(r)}
            >
              {RANGE_LABELS[r]}
            </Button>
          ))}
        </div>
        {error ? (
          <p className="py-12 text-center text-sm text-destructive">{error}</p>
        ) : (
          <div ref={setContainer} className="h-80 w-full" />
        )}
      </DialogContent>
    </Dialog>
  )
}
