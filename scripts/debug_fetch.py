# -*- coding: utf-8 -*-
"""
scripts/debug_fetch.py — 数据源逐步验证工具

在进入 AI 流水线之前，逐步验证三个真实数据源是否可正常抓取。
每步独立执行，失败只打印原因，不抛出未处理异常。

运行方式：
  cd kol-intel
  python scripts/debug_fetch.py
"""

import json
import os
import sys
from pathlib import Path

import feedparser
import requests
from dotenv import load_dotenv

load_dotenv()

# ── Project root on path ──────────────────────────────────────────────────────
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

SEEDS_PATH = ROOT / "config" / "seeds.json"

# ── Result tracking ───────────────────────────────────────────────────────────
# Each entry: {"kol": str, "platform": str, "ok": bool, "count": int, "detail": str}
_results: list[dict] = []


def _load_seeds() -> list[dict]:
    with open(SEEDS_PATH, encoding="utf-8") as f:
        return json.load(f)


def _record(kol_name: str, platform: str, ok: bool, count: int, detail: str) -> None:
    _results.append({"kol": kol_name, "platform": platform,
                     "ok": ok, "count": count, "detail": detail})


# ─────────────────────────────────────────────────────────────────────────────
# Step 1 — YouTube RSS
# ─────────────────────────────────────────────────────────────────────────────

def step1_youtube(seeds: list[dict]) -> None:
    print("\n─── Step 1: YouTube RSS ─────────────────────────────────────────")
    candidates = [
        k for k in seeds
        if "youtube" in k.get("platforms", []) and k.get("youtube_channel_id")
    ]
    if not candidates:
        print("[YouTube] seeds.json 中没有配置 youtube_channel_id 的 KOL，跳过。")
        return

    for kol in candidates:
        name = kol["name"]
        channel_id = kol["youtube_channel_id"]

        if kol.get("youtube_status") == "unavailable":
            print(f"[YouTube] {name} → youtube_status=unavailable，已跳过（外部 feed 不可用）")
            _record(name, "youtube", None, 0, "skip: youtube_status=unavailable")
            continue

        url = f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"
        _yt_headers = {
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            )
        }
        try:
            resp = requests.get(url, headers=_yt_headers, timeout=10)
            resp.raise_for_status()
            feed = feedparser.parse(resp.content)
            entries = feed.entries
            if entries:
                latest_title = entries[0].get("title", "(无标题)")
                print(f"[YouTube] {name} → {len(entries)} entries，"
                      f"最新标题：{latest_title}")
                _record(name, "youtube", True, len(entries), latest_title)
            else:
                msg = f"0 entries，检查 channel ID 是否正确（当前：{channel_id}）"
                print(f"[YouTube] {name} → {msg}")
                _record(name, "youtube", False, 0, msg)
        except Exception as exc:
            msg = f"请求/解析异常：{exc}"
            print(f"[YouTube] {name} → {msg}")
            _record(name, "youtube", False, 0, msg)


# ─────────────────────────────────────────────────────────────────────────────
# Step 2 — WeChat via RSSHub
# ─────────────────────────────────────────────────────────────────────────────

