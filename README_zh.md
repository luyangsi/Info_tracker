# KOL Intel

**语言：** [English](README.md) · 中文

---

## 项目简介

每日自动追踪科技、AI、金融行业 KOL 动态。通过 Claude API 多阶段分析，输出中英双语每日简报与 7 日趋势报告，并支持邮件推送。

## 功能特性

- **多平台抓取**：微信公众号（via RSSHub）、YouTube、RSS（博客 / 行业媒体）
- **Claude 多阶段分析**：原始摄取 → 相关性过滤 → 主题聚合 → 简报生成 → 趋势分析
- **双语输出**：中英文每日简报 + 7 日滚动趋势报告
- **自动推送**：邮件（SendGrid）
- **GitHub Actions**：每日 UTC 06:00（北京时间 14:00）自动运行

## 架构

```
                      config/seeds.json
                         (18 个 KOL)
                              │
                              ▼
┌─────────────┐  原始帖子  ┌──────────────────┐  结构化数据  ┌─────────────┐
│  Fetcher    │ ─────────► │    Pipeline      │ ──────────► │  Reporter   │
│(fetcher.py) │            │  (pipeline.py)   │             │(reporter.py)│
└─────────────┘            └──────────────────┘             └─────────────┘
                                    ▲                               │
                            config/prompts.py                       │ 报告
                            (Claude Prompt)                         ▼
                                                          ┌─────────────┐
                                                          │  Delivery   │
                                                          │(delivery.py)│
                                                          └─────────────┘
                                                             邮件推送
```

**数据流：**
```
Fetcher ──► [原始 JSON] ──► Pipeline ──► [分析 JSON] ──► Reporter ──► [HTML] ──► Delivery
```

**Pipeline 五阶段：**

| 阶段 | 模块 | 说明 |
|---|---|---|
| P1 Ingest | pipeline.py | 结构化验证原始帖子 |
| P2 Filter | pipeline.py | 相关性评分，过滤噪声 |
| P3 Aggregate | pipeline.py | 跨 KOL 主题聚合（COVE 核查） |
| P4 Brief | reporter.py | 生成每日双语简报 |
| P5 Trend | reporter.py | 生成 7 日滚动趋势报告 |

## 快速启动

**1. 克隆仓库**

```bash
git clone https://github.com/your-org/kol-intel.git
cd kol-intel
```

**2. 配置环境变量**

```bash
cp .env.example .env
```

编辑 `.env`，填入以下字段：

| 变量 | 说明 |
|---|---|
| `ANTHROPIC_API_KEY` | Claude API 密钥（必填） |
| `RSSHUB_BASE_URL` | 自建 RSSHub 地址，默认 `http://localhost:1200` |
| `DELIVERY_EMAIL` | 报告收件邮箱 |
| `SENDGRID_API_KEY` | SendGrid 邮件推送密钥（可选） |

**3. 安装依赖**

```bash
pip install -r requirements.txt
```

**4. 本地运行**

```bash
# 完整运行（需 API Key）
python main.py

# DRY RUN：跳过 AI 分析和邮件发送，验证其余链路
DRY_RUN=1 python main.py

# 单独运行抓取模块
python src/fetcher.py
```

**5. GitHub Actions 自动化**

将以下 Secrets 添加至仓库（Settings → Secrets and variables → Actions）：

- `ANTHROPIC_API_KEY`
- `RSSHUB_BASE_URL`（可选）
- `SENDGRID_API_KEY`（可选）
- `DELIVERY_EMAIL`（可选）

工作流每日 UTC 06:00 自动触发，输出文件上传为 Artifact，保留 30 天。

## 目录结构

```
kol-intel/
├── main.py                     # 主入口，串联全部模块
├── .env.example                # 环境变量模板
├── requirements.txt
├── README.md                   # 英文文档
├── README_zh.md                # 中文文档
├── config/
│   ├── seeds.json              # KOL 种子列表（18 个）
│   └── prompts.py              # Claude 分析 Prompt 常量
├── src/
│   ├── fetcher.py              # 多平台数据抓取
│   ├── pipeline.py             # Claude 多阶段分析流水线（P1–P3）
│   ├── reporter.py             # 双语报告生成（P4–P5）
│   └── delivery.py             # 邮件推送
├── data/
│   └── history/                # 7 日历史数据存储（.gitignore）
├── outputs/                    # 当日输出（.gitignore）
└── .github/
    └── workflows/
        └── daily.yml           # GitHub Actions 定时任务
```

## KOL 覆盖范围

| 行业 | 来源 |
|---|---|
| AI | Sam Altman, Andrej Karpathy, Yann LeCun, Andrew Ng, Jensen Huang, Demis Hassabis, Li Feifei |
| VC / 创业 | Marc Andreessen, Paul Graham |
| 金融 | Ray Dalio, Howard Marks, Michael Burry |
| AI 博客 | Karpathy Blog, Paul Graham Essays |
| 科技媒体 | Benedict Evans, VentureBeat AI, TechCrunch, The Verge |

---

## License

MIT
