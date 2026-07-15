import { useEffect, useState } from "react"

import { Sparkline } from "@/components/Sparkline"
import { getPrices } from "@/lib/api"
import type { PriceSeries, Stock } from "@/lib/api"

export function StockSidebar({
  stocks,
  onSelect,
}: {
  stocks: Stock[]
  onSelect: (series: PriceSeries) => void
}) {
  const [series, setSeries] = useState<Record<string, PriceSeries | null>>({})

  useEffect(() => {
    let cancelled = false
    // Drop cached series for tickers no longer on the watchlist.
    setSeries((prev) =>
      Object.fromEntries(
        Object.entries(prev).filter(([ticker]) =>
          stocks.some((s) => s.ticker === ticker),
        ),
      ),
    )
    for (const stock of stocks) {
      getPrices(stock.ticker, "1d")
        .then((data) => {
          if (!cancelled) setSeries((prev) => ({ ...prev, [stock.ticker]: data }))
        })
        .catch(() => {
          if (!cancelled) setSeries((prev) => ({ ...prev, [stock.ticker]: null }))
        })
    }
    return () => {
      cancelled = true
    }
  }, [stocks])

  if (stocks.length === 0) return null

  return (
    <aside className="w-full shrink-0 lg:w-72">
      <h2 className="mb-2 text-sm font-semibold text-muted-foreground">Watchlist</h2>
      <ul className="divide-y rounded-xl border bg-card">
        {stocks.map((stock) => {
          const data = series[stock.ticker]
          const up = (data?.change ?? 0) >= 0
          return (
            <li key={stock.ticker}>
              <button
                className="flex w-full items-center gap-2 px-3 py-2.5 text-left hover:bg-accent/50 disabled:cursor-default"
                disabled={!data}
                onClick={() => data && onSelect(data)}
              >
                <div className="min-w-0 flex-1">
                  <div className="text-sm font-semibold">{stock.ticker}</div>
                  <div className="truncate text-xs text-muted-foreground">
                    {stock.company_name}
                  </div>
                </div>
                {data === undefined && (
                  <span className="text-xs text-muted-foreground">...</span>
                )}
                {data === null && (
                  <span className="text-xs text-muted-foreground">no price data</span>
                )}
                {data && (
                  <>
                    <Sparkline points={data.points} up={up} />
                    <div className="w-20 text-right">
                      <div className="text-sm font-medium tabular-nums">
                        {data.price?.toFixed(2)}
                      </div>
                      <div
                        className={`text-xs tabular-nums ${up ? "text-green-600" : "text-red-600"}`}
                      >
                        {data.change !== null && (up ? "+" : "") + data.change.toFixed(2)}
                        {data.change_percent !== null &&
                          ` (${up ? "+" : ""}${data.change_percent.toFixed(2)}%)`}
                      </div>
                    </div>
                  </>
                )}
              </button>
            </li>
          )
        })}
      </ul>
    </aside>
  )
}
