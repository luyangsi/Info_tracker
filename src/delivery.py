# -*- coding: utf-8 -*-
"""
delivery.py — 报告推送模块

功能：
  format_email_html(brief, trend) -> str   将 brief/trend dict 渲染为 HTML 邮件
  send_email(html_content, date_str) -> bool  通过 SendGrid 发送邮件
"""

import html as _html_lib
import logging
import os
from typing import Any

from dotenv import load_dotenv

# SendGrid 为可选依赖，未安装时降级跳过
try:
    from sendgrid import SendGridAPIClient
    from sendgrid.helpers.mail import Mail
    _SENDGRID_AVAILABLE = True
except ImportError:
    _SENDGRID_AVAILABLE = False

load_dotenv()

logger = logging.getLogger(__name__)

_FROM_EMAIL = "kol-intel@noreply.com"


# ─────────────────────────────────────────────
# HTML rendering helpers
# ─────────────────────────────────────────────

def _e(text: str) -> str:
    """HTML-escape a plain string."""
    return _html_lib.escape(str(text) if text is not None else "")


def _section(title: str, body: str, bg: str = "#ffffff") -> str:
    """Wrap content in a labeled section block."""
    return f"""
    <table width="100%" cellpadding="0" cellspacing="0" style="margin-bottom:24px;">
      <tr>
        <td style="background:{bg};border-radius:6px;padding:20px 24px;">
          <h2 style="margin:0 0 14px 0;font-size:16px;font-weight:700;
                     color:#1a1a1a;letter-spacing:0.3px;">{_e(title)}</h2>
          {body}
        </td>
      </tr>
    </table>"""


# ─────────────────────────────────────────────
# Public: HTML formatter
# ─────────────────────────────────────────────

