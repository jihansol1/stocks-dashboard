import { useCallback, useEffect, useState } from "react"

import { ArticleList } from "@/components/ArticleList"
import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { getNews, refreshStock } from "@/lib/api"
import type { Article, Stock } from "@/lib/api"

export function StockPanel({
  stock,
  onClose,
  onChanged,
}: {
  stock: Stock
  onClose: () => void
  onChanged: () => void
}) {
  const [articles, setArticles] = useState<Article[] | null>(null)
  const [status, setStatus] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const load = useCallback(async () => {
    try {
      setArticles(await getNews(stock.ticker))
    } catch (e) {
      setStatus(e instanceof Error ? e.message : "Failed to load news")
    }
  }, [stock.ticker])

  useEffect(() => {
    void load()
  }, [load])

  async function update() {
    if (busy) return
    setBusy(true)
    setStatus(null)
    try {
      const stats = await refreshStock(stock.ticker)
      if (stats.refreshed) {
        setStatus(`Fetched ${stats.fetched}, ${stats.inserted} new`)
        await load()
        onChanged()
      } else {
        setStatus("Recently updated, serving cached news")
      }
    } catch (e) {
      setStatus(e instanceof Error ? e.message : "Update failed")
    } finally {
      setBusy(false)
    }
  }

  return (
    <Dialog open onOpenChange={(next) => !next && onClose()}>
      <DialogContent className="max-h-[85vh] overflow-y-auto sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle>
            {stock.ticker}
            {stock.company_name && (
              <span className="ml-2 text-base font-normal text-muted-foreground">
                {stock.company_name}
              </span>
            )}
          </DialogTitle>
          <DialogDescription>Recent news from the local cache.</DialogDescription>
        </DialogHeader>
        <div className="flex items-center gap-3">
          <Button size="sm" variant="outline" onClick={() => void update()} disabled={busy}>
            {busy ? "Updating..." : "Update"}
          </Button>
          {status && <span className="text-xs text-muted-foreground">{status}</span>}
        </div>
        {articles === null ? (
          <p className="py-8 text-center text-sm text-muted-foreground">Loading...</p>
        ) : (
          <ArticleList articles={articles} />
        )}
      </DialogContent>
    </Dialog>
  )
}
