# KOL Intel

**Language:** English · [中文](README_zh.md)

---

## Overview

Automatically tracks daily activity from tech, AI, and finance KOLs. A multi-stage Claude API pipeline ingests content, filters for signal, and produces a bilingual (Chinese/English) daily brief plus a 7-day rolling trend report, delivered by email.

## Features

- **Multi-platform fetching**: WeChat (via RSSHub), YouTube, RSS (blogs and industry media)
- **Multi-stage Claude analysis**: ingest → filter → aggregate → brief → trend
- **Bilingual output**: daily brief + 7-day rolling trend report in both Chinese and English
- **Automated delivery**: email (SendGrid)
- **GitHub Actions**: runs daily at UTC 06:00 (Beijing 14:00)

## Architecture

```
                      config/seeds.json
                          (18 KOLs)
                              │
                              ▼
┌─────────────┐  raw posts ┌──────────────────┐  structured  ┌─────────────┐
│   Fetcher   │ ──────────►│    Pipeline      │ ───────────► │  Reporter   │
│(fetcher.py) │            │  (pipeline.py)   │              │(reporter.py)│
└─────────────┘            └──────────────────┘              └─────────────┘
                                    ▲                                │
                            config/prompts.py                        │ reports
                            (Claude prompts)                         ▼
                                                           ┌─────────────┐
                                                           │  Delivery   │
                                                           │(delivery.py)│
                                                           └─────────────┘
                                                             Email
```

**Data flow:**
```
Fetcher ──► [raw JSON] ──► Pipeline ──► [analyzed JSON] ──► Reporter ──► [HTML] ──► Delivery
```

**Five pipeline phases:**

| Phase | Module | Description |
|---|---|---|
| P1 Ingest | pipeline.py | Structure and validate raw posts |
| P2 Filter | pipeline.py | Score relevance, discard noise |
| P3 Aggregate | pipeline.py | Cross-KOL topic clustering (COVE verification) |
| P4 Brief | reporter.py | Generate bilingual daily brief |
| P5 Trend | reporter.py | Generate 7-day rolling trend report |

## Quick Start

**1. Clone the repo**

```bash
git clone https://github.com/your-org/kol-intel.git
cd kol-intel
```

**2. Configure environment variables**

```bash
cp .env.example .env
```

Edit `.env` with the following:

| Variable | Description |
|---|---|
| `ANTHROPIC_API_KEY` | Claude API key (required) |
| `RSSHUB_BASE_URL` | Self-hosted RSSHub URL, default `http://localhost:1200` |
| `DELIVERY_EMAIL` | Report recipient email |
| `SENDGRID_API_KEY` | SendGrid key for email delivery (optional) |

**3. Install dependencies**

```bash
pip install -r requirements.txt
```

**4. Run locally**

```bash
# Full run (requires API key)
python main.py

# DRY RUN: skip AI pipeline and email, validate all other steps
DRY_RUN=1 python main.py

# Run fetcher only
python src/fetcher.py
```

**5. GitHub Actions automation**

Add the following Secrets to your repository (Settings → Secrets and variables → Actions):

- `ANTHROPIC_API_KEY`
- `RSSHUB_BASE_URL` (optional)
- `SENDGRID_API_KEY` (optional)
- `DELIVERY_EMAIL` (optional)

The workflow triggers daily at UTC 06:00. Output files are uploaded as an Artifact and retained for 30 days.

## Project Structure

```
kol-intel/
├── main.py                     # Entry point, orchestrates all modules
├── .env.example                # Environment variable template
├── requirements.txt
├── README.md
├── README_zh.md                # Chinese documentation
├── config/
│   ├── seeds.json              # KOL seed list (18 sources)
│   └── prompts.py              # Claude prompt constants
├── src/
│   ├── fetcher.py              # Multi-platform content fetching
│   ├── pipeline.py             # Claude analysis pipeline (P1–P3)
│   ├── reporter.py             # Bilingual report generation (P4–P5)
│   └── delivery.py             # Email delivery
├── data/
│   └── history/                # 7-day history store (.gitignore)
├── outputs/                    # Daily outputs (.gitignore)
└── .github/
    └── workflows/
        └── daily.yml           # GitHub Actions scheduled workflow
```

## 📡 Data Sources

### Active (verified working)

| Name | Type | Sector | Source |
|------|------|--------|--------|
| Karpathy Blog | RSS | AI | karpathy.github.io |
| Paul Graham Essays | RSS | Startup/Tech | paulgraham.com |
| Benedict Evans Newsletter | RSS | Tech Strategy | ben-evans.com |
| VentureBeat AI | RSS | AI/Tech | venturebeat.com |
| TechCrunch | RSS | Tech | techcrunch.com |
| The Verge | RSS | Tech | theverge.com |
| Macro Musings (David Beckworth) | RSS | Finance/Macro | macromusings.libsyn.com |

### Configured but currently unavailable

| Name | Platform | Reason |
|------|----------|--------|
| Sam Altman | X/LinkedIn | X API not connected ($200/mo) |
| Andrej Karpathy | YouTube | YouTube RSS restricted for this channel |
| Yann LeCun | X/LinkedIn | X API not connected |
| Andrew Ng | YouTube | YouTube RSS restricted for this channel |
| Jensen Huang (NVIDIA) | YouTube | YouTube RSS restricted for this channel |
| Marc Andreessen | X | X API not connected |
| Paul Graham | X | X API not connected |
| Demis Hassabis | X/LinkedIn | X API not connected |
| Li Feifei | X/LinkedIn | X API not connected |
| Ray Dalio | X/LinkedIn | X API not connected |
| Howard Marks | RSS | Oaktree RSS feed returns broken XML |
| Michael Burry | X | X API not connected |
| AQR Capital (Cliff Asness) | RSS | Feed returns no entries (bot-blocked) |
| Epsilon Theory (Ben Hunt) | RSS | Feed returns no entries (bot-blocked) |
| Verdad Research | RSS | Feed returns no entries (bot-blocked) |

### How to add sources

Add an entry to `config/seeds.json`. Supported platform types:
- `rss`: provide an `rss_url` directly
- `youtube`: provide a `youtube_channel_id` (note: some large channels have RSS restricted by YouTube)
- `wechat`: requires self-hosted RSSHub + Sogou WeChat ID
- `x`: requires Twitter API v2 Basic ($200/mo)

---

## License

MIT
