# -*- coding: utf-8 -*-
"""
main.py — KOL Intel Pipeline 主入口

完整执行流程：
  Step 1  Fetch    — 多平台 KOL 内容抓取（fetcher）
  Step 2  Pipeline — Claude 三阶段分析（pipeline: P1 Ingest → P2 Filter → P3 Aggregate）
  Step 3  Reports  — Claude 双阶段报告生成（reporter: P4 Brief → P5 Trend）
  Step 4  Delivery — SendGrid 邮件推送（delivery）

运行方式：
  python main.py            # 完整运行
  DRY_RUN=1 python main.py  # 跳过 AI Pipeline，跳过实际邮件发送，验证其余链路
"""

import collections
import datetime
import json
import logging
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

from config.seeds import load_seeds
from src.delivery import format_email_html, send_email
from src.fetcher import fetch_all, save_raw
from src.pipeline import run_pipeline
from src.reporter import generate_brief, generate_trend_report, save_outputs

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)

# ── DRY RUN mock clusters ────────────────────────────────────────────────────

def _mock_clusters(date_str: str) -> dict:
    return {
        "aggregation_date": date_str,
        "topic_clusters": [
            {
                "topic_id": "T001",
                "topic_label_en": "DRY RUN TEST",
                "topic_label_zh": "演练测试",
                "signal_strength": "LOW",
                "post_count": 1,
                "kols_involved": ["TEST"],
                "consensus_view": {"en": "dry run", "zh": "演练"},
                "dissenting_views": [],
                "verified_facts": [],
                "disputed_claims": [],
                "source_post_ids": [],
            }
        ],
    }


def main() -> None:
    """
    串联所有模块，执行从数据抓取到邮件推送的完整每日情报流水线。

    DRY_RUN=1 时跳过 AI Pipeline（Step 2）和实际邮件发送，
    其余步骤照常运行，用于低成本全链路验证。

    任何阶段抛出未捕获的异常都会向上传播，导致进程以非零退出码终止，
    从而触发 GitHub Actions 的 workflow failure 告警。
    """
    dry_run = os.getenv("DRY_RUN", "").strip() == "1"
    date_str = os.getenv("PIPELINE_DATE", datetime.date.today().isoformat())

    if dry_run:
        logger.info("=== KOL Intel Pipeline starting [DRY RUN]: %s ===", date_str)
    else:
        logger.info("=== KOL Intel Pipeline starting: %s ===", date_str)

    # ── Step 1: Fetch ────────────────────────────────────────────────────
    logger.info("Step 1/4 — Fetching KOL content...")
    seeds = load_seeds()
    raw_posts = fetch_all(seeds, date_str)
    raw_path = save_raw(raw_posts, date_str)
    logger.info("Fetched %d raw posts → %s", len(raw_posts), raw_path)

    if not raw_posts:
        logger.warning(
            "No posts fetched for %s. "
            "Check API credentials and platform availability. "
            "Continuing pipeline with empty input.",
            date_str,
        )

    # ── Step 2: AI Pipeline (P1 → P2 → P3) ─────────────────────────────
    if dry_run:
        logger.info("Step 2/4 — [DRY RUN] Skipping AI pipeline, using mock clusters.")
        clusters = _mock_clusters(date_str)
    else:
        logger.info("Step 2/4 — Running AI analysis pipeline (P1→P2→P3)...")
        clusters = run_pipeline(raw_posts, date_str)

    n_clusters = len(clusters.get("topic_clusters", []))
    logger.info("Clustered into %d topics", n_clusters)

    # ── Step 3: Reports (P4 + P5) ────────────────────────────────────────
    logger.info("Step 3/4 — Generating reports (P4 Brief + P5 Trend)...")
    stats = {
        "kols_monitored": len(seeds),
        "posts_analyzed": len(raw_posts),
    }
    brief = generate_brief(clusters, date_str, stats)
    trend = generate_trend_report(brief, date_str)
    save_outputs(brief, trend, date_str)

    # ── Step 4: Delivery ─────────────────────────────────────────────────
    logger.info("Step 4/4 — Preparing email report...")
    html = format_email_html(brief, trend)

    if dry_run:
        logger.info("[DRY RUN] 邮件内容预览：\n%s", html[:500])
        logger.info("[DRY RUN] 跳过实际邮件发送。")
        email_success = False
        email_status = "skipped (dry run)"
    else:
        success = send_email(html, date_str)
        email_success = success
        if success:
            logger.info("Email delivered successfully.")
            email_status = "sent"
        else:
            logger.warning("Email delivery did not complete (see above for details).")
            email_status = "failed / skipped"

    # ── Final summary ────────────────────────────────────────────────────
    platform_counts = collections.Counter(p["platform"] for p in raw_posts)
    topic_list = clusters.get("topic_clusters", [])

    print("\n" + "═" * 60)
    print(f"  Pipeline Summary {'[DRY RUN] ' if dry_run else ''}— {date_str}")
    print("═" * 60)

    print("  抓取条数 / Fetch counts:")
    for platform in ("youtube", "wechat", "rss"):
        print(f"    {platform:<10} {platform_counts.get(platform, 0)} 条")
    print(f"    {'total':<10} {len(raw_posts)} 条")

    print(f"\n  Topic clusters : {len(topic_list)}")
    for t in topic_list:
        label = t.get("topic_label_en", "?")
        strength = t.get("signal_strength", "?")
        print(f"    [{strength}] {label}")

    brief_ok = bool(brief.get("top_signals"))
    trend_ok = bool(trend.get("trends"))
    print(f"\n  Brief (P4)     : {'✓ generated' if brief_ok else '⚠ empty'}")
    print(f"  Trend (P5)     : {'✓ generated' if trend_ok else '⚠ empty'}")
    print(f"  Email delivery : {email_status}")

    print("═" * 60)

    if dry_run:
        logger.info("=== DRY RUN complete: %s ===", date_str)
    else:
        logger.info("=== Pipeline complete: %s ===", date_str)


if __name__ == "__main__":
    main()
