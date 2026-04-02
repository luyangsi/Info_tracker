# -*- coding: utf-8 -*-
"""
reporter.py — 双语报告生成模块

阶段：
  Phase 4 (Brief)  — 将 topic clusters 转化为每日双语简报（PROMPT_4_BRIEF）
  Phase 5 (Trend)  — 基于 7 日历史简报生成滚动趋势报告（PROMPT_5_TREND）

入口：
  generate_brief(clusters, date_str, pipeline_stats)  -> dict
  generate_trend_report(brief, date_str)              -> dict
  save_outputs(brief, trend, date_str)                -> None
"""

import glob
import json
import logging
import shutil
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from config.prompts import SYSTEM_PROMPT, PROMPT_4_BRIEF, PROMPT_5_TREND
from src.pipeline import _call_claude  # reuse the shared Claude wrapper

load_dotenv()

logger = logging.getLogger(__name__)

OUTPUTS_DIR = Path(__file__).parent.parent / "outputs"
HISTORY_DIR = Path(__file__).parent.parent / "data" / "history"


def _ensure_dirs() -> None:
    """确保 outputs/ 和 data/history/ 目录存在。"""
    OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
    HISTORY_DIR.mkdir(parents=True, exist_ok=True)


def _write_json(path: Path, data: dict[str, Any]) -> None:
    """以 UTF-8 / ensure_ascii=False / indent=2 写入 JSON 文件。"""
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# ─────────────────────────────────────────────
# Phase 4: Daily Brief
# ─────────────────────────────────────────────

def generate_brief(
    clusters: dict[str, Any],
    date_str: str,
    pipeline_stats: dict[str, Any],
) -> dict[str, Any]:
    """
    Phase 4 — Daily Brief：将 topic clusters 转化为每日双语简报。

    从 pipeline_stats 中读取 kols_monitored 和 posts_analyzed，
    注入 clusters 后调用 Claude（PROMPT_4_BRIEF），返回 brief dict。

    Args:
        clusters:       run_pipeline() 返回的 topic clusters dict。
        date_str:       目标日期，格式 "YYYY-MM-DD"。
        pipeline_stats: 包含 "kols_monitored" 和 "posts_analyzed" 的 dict。

    Returns:
        Claude 返回的 brief dict，含 briefing_date、stats、top_signals、
        deep_dives、notable_voices、watchlist 字段。
    """
    # Embed pipeline metadata so Claude can populate the HEADER stats block
    enriched_clusters = {
        **clusters,
        "_meta": {
            "kols_monitored": pipeline_stats.get("kols_monitored", 0),
            "posts_analyzed": pipeline_stats.get("posts_analyzed", 0),
            "topics_surfaced": len(clusters.get("topic_clusters", [])),
        },
    }

    user_prompt = PROMPT_4_BRIEF.format(
        TOPIC_CLUSTERS=json.dumps(enriched_clusters, ensure_ascii=False, indent=2)
    )

    brief = _call_claude(system=SYSTEM_PROMPT, user=user_prompt)

    n_signals = len(brief.get("top_signals", []))
    n_dives = len(brief.get("deep_dives", []))
    logger.info("Daily brief generated: %d signals, %d deep-dives", n_signals, n_dives)

    return brief


# ─────────────────────────────────────────────
# Phase 5: 7-Day Trend Report
# ─────────────────────────────────────────────

def _load_history_briefs(date_str: str, max_days: int = 6) -> list[dict[str, Any]]:
    """
    从 data/history/ 扫描最近 max_days 个 *_brief.json 文件。

    按文件名（日期）升序排列后取最新的 max_days 个，
    排除文件名与 date_str 完全匹配的当日文件（尚未写入 history/）。

    Args:
        date_str:  今日日期字符串，用于排除当日文件。
        max_days:  最多加载的历史天数，默认 6。

    Returns:
        历史 brief dict 列表（最旧→最新），数量 0–max_days。
    """
    pattern = str(HISTORY_DIR / "*_brief.json")
    all_files = sorted(glob.glob(pattern))  # lexicographic = chronological for YYYY-MM-DD

    # Exclude today's file if it already exists in history
    today_filename = f"{date_str}_brief.json"
    history_files = [f for f in all_files if Path(f).name != today_filename]

    # Take the most recent max_days files
    selected = history_files[-max_days:] if len(history_files) > max_days else history_files

    briefs: list[dict[str, Any]] = []
    for fpath in selected:
        try:
            with open(fpath, encoding="utf-8") as f:
                briefs.append(json.load(f))
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("Could not load history brief %s: %s", fpath, exc)

    logger.info("Loaded %d historical brief(s) for trend analysis.", len(briefs))
    return briefs