def format_email_html(brief: dict[str, Any], trend: dict[str, Any]) -> str:
    """
    将 brief 和 trend dict 渲染为完整 HTML 邮件正文（内联样式，无外部 CSS 框架）。

    布局：
      Header    — 标题 + 日期，深灰背景
      Section 1 — 今日三大信号（EN + ZH 交替编号列表）
      Section 2 — 话题深度解析（每话题一张卡片）
      Section 3 — 值得关注的声音（引用块）
      Section 4 — 趋势报告摘要（macro_signal + 前 3 条 trend）
      Footer    — 免责声明小字

    Args:
        brief: generate_brief() 返回的 dict。
        trend: generate_trend_report() 返回的 dict。

    Returns:
        完整 HTML 字符串，适合作为 SendGrid 的 html_content。
    """
    date_str = _e(brief.get("briefing_date", ""))
    stats = brief.get("stats", {})

    # ── Header ────────────────────────────────────────────────────────────
    header = f"""
    <table width="100%" cellpadding="0" cellspacing="0">
      <tr>
        <td style="background:#1c1c1e;border-radius:8px 8px 0 0;padding:28px 28px 20px;">
          <p style="margin:0;font-size:11px;color:#8e8e93;letter-spacing:1.5px;
                    text-transform:uppercase;">KOL INTELLIGENCE</p>
          <h1 style="margin:6px 0 10px;font-size:24px;color:#ffffff;font-weight:700;">
            Daily Brief — {date_str}
          </h1>
          <p style="margin:0;font-size:13px;color:#aeaeb2;">
            {_e(str(stats.get("kols_monitored", "—")))} KOLs monitored &nbsp;·&nbsp;
            {_e(str(stats.get("posts_analyzed", "—")))} posts analyzed &nbsp;·&nbsp;
            {_e(str(stats.get("topics_surfaced", "—")))} topics surfaced
          </p>
        </td>
      </tr>
    </table>
    <div style="height:4px;background:linear-gradient(90deg,#0a84ff,#30d158,#ffd60a);
                border-radius:0;margin-bottom:24px;"></div>"""

    # ── Section 1: Top Signals ────────────────────────────────────────────
    signals_html = "<ol style='margin:0;padding-left:20px;'>"
    for sig in brief.get("top_signals", []):
        en = _e(sig.get("en", ""))
        zh = _e(sig.get("zh", ""))
        signals_html += f"""
        <li style="margin-bottom:14px;">
          <p style="margin:0 0 4px;font-size:14px;color:#1a1a1a;line-height:1.5;">{en}</p>
          <p style="margin:0;font-size:13px;color:#636366;line-height:1.5;">{zh}</p>
        </li>"""
    signals_html += "</ol>"
    section1 = _section("📡 Today's Top Signals · 今日三大信号", signals_html, "#f2f2f7")

    # ── Section 2: Deep Dives ─────────────────────────────────────────────
    dives_html = ""
    for dive in brief.get("deep_dives", []):
        headline_en = _e(dive.get("headline_en", ""))
        headline_zh = _e(dive.get("headline_zh", ""))
        body_en = _e(dive.get("body_en", ""))
        body_zh = _e(dive.get("body_zh", ""))
        sources = ", ".join(_e(s) for s in dive.get("sources", []))
        dives_html += f"""
        <div style="border:1px solid #e5e5ea;border-radius:6px;padding:16px 18px;
                    margin-bottom:14px;background:#ffffff;">
          <p style="margin:0 0 4px;font-size:15px;font-weight:700;color:#1a1a1a;">
            {headline_en}
          </p>
          <p style="margin:0 0 10px;font-size:13px;font-weight:600;color:#636366;">
            {headline_zh}
          </p>
          <p style="margin:0 0 8px;font-size:13px;color:#3a3a3c;line-height:1.6;">{body_en}</p>
          <p style="margin:0 0 10px;font-size:13px;color:#636366;line-height:1.6;">{body_zh}</p>
          <p style="margin:0;font-size:11px;color:#8e8e93;">Sources: {sources}</p>
        </div>"""
    section2 = _section("🔍 Topic Deep-Dives · 话题深度解析", dives_html, "#ffffff")

    # ── Section 3: Notable Voices ─────────────────────────────────────────
    voices_html = ""
    for voice in brief.get("notable_voices", []):
        quote = _e(voice.get("quote", ""))
        kol = _e(voice.get("kol", ""))
        platform = _e(voice.get("platform", ""))
        date_v = _e(voice.get("date", ""))
        voices_html += f"""
        <blockquote style="margin:0 0 16px;padding:14px 18px;
                           border-left:4px solid #0a84ff;background:#f0f6ff;
                           border-radius:0 6px 6px 0;">
          <p style="margin:0 0 8px;font-size:14px;color:#1a1a1a;
                    font-style:italic;line-height:1.6;">"{quote}"</p>
          <p style="margin:0;font-size:12px;color:#636366;">
            — <strong>{kol}</strong> · {platform} · {date_v}
          </p>
        </blockquote>"""
    if not voices_html:
        voices_html = '<p style="margin:0;font-size:13px;color:#8e8e93;">No notable quotes today.</p>'
    section3 = _section("💬 Notable Voices · 值得关注的声音", voices_html, "#f9f9fb")

    # ── Section 4: Trend Summary ──────────────────────────────────────────
    macro = trend.get("macro_signal", {})
    macro_en = _e(macro.get("en", ""))
    macro_zh = _e(macro.get("zh", ""))
    trend_html = f"""
    <div style="background:#fff8e1;border-radius:6px;padding:14px 18px;margin-bottom:18px;">
      <p style="margin:0 0 2px;font-size:11px;color:#8e8e93;
                text-transform:uppercase;letter-spacing:1px;">Macro Signal</p>
      <p style="margin:0 0 6px;font-size:14px;color:#1a1a1a;
                font-weight:600;line-height:1.5;">{macro_en}</p>
      <p style="margin:0;font-size:13px;color:#636366;line-height:1.5;">{macro_zh}</p>
    </div>"""

    _DIRECTION_BADGE = {
        "ACCELERATING": ("#30d158", "↑ ACCELERATING"),
        "EMERGING":     ("#0a84ff", "◆ EMERGING"),
        "STEADY":       ("#8e8e93", "→ STEADY"),
        "DECELERATING": ("#ff9f0a", "↓ DECELERATING"),
        "FADING":       ("#ff453a", "↓ FADING"),
    }

    for t in trend.get("trends", [])[:3]:
        label_en = _e(t.get("label_en", ""))
        label_zh = _e(t.get("label_zh", ""))
        direction = str(t.get("direction", "STEADY")).upper()
        badge_color, badge_text = _DIRECTION_BADGE.get(direction, ("#8e8e93", direction))
        momentum = _e(str(t.get("momentum_score", "—")))
        novelty = _e(str(t.get("novelty_score", "—")))
        evidence_en = _e(t.get("evidence_en", ""))

        trend_html += f"""
        <div style="border:1px solid #e5e5ea;border-radius:6px;padding:14px 18px;
                    margin-bottom:12px;">
          <table width="100%" cellpadding="0" cellspacing="0">
            <tr>
              <td>
                <p style="margin:0 0 2px;font-size:14px;font-weight:700;
                           color:#1a1a1a;">{label_en}</p>
                <p style="margin:0;font-size:12px;color:#636366;">{label_zh}</p>
              </td>
              <td style="text-align:right;white-space:nowrap;vertical-align:top;">
                <span style="background:{badge_color};color:#fff;font-size:10px;
                             font-weight:700;padding:3px 7px;border-radius:4px;
                             letter-spacing:0.5px;">{_e(badge_text)}</span>
              </td>
            </tr>
          </table>
          <p style="margin:10px 0 8px;font-size:13px;color:#3a3a3c;
                    line-height:1.5;">{evidence_en}</p>
          <p style="margin:0;font-size:11px;color:#8e8e93;">
            Momentum: <strong>{momentum}/10</strong> &nbsp;·&nbsp;
            Novelty: <strong>{novelty}/10</strong>
          </p>
        </div>"""

    section4 = _section("📈 7-Day Trend Summary · 趋势报告摘要", trend_html, "#ffffff")

    # ── Footer ────────────────────────────────────────────────────────────
    footer = """
    <p style="text-align:center;font-size:11px;color:#8e8e93;margin:24px 0 0;
              line-height:1.6;">
      由 KOL Intel Pipeline 自动生成 · 仅供参考<br>
      Generated automatically by KOL Intel Pipeline · For reference only
    </p>"""

    # ── Assemble full email ───────────────────────────────────────────────
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width,initial-scale=1.0">
  <title>KOL Intelligence Daily — {date_str}</title>
