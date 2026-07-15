import { useEffect, useRef, useState } from "react"

import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { addStock, getSymbolSuggestions } from "@/lib/api"
import type { SymbolSuggestion } from "@/lib/api"

export function AddStockDialog({ onAdded }: { onAdded: () => void }) {
  const [open, setOpen] = useState(false)
  const [ticker, setTicker] = useState("")
  const [suggestions, setSuggestions] = useState<SymbolSuggestion[]>([])
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  // Set when the user picks from the dropdown, so we don't re-open it.
  const picked = useRef<string | null>(null)

  useEffect(() => {
    const q = ticker.trim()
    if (!q || q === picked.current) {
      setSuggestions([])
      return
    }
    const timer = setTimeout(() => {
      getSymbolSuggestions(q)
        .then(setSuggestions)
        .catch(() => setSuggestions([]))
    }, 250)
    return () => clearTimeout(timer)
  }, [ticker])

  function pick(suggestion: SymbolSuggestion) {
    picked.current = suggestion.ticker
    setTicker(suggestion.ticker)
    setSuggestions([])
  }

  async function submit() {
    const value = ticker.trim()
    if (!value || busy) return
    setBusy(true)
    setError(null)
    try {
      await addStock(value)
      setTicker("")
      setOpen(false)
      onAdded()
    } catch (e) {
      setError(e instanceof Error ? e.message : "Something went wrong")
    } finally {
      setBusy(false)
    }
  }

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        setOpen(next)
        setError(null)
        setSuggestions([])
        picked.current = null
      }}
    >
      <DialogTrigger asChild>
        <button className="flex min-h-32 w-full items-center justify-center rounded-xl border border-dashed text-muted-foreground transition-colors hover:border-foreground/40 hover:text-foreground">
          + Add stock
        </button>
      </DialogTrigger>
      <DialogContent className="sm:max-w-sm">
        <DialogHeader>
          <DialogTitle>Add a stock</DialogTitle>
          <DialogDescription>
            Start typing a ticker or company name and pick a match.
          </DialogDescription>
        </DialogHeader>
        <form
          onSubmit={(e) => {
            e.preventDefault()
            void submit()
          }}
          className="space-y-3"
        >
          <div className="relative">
            <Input
              autoFocus
              placeholder="e.g. AAPL"
              value={ticker}
              onChange={(e) => {
                picked.current = null
                setTicker(e.target.value.toUpperCase())
              }}
            />
            {suggestions.length > 0 && (
              <ul className="absolute z-10 mt-1 max-h-56 w-full overflow-y-auto rounded-md border bg-popover text-popover-foreground shadow-md">
                {suggestions.map((s) => (
                  <li key={s.ticker}>
                    <button
                      type="button"
                      className="flex w-full items-baseline gap-2 px-3 py-2 text-left text-sm hover:bg-accent"
                      onClick={() => pick(s)}
                    >
                      <span className="font-semibold">{s.ticker}</span>
                      <span className="truncate text-xs text-muted-foreground">{s.name}</span>
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </div>
          {error && <p className="text-sm text-destructive">{error}</p>}
          <Button type="submit" className="w-full" disabled={busy || !ticker.trim()}>
            {busy ? "Validating and fetching news..." : "Add to watchlist"}
          </Button>
        </form>
      </DialogContent>
    </Dialog>
  )
}
