# Stock Chat Assistant — Frontend Integration Design

Date: 2026-07-20
Status: Approved

## Goal

Wire the existing LangGraph multi-agent analyst (`backend/app/analyst.py`, exposed
at `POST /stocks/{ticker}/ask`) into the dashboard so a user can actually ask
questions about a stock's cached news from the UI. Today the backend is fully
built but reachable only via curl or `/docs` — there is no way to use it from
the website.

## Decisions

- **Placement: a tab inside the existing per-stock `StockPanel` dialog.** The
  panel already scopes itself to one ticker and already fetches that ticker's
  news, so an "Ask" view sits naturally next to "News" rather than introducing
  a new entry point.
- **Chat model: a visible running thread, backend stays stateless.** The
  backend's `analyze()` has no memory between calls; the frontend stacks each
  Q&A into a list purely for display continuity. No conversation history is
  sent back to the backend — every question still resolves independently
  through the graph, scoped by the ticker's cached articles.
- **Loading UX: a simple "Thinking..." placeholder, no streaming.** The
  pipeline can run up to 4 sequential Claude calls (router → 1–2 analysts →
  synthesizer → compliance guard), so a single question can take significant
  time. Streaming per-node progress would require converting `/ask` to
  Server-Sent Events and emitting progress from each LangGraph node — real
  scope increase, deferred.
- **History scope: resets per panel open.** Chat state lives inside the new
  component's local state, not lifted to `App.tsx`. Closing the stock panel
  and reopening it (same ticker or a different one) starts a fresh
  conversation, matching how the news list already reloads fresh each time.

## Components

### 1. Backend verification (no code changes expected)

Before any frontend work: restart the dev backend so it's running the merged
code that includes `/ask` (confirmed missing as of this write-up), then:

- `curl -X POST /stocks/{ticker}/ask` for a ticker with cached articles and a
  normal question — confirm a compliant answer comes back.
- Same ticker, a leading question ("should I buy X?") — confirm the
  compliance guard neutralizes it rather than the request failing outright.
- A ticker with no cached articles — confirm the friendly "no cached news
  yet" message, not an error.

If any of these fail, fix the backend before building the UI on top of it.

### 2. `frontend/src/lib/api.ts` — add `askAboutStock`

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

Uses the existing `request<T>` helper — thrown-`Error` behavior for non-2xx
responses (including the backend's 502 for `AnalystError` and 404 for an
unknown ticker) is already handled generically.

### 3. `frontend/src/components/StockChatPanel.tsx` (new)

Renders the Ask view. Owns local state:

- `messages: { question: string; answer?: string; error?: string }[]`
- `input: string`
- `busy: boolean`

On submit: append a pending message (no `answer`/`error` yet), call
`askAboutStock`, then fill in `answer` on success or `error` on failure for
that specific entry — earlier entries are untouched either way.

UI states:

- **Empty** (no messages yet): "Ask a question about this stock's recent
  news."
- **Pending** entry: "Thinking..." placeholder in place of the answer.
- **Per-turn error**: the error text renders where the answer would go,
  styled like the existing `text-destructive` usage in `App.tsx`.
- **Disclaimer caption** under the input, always visible: "AI-generated from
  cached news only. Not financial advice."

### 4. `frontend/src/components/StockPanel.tsx` — add a News/Ask toggle

A two-state toggle built from the existing `Button` component
(`variant="outline"` for the inactive state, default for active) — a
lightweight segmented control, no new shadcn dependency needed for just two
states. Toggling swaps between the existing `ArticleList` and the new
`StockChatPanel`, both already scoped to `stock.ticker`.

## Error handling summary

| Failure | Behavior |
| --- | --- |
| `ANTHROPIC_API_KEY` unset on the backend | `/ask` returns 502 with `AnalystError` detail; frontend shows it as the per-turn error |
| Model refusal / bad JSON from a node | Same — 502, surfaced per-turn, prior answers in the thread stay visible |
| No cached articles for the ticker | Backend returns 200 with a friendly "no cached news yet" answer (not an error) |
| Empty question submitted | Backend returns 400; frontend should also block submitting a blank/whitespace-only question client-side |
| Network failure | `request()`'s existing catch-all `Request failed (...)` message |

## Testing

- Backend: manual curl smoke tests per Component 1, run once before frontend
  work starts.
- Frontend: manual QA in the running dev server — open a stock panel, switch
  to Ask, ask two questions in sequence (confirm both stay visible), ask a
  leading/advice-seeking question (confirm the compliant, non-advice answer
  renders), and check the empty-news-cache ticker case.
- No new automated tests planned for this pass — the existing `backend/tests/`
  suite doesn't cover `analyst.py` yet; adding coverage for the LangGraph
  pipeline is out of scope here (see below).

## Out of scope

- No conversation memory / multi-turn context sent to the backend.
- No streaming / SSE progress updates.
- No persistence of chat history across panel close/reopen or across page
  reloads.
- No automated backend tests for `analyst.py` (unit tests with a fake
  Anthropic client, mirroring the `embeddings.py` testing approach in the
  semantic-search design, would be a reasonable follow-up).