def step2_wechat(seeds: list[dict]) -> None:
    print("\n─── Step 2: WeChat (RSSHub) ─────────────────────────────────────")
    rsshub_base = os.environ.get("RSSHUB_BASE_URL", "").rstrip("/")
    if not rsshub_base:
        print("[WeChat] RSSHUB_BASE_URL 未设置，跳过 Step 2。")
        print("         请在 .env 中设置，例如：RSSHUB_BASE_URL=https://your-rsshub.railway.app")
        return

    # ── Health check ─────────────────────────────────────────────────────
    try:
        health_resp = requests.get(f"{rsshub_base}/healthz", timeout=5)
        if health_resp.status_code == 200:
            print(f"[RSSHub] 服务正常: {rsshub_base}")
        else:
            print(f"[RSSHub] 服务异常（HTTP {health_resp.status_code}），跳过所有 WeChat KOL")
            return
    except requests.exceptions.RequestException as exc:
        print(f"[RSSHub] 服务异常，跳过所有 WeChat KOL（{exc}）")
        return

    candidates = [k for k in seeds if "wechat" in k.get("platforms", [])]
    if not candidates:
        print("[WeChat] seeds.json 中没有 wechat 平台的 KOL，跳过。")
        return

    for kol in candidates:
        name = kol["name"]
        wechat_id = kol.get("wechat_id", "")
        if not wechat_id:
            print(f"[WeChat] {name} → wechat_id 字段缺失，跳过。")
            _record(name, "wechat", False, 0, "wechat_id 字段缺失")
            continue

        url = f"{rsshub_base}/wechat/sogou/{wechat_id}"
        try:
            resp = requests.get(url, timeout=10)
            if resp.status_code == 200:
                feed = feedparser.parse(resp.text)
                entries = feed.entries
                if entries:
                    latest_title = entries[0].get("title", "(无标题)")
                    print(f"[WeChat] {name} → {len(entries)} entries，"
                          f"最新标题：{latest_title}")
                    _record(name, "wechat", True, len(entries), latest_title)
                else:
                    msg = "HTTP 200 但 feed 为空，可能 wechat_id 有误或 RSSHub 路由不支持"
                    print(f"[WeChat] {name} → {msg}")
                    _record(name, "wechat", False, 0, msg)
            else:
                msg = f"HTTP {resp.status_code}"
                print(f"[WeChat] {name} → {msg}")
                _record(name, "wechat", False, 0, msg)
        except requests.exceptions.ConnectionError as exc:
            msg = f"Connection failed: {exc}"
            print(f"[WeChat] {name} → {msg}")
            _record(name, "wechat", False, 0, msg)
        except requests.exceptions.Timeout:
            msg = "请求超时（>10s），检查 RSSHub 服务是否正常"
            print(f"[WeChat] {name} → {msg}")
            _record(name, "wechat", False, 0, msg)
        except Exception as exc:
            msg = f"未预期异常：{exc}"
            print(f"[WeChat] {name} → {msg}")
            _record(name, "wechat", False, 0, msg)


# ─────────────────────────────────────────────────────────────────────────────
# Step 3 — Direct RSS feeds
# ─────────────────────────────────────────────────────────────────────────────

_RSS_FALLBACK_CANDIDATES = [
    "https://www.oaktreecapital.com/insights/memo/rss",
    "https://feeds.feedburner.com/OaktreeCapital",
    "https://www.oaktreecapital.com/insights/rss",
]


def _probe_rss_candidates(name: str, candidates: list[str]) -> tuple[str | None, int, str]:
    """
    逐一探测候选 RSS URL，返回 (可用URL或None, entries数, 最新标题或错误信息)。
    打印每个候选的探测结果（bozo + entries 条数）。
    """
    for url in candidates:
        try:
            resp = requests.get(url, timeout=10, headers={"User-Agent": "kol-intel-debug/1.0"})
            feed = feedparser.parse(resp.text)
            bozo = feed.bozo
            count = len(feed.entries)
            print(f"  探测 {url}")
            print(f"    HTTP {resp.status_code}  bozo={bozo}  entries={count}")
            if not bozo and count > 0:
                title = feed.entries[0].get("title", "(无标题)")
                return url, count, title
        except Exception as exc:
            print(f"  探测 {url} → 异常: {exc}")
    return None, 0, "所有候选 URL 均不可用"


