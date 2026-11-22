"""Discord embed/digest builders for the review surface (P7.3)."""
from __future__ import annotations

import discord


def _badge(value: str) -> str:
    """Render a gate value as a credibility badge.

    Verified/ok/registered/supported -> ✅
    Unverified/review                 -> ⚠️
    Unlicensed/strike-risk/not-registered/unsupported -> ❌
    """
    marks = {
        "verified": "✅",
        "ok": "✅",
        "registered": "✅",
        "supported": "✅",
        "unverified": "⚠️",
        "review": "⚠️",
        "unlicensed": "❌",
        "strike-risk": "❌",
        "not-registered": "❌",
        "unsupported": "❌",
    }
    mark = marks.get(str(value).lower(), "⚠️")
    return f"{mark} {value}"


def build_review_embed(post: dict) -> discord.Embed:
    """Build a review embed with enough evidence to approve/reject confidently.

    The post dict may carry clip fields (broadcaster, duration, view_count,
    fetched_at, clip_url) when joined through renders->clips_raw, and news
    fields (posted_at, post_url, source) when ingested from news sources.
    Missing fields degrade gracefully to '—'.
    """
    hook = str(post.get("caption") or "").strip()
    if not hook:
        raise ValueError("post has no caption/hook")

    post_id = post.get("id", "?")
    render_id = post.get("render_id")
    angle = post.get("angle") or "review"
    broadcaster = post.get("broadcaster") or "—"
    source = post.get("source") or "—"
    fetched_at = post.get("fetched_at") or ""
    posted_at = post.get("posted_at") or ""
    duration = post.get("duration")
    view_count = post.get("view_count")
    rights = post.get("rights", "unverified")
    rockstar = post.get("rockstar", "review")
    campaign = post.get("campaign", "review")
    platform = post.get("platform", "review")
    post_url = post.get("post_url") or post.get("url") or ""
    clip_url = post.get("clip_url") or ""

    is_news = render_id is None

    embed = discord.Embed(
        title=hook[:256],
        color=discord.Color.blurple() if is_news else discord.Color.orange(),
    )

    # ── Description: evidence specific to post type ──
    if is_news:
        parts = [f"📰 **Source:** {source}"]
        if posted_at:
            parts.append(f"🕒 **Published:** {posted_at}")
        if post_url:
            parts.append(f"🔗 **Article:** {post_url}")
        embed.description = "\n".join(parts)
        embed.add_field(
            name="Type",
            value="News (text-only — publishes to X)",
            inline=True,
        )
    else:
        parts = [f"🎮 **Streamer:** {broadcaster}", f"🎯 **Angle:** {angle}"]
        if duration:
            parts.append(f"⏱ **Duration:** {duration:.0f}s")
        if view_count:
            parts.append(f"👁 **Views:** {view_count:,}")
        if fetched_at:
            parts.append(f"🕒 **Fetched:** {fetched_at}")
        if clip_url:
            parts.append(f"🔗 **Clip:** {clip_url}")
        embed.description = "\n".join(parts)
        embed.add_field(
            name="Type",
            value="Clip (video — renders to vertical)",
            inline=True,
        )
        embed.add_field(
            name="Preview",
            value="Master MP4 on VPS — review before approving",
            inline=False,
        )

    # ── Gates: actual verification state, not hardcoded 'review' ──
    embed.add_field(
        name="Gates",
        value=(
            f"rights: {_badge(rights)}\n"
            f"rockstar: {_badge(rockstar)}\n"
            f"campaign: {_badge(campaign)}\n"
            f"platform: {_badge(platform)}"
        ),
        inline=False,
    )

    embed.set_footer(text=f"Post #{post_id} — Approve / Reject / Edit-caption")
    return embed


def build_alert_embed(kind: str, detail: str) -> discord.Embed:
    title = f"ALERT — {kind.upper()}"
    if kind.lower() == "strike":
        title = "STRIKE — publishing halted"
    return discord.Embed(title=title, description=detail, color=discord.Color.red())


def build_digest(stats: dict) -> str:
    return (
        f"CLIPZIDA daily — pending: {stats.get('pending', 0)} | "
        f"published yesterday: {stats.get('published', 0)} | "
        f"views: {stats.get('views', 0):,} | "
        f"revenue est: ${stats.get('revenue', 0):.2f}"
    )
