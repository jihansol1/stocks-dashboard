import { useCallback, useEffect, useState } from "react"

import { AddStockDialog } from "@/components/AddStockDialog"
import { ArticleList } from "@/components/ArticleList"
import { PriceChartPanel } from "@/components/PriceChartPanel"
import { StockPanel } from "@/components/StockPanel"
import { StockSidebar } from "@/components/StockSidebar"
import { Card, CardContent } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { deleteStock, getStocks, searchArticles } from "@/lib/api"
import type { Article, PriceSeries, Stock } from "@/lib/api"

function formatDay(iso: string | null): string {
  if (!iso) return "no articles yet"
  return new Date(iso).toLocaleDateString(undefined, { month: "short", day: "numeric" })
}

export default function App() {
  const [stocks, setStocks] = useState<Stock[] | null>(null)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [selected, setSelected] = useState<Stock | null>(null)
  const [chart, setChart] = useState<PriceSeries | null>(null)
  const [query, setQuery] = useState("")
  const [results, setResults] = useState<Article[] | null>(null)

  const loadStocks = useCallback(async () => {
    try {
      setStocks(await getStocks())
      setLoadError(null)
    } catch (e) {
      setLoadError(e instanceof Error ? e.message : "Failed to load watchlist")
    }
  }, [])

  // First load of a new market day triggers the backend's watchlist refresh.
  useEffect(() => {
    void loadStocks()
  }, [loadStocks])

  // Debounced search over the cached articles of every watchlist ticker.
  useEffect(() => {
    const q = query.trim()
    if (!q) {
      setResults(null)
      return
    }
    const timer = setTimeout(() => {
      searchArticles(q)
        .then(setResults)
        .catch(() => setResults([]))
    }, 250)
    return () => clearTimeout(timer)
  }, [query])

  async function remove(ticker: string) {
    if (!confirm(`Remove ${ticker} and its cached articles?`)) return
    await deleteStock(ticker)
    // Close any panel showing the removed stock.
    if (chart?.ticker === ticker) setChart(null)
    if (selected?.ticker === ticker) setSelected(null)
    void loadStocks()
  }

  const searching = query.trim().length > 0

  return (
    <div className="mx-auto max-w-6xl px-4 py-8">
      <header className="mb-6 space-y-4">
        <h1 className="text-2xl font-semibold tracking-tight">Stock News Dashboard</h1>
        <Input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Search cached news across your watchlist..."
          className="max-w-xl"
        />
      </header>

      {loadError && <p className="mb-4 text-sm text-destructive">{loadError}</p>}

      <div className="flex flex-col-reverse gap-8 lg:flex-row">
        <main className="min-w-0 flex-1">
          {searching ? (
            results === null ? (
              <p className="py-8 text-center text-sm text-muted-foreground">Searching...</p>
            ) : (
              <ArticleList
                articles={results}
                showTicker
                emptyMessage={`No cached articles match "${query.trim()}".`}
              />
            )
          ) : (
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
              {stocks?.map((stock) => (
                <Card
                  key={stock.ticker}
                  className="cursor-pointer transition-shadow hover:shadow-md"
                  onClick={() => setSelected(stock)}
                >
                  <CardContent className="relative">
                    <button
                      aria-label={`Remove ${stock.ticker}`}
                      className="absolute right-3 top-0 text-muted-foreground hover:text-destructive"
                      onClick={(e) => {
                        e.stopPropagation()
                        void remove(stock.ticker)
                      }}
                    >
                      ×
                    </button>
                    <div className="text-xl font-semibold">{stock.ticker}</div>
                    <div className="truncate text-sm text-muted-foreground">
                      {stock.company_name || " "}
                    </div>
                    <div className="mt-3 text-xs text-muted-foreground">
                      {stock.article_count} article{stock.article_count === 1 ? "" : "s"} ·
                      latest {formatDay(stock.latest_published_at)}
                    </div>
                  </CardContent>
                </Card>
              ))}
              <AddStockDialog onAdded={() => void loadStocks()} />
              {stocks !== null && stocks.length === 0 && (
                <p className="col-span-full py-4 text-center text-sm text-muted-foreground">
                  Your watchlist is empty. Add a ticker to start tracking news.
                </p>
              )}
            </div>
          )}
        </main>
        <StockSidebar stocks={stocks ?? []} onSelect={setChart} />
      </div>

      {selected && (
        <StockPanel
          stock={selected}
          onClose={() => setSelected(null)}
          onChanged={() => void loadStocks()}
        />
      )}
      {chart && (
        <PriceChartPanel
          initial={chart}
          companyName={
            stocks?.find((s) => s.ticker === chart.ticker)?.company_name ?? null
          }
          onClose={() => setChart(null)}
        />
      )}
    </div>
  )
}