def step3_rss(seeds: list[dict]) -> None:
    print("\n─── Step 3: RSS 直连 ────────────────────────────────────────────")
    candidates = [
        k for k in seeds
        if "rss" in k.get("platforms", []) and k.get("rss_url")
    ]
    if not candidates:
        print("[RSS] seeds.json 中没有配置 rss_url 的 KOL，跳过。")
        return

    for kol in candidates:
        name = kol["name"]
        rss_url = kol["rss_url"]

        # KOL explicitly marked unavailable — skip without hitting the network
        if kol.get("rss_status") == "unavailable":
            print(f"[RSS] {name} → rss_status=unavailable，已跳过（外部 feed 不可用）")
            _record(name, "rss", None, 0, "skip: rss_status=unavailable")
            continue

        try:
            # Pre-fetch via requests to honour timeout; feedparser then parses the text
            resp = requests.get(rss_url, timeout=10,
                                headers={"User-Agent": "kol-intel-debug/1.0"})
            feed = feedparser.parse(resp.text)
            entries = feed.entries

            if feed.bozo:
                exc_msg = str(feed.get("bozo_exception", "unknown"))
                print(f"[RSS] {name} → 解析警告: {exc_msg}")
                # Primary URL failed — probe fallback candidates
                print(f"[RSS] {name} → 探测备用候选地址...")
                good_url, count, detail = _probe_rss_candidates(name, _RSS_FALLBACK_CANDIDATES)
                if good_url:
                    print(f"[RSS] {name} → 备用地址可用: {good_url}  ({count} entries，最新: {detail})")
                    _record(name, "rss", True, count, detail)
                else:
                    print(f"[RSS] {name} → 所有候选均不可用，建议设置 rss_status: unavailable")
                    _record(name, "rss", False, 0, detail)
                continue

            if entries:
                latest_title = entries[0].get("title", "(无标题)")
                print(f"[RSS] {name} → {len(entries)} entries，"
                      f"最新标题：{latest_title}")
                _record(name, "rss", True, len(entries), latest_title)
            else:
                msg = f"0 entries（URL: {rss_url}）"
                print(f"[RSS] {name} → {msg}")
                _record(name, "rss", False, 0, msg)

        except requests.exceptions.ConnectionError as exc:
            msg = f"Connection failed: {exc}"
            print(f"[RSS] {name} → {msg}")
            _record(name, "rss", False, 0, msg)
        except requests.exceptions.Timeout:
            msg = "请求超时（>10s）"
            print(f"[RSS] {name} → {msg}")
            _record(name, "rss", False, 0, msg)
        except Exception as exc:
            msg = f"未预期异常：{exc}"
            print(f"[RSS] {name} → {msg}")
            _record(name, "rss", False, 0, msg)


# ─────────────────────────────────────────────────────────────────────────────
# Step 4 — Summary report
# ─────────────────────────────────────────────────────────────────────────────

def step4_summary() -> bool:
    """Print summary. Returns True if all sources succeeded."""
    print("\n" + "═" * 60)
    print("  汇总报告 / Summary")
    print("═" * 60)

    if not _results:
        print("  没有可验证的数据源（seeds.json 中无 youtube/wechat/rss KOL）。")
        return False

    ok_count  = sum(1 for r in _results if r["ok"] is True)
    skip_count = sum(1 for r in _results if r["ok"] is None)
    fail_count = sum(1 for r in _results if r["ok"] is False)
    total = len(_results)
    print(f"  成功: {ok_count} / {total}  跳过: {skip_count}  失败: {fail_count}\n")

    for r in _results:
        if r["ok"] is True:
            icon, count_str = "✓", f"{r['count']} 条"
        elif r["ok"] is None:
            icon, count_str = "⊘", "skip"
        else:
            icon, count_str = "✗", "─"
        print(f"  {icon}  [{r['platform']:<8}] {r['kol']:<20} {count_str}")
        if r["ok"] is False:
            print(f"       原因：{r['detail']}")
        elif r["ok"] is None:
            print(f"       说明：{r['detail']}")

    print()
    all_ok = fail_count == 0   # skips are acceptable
    if not all_ok:
        print("  ⚠️  部分数据源未就绪，建议修复后再运行 main.py")
    else:
        print("  ✓ 所有数据源正常，可以运行 python main.py")
    print("═" * 60)
    return all_ok


# ─────────────────────────────────────────────────────────────────────────────
# Step 5 — Optional: trigger full pipeline
# ─────────────────────────────────────────────────────────────────────────────

def step5_prompt_run() -> None:
    print()
    try:
        answer = input("所有数据源已验证。是否立即运行完整 pipeline？(y/n): ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        print("\n已跳过，可手动运行 python main.py")
        return

    if answer == "y":
        import subprocess
        subprocess.run([sys.executable, str(ROOT / "main.py")])
    else:
        print("已跳过，可手动运行 python main.py")


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def main() -> None:
    print("╔══════════════════════════════════════════════════════════╗")
    print("║       kol-intel  数据源诊断工具  debug_fetch.py          ║")
    print("╚══════════════════════════════════════════════════════════╝")

    seeds = _load_seeds()
    print(f"\n已加载 {len(seeds)} 个 KOL 种子。\n")

    step1_youtube(seeds)
    step2_wechat(seeds)
    step3_rss(seeds)
    all_ok = step4_summary()
    step5_prompt_run()


if __name__ == "__main__":
    main()
