# CMC AI Market Analyst

**Live app**: <https://web-production-1d68ca.up.railway.app/>

A live crypto market intelligence dashboard with an AI copilot, powered by the **CoinMarketCap API** and **Qwen** (Alibaba Cloud's LLM).

Built for the **Build with CMC: API Hackathon** (DoraHacks, September 2026).

![CMC AI Market Analyst](https://img.shields.io/badge/CMC%20API-v1%20%2F%20v2%20%2F%20v5-3861fb)
![Qwen](https://img.shields.io/badge/Qwen-qwen--plus-22d3ee)
![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688)

---

## What It Does

Most AI chat tools hallucinate crypto prices because their training data is stale. This app fixes that: the LLM **cannot answer from memory** — it must call a tool that fetches live data from CoinMarketCap, then reason over the result.

The dashboard shows live market state at a glance. The copilot answers natural-language questions with real numbers, and every API call is visible in a trace drawer.

### Features

- **Live dashboard** — total market cap, 24h volume, BTC/ETH dominance with sparklines
- **Market signals** — computed from live data (top movers, volume anomalies, dominance shifts)
- **Top 100 markets** — sortable, searchable table with watchlist stars
- **Screener** — filter 200 assets by market cap, 24h change, and volume
- **Watchlist** — star assets, persisted to `localStorage`
- **Alerts** — price threshold rules with browser notifications, checked every 60s
- **Tokenized Assets** — real-world assets (stocks, commodities, government securities, ETFs) via CMC's RWA API
- **News** — latest CMC content (requires a Standard+ CMC plan; degrades gracefully with a clear message on free-tier keys)
- **Settings** — connection status, live API credit usage, and local data management
- **AI Copilot** — natural-language queries answered with real CMC data via Qwen tool-calling, available as a side panel and as a full-screen chat
- **API Trace drawer** — every tool call shown with raw request args and CMC response

---

## Architecture

┌─────────────────────────────────────────────────────────────┐
│ BROWSER (index.html) │
│ Overview · Markets · Watchlist · Alerts · Screener · │
│ Tokenized Assets · News · Settings · AI Chat │
└──────────────────────────┬──────────────────────────────────┘
│
▼
┌─────────────────────────────────────────────────────────────┐
│ FastAPI backend (Python) │
│ │
│ /dashboard/summary ──► cached aggregate for the UI │
│ /markets/top100 ──► ranked asset list │
│ /markets/top200 ──► screener source data │
│ /tokenized-assets ──► CMC Real-World Assets list │
│ /news ──► CMC Content Latest (Standard+ plan) │
│ /chat ──► LLM tool-calling loop │
└──────┬──────────────────────────────────┬────────────────────┘
│ │
▼ ▼
┌──────────────────┐ ┌──────────────────┐
│ CoinMarketCap │ │ Qwen (Alibaba) │
│ REST API │ │ OpenAI-compat │
└──────────────────┘ └──────────────────┘

The `/chat` endpoint runs a **tool-calling loop**:

1. User asks a question.
2. Qwen decides whether to call a tool (`get_asset_quotes`, `get_market_overview`, `get_top_assets`, `get_trending`).
3. The backend executes the tool against the CMC API.
4. The tool result is sent back to Qwen as ground truth.
5. Qwen writes the final answer using only the returned data.

Every tool call is returned to the frontend and rendered in the API Trace drawer with the raw CMC JSON.

---

## CoinMarketCap API Endpoints Used

| Endpoint | Purpose | Credits |
| --- | --- | --- |
| `GET /v1/cryptocurrency/map` | Resolve ticker symbols → CMC numeric IDs | **0** (free) |
| `GET /v2/cryptocurrency/quotes/latest` | Live price, 1h/24h/7d % changes, market cap, volume | 1 per 250 assets |
| `GET /v1/cryptocurrency/listings/latest` | Ranked top-N by market cap / volume / % change | 1 per 250 assets |
| `GET /v1/global-metrics/quotes/latest` | Total market cap, 24h volume, BTC & ETH dominance | 1 |
| `GET /v1/cryptocurrency/trending/latest` | Trending assets | 1 (tier-dependent) |
| `GET /v1/cryptocurrency/trending/gainers-losers` | Top 24h gainers and losers | 1 (tier-dependent) |
| `GET /v5/real-world-assets/assets/list` | Tokenized stocks, commodities, government securities, ETFs | 1 per 250 assets |
| `GET /v1/content/latest` | Latest CMC news/content | 1 (Standard+ plan only) |

### Credit discipline

- Symbol→ID resolution uses the **free** `/map` endpoint and is cached per process.
- `/dashboard/summary` caches its result for **60 seconds**, so refreshing the dashboard doesn't burn credits.
- The alert poll loop reuses `/markets/top100` — no extra API calls beyond the normal market refresh.
- Every CMC response is logged with `credit_count`, and the sidebar / Settings page show live running usage from `/health`.

---

## Tool-Calling Tools Exposed to Qwen

| Tool | Backing CMC endpoint | When Qwen uses it |
| --- | --- | --- |
| `get_asset_quotes` | `/v2/cryptocurrency/quotes/latest` | Any price, comparison, or momentum question |
| `get_market_overview` | `/v1/global-metrics/quotes/latest` | "How is the market doing?" |
| `get_top_assets` | `/v1/cryptocurrency/listings/latest` | Leaderboards, best/worst performers |
| `get_trending` | `/v1/cryptocurrency/trending/*` | Discovery, narratives |

The system prompt enforces: **never state a price from memory**. If a tool result contains a `quotes`, `global`, or `assets` key, Qwen must use that data. If a tool returns an `error` key, Qwen reports the error — it is not allowed to invent data. The prompt also disallows em dashes/en dashes in responses, to keep answers plain and copy-paste friendly.

---

## Qwen Integration Notes

- **Endpoint**: `https://dashscope-intl.aliyuncs.com/compatible-mode/v1` (Singapore region)
- **Model**: `qwen-plus` (configurable via `QWEN_MODEL` env var)
- **SDK**: official `openai` Python package, pointed at the DashScope OpenAI-compatible endpoint
- **Temperature**: `0.0` for deterministic tool-calling

### API Pros and Cons

**Pros:**

- CoinMarketCap's `/map` endpoint is free (0 credits) — ideal for symbol resolution before billing calls.
- The response format is consistent across endpoints, so one normalization function handles all quote shapes.
- The `status.credit_count` field in every response makes cost tracking trivial.
- The OpenAI-compatible DashScope endpoint means zero SDK swaps — the standard `openai` client works.
- CMC's RWA API (Real-World Assets) is available on the free Basic plan, so Tokenized Assets works out of the box.

**Cons:**

- The `/v3/cryptocurrency/quotes/latest` endpoint's response shape varies between a dict-of-dicts and a dict-of-lists depending on the number of IDs requested. We use `/v2/` instead, which has a stable shape.
- The free tier doesn't include trending endpoints reliably — our implementation degrades gracefully and surfaces the error rather than crashing.
- The Content/News endpoint requires a Standard plan or higher; on a free key it returns a 403, which the app surfaces as a clear message instead of failing.
- Qwen occasionally emits pseudo-tool-call markup (`<function-call>...</function-call>`) inside its visible reply. We strip this on the backend with a regex post-processor.
- DashScope's international endpoint must be used with Singapore-region API keys; using the China endpoint with an international key returns `401 Invalid API key`.

---

## Tech Stack

| Layer | Choice | Why |
| --- | --- | --- |
| Backend | FastAPI + Uvicorn | Async, fast, minimal boilerplate |
| HTTP client | httpx (async) | Non-blocking CMC requests |
| LLM | Qwen via OpenAI SDK | Tool calling, no vendor lock-in |
| Frontend | Vanilla HTML/CSS/JS | Single file, no build step, fast deploys |
| Charts | Chart.js (CDN) | Lightweight, no framework |
| Fonts | Inter + JetBrains Mono | Loaded from Google Fonts |
| Hosting | Railway (Nixpacks) | Zero-config Python detection, no Dockerfile needed |

No frontend build step, no bundler, no npm. The whole UI is one `index.html` served as a static file.

---

## Project Structure

cmc-ai-analyst/
├── app/
│ ├── init.py
│ ├── main.py # FastAPI app + routes
│ ├── cmc.py # CoinMarketCap API client
│ ├── tools.py # Tool schemas + dispatcher
│ ├── llm.py # Qwen tool-calling loop
│ ├── dashboard.py # Aggregate endpoint + signal generation
│ └── static/
│ └── index.html # Full SPA (dashboard, markets, screener, alerts, tokenized assets, news, settings, chat)
├── Procfile # Railway start command
├── requirements.txt
├── .gitignore
├── .env # NOT committed — local only
└── README.md

---

## Local Development

### Prerequisites

- Python 3.11+
- CoinMarketCap API key (free tier works for everything except News)
- Alibaba Cloud DashScope API key (Singapore region)

### Setup

```bash
git clone https://github.com/Abbagigo13/cmc-ai-analyst.git
cd cmc-ai-analyst

python -m venv .venv

# Windows
.\.venv\Scripts\Activate.ps1

# macOS / Linux
source .venv/bin/activate

pip install -r requirements.txt
```

### Configure environment

Create `.env` in the project root:

CMC_API_KEY=your_coinmarketcap_key
DASHSCOPE_API_KEY=your_qwen_key
QWEN_MODEL=qwen-plus
QWEN_BASE_URL=<https://dashscope-intl.aliyuncs.com/compatible-mode/v1>

### Run

```bash
uvicorn app.main:app --reload
```

Open <http://127.0.0.1:8000/>

### Verify

<http://127.0.0.1:8000/health>

Expected:

```json
{"ok":true,"cmc_key_set":true,"qwen_key_set":true,"model":"qwen-plus","credits_used":0}
```

---

## Deployment

**Live app**: <https://web-production-1d68ca.up.railway.app/>

Deployed on Railway using Nixpacks (auto-detected from `requirements.txt`, no Dockerfile needed).

- **Build**: `pip install -r requirements.txt`
- **Start**: `uvicorn app.main:app --host 0.0.0.0 --port $PORT` (from `Procfile`)

Environment variables set in the Railway dashboard:

- `CMC_API_KEY`
- `DASHSCOPE_API_KEY`
- `QWEN_MODEL`
- `QWEN_BASE_URL`

---

## Example Queries

Try these in the Copilot panel (side panel or full-screen AI Chat):

1. What is the total crypto market cap right now?
2. Compare BTC, ETH and SOL over the last 24 hours
3. What are the top 10 gainers today?
4. Why is ZEC up 8% today?
5. Is SOL outperforming ETH this week?
6. What is trending in crypto right now?

Every answer that cites a number is backed by a live tool call. Click the API Trace button (bottom right) to see the raw JSON.

---

## What's Next

Features that would extend the app if the hackathon ran longer:

1. **Historical charts** — wire the main chart to real OHLCV data from `/v1/cryptocurrency/quotes/historical`
2. **Derivatives track** — open interest, funding rates, liquidation data
3. **Persistent alert delivery** — server-side alert engine with email/webhook delivery
4. **MCP server mode** — expose the CMC tools as a Model Context Protocol server so other AI clients can use them
5. **News on a paid CMC plan** — upgrade to Standard+ to light up the News page with live articles

---

## Acknowledgements

- CoinMarketCap API — market data
- Alibaba Cloud Model Studio — Qwen LLM
- DoraHacks — hackathon platform

## License

MIT
