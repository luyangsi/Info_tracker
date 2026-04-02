# -*- coding: utf-8 -*-
# Supported platforms: YouTube, WeChat (via RSSHub), RSS
"""
fetcher.py — 多平台 KOL 内容抓取模块

支持平台：
  - YouTube  via YouTube 原生 RSS feed（无需 API key）
  - WeChat   via 自托管 RSSHub
  - RSS      via feedparser（直接解析 RSS/Atom feed）

输出统一格式，供 pipeline.py 的 Claude 分析阶段消费。
"""

import json
import logging
import os
import re
import datetime as _dt
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

import feedparser
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

SEEDS_PATH = Path(__file__).parent.parent / "config" / "seeds.json"
HISTORY_DIR = Path(__file__).parent.parent / "data" / "history"


# ─────────────────────────────────────────────
# Internal helpers
# ─────────────────────────────────────────────

_HTML_TAG_RE = re.compile(r"<[^>]+>")
_URL_RE = re.compile(r"https?://\S+|www\.\S+")
_WHITESPACE_RE = re.compile(r"\s+")
_CJK_RE = re.compile(r"[\u4e00-\u9fff]")
_MAX_CONTENT_LEN = 2000


def _clean_text(text: str) -> str:
    """去除 HTML 标签、URL，并归一化空白字符。双引号替换为单引号以避免 Claude JSON 生成时的转义问题。"""
    text = _HTML_TAG_RE.sub("", text)
    text = _URL_RE.sub("", text)
    text = _WHITESPACE_RE.sub(" ", text).strip()
    text = text.replace('"', "'")  # prevent unescaped " inside Claude-generated JSON strings
    return text


def _detect_language(text: str) -> str:
    """
    简单语言检测：含 CJK 字符则判定为中文，否则为英文。
    Unicode 范围：U+4E00–U+9FFF（CJK 统一表意文字基本区）。
    """
    return "zh" if _CJK_RE.search(text) else "en"


def _is_repost(text: str, entry: Any = None) -> bool:
    """
    判断内容是否为转发/转载。
    规则：feedparser entry 的 title 以 "re:" 开头（邮件列表风格）。
    """
    if entry is not None:
        title: str = entry.get("title", "") or ""
        if title.lower().startswith("re:"):
            return True
    return False


def _make_id(platform: str, handle: str, date_str: str, seq: int) -> str:
    """生成统一格式的帖子 ID：{platform}_{handle}_{YYYYMMDD}_{seq:03d}。"""
    yyyymmdd = date_str.replace("-", "")
    return f"{platform}_{handle}_{yyyymmdd}_{seq:03d}"


def _parse_feedparser_dt(entry: Any) -> datetime | None:
    """
    从 feedparser entry 提取发布时间，返回 UTC datetime。
    优先使用 published_parsed，回退到 updated_parsed。
    """
    raw = entry.get("published_parsed") or entry.get("updated_parsed")
    if raw is None:
        return None
    return datetime(*raw[:6], tzinfo=timezone.utc)


# ─────────────────────────────────────────────
# Seed loader
# ─────────────────────────────────────────────

def load_seeds() -> list[dict[str, Any]]:
    """从 config/seeds.json 加载 KOL 种子列表。"""
    with open(SEEDS_PATH, encoding="utf-8") as f:
        return json.load(f)


# ─────────────────────────────────────────────
# Platform fetchers
# ─────────────────────────────────────────────


def fetch_youtube(kol: dict[str, Any], date_str: str) -> list[dict[str, Any]]:
    """
    通过 YouTube 原生 Atom feed 抓取频道最新视频（无需 API key）。

    Feed URL 模板：
        https://www.youtube.com/feeds/videos.xml?channel_id={youtube_channel_id}

    若 seeds.json 中未配置 youtube_channel_id，则跳过该 KOL。

    Args:
        kol:       KOL 配置 dict。
        date_str:  目标日期，格式 "YYYY-MM-DD"。

    Returns:
        符合统一输出格式的帖子列表。
    """
    if kol.get("youtube_status") == "unavailable":
        logger.debug("YouTube marked unavailable for %s, skipping.", kol["name"])
        return []

    channel_id: str | None = kol.get("youtube_channel_id")
    if not channel_id:
        logger.debug("No youtube_channel_id for %s, skipping YouTube.", kol["name"])
        return []

    kol_name = kol["name"]
    feed_url = f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"
    _yt_headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        )
    }

    try:
        import requests as _requests
        resp = _requests.get(feed_url, headers=_yt_headers, timeout=10)
        resp.raise_for_status()
        feed = feedparser.parse(resp.content)
    except Exception as exc:
        logger.warning("YouTube feed fetch failed for %s: %s", kol["name"], exc)
        return []

    if feed.bozo and not feed.entries:
        logger.warning(
            "YouTube feed error for %s: %s", kol["name"], feed.get("bozo_exception", "unknown")
        )
        return []

    posts: list[dict[str, Any]] = []
    for entry in feed.entries:
        dt = _parse_feedparser_dt(entry)
        if dt is None:
            continue

        post_date = dt.strftime("%Y-%m-%d")
        _cutoff = (_dt.date.fromisoformat(date_str) - timedelta(days=7)).isoformat()
        if post_date < _cutoff or post_date > date_str:
            continue

        title: str = entry.get("title", "")
        summary: str = entry.get("summary", "") or ""
        raw_content = _clean_text(f"{title}\n\n{summary}")
        seq = len(posts)

        posts.append({
            "id": _make_id("youtube", kol_name, date_str, seq),
            "kol_name": kol_name,
            "platform": "youtube",
            "post_date": post_date,
            "post_time_utc": dt.strftime("%H:%M"),
            "original_language": _detect_language(raw_content),
            "raw_content": raw_content[:_MAX_CONTENT_LEN],
            "url": entry.get("link", ""),
            "is_repost": False,
            "engagement": {
                "likes": None,
                "shares": None,
                "comments": None,
            },
        })

    return posts


