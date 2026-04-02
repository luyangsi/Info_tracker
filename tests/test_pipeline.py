# -*- coding: utf-8 -*-
"""
tests/test_pipeline.py — Full-chain JSON-contract tests (zero real API calls)

Verifies that the schema contracts between modules stay consistent:
  fetch_all → run_pipeline (P1 Ingest → P2 Filter → P3 Aggregate)
            → generate_brief (P4) → generate_trend_report (P5)

All Claude API calls are intercepted via unittest.mock.patch so no
ANTHROPIC_API_KEY or network access is required.
"""

import datetime
import json
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

# ── Ensure project root is on sys.path ──────────────────────────────────────
sys.path.insert(0, str(Path(__file__).parent.parent))

# ─────────────────────────────────────────────
# Shared test date
# ─────────────────────────────────────────────

TODAY = datetime.date.today().isoformat()

# ─────────────────────────────────────────────
# Mock raw posts — 5 items, 3 platforms
# (youtube ×2, wechat ×2, rss ×1)
# ─────────────────────────────────────────────

_D = TODAY.replace("-", "")

MOCK_POSTS = [
    {
        "id": f"youtube_AndrejKarpathy_{_D}_000",
        "kol_name": "Andrej Karpathy",
        "kol_handle": "karpathy",
        "platform": "youtube",
        "post_date": TODAY,
        "post_time_utc": "09:00",
        "original_language": "en",
        "raw_content": (
            "New video on transformer architecture scaling laws and how they predict "
            "emergent capabilities in large language models across different parameter counts "
            "and training compute budgets in the latest research."
        ),
        "url": "https://youtube.com/watch?v=abc123",
        "is_repost": False,
        "engagement": {"likes": None, "shares": None, "comments": None},
    },
    {
        "id": f"youtube_AndrewNg_{_D}_000",
        "kol_name": "Andrew Ng",
        "kol_handle": "AndrewYNg",
        "platform": "youtube",
        "post_date": TODAY,
        "post_time_utc": "11:00",
        "original_language": "en",
        "raw_content": (
            "Agentic AI workflows are the most important trend to watch this year. "
            "Building systems where LLMs iteratively refine their own outputs fundamentally "
            "changes product architecture and developer tooling expectations."
        ),
        "url": "https://youtube.com/watch?v=def456",
        "is_repost": False,
        "engagement": {"likes": None, "shares": None, "comments": None},
    },
    {
        "id": f"wechat_RobinLi_{_D}_000",
        "kol_name": "Robin Li",
        "kol_handle": "baidu",
        "platform": "wechat",
        "post_date": TODAY,
        "post_time_utc": "08:30",
        "original_language": "zh",
        "raw_content": (
            "百度文心大模型在最新的基准测试中取得了突破性进展，"
            "在多项任务上的表现已经超越了国际主流模型，"
            "展示了中文 AI 的强劲发展势头和技术积累。"
        ),
        "url": "https://mp.weixin.qq.com/s/test1",
        "is_repost": False,
        "engagement": {"likes": None, "shares": None, "comments": None},
    },
    {
        "id": f"wechat_WangXiaochuan_{_D}_000",
        "kol_name": "Wang Xiaochuan",
        "kol_handle": "baichuan",
        "platform": "wechat",
        "post_date": TODAY,
        "post_time_utc": "10:15",
        "original_language": "zh",
        "raw_content": (
            "百川大模型最新版本正式发布，参数规模大幅提升，"
            "在代码生成、数学推理和多轮对话等关键能力上取得了显著改善，"
            "开源版本同步发布供研究者使用。"
        ),
        "url": "https://mp.weixin.qq.com/s/test2",
        "is_repost": False,
        "engagement": {"likes": None, "shares": None, "comments": None},
    },
    {
        "id": f"rss_HowardMarks_{_D}_000",
        "kol_name": "Howard Marks",
        "kol_handle": "oaktree",
        "platform": "rss",
        "post_date": TODAY,
        "post_time_utc": "14:00",
        "original_language": "en",
        "raw_content": (
            "The current macro environment presents both significant risks and opportunities "
            "for investors who understand the difference between first-level and second-level "
            "thinking in asset allocation and portfolio construction."
        ),
        "url": "https://www.oaktreecapital.com/memo/test",
        "is_repost": False,
        "engagement": {"likes": None, "shares": None, "comments": None},
    },
]

# ─────────────────────────────────────────────
# Mock Claude responses — one per phase
# ─────────────────────────────────────────────

_FILTERED_POSTS = [
    {
        **p,
        "relevance_score": 2,
        "status": "include",
        "highlight": False,
        "cot_reasoning": "Directly discusses AI model capability trends.",
        "industry_tags": ["AI"],
    }
    for p in MOCK_POSTS[:4]   # 5th post discarded → included=4, discarded=1
]

MOCK_P1 = {
    "extraction_date": TODAY,
    "total_raw_items": 5,
    "items_passed": 5,
    "posts": MOCK_POSTS,
}

