import { useState } from "react"

import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { askAboutStock } from "@/lib/api"

interface ChatMessage {
  question: string
  answer?: string
  error?: string
}

export function StockChatPanel({ ticker }: { ticker: string }) {
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [input, setInput] = useState("")
  const [busy, setBusy] = useState(false)

  async function submit() {
    const question = input.trim()
    if (!question || busy) return
    setInput("")
    setBusy(true)
    let index = -1
    setMessages((prev) => {
      index = prev.length
      return [...prev, { question }]
    })
    try {
      const result = await askAboutStock(ticker, question)
      setMessages((prev) => prev.map((m, i) => (i === index ? { ...m, answer: result.answer } : m)))
    } catch (e) {
      const error = e instanceof Error ? e.message : "Failed to get an answer"
      setMessages((prev) => prev.map((m, i) => (i === index ? { ...m, error } : m)))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="flex flex-col gap-4">
      {messages.length === 0 ? (
        <p className="py-8 text-center text-sm text-muted-foreground">
          Ask a question about this stock's recent news.
        </p>
      ) : (
        <ul className="flex flex-col gap-4">
          {messages.map((m, i) => (
            <li key={i} className="flex flex-col gap-1.5">
              <p className="text-sm font-medium">{m.question}</p>
              {m.error ? (
                <p className="text-sm text-destructive">{m.error}</p>
              ) : m.answer ? (
                <p className="text-sm whitespace-pre-wrap text-muted-foreground">{m.answer}</p>
              ) : (
                <p className="text-sm text-muted-foreground">Thinking...</p>
              )}
            </li>
          ))}
        </ul>
      )}
      <div className="flex items-center gap-2">
        <Input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault()
              void submit()
            }
          }}
          placeholder="Ask about this stock's news..."
          disabled={busy}
        />
        <Button size="sm" onClick={() => void submit()} disabled={busy || !input.trim()}>
          {busy ? "Asking..." : "Ask"}
        </Button>
      </div>
      <p className="text-xs text-muted-foreground">
        AI-generated from cached news only. Not financial advice.
      </p>
    </div>
  )
}