def fetch_wechat(kol: dict[str, Any], date_str: str) -> list[dict[str, Any]]:
    """
    通过自托管 RSSHub 抓取微信公众号文章。

    Feed URL 模板：
        {RSSHUB_BASE_URL}/wechat/sogou/{wechat_id}

    RSSHub 地址从环境变量 RSSHUB_BASE_URL 读取（默认 http://localhost:1200）。
    若 seeds.json 中未配置 wechat_id，则跳过该 KOL。

    Args:
        kol:       KOL 配置 dict。
        date_str:  目标日期，格式 "YYYY-MM-DD"。

    Returns:
        符合统一输出格式的帖子列表。
    """
    wechat_id: str | None = kol.get("wechat_id")
    if not wechat_id:
        logger.debug("No wechat_id for %s, skipping WeChat.", kol["name"])
        return []

    rsshub_base = os.environ.get("RSSHUB_BASE_URL", "http://localhost:1200").rstrip("/")
    kol_name = kol["name"]
    feed_url = f"{rsshub_base}/wechat/sogou/{wechat_id}"

    try:
        feed = feedparser.parse(feed_url)
    except Exception as exc:
        logger.warning("WeChat feed parse failed for %s: %s", kol["name"], exc)
        return []

    if feed.bozo and not feed.entries:
        logger.warning(
            "WeChat feed error for %s: %s", kol["name"], feed.get("bozo_exception", "unknown")
        )
        return []

    posts: list[dict[str, Any]] = []
    for entry in feed.entries:
        dt = _parse_feedparser_dt(entry)
        if dt is None:
            continue

        post_date = dt.strftime("%Y-%m-%d")
        _cutoff = (_dt.date.fromisoformat(date_str) - timedelta(days=7)).isoformat()
        if post_date < _cutoff or post_date > date_str:
            continue

        title: str = entry.get("title", "")
        summary: str = entry.get("summary", "") or ""
        raw_content = _clean_text(f"{title}\n\n{summary}")
        seq = len(posts)

        posts.append({
            "id": _make_id("wechat", kol_name, date_str, seq),
            "kol_name": kol_name,
            "platform": "wechat",
            "post_date": post_date,
            "post_time_utc": dt.strftime("%H:%M"),
            "original_language": _detect_language(raw_content),
            "raw_content": raw_content[:_MAX_CONTENT_LEN],
            "url": entry.get("link", ""),
            "is_repost": _is_repost(raw_content, entry),
            "engagement": {
                "likes": None,
                "shares": None,
                "comments": None,
            },
        })

    return posts