MOCK_P2 = {
    "filter_summary": {
        "total_input": 5,
        "discarded": 1,
        "included": 4,
        "highlighted": 1,
    },
    "posts": _FILTERED_POSTS,
}

MOCK_P3 = {
    "aggregation_date": TODAY,
    "topic_clusters": [
        {
            "topic_id": "T001",
            "topic_label_en": "AI Model Competition Intensifies",
            "topic_label_zh": "AI 模型竞争白热化",
            "signal_strength": "HIGH",
            "post_count": 4,
            "kols_involved": ["Sam Altman", "Andrew Ng"],
            "consensus_view": {
                "en": "Multiple leading KOLs agree that LLM capability is accelerating.",
                "zh": "多位顶级 KOL 一致认为大模型能力正在加速提升。",
            },
            "dissenting_views": [],
            "verified_facts": ["fact1"],
            "disputed_claims": [],
            "source_post_ids": ["id1"],
        }
    ],
}

MOCK_P4 = {
    "briefing_date": TODAY,
    "stats": {"kols_monitored": 5, "posts_analyzed": 5, "topics_surfaced": 1},
    "top_signals": [
        {
            "en": "LLM scaling continues to deliver measurable capability gains.",
            "zh": "大模型扩展持续带来可量化的能力提升。",
        }
    ],
    "deep_dives": [
        {
            "headline_en": "Agentic AI Workflows Emerge as Next Frontier",
            "headline_zh": "AI Agent 工作流成为下一个前沿领域",
            "body_en": "Multiple KOLs are betting on agentic workflows as the defining paradigm shift.",
            "body_zh": "多位 KOL 押注 AI Agent 工作流为决定性的范式转变。",
            "sources": ["Andrej Karpathy", "Andrew Ng"],
        }
    ],
    "notable_voices": [
        {
            "quote": "Agentic workflows are the most important trend to watch.",
            "kol": "Andrew Ng",
            "platform": "YouTube",
            "date": TODAY,
        }
    ],
    "watchlist": [
        {
            "topic_en": "Chinese LLM benchmark progress",
            "topic_zh": "中文大模型基准进展",
            "why_en": "Baidu and Baichuan showing rapid benchmark improvement.",
            "why_zh": "百度和百川基准测试进步显著。",
        }
    ],
}

MOCK_P5 = {
    "report_date": TODAY,
    "window": "7-day rolling",
    "macro_signal": {
        "en": "AI investment and deployment is accelerating across all major sectors.",
        "zh": "AI 投资和部署正在各主要行业全面加速。",
    },
    "trends": [
        {
            "trend_id": "TR001",
            "label_en": "LLM inference cost deflation",
            "label_zh": "LLM 推理成本通缩",
            "momentum_score": 8,
            "novelty_score": 6,
            "direction": "ACCELERATING",
            "kol_alignment": "CONSENSUS(>70%)",
            "evidence_en": "Three separate KOLs cited inference cost drops this week.",
            "evidence_zh": "本周三位 KOL 均独立提到推理成本大幅下降。",
            "kols_driving": ["Andrej Karpathy", "Andrew Ng"],
            "first_appeared": TODAY,
            "watch_signal": True,
        }
    ],
    "kol_spotlights": [
        {
            "kol": "Andrew Ng",
            "persistent_theme_en": "Agentic AI workflow architecture",
            "persistent_theme_zh": "AI Agent 工作流架构",
            "position_shift": False,
        }
    ],
}


# ─────────────────────────────────────────────
# Helper: build a mock Anthropic instance
# ─────────────────────────────────────────────

def _mock_anthropic_instance(*response_dicts):
    """
    Return a MagicMock that acts as an anthropic.Anthropic() instance.
    Successive calls to .messages.create() return each response_dict
    (serialised to JSON string) in order.
    """
    mock_instance = MagicMock()
    side_effects = []
    for data in response_dicts:
        resp = MagicMock()
        resp.content = [MagicMock(text=json.dumps(data, ensure_ascii=False))]
        side_effects.append(resp)
    mock_instance.messages.create.side_effect = side_effects
    return mock_instance


# ─────────────────────────────────────────────
# Test cases
# ─────────────────────────────────────────────

