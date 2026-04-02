# kol-intel

> 每日自动追踪科技/AI/金融行业 KOL 动态，通过 Claude API 多阶段分析，输出中英双语简报与 7 日趋势报告。
>
> Daily KOL intelligence: scrape → analyze with Claude → bilingual brief + 7-day trend report.

---

## 功能特性 / Features

- **多平台抓取**：X (Twitter)、LinkedIn、微信公众号（via RSSHub）、YouTube、RSS
- **Claude 多阶段分析**：摄取 → 过滤 → 聚合 → 简报生成 → 趋势分析
- **双语输出**：中英文每日简报 + 7 日趋势报告
- **自动推送**：邮件（SendGrid）或 Webhook
- **GitHub Actions**：每日 UTC 08:00 自动运行

---

## 架构图 / Architecture

```
                        config/seeds.json
                          (15 KOLs)
                               │
                               ▼
┌──────────────┐   raw posts  ┌──────────────────┐  structured  ┌──────────────┐
│   Fetcher    │ ────────────►│     Pipeline     │ ────────────►│   Reporter   │
│ (fetcher.py) │              │  (pipeline.py)   │              │(reporter.py) │
└──────────────┘              └──────────────────┘              └──────────────┘
                                       ▲                                │
                               config/prompts.py                        │ reports
                               (Claude prompts)                         ▼
                                                               ┌──────────────┐
                                                               │   Delivery   │
                                                               │(delivery.py) │
                                                               └──────────────┘
                                                               Email / Webhook
```

**数据流 / Data Flow:**
```
Fetcher ──► [raw JSON] ──► Pipeline ──► [analyzed JSON] ──► Reporter ──► [MD/HTML] ──► Delivery
```

---

## 快速启动 / Quick Start

### 1. 克隆仓库

```bash
git clone https://github.com/your-org/kol-intel.git
cd kol-intel
```

### 2. 配置环境变量

```bash
cp .env.example .env
# 编辑 .env，填入以下 API Key：
#   ANTHROPIC_API_KEY      — Claude API 密钥
#   TWITTER_BEARER_TOKEN   — X (Twitter) Bearer Token
#   RSSHUB_BASE_URL        — 自建 RSSHub 地址（默认 http://localhost:1200）
#   DELIVERY_EMAIL         — 收件邮箱
#   SENDGRID_API_KEY       — SendGrid API 密钥
```

### 3. 安装依赖

```bash
pip install -r requirements.txt
```

### 4. 测试抓取模块

```bash
python src/fetcher.py
```

### 5. 验证 KOL 列表加载

```bash
python -c "import json; d=json.load(open('config/seeds.json')); print(f'Loaded {len(d)} KOLs')"
```

---

## 目录结构 / Project Structure

```
kol-intel/
├── .env.example                # 环境变量模板
├── .gitignore
├── requirements.txt
├── README.md
├── config/
│   ├── seeds.json              # KOL 种子列表（15 位）
│   └── prompts.py              # Claude 分析 Prompt 常量
├── src/
│   ├── __init__.py
│   ├── fetcher.py              # 多平台数据抓取
│   ├── pipeline.py             # Claude 多阶段分析流水线
│   ├── reporter.py             # 双语报告生成
│   └── delivery.py             # 邮件 / Webhook 推送
├── data/
│   └── history/                # 7 日历史简报存储（gitignored）
├── outputs/                    # 当日输出（gitignored）
└── .github/
    └── workflows/
        └── daily.yml           # GitHub Actions 定时任务
```

---

## KOL 覆盖范围 / KOL Coverage

| 行业 | 代表人物 |
|---|---|
| AI | Sam Altman, Andrej Karpathy, Yann LeCun, Andrew Ng, Jensen Huang, Demis Hassabis, Li Feifei |
| AI/China | Robin Li, Zhou Hongyi, Wang Xiaochuan |
| VC/Startup | Marc Andreessen, Paul Graham |
| Finance | Ray Dalio, Howard Marks, Michael Burry |

---

## License

MIT