def fetch_rss(kol: dict[str, Any], date_str: str) -> list[dict[str, Any]]:
    """
    直接解析 RSS/Atom feed（如 Oaktree Capital Memo）。

    rss_url 从 seeds.json 的 rss_url 字段读取。
    若未配置，则跳过该 KOL。

    Args:
        kol:       KOL 配置 dict。
        date_str:  目标日期，格式 "YYYY-MM-DD"。

    Returns:
        符合统一输出格式的帖子列表。
    """
    if kol.get("rss_status") == "unavailable":
        logger.debug("RSS marked unavailable for %s, skipping.", kol["name"])
        return []

    rss_url: str | None = kol.get("rss_url")
    if not rss_url:
        logger.debug("No rss_url for %s, skipping RSS.", kol["name"])
        return []

    kol_name = kol["name"]

    try:
        feed = feedparser.parse(rss_url)
    except Exception as exc:
        logger.warning("RSS feed parse failed for %s: %s", kol["name"], exc)
        return []

    if feed.bozo and not feed.entries:
        logger.warning(
            "RSS feed error for %s: %s", kol["name"], feed.get("bozo_exception", "unknown")
        )
        return []

    posts: list[dict[str, Any]] = []
    for entry in feed.entries:
        dt = _parse_feedparser_dt(entry)
        if dt is None:
            continue

        post_date = dt.strftime("%Y-%m-%d")
        _cutoff = (_dt.date.fromisoformat(date_str) - timedelta(days=7)).isoformat()
        if post_date < _cutoff or post_date > date_str:
            continue

        title: str = entry.get("title", "")
        summary: str = entry.get("summary", "") or ""
        raw_content = _clean_text(f"{title}\n\n{summary}")
        seq = len(posts)

        posts.append({
            "id": _make_id("rss", kol_name, date_str, seq),
            "kol_name": kol_name,
            "platform": "rss",
            "post_date": post_date,
            "post_time_utc": dt.strftime("%H:%M"),
            "original_language": _detect_language(raw_content),
            "raw_content": raw_content[:_MAX_CONTENT_LEN],
            "url": entry.get("link", ""),
            "is_repost": _is_repost(raw_content, entry),
            "engagement": {
                "likes": None,
                "shares": None,
                "comments": None,
            },
        })

    return posts


# ─────────────────────────────────────────────
# Main dispatcher
# ─────────────────────────────────────────────

_PLATFORM_FETCHERS: dict[str, Any] = {
    "youtube": fetch_youtube,
    "wechat": fetch_wechat,
    "rss": fetch_rss,
}


def fetch_all(seeds: list[dict[str, Any]], date_str: str) -> list[dict[str, Any]]:
    """
    主入口：遍历所有 KOL 种子，按平台分发抓取，返回合并后的帖子列表。

    单个 KOL 抓取失败不影响其他 KOL（每个平台调用独立 try/except）。
    不支持的平台（如 linkedin）会记录 debug 日志后跳过。

    Args:
        seeds:     KOL 种子列表（来自 load_seeds()）。
        date_str:  目标日期，格式 "YYYY-MM-DD"。

    Returns:
        所有平台当日帖子的合并列表，已过滤至目标日期。
    """
    all_posts: list[dict[str, Any]] = []

    for kol in seeds:
        for platform in kol.get("platforms", []):
            fetcher = _PLATFORM_FETCHERS.get(platform)
            if fetcher is None:
                logger.debug(
                    "No fetcher for platform '%s' (KOL: %s), skipping.", platform, kol["name"]
                )
                continue
            try:
                posts = fetcher(kol, date_str)
                all_posts.extend(posts)
                if posts:
                    logger.info(
                        "  [%s/%s] fetched %d posts", platform, kol["name"], len(posts)
                    )
            except Exception as exc:
                logger.warning(
                    "Unexpected error fetching %s/%s: %s", platform, kol["name"], exc
                )

    return all_posts


# ─────────────────────────────────────────────
# Persistence
# ─────────────────────────────────────────────

def save_raw(posts: list[dict[str, Any]], date_str: str) -> str:
    """
    将抓取结果持久化为 data/history/{date_str}_raw.json。

    目录不存在时自动创建。文件以 UTF-8 编码写入，保留非 ASCII 字符（ensure_ascii=False）。

    Args:
        posts:     fetch_all 返回的帖子列表。
        date_str:  目标日期，格式 "YYYY-MM-DD"，用于文件命名。

    Returns:
        写入文件的绝对路径字符串。
    """
    HISTORY_DIR.mkdir(parents=True, exist_ok=True)
    out_path = HISTORY_DIR / f"{date_str}_raw.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(posts, f, ensure_ascii=False, indent=2)
    return str(out_path)


# ─────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        datefmt="%H:%M:%S",
    )

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    logger.info("=== kol-intel fetcher | date: %s ===", today)

    seeds = load_seeds()
    logger.info("Loaded %d KOLs from seeds.json", len(seeds))

    all_posts = fetch_all(seeds, today)

    # ── Summary by platform ──
    from collections import Counter
    counts: Counter = Counter(p["platform"] for p in all_posts)
    logger.info("─── Fetch summary ───────────────────────")
    for platform in ("youtube", "wechat", "rss"):
        logger.info("  %-10s %d posts", platform, counts.get(platform, 0))
    logger.info("  %-10s %d posts (total)", "ALL", len(all_posts))
    logger.info("─────────────────────────────────────────")

    if all_posts:
        path = save_raw(all_posts, today)
        logger.info("Saved → %s", path)
    else:
        logger.info("No posts fetched for %s (all platforms may be TODO or date-filtered).", today)
