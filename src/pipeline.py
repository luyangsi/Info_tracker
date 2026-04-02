# -*- coding: utf-8 -*-
"""
pipeline.py — Claude API 多阶段智能分析流水线

阶段：
  Phase 1 (Ingest)     — 原始帖子结构化与验证（PROMPT_1_INGEST）
  Phase 2 (Filter)     — 相关性评分与噪声过滤（PROMPT_2_FILTER）
  Phase 3 (Aggregate)  — 跨 KOL 主题聚合，含 COVE 核查（PROMPT_3_AGGREGATE）

入口：run_pipeline(raw_posts, date_str) -> dict
"""

import json
import logging
import os
import time
from pathlib import Path
from typing import Any

import anthropic
from dotenv import load_dotenv

from config.prompts import (
    SYSTEM_PROMPT,
    PROMPT_1_INGEST,
    PROMPT_2_FILTER,
    PROMPT_3_AGGREGATE,
)

load_dotenv()

logger = logging.getLogger(__name__)

_MODEL = "claude-opus-4-5"
_MAX_TOKENS = 4096
_RATE_LIMIT_SLEEP = 3  # seconds between API calls

HISTORY_DIR = Path(__file__).parent.parent / "data" / "history"


# ─────────────────────────────────────────────
# Internal Claude wrapper
# ─────────────────────────────────────────────

def _call_claude(system: str, user: str) -> dict[str, Any]:
    """
    执行单次 Claude API 调用，返回解析后的 JSON dict。

    调用前 sleep 3 秒以避免触发速率限制。
    若响应文本不是合法 JSON，打印原始内容后抛出 ValueError。

    Args:
        system: 系统 prompt（角色 + 规则）。
        user:   用户 prompt（任务 + 数据）。

    Returns:
        Claude 响应文本经 json.loads 解析后的 dict。

    Raises:
        ValueError:          响应不是合法 JSON。
        anthropic.APIError:  API 调用失败（由调用方捕获）。
    """
    time.sleep(_RATE_LIMIT_SLEEP)

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise EnvironmentError("ANTHROPIC_API_KEY is not set in environment.")

    client = anthropic.Anthropic(api_key=api_key)

    response = client.messages.create(
        model=_MODEL,
        max_tokens=_MAX_TOKENS,
        system=system,
        messages=[
            {"role": "user", "content": user},
            {"role": "assistant", "content": "{"},
        ],
    )

    raw_text: str = "{" + response.content[0].text

    import re as _re

    def _try_parse(text: str):
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return None

    # 1. Direct parse
    result = _try_parse(raw_text)
    if result is not None:
        return result

    stripped = raw_text.strip()

    # 2. Leading code fence (```json ... ``` or ``` ... ```)
    if stripped.startswith("```"):
        inner = stripped.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
        result = _try_parse(inner)
        if result is not None:
            return result

    # 3. Embedded code fence anywhere in the response
    fence_match = _re.search(r"```(?:json)?\s*\n([\s\S]*?)\n```", stripped)
    if fence_match:
        result = _try_parse(fence_match.group(1).strip())
        if result is not None:
            return result

    # 4. First JSON object or array in the text
    obj_match = _re.search(r"\{[\s\S]*\}", stripped)
    if obj_match:
        result = _try_parse(obj_match.group(0))
        if result is not None:
            return result

    logger.error("Claude returned non-JSON response:\n%s", raw_text)
    raise ValueError(f"Claude response is not valid JSON. Raw text logged above.")


# ─────────────────────────────────────────────
# Pipeline stages
# ─────────────────────────────────────────────

def _phase1_ingest(raw_posts: list[dict[str, Any]], date_str: str) -> dict[str, Any]:
    """
    Phase 1 — Ingest：将原始帖子列表发送给 Claude，执行结构化验证。

    使用 PROMPT_1_INGEST，注入 DATE 和 RAW_POSTS 变量。
    返回 Claude 输出的完整 dict（含 extraction_date、total_raw_items、items_passed、posts）。

    Args:
        raw_posts: fetch_all() 返回的原始帖子列表。
        date_str:  目标日期，格式 "YYYY-MM-DD"。

    Returns:
        结构化验证结果 dict。
    """
    raw_posts_json = json.dumps(raw_posts, ensure_ascii=False, indent=2)
    user_prompt = PROMPT_1_INGEST.format(DATE=date_str, RAW_POSTS=raw_posts_json)
    return _call_claude(system=SYSTEM_PROMPT, user=user_prompt)


def _phase2_filter(structured: dict[str, Any]) -> dict[str, Any]:
    """
    Phase 2 — Filter：对结构化帖子进行相关性评分，保留高信号内容。

    使用 PROMPT_2_FILTER，注入 STRUCTURED_POSTS（仅传 posts 列表）。
    调用后打印 filter_summary 摘要。

    Args:
        structured: _phase1_ingest() 返回的 dict，需含 "posts" 键。

    Returns:
        过滤结果 dict（含 filter_summary 和 posts）。
    """
    posts_json = json.dumps(structured.get("posts", []), ensure_ascii=False, indent=2)
    user_prompt = PROMPT_2_FILTER.format(STRUCTURED_POSTS=posts_json)
    filtered = _call_claude(system=SYSTEM_PROMPT, user=user_prompt)

    summary = filtered.get("filter_summary", {})
    logger.info(
        "  Filter summary — input: %d, included: %d, highlighted: %d, discarded: %d",
        summary.get("total_input", "?"),
        summary.get("included", "?"),
        summary.get("highlighted", "?"),
        summary.get("discarded", "?"),
    )
    return filtered


