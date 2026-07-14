import { useState } from "react"

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
import { addStock } from "@/lib/api"

export function AddStockDialog({ onAdded }: { onAdded: () => void }) {
  const [open, setOpen] = useState(false)
  const [ticker, setTicker] = useState("")
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

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
            Enter a ticker symbol. It is validated before being added.
          </DialogDescription>
        </DialogHeader>
        <form
          onSubmit={(e) => {
            e.preventDefault()
            void submit()
          }}
          className="space-y-3"
        >
          <Input
            autoFocus
            placeholder="e.g. AAPL"
            value={ticker}
            onChange={(e) => setTicker(e.target.value.toUpperCase())}
          />
          {error && <p className="text-sm text-destructive">{error}</p>}
          <Button type="submit" className="w-full" disabled={busy || !ticker.trim()}>
            {busy ? "Validating and fetching news..." : "Add to watchlist"}
          </Button>
        </form>
      </DialogContent>
    </Dialog>
  )
}
