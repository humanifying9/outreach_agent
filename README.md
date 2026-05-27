# ColdEmailer

Browser-based cold-email agent. Type who you want to reach, watch a real Chrome window discover companies and contacts, review LLM-written drafts, and have them saved straight into your Gmail drafts folder for you to send manually.

## What's in here

- **`backend/`** — FastAPI server, Gmail OAuth client, Playwright browser agent, Hunter.io lead finder, copywriter orchestrator. Streams agent activity over a WebSocket.
- **`frontend/`** — single-page UI (HTML/CSS/JS). Live activity log + draft review.
- **`cold_emailer.py`** — the original Ollama-based researcher + copywriter, used as a library now.

## Setup

### 1. Install dependencies

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium
```

### 2. Get a Gmail OAuth client secret

1. Go to https://console.cloud.google.com/
2. Create a new project (or pick an existing one).
3. Enable the **Gmail API** under *APIs & Services > Library*.
4. Configure the OAuth consent screen as **External**. Add your own Google email as a Test user. Scopes you need: `gmail.compose` (and the basic profile scopes are added automatically).
5. *APIs & Services > Credentials > Create credentials > OAuth client ID > Desktop app*.
6. Download the JSON. Save it as `credentials/google_client_secret.json` in this project.

### 3. (Optional) Hunter.io API key for contact finding

Sign up at https://hunter.io (25 free searches/month). Then:

```bash
cp .env.example .env
# edit .env and paste your HUNTER_API_KEY
```

Without a Hunter key the agent falls back to scraping any `mailto:` links / publicly-visible addresses it can find on the company website.

### 4. Make sure Ollama is running with your model

```bash
ollama serve            # in one terminal
ollama pull qwen2.5     # or whatever model you set in .env
```

### 5. Edit `resume.json`

Replace the default with your actual skills, projects, interests. The copywriter uses this to personalize emails.

## Running

```bash
source .venv/bin/activate
uvicorn backend.server:app --reload --port 8000
```

Open http://localhost:8000 in your browser.

## Using it

1. Click **Connect Gmail** — a browser tab opens for Google consent.
2. Type a target description into the search box (e.g. *"AI startups in San Francisco under 50 people"*).
3. Hit **Start campaign**. A Chrome window opens; you can watch the agent search DuckDuckGo, visit company sites, and scrape contact info.
4. The live activity panel streams every step. Drafts appear in panel 3 as they're generated.
5. Each draft is saved into your Gmail Drafts folder. Open Gmail, review, and hit send (or edit first).

## Safety / behavior

- The agent **never sends mail automatically**. It only creates drafts.
- The OAuth scope it requests is `gmail.compose` — it cannot read your inbox.
- Tokens are stored in `credentials/google_token.json` (gitignored). Delete that file or click *Disconnect Gmail* to revoke locally.
- Search uses DuckDuckGo (no API key) to avoid Google's bot protection.

## Project layout

```
ColdEmailer/
├── backend/
│   ├── server.py          # FastAPI app + WebSocket
│   ├── orchestrator.py    # discover -> research -> write -> Gmail draft
│   ├── browser_agent.py   # Playwright (headed Chrome)
│   ├── lead_finder.py     # Hunter.io + scraping fallback
│   ├── gmail_client.py    # OAuth + draft creation
│   ├── copywriter.py      # async wrapper over cold_emailer.py
│   └── event_bus.py       # broadcasts agent events to WebSocket subscribers
├── frontend/
│   ├── index.html
│   ├── app.js
│   └── style.css
├── credentials/           # gitignored — your OAuth secret + token live here
├── data/                  # gitignored — saved drafts metadata
├── cold_emailer.py        # original Ollama researcher + copywriter
├── resume.json
├── companies.csv
├── requirements.txt
└── .env.example
```