def generate_trend_report(
    brief: dict[str, Any],
    date_str: str,
) -> dict[str, Any]:
    """
    Phase 5 — Trend Report：基于今日简报与最近 6 天历史简报生成 7 日滚动趋势报告。

    历史文件数量不足 6 天时使用已有数量。

    Args:
        brief:     generate_brief() 返回的今日 brief dict。
        date_str:  今日日期，格式 "YYYY-MM-DD"。

    Returns:
        Claude 返回的 trend dict，含 report_date、window、macro_signal、
        trends、kol_spotlights 字段。
    """
    history_briefs = _load_history_briefs(date_str, max_days=6)

    user_prompt = PROMPT_5_TREND.format(
        TODAY_BRIEFING=json.dumps(brief, ensure_ascii=False, indent=2),
        HISTORICAL_BRIEFINGS=json.dumps(history_briefs, ensure_ascii=False, indent=2),
    )

    trend = _call_claude(system=SYSTEM_PROMPT, user=user_prompt)

    n_trends = len(trend.get("trends", []))
    n_spotlights = len(trend.get("kol_spotlights", []))
    logger.info(
        "Trend report generated: %d trends, %d KOL spotlights (window: %s)",
        n_trends, n_spotlights, trend.get("window", "7-day rolling"),
    )

    return trend


# ─────────────────────────────────────────────
# Persistence
# ─────────────────────────────────────────────

def save_outputs(
    brief: dict[str, Any],
    trend: dict[str, Any],
    date_str: str,
) -> None:
    """
    将 brief 和 trend 写入 outputs/，并将 brief 备份到 data/history/。

    写入路径：
      outputs/{date_str}_brief.json
      outputs/{date_str}_trend.json
      data/history/{date_str}_brief.json  （供次日 Phase 5 使用）

    Args:
        brief:     generate_brief() 返回的简报 dict。
        trend:     generate_trend_report() 返回的趋势 dict。
        date_str:  目标日期，格式 "YYYY-MM-DD"。
    """
    _ensure_dirs()

    brief_out = OUTPUTS_DIR / f"{date_str}_brief.json"
    trend_out = OUTPUTS_DIR / f"{date_str}_trend.json"
    brief_hist = HISTORY_DIR / f"{date_str}_brief.json"

    _write_json(brief_out, brief)
    logger.info("Saved → %s", brief_out)

    _write_json(trend_out, trend)
    logger.info("Saved → %s", trend_out)

    shutil.copy2(brief_out, brief_hist)
    logger.info("Copied → %s  (history backup)", brief_hist)


# ─────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────

if __name__ == "__main__":
    import sys

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        datefmt="%H:%M:%S",
    )

    # ── Find latest clusters file ────────────────────────────────────────
    cluster_files = sorted(glob.glob(str(HISTORY_DIR / "*_clusters.json")))
    if not cluster_files:
        logger.error(
            "No *_clusters.json found in %s. Run src/pipeline.py first.", HISTORY_DIR
        )
        sys.exit(1)

    latest_clusters_path = cluster_files[-1]
    date_str = Path(latest_clusters_path).name.replace("_clusters.json", "")
    logger.info("Loading clusters from: %s  (date: %s)", latest_clusters_path, date_str)

    with open(latest_clusters_path, encoding="utf-8") as f:
        clusters: dict[str, Any] = json.load(f)

    n_clusters = len(clusters.get("topic_clusters", []))
    logger.info("Loaded %d topic cluster(s).", n_clusters)

    # ── Derive pipeline stats from clusters (best-effort) ───────────────
    # pipeline.py saves kols/posts count in cluster metadata if present;
    # fall back to reasonable defaults so reporter can always run standalone.
    all_kols: set[str] = set()
    all_post_ids: set[str] = set()
    for tc in clusters.get("topic_clusters", []):
        all_kols.update(tc.get("kols_involved", []))
        all_post_ids.update(tc.get("source_post_ids", []))

    pipeline_stats = {
        "kols_monitored": len(all_kols) or clusters.get("_meta", {}).get("kols_monitored", 0),
        "posts_analyzed": len(all_post_ids) or clusters.get("_meta", {}).get("posts_analyzed", 0),
    }
    logger.info(
        "Pipeline stats — KOLs: %d, posts: %d",
        pipeline_stats["kols_monitored"],
        pipeline_stats["posts_analyzed"],
    )

    # ── Phase 4: Daily Brief ─────────────────────────────────────────────
    logger.info("Running Phase 4/5 — Daily Brief...")
    brief = generate_brief(clusters, date_str, pipeline_stats)

    # ── Phase 5: Trend Report ────────────────────────────────────────────
    logger.info("Running Phase 5/5 — Trend Report...")
    trend = generate_trend_report(brief, date_str)

    # ── Save all outputs ─────────────────────────────────────────────────
    save_outputs(brief, trend, date_str)

    # ── Print summary ────────────────────────────────────────────────────
    logger.info("─── Brief Summary ──────────────────────────")
    for i, sig in enumerate(brief.get("top_signals", []), 1):
        logger.info("  Signal %d: %s", i, sig.get("en", ""))
    logger.info("─── Trend Summary ──────────────────────────")
    macro = trend.get("macro_signal", {})
    logger.info("  Macro signal: %s", macro.get("en", ""))
    for t in trend.get("trends", []):
        logger.info(
            "  [%s] %s  momentum=%s novelty=%s",
            t.get("direction", "?"),
            t.get("label_en", "?"),
            t.get("momentum_score", "?"),
            t.get("novelty_score", "?"),
        )
    logger.info("────────────────────────────────────────────")
