import { useCallback, useEffect, useState } from "react"
import { Activity, Newspaper, Search, TrendingUp, X } from "lucide-react"

import { AddStockDialog } from "@/components/AddStockDialog"
import { ArticleList } from "@/components/ArticleList"
import { PriceChartPanel } from "@/components/PriceChartPanel"
import { StockPanel } from "@/components/StockPanel"
import { StockSidebar } from "@/components/StockSidebar"
import { ThemeToggle } from "@/components/ThemeToggle"
import { Card, CardContent } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { deleteStock, getStocks, searchArticles } from "@/lib/api"
import type { Article, PriceSeries, Stock } from "@/lib/api"

function formatDay(iso: string | null): string {
  if (!iso) return "no articles yet"
  return new Date(iso).toLocaleDateString(undefined, { month: "short", day: "numeric" })
}

function SentimentBar({ stock }: { stock: Stock }) {
  const bullish = stock.bullish_count ?? 0
  const bearish = stock.bearish_count ?? 0
  const neutral = stock.neutral_count ?? 0
  const total = bullish + bearish + neutral
  if (total === 0) return null
  const pct = (n: number) => `${(n / total) * 100}%`
  return (
    <div
      className="mt-3 flex h-1.5 overflow-hidden rounded-full bg-muted"
      title={`${bullish} bullish · ${neutral} neutral · ${bearish} bearish`}
    >
      <div className="bg-emerald-500" style={{ width: pct(bullish) }} />
      <div className="bg-muted-foreground/25" style={{ width: pct(neutral) }} />
      <div className="bg-red-500" style={{ width: pct(bearish) }} />
    </div>
  )
}

function StatChip({
  icon: Icon,
  label,
  value,
}: {
  icon: typeof Activity
  label: string
  value: string
}) {
  return (
    <div className="flex items-center gap-2.5 rounded-xl border bg-card px-4 py-2.5">
      <Icon className="size-4 text-muted-foreground" />
      <div className="text-sm">
        <span className="font-semibold tabular-nums">{value}</span>{" "}
        <span className="text-muted-foreground">{label}</span>
      </div>
    </div>
  )
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
    if (chart?.ticker === ticker) setChart(null)
    if (selected?.ticker === ticker) setSelected(null)
    void loadStocks()
  }

  const searching = query.trim().length > 0
  const totalArticles = stocks?.reduce((n, s) => n + s.article_count, 0) ?? 0

  return (
    <div className="min-h-screen bg-background">
      <header className="sticky top-0 z-20 border-b bg-background/80 backdrop-blur-md">
        <div className="mx-auto flex max-w-6xl items-center gap-4 px-4 py-3">
          <div className="flex items-center gap-2.5">
            <div className="flex size-8 items-center justify-center rounded-lg bg-primary text-primary-foreground">
              <TrendingUp className="size-4.5" />
            </div>
            <span className="font-display text-lg font-bold tracking-tight max-sm:hidden">
              Stock News Dashboard
            </span>
          </div>
          <div className="relative ml-auto w-full max-w-md">
            <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
            <Input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search cached news..."
              className="rounded-full bg-muted/50 pl-9 pr-8"
            />
            {searching && (
              <button
                aria-label="Clear search"
                className="absolute right-2.5 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
                onClick={() => setQuery("")}
              >
                <X className="size-4" />
              </button>
            )}
          </div>
          <ThemeToggle />
        </div>
      </header>

      <div className="mx-auto max-w-6xl px-4 py-8">
        {loadError && <p className="mb-4 text-sm text-destructive">{loadError}</p>}

        {!searching && stocks !== null && stocks.length > 0 && (
          <div className="mb-6 flex flex-wrap gap-3">
            <StatChip icon={Activity} label="tickers tracked" value={String(stocks.length)} />
            <StatChip
              icon={Newspaper}
              label="articles cached"
              value={totalArticles.toLocaleString()}
            />
          </div>
        )}

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
                    className="group cursor-pointer border transition-all duration-200 hover:-translate-y-0.5 hover:border-foreground/20 hover:shadow-lg"
                    onClick={() => setSelected(stock)}
                  >
                    <CardContent className="relative">
                      <button
                        aria-label={`Remove ${stock.ticker}`}
                        className="absolute right-4 top-0 rounded p-0.5 text-muted-foreground opacity-0 transition-opacity hover:text-destructive group-hover:opacity-100"
                        onClick={(e) => {
                          e.stopPropagation()
                          void remove(stock.ticker)
                        }}
                      >
                        <X className="size-4" />
                      </button>
                      <div className="font-display text-xl font-bold tracking-tight">
                        {stock.ticker}
                      </div>
                      <div className="truncate text-sm text-muted-foreground">
                        {stock.company_name || " "}
                      </div>
                      <SentimentBar stock={stock} />
                      <div className="mt-2.5 text-xs text-muted-foreground">
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