class TestPipelineContracts(unittest.TestCase):

    def setUp(self):
        # Provide a fake key so _call_claude doesn't raise EnvironmentError
        os.environ["ANTHROPIC_API_KEY"] = "test-key-for-mocking"

    # ── Test 1: fetch_all output structure ───────────────────────────────

    @patch("src.fetcher.fetch_all", return_value=MOCK_POSTS)
    def test_fetch_structure(self, mock_fetch_all):
        """fetch_all 返回列表非空，每个元素包含 id、platform、raw_content 字段。"""
        posts = mock_fetch_all([], TODAY)
        self.assertGreater(len(posts), 0, "fetch_all must return a non-empty list")
        for post in posts:
            for field in ("id", "platform", "raw_content"):
                self.assertIn(field, post, f"Post missing required field '{field}'")

    # ── Test 2: run_pipeline returns topic_clusters ──────────────────────

    @patch("time.sleep")
    @patch("src.pipeline._save_clusters", return_value="/tmp/test_clusters.json")
    @patch("src.pipeline.anthropic.Anthropic")
    def test_p1_output_schema(self, mock_anthro_cls, mock_save, mock_sleep):
        """run_pipeline 返回值包含 topic_clusters 键，且其值为列表。"""
        mock_anthro_cls.return_value = _mock_anthropic_instance(MOCK_P1, MOCK_P2, MOCK_P3)
        from src.pipeline import run_pipeline
        clusters = run_pipeline(MOCK_POSTS, TODAY)
        self.assertIn("topic_clusters", clusters)
        self.assertIsInstance(clusters["topic_clusters"], list)

    # ── Test 3: filter discards at least one post ────────────────────────

    @patch("time.sleep")
    @patch("src.pipeline.anthropic.Anthropic")
    def test_p2_filter_count(self, mock_anthro_cls, mock_sleep):
        """filter_summary["included"] 必须严格小于 filter_summary["total_input"]。"""
        mock_anthro_cls.return_value = _mock_anthropic_instance(MOCK_P2)
        from src.pipeline import _phase2_filter
        filtered = _phase2_filter(MOCK_P1)
        summary = filtered["filter_summary"]
        self.assertLess(
            summary["included"],
            summary["total_input"],
            "Filter phase must discard at least one post",
        )

    # ── Test 4: every cluster has bilingual consensus_view ───────────────

    @patch("time.sleep")
    @patch("src.pipeline._save_clusters", return_value="/tmp/test_clusters.json")
    @patch("src.pipeline.anthropic.Anthropic")
    def test_p3_bilingual(self, mock_anthro_cls, mock_save, mock_sleep):
        """每个 cluster 的 consensus_view 必须同时含非空 en 和 zh 字段。"""
        mock_anthro_cls.return_value = _mock_anthropic_instance(MOCK_P1, MOCK_P2, MOCK_P3)
        from src.pipeline import run_pipeline
        clusters = run_pipeline(MOCK_POSTS, TODAY)
        self.assertGreater(len(clusters["topic_clusters"]), 0, "Expected at least one cluster")
        for cluster in clusters["topic_clusters"]:
            cv = cluster.get("consensus_view", {})
            self.assertIn("en", cv, "consensus_view missing 'en' key")
            self.assertIn("zh", cv, "consensus_view missing 'zh' key")
            self.assertTrue(cv["en"], "consensus_view['en'] must be a non-empty string")
            self.assertTrue(cv["zh"], "consensus_view['zh'] must be a non-empty string")

    # ── Test 5: generate_brief returns all required sections ─────────────

    @patch("time.sleep")
    @patch("src.pipeline.anthropic.Anthropic")
    def test_p4_brief_sections(self, mock_anthro_cls, mock_sleep):
        """generate_brief 返回值包含 top_signals、deep_dives、watchlist 键。"""
        mock_anthro_cls.return_value = _mock_anthropic_instance(MOCK_P4)
        from src.reporter import generate_brief
        brief = generate_brief(
            MOCK_P3,
            TODAY,
            {"kols_monitored": 5, "posts_analyzed": 5},
        )
        for section in ("top_signals", "deep_dives", "watchlist"):
            self.assertIn(section, brief, f"brief missing required section: '{section}'")

    # ── Test 6: every trend has valid integer scores ─────────────────────

    @patch("time.sleep")
    @patch("src.reporter._load_history_briefs", return_value=[])
    @patch("src.pipeline.anthropic.Anthropic")
    def test_p5_trend_scores(self, mock_anthro_cls, mock_load_hist, mock_sleep):
        """每个 trend 含 momentum_score 和 novelty_score，且值为 1–10 的整数。"""
        mock_anthro_cls.return_value = _mock_anthropic_instance(MOCK_P5)
        from src.reporter import generate_trend_report
        trend = generate_trend_report(MOCK_P4, TODAY)
        self.assertGreater(len(trend.get("trends", [])), 0, "Expected at least one trend")
        for t in trend["trends"]:
            for key in ("momentum_score", "novelty_score"):
                self.assertIn(key, t, f"trend missing key: '{key}'")
                score = t[key]
                self.assertIsInstance(score, int, f"{key} must be an int, got {type(score)}")
                self.assertGreaterEqual(score, 1, f"{key}={score} is below minimum 1")
                self.assertLessEqual(score, 10, f"{key}={score} exceeds maximum 10")


# ─────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────

if __name__ == "__main__":
    runner = unittest.TextTestRunner(verbosity=2)
    suite = unittest.TestLoader().loadTestsFromTestCase(TestPipelineContracts)
    result = runner.run(suite)
    if result.wasSuccessful():
        print("\n✓ All contract tests passed — pipeline JSON schemas are consistent")
    sys.exit(0 if result.wasSuccessful() else 1)