</head>
<body style="margin:0;padding:0;background:#f2f2f7;
             font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;">
  <table width="100%" cellpadding="0" cellspacing="0" style="background:#f2f2f7;">
    <tr>
      <td align="center" style="padding:24px 16px;">
        <table width="600" cellpadding="0" cellspacing="0"
               style="max-width:600px;width:100%;">
          <tr><td>{header}</td></tr>
          <tr><td>{section1}</td></tr>
          <tr><td>{section2}</td></tr>
          <tr><td>{section3}</td></tr>
          <tr><td>{section4}</td></tr>
          <tr><td>{footer}</td></tr>
        </table>
      </td>
    </tr>
  </table>
</body>
</html>"""


# ─────────────────────────────────────────────
# Public: SendGrid delivery
# ─────────────────────────────────────────────

def send_email(html_content: str, date_str: str) -> bool:
    """
    通过 SendGrid API 发送 HTML 邮件。

    收件人从环境变量 DELIVERY_EMAIL 读取，
    发件人为 kol-intel@noreply.com，
    主题为 "[KOL Intel] Daily Brief — {date_str}"。

    若 SENDGRID_API_KEY 未配置，跳过发送并打印提示，返回 False。
    发送失败时打印错误信息，返回 False，不抛出异常。

    Args:
        html_content: format_email_html() 返回的 HTML 字符串。
        date_str:     目标日期，格式 "YYYY-MM-DD"，用于邮件主题。

    Returns:
        True 表示发送成功（HTTP 2xx），False 表示跳过或失败。
    """
    api_key = os.environ.get("SENDGRID_API_KEY", "")
    if not api_key:
        print("Email delivery skipped: no API key")
        return False

    if not _SENDGRID_AVAILABLE:
        logger.warning("sendgrid package not installed; email delivery skipped.")
        return False

    to_email = os.environ.get("DELIVERY_EMAIL", "")
    if not to_email:
        logger.warning("DELIVERY_EMAIL not set; email delivery skipped.")
        return False

    subject = f"[KOL Intel] Daily Brief — {date_str}"

    try:
        message = Mail(
            from_email=_FROM_EMAIL,
            to_emails=to_email,
            subject=subject,
            html_content=html_content,
        )
        sg = SendGridAPIClient(api_key)
        response = sg.send(message)
        status = response.status_code
        if 200 <= status < 300:
            logger.info("Email sent to %s (status %d)", to_email, status)
            return True
        logger.error("SendGrid returned unexpected status %d", status)
        return False

    except Exception as exc:
        logger.error("Email delivery failed: %s", exc)
        return False
