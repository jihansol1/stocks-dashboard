// Thin client for the FastAPI backend. Dev server proxies these paths to :8000.

export type Sentiment = "bullish" | "bearish" | "neutral"

export interface Stock {
  ticker: string
  company_name: string | null
  added_at: string
  article_count: number
  latest_published_at: string | null
}

export interface Article {
  id: number
  ticker: string
  headline: string
  source: string | null
  url: string
  published_at: string | null
  fetched_at: string
  summary: string | null
  sentiment: Sentiment | null
}

export interface RefreshStats {
  refreshed: boolean
  fetched: number
  inserted: number
  queued: number
}

export interface AddStockResult {
  ticker: string
  company_name: string | null
  news: RefreshStats
}

export interface SymbolSuggestion {
  ticker: string
  name: string
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const resp = await fetch(path, init)
  if (!resp.ok) {
    let detail = `Request failed (${resp.status})`
    try {
      const body = await resp.json()
      if (typeof body.detail === "string") detail = body.detail
    } catch {
      // keep the generic message
    }
    throw new Error(detail)
  }
  if (resp.status === 204) return undefined as T
  return resp.json() as Promise<T>
}

export function getStocks(): Promise<Stock[]> {
  return request("/stocks")
}

export function addStock(ticker: string): Promise<AddStockResult> {
  return request("/stocks", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ ticker }),
  })
}

export function deleteStock(ticker: string): Promise<void> {
  return request(`/stocks/${encodeURIComponent(ticker)}`, { method: "DELETE" })
}

export function getNews(ticker: string): Promise<Article[]> {
  return request(`/stocks/${encodeURIComponent(ticker)}/news`)
}

export function refreshStock(ticker: string): Promise<RefreshStats> {
  return request(`/stocks/${encodeURIComponent(ticker)}/refresh`, { method: "POST" })
}

export function searchArticles(q: string): Promise<Article[]> {
  return request(`/search?q=${encodeURIComponent(q)}`)
}

export function getSymbolSuggestions(q: string): Promise<SymbolSuggestion[]> {
  return request(`/symbols?q=${encodeURIComponent(q)}`)
}

export type PriceRange = "1d" | "5d" | "1mo" | "6mo" | "1y"

export interface PricePoint {
  t: number // unix seconds
  c: number // close
}

export interface PriceSeries {
  ticker: string
  range: PriceRange
  currency: string | null
  price: number | null
  prev_close: number | null
  change: number | null
  change_percent: number | null
  points: PricePoint[]
}

export function getPrices(ticker: string, range: PriceRange = "1d"): Promise<PriceSeries> {
  return request(`/stocks/${encodeURIComponent(ticker)}/prices?range=${range}`)
}