def _phase3_aggregate(filtered: dict[str, Any], date_str: str) -> dict[str, Any]:
    """
    Phase 3 — Aggregate：将 status=="include" 的帖子发送给 Claude 进行主题聚合。

    使用 PROMPT_3_AGGREGATE，注入 FILTERED_POSTS（仅含 include 状态的帖子）。
    应用 COVE 核查，返回 topic_clusters。

    Args:
        filtered:  _phase2_filter() 返回的 dict，需含 "posts" 键。
        date_str:  目标日期，用于日志标注。

    Returns:
        聚合结果 dict（含 aggregation_date 和 topic_clusters）。
    """
    include_posts = [
        p for p in filtered.get("posts", [])
        if p.get("status") == "include"
    ]
    logger.info("  Aggregating %d included posts for %s", len(include_posts), date_str)

    posts_json = json.dumps(include_posts, ensure_ascii=False, indent=2)
    user_prompt = PROMPT_3_AGGREGATE.format(FILTERED_POSTS=posts_json)
    return _call_claude(system=SYSTEM_PROMPT, user=user_prompt)


# ─────────────────────────────────────────────
# Persistence
# ─────────────────────────────────────────────

def _save_clusters(clusters: dict[str, Any], date_str: str) -> str:
    """
    将 topic clusters 保存为 data/history/{date_str}_clusters.json。

    Args:
        clusters:  _phase3_aggregate() 返回的 dict。
        date_str:  目标日期，用于文件命名。

    Returns:
        写入文件的绝对路径字符串。
    """
    HISTORY_DIR.mkdir(parents=True, exist_ok=True)
    out_path = HISTORY_DIR / f"{date_str}_clusters.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(clusters, f, ensure_ascii=False, indent=2)
    return str(out_path)


# ─────────────────────────────────────────────
# Public entry point
# ─────────────────────────────────────────────

def run_pipeline(raw_posts: list[dict[str, Any]], date_str: str) -> dict[str, Any]:
    """
    执行 P1 → P2 → P3 三阶段 Claude API 调用链，返回 topic_clusters dict。

    流程：
      Phase 1/3 Ingest    — 结构化验证原始帖子
      Phase 2/3 Filter    — 相关性评分 + 噪声过滤
      Phase 3/3 Aggregate — 跨 KOL 主题聚合（COVE 核查）

    任何阶段的 anthropic.APIError 都会被捕获、记录后重新抛出，
    以便调用方决定是否重试或告警。

    Args:
        raw_posts: fetch_all() 返回的原始帖子列表。
        date_str:  目标日期，格式 "YYYY-MM-DD"。

    Returns:
        topic clusters dict，结构见 PROMPT_3_AGGREGATE 输出格式。

    Raises:
        anthropic.APIError: Claude API 调用失败。
        ValueError:         某阶段响应不是合法 JSON。
        EnvironmentError:   ANTHROPIC_API_KEY 未配置。
    """
    logger.info("=== Pipeline start | date: %s | posts: %d ===", date_str, len(raw_posts))

    try:
        # ── Phase 1: Ingest ──────────────────────────────────────────────
        logger.info("Running Phase 1/3 — Ingest (structuring %d raw posts)...", len(raw_posts))
        structured = _phase1_ingest(raw_posts, date_str)
        items_passed = structured.get("items_passed", len(structured.get("posts", [])))
        logger.info("  Ingest complete — %d / %d posts passed validation.",
                    items_passed, structured.get("total_raw_items", len(raw_posts)))

        # ── Phase 2: Filter ──────────────────────────────────────────────
        logger.info("Running Phase 2/3 — Filter (scoring %d structured posts)...", items_passed)
        filtered = _phase2_filter(structured)

        # ── Phase 3: Aggregate ───────────────────────────────────────────
        included_count = sum(
            1 for p in filtered.get("posts", []) if p.get("status") == "include"
        )
        logger.info("Running Phase 3/3 — Aggregate (%d included posts)...", included_count)
        clusters = _phase3_aggregate(filtered, date_str)

    except anthropic.APIError as exc:
        logger.error("Claude API error during pipeline: %s", exc)
        raise

    # ── Persist ──────────────────────────────────────────────────────────
    saved_path = _save_clusters(clusters, date_str)
    cluster_count = len(clusters.get("topic_clusters", []))
    logger.info("=== Pipeline complete — %d topic clusters → %s ===", cluster_count, saved_path)

    return clusters


# ─────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────

if __name__ == "__main__":
    import glob

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        datefmt="%H:%M:%S",
    )

    # Find the latest *_raw.json in data/history/
    raw_files = sorted(glob.glob(str(HISTORY_DIR / "*_raw.json")))
    if not raw_files:
        logger.error("No *_raw.json found in %s. Run src/fetcher.py first.", HISTORY_DIR)
        raise SystemExit(1)

    latest_raw = raw_files[-1]
    # Extract date_str from filename, e.g. "2024-01-15_raw.json" -> "2024-01-15"
    date_str = Path(latest_raw).name.replace("_raw.json", "")
    logger.info("Loading raw posts from: %s", latest_raw)

    with open(latest_raw, encoding="utf-8") as f:
        raw_posts: list[dict] = json.load(f)

    logger.info("Loaded %d raw posts for date %s", len(raw_posts), date_str)

    clusters = run_pipeline(raw_posts, date_str)

    topic_list = clusters.get("topic_clusters", [])
    logger.info("─── Topic Clusters (%d) ───────────────────", len(topic_list))
    for t in topic_list:
        label_en = t.get("topic_label_en", "?")
        label_zh = t.get("topic_label_zh", "?")
        strength = t.get("signal_strength", "?")
        kols = ", ".join(t.get("kols_involved", []))
        logger.info("  [%s] %s / %s  (KOLs: %s)", strength, label_en, label_zh, kols)
    logger.info("───────────────────────────────────────────")
