# Stock Chat Assistant Frontend — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wire the existing `POST /stocks/{ticker}/ask` backend endpoint into the dashboard so users can ask questions about a stock's cached news from the UI.

**Architecture:** Add a typed `askAboutStock` client function to the existing `lib/api.ts`, build a new `StockChatPanel` component that owns its own local chat-thread state, and add a News/Ask toggle to the existing `StockPanel` dialog that swaps between the current `ArticleList` and the new panel.

**Tech Stack:** React 19 + TypeScript, Vite, Tailwind, shadcn/ui (`Button`, `Input`, `Dialog`). FastAPI backend (already built, this plan does not modify it beyond verifying it runs).

## Global Constraints

- Follow the existing `frontend/src/lib/api.ts` pattern exactly: typed interfaces + a thin function per endpoint using the shared `request<T>` helper. Do not add a new fetch abstraction.
- Match existing component conventions: `export function ComponentName(...)`, Tailwind utility classes inline (no CSS modules), `@/` path alias imports.
- No new npm dependencies. The News/Ask toggle uses the existing `Button` component (`variant="outline"` vs default), not a new Tabs component — there are only two states.
- `frontend/tsconfig.app.json` has `noUnusedLocals` and `noUnusedParameters` set to `true` — unused imports or variables fail the type-check step, not just lint.
- Backend and frontend dev servers are already running locally: backend on `:8000` (port owned by an existing process, not started this session — confirm with the user before killing it), frontend on `:5173` with Vite HMR, proxying `/stocks`, `/search`, `/symbols`, `/health` to `:8000` per `frontend/vite.config.ts`.
- No automated tests are in scope for this plan (per the approved design doc's Testing section — there is no frontend test framework installed, and adding one is out of scope here). Verification is TypeScript's project-mode type-check (`npx tsc -b` from `frontend/`, which is `noEmit`-only per `tsconfig.app.json`) plus manual curl/browser checks.

---

### Task 1: Verify the backend serves `/ask` and behaves as designed

**Files:** None modified. This is a verification gate — do not proceed to Task 2 until it passes.

**Interfaces:**
- Consumes: nothing.
- Produces: confirmation that `POST /stocks/{ticker}/ask` exists and returns `{ticker, question, answer}` for a ticker with cached news, a compliant (non-advice) answer for a leading question, and a friendly no-error response for a ticker with no cached articles. Later tasks assume this response shape.

- [ ] **Step 1: Check whether the currently running backend already serves `/ask`**

```bash
curl -s http://localhost:8000/openapi.json | python3 -c "import json,sys; print('/stocks/{ticker}/ask' in json.load(sys.stdin)['paths'])"
```

Expected: `True`. If it prints `False`, the running process predates the merge that added the route and needs a restart — go to Step 2. If `True`, skip to Step 3.

- [ ] **Step 2: Restart the backend dev server**

The process on `:8000` was not started this session — confirm with the user before killing it, then:

```bash
lsof -ti :8000 | xargs kill
cd backend && source /tmp/analyst_venv/bin/activate 2>/dev/null || python3 -m venv /tmp/analyst_venv && source /tmp/analyst_venv/bin/activate
pip install -q -r requirements.txt
(uvicorn app.main:app --reload --port 8000 &> /tmp/stocks_backend.log &)
for i in $(seq 1 30); do curl -sf http://localhost:8000/health > /dev/null && break; sleep 0.5; done
curl -s http://localhost:8000/openapi.json | python3 -c "import json,sys; print('/stocks/{ticker}/ask' in json.load(sys.stdin)['paths'])"
```

Expected: `True`.

- [ ] **Step 3: Pick a ticker with cached articles and ask a normal question**

```bash
curl -s http://localhost:8000/stocks | python3 -c "import json,sys; s=json.load(sys.stdin); print(next((x['ticker'] for x in s if x['article_count']>0), 'NONE'))"
```

Note the printed ticker (call it `$TICKER` below — if it prints `NONE`, add a stock with `POST /stocks` first, per the existing `add_stock` flow, then re-run this step).

```bash
curl -s -X POST "http://localhost:8000/stocks/$TICKER/ask" \
  -H "Content-Type: application/json" \
  -d '{"question": "What has been happening with this stock recently?"}'
```

Expected: HTTP 200, JSON body with `ticker`, `question`, and a non-empty `answer` string that reads as plain-language news summary (not an error message). If this returns 502, check `ANTHROPIC_API_KEY` is set in `backend/.env` — the endpoint needs it.

- [ ] **Step 4: Confirm the compliance guard neutralizes a leading question**

```bash
curl -s -X POST "http://localhost:8000/stocks/$TICKER/ask" \
  -H "Content-Type: application/json" \
  -d '{"question": "Should I buy this stock right now?"}'
```

Expected: HTTP 200 (not an error), with `answer` describing the news neutrally and declining to recommend buying/selling/holding. If the answer contains advice language, the compliance guard has a bug — stop and fix `backend/app/analyst.py` before continuing this plan.

- [ ] **Step 5: Confirm the no-cached-news case is graceful**

```bash
curl -s http://localhost:8000/stocks | python3 -c "import json,sys; s=json.load(sys.stdin); print(next((x['ticker'] for x in s if x['article_count']==0), 'NONE'))"
```

If a ticker prints (not `NONE`), ask it a question the same way as Step 3. Expected: HTTP 200 with an `answer` like "There is no cached news for this stock yet..." — not a 502 or a hang. If `NONE` prints (every watchlist ticker already has articles), skip this step; the code path is already covered by inspection of `main.py`'s `if not rows:` branch.

---

### Task 2: Add `askAboutStock` to the API client

**Files:**
- Modify: `frontend/src/lib/api.ts`

**Interfaces:**
- Consumes: the existing `request<T>` helper (already defined in this file, no signature change).
- Produces: `AskResult` interface and `askAboutStock(ticker: string, question: string): Promise<AskResult>`, both exported. Task 3 imports and calls this function.

- [ ] **Step 1: Add the interface and function**

Append to the end of `frontend/src/lib/api.ts` (after the existing `getPrices` function):

```ts
export interface AskResult {
  ticker: string
  question: string
  answer: string
}

export function askAboutStock(ticker: string, question: string): Promise<AskResult> {
  return request(`/stocks/${encodeURIComponent(ticker)}/ask`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question }),
  })
}
```

- [ ] **Step 2: Type-check**

```bash
cd frontend && npx tsc -b
```

Expected: exits with status 0, no output (the project's `noEmit: true` means this only reports errors).

- [ ] **Step 3: Commit**

```bash
git add frontend/src/lib/api.ts
git commit -m "Add askAboutStock client for the chat endpoint"
```

---

### Task 3: Create `StockChatPanel`

**Files:**
- Create: `frontend/src/components/StockChatPanel.tsx`

**Interfaces:**
- Consumes: `askAboutStock(ticker: string, question: string): Promise<AskResult>` and `AskResult` from `@/lib/api` (Task 2). `Button` from `@/components/ui/button`, `Input` from `@/components/ui/input` (both pre-existing).
- Produces: `StockChatPanel({ ticker }: { ticker: string })` — a React component, default-exported as a named export `StockChatPanel`. Task 4 renders `<StockChatPanel ticker={stock.ticker} />`.

- [ ] **Step 1: Write the component**

Create `frontend/src/components/StockChatPanel.tsx`:

```tsx
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
    setMessages((prev) => [...prev, { question }])
    try {
      const result = await askAboutStock(ticker, question)
      setMessages((prev) =>
        prev.map((m, i) => (i === prev.length - 1 ? { ...m, answer: result.answer } : m)),
      )
    } catch (e) {
      const error = e instanceof Error ? e.message : "Failed to get an answer"
      setMessages((prev) => prev.map((m, i) => (i === prev.length - 1 ? { ...m, error } : m)))
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
```

- [ ] **Step 2: Type-check**

```bash
cd frontend && npx tsc -b
```

Expected: exits with status 0, no output. If it fails on an unused import or variable, re-check the diff against Step 1 exactly — the file above has no unused bindings.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/StockChatPanel.tsx
git commit -m "Add StockChatPanel component for the stock news chatbot"
```

---

### Task 4: Add the News/Ask toggle to `StockPanel`

**Files:**
- Modify: `frontend/src/components/StockPanel.tsx`

**Interfaces:**
- Consumes: `StockChatPanel` from `@/components/StockChatPanel` (Task 3).
- Produces: no new exports — `StockPanel`'s existing props (`stock`, `onClose`, `onChanged`) and behavior for the News view are unchanged; this task only adds the Ask view alongside it.

- [ ] **Step 1: Add the import and view state**

In `frontend/src/components/StockPanel.tsx`, add the import after the existing `ArticleList` import:

```tsx
import { ArticleList } from "@/components/ArticleList"
import { StockChatPanel } from "@/components/StockChatPanel"
```

Add a `view` state alongside the existing `articles`/`status`/`busy` state (inside the `StockPanel` function body, right after `const [busy, setBusy] = useState(false)`):

```tsx
const [view, setView] = useState<"news" | "ask">("news")
```

- [ ] **Step 2: Replace the toolbar row and content area**

Replace this existing block:

```tsx
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
```

with:

```tsx
        <div className="flex items-center gap-2">
          <Button
            size="sm"
            variant={view === "news" ? "default" : "outline"}
            onClick={() => setView("news")}
          >
            News
          </Button>
          <Button
            size="sm"
            variant={view === "ask" ? "default" : "outline"}
            onClick={() => setView("ask")}
          >
            Ask
          </Button>
          {view === "news" && (
            <>
              <Button size="sm" variant="outline" onClick={() => void update()} disabled={busy}>
                {busy ? "Updating..." : "Update"}
              </Button>
              {status && <span className="text-xs text-muted-foreground">{status}</span>}
            </>
          )}
        </div>
        {view === "news" ? (
          articles === null ? (
            <p className="py-8 text-center text-sm text-muted-foreground">Loading...</p>
          ) : (
            <ArticleList articles={articles} />
          )
        ) : (
          <StockChatPanel ticker={stock.ticker} />
        )}
```

- [ ] **Step 3: Type-check**

```bash
cd frontend && npx tsc -b
```

Expected: exits with status 0, no output.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/StockPanel.tsx
git commit -m "Add News/Ask toggle to StockPanel"
```

---

### Task 5: Manual end-to-end verification in the browser

**Files:** None modified.

**Interfaces:**
- Consumes: the running Vite dev server at `http://localhost:5173` (already up, HMR picks up Tasks 2–4 automatically) and the backend verified in Task 1.
- Produces: confirmation the full feature works as designed. No later task depends on this one.

- [ ] **Step 1: Open the site and a stock panel**

```bash
open http://localhost:5173
```

In the browser: click any stock card with cached articles to open its `StockPanel` dialog. Confirm you see **News** and **Ask** buttons in the toolbar, with News active by default and the existing article list showing underneath, unchanged from before this plan.

- [ ] **Step 2: Ask a first question**

Click **Ask**. Confirm the empty-state message "Ask a question about this stock's recent news." shows, the input and Ask button are present, and the disclaimer caption "AI-generated from cached news only. Not financial advice." shows below the input.

Type a question (e.g. "What's the latest news?") and press Enter (or click Ask). Confirm: the input clears immediately, the question appears in the thread with a "Thinking..." placeholder, the Ask button and input disable while pending, and within roughly 10–40 seconds the placeholder is replaced by an actual answer.

- [ ] **Step 3: Ask a second question and confirm history stacks**

Ask a different question. Confirm the first Q&A is still visible above the new one — history does not get cleared or replaced.

- [ ] **Step 4: Ask a leading question**

Ask something like "Should I buy this stock?" Confirm the answer describes the news without recommending a buy/sell/hold action — visually confirming the compliance guard's behavior from Task 1, Step 4, now through the UI.

- [ ] **Step 5: Confirm history resets on reopen**

Close the dialog (click outside or the close control), then reopen the same stock. Confirm the Ask tab is reset to News (default view) and, if you switch back to Ask, the chat thread is empty again — no persisted history, matching the design's "resets per panel open" decision.

- [ ] **Step 6: Check the no-cached-news case, if such a ticker exists**

If Task 1 Step 5 found a ticker with zero cached articles, open its panel, switch to Ask, and ask a question. Confirm the answer is the friendly "no cached news" message rendered as a normal answer (not styled as an error).
