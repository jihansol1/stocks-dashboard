import { Badge } from "@/components/ui/badge"
import type { Article, Sentiment } from "@/lib/api"

const SENTIMENT_STYLES: Record<Sentiment, string> = {
  bullish:
    "bg-emerald-100 text-emerald-800 border-emerald-200 dark:bg-emerald-950 dark:text-emerald-300 dark:border-emerald-900",
  bearish:
    "bg-red-100 text-red-800 border-red-200 dark:bg-red-950 dark:text-red-300 dark:border-red-900",
  neutral:
    "bg-neutral-100 text-neutral-600 border-neutral-200 dark:bg-neutral-800 dark:text-neutral-300 dark:border-neutral-700",
}

function formatDate(iso: string | null): string {
  if (!iso) return ""
  const d = new Date(iso)
  return d.toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  })
}

export function ArticleList({
  articles,
  showTicker = false,
  emptyMessage = "No articles cached yet.",
}: {
  articles: Article[]
  showTicker?: boolean
  emptyMessage?: string
}) {
  if (articles.length === 0) {
    return <p className="py-8 text-center text-sm text-muted-foreground">{emptyMessage}</p>
  }
  return (
    <ul className="divide-y">
      {articles.map((article) => (
        <li key={article.id} className="py-3">
          <div className="flex items-start justify-between gap-3">
            <a
              href={article.url}
              target="_blank"
              rel="noopener noreferrer"
              className="font-medium leading-snug hover:underline"
            >
              {article.headline}
            </a>
            {article.sentiment && (
              <Badge variant="outline" className={SENTIMENT_STYLES[article.sentiment]}>
                {article.sentiment}
              </Badge>
            )}
          </div>
          <div className="mt-1 text-xs text-muted-foreground">
            {showTicker && <span className="font-semibold">{article.ticker} · </span>}
            {article.source && <span>{article.source} · </span>}
            <span>{formatDate(article.published_at)}</span>
          </div>
          {article.summary && (
            <p className="mt-1.5 text-sm text-muted-foreground">{article.summary}</p>
          )}
        </li>
      ))}
    </ul>
  )
}
