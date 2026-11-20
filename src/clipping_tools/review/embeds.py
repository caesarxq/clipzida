"""Discord embed/digest builders for the review surface (P7.3)."""
from __future__ import annotations

import discord


def build_review_embed(post: dict) -> discord.Embed:
    hook = str(post.get("caption") or "").strip()
    if not hook:
        raise ValueError("post has no caption/hook")
    embed = discord.Embed(
        title=hook,
        description=(
            f"Campaign: {post.get('campaign', '—')}\n"
            f"Score: {post.get('score', 0)}\n"
            f"Angle: {post.get('angle', '—')} | streamer: {post.get('broadcaster', '—')}"
        ),
        color=discord.Color.blurple(),
    )
    embed.add_field(name="Gates", value=" | ".join(
        f"{gate}: {post.get(key, 'review')}"
        for gate, key in (("rights", "rights"), ("rockstar", "rockstar"),
                          ("campaign", "campaign_gate"), ("platform", "platform"))
    ), inline=False)
    embed.set_footer(text=f"Post #{post.get('id', '?')} — Approve / Reject / Edit-caption")
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
