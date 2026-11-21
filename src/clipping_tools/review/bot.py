"""Discord review bot: persistent Approve / Reject / Edit-caption buttons (P7.3).

Runs on the VPS. Outbound WebSocket only — no inbound port. The decision path
is a pure function so the role gate is unit-testable without a gateway.
"""
from __future__ import annotations

import os
import sqlite3

import discord

from ..db import init_db, utcnow
from .embeds import build_review_embed
from .store import is_reviewer, record_decision

_DB_PATH = os.environ.get("CLIPZIDA_DB", "data/state.db")
_REVIEWER_ROLE = os.environ.get("DISCORD_REVIEWER_ROLE_ID", "")


def decide(
    member_role_ids: list[str] | set[str],
    required_role: str,
    decision: str,
    post_id: int,
    reviewer: str,
    reason: str | None = None,
    edits: dict | None = None,
    conn: sqlite3.Connection | None = None,
) -> str:
    """Return 'ignored' for non-reviewers, otherwise apply the decision."""
    if not is_reviewer(member_role_ids, required_role):
        return "ignored"
    own = conn is None
    conn = conn or init_db(_DB_PATH)
    try:
        record_decision(conn, post_id, decision, reviewer, reason=reason, edits=edits)
    finally:
        if own:
            conn.close()
    return "approved" if decision == "approve" else "rejected"


class ReviewView(discord.ui.View):
    """Persistent view — survives restarts via stable custom_ids."""

    def __init__(self, post_id: int, reviewer_role: str, db_path: str):
        super().__init__(timeout=None)
        self.post_id = post_id
        self.reviewer_role = reviewer_role
        self.db_path = db_path
        # Per-post custom_ids prevent a restart from routing old buttons to the wrong draft.
        self.approve.custom_id = f"clipzida:approve:{post_id}"
        self.reject.custom_id = f"clipzida:reject:{post_id}"
        self.edit.custom_id = f"clipzida:edit:{post_id}"

    def _allowed(self, interaction: discord.Interaction) -> bool:
        roles = [str(r.id) for r in getattr(interaction.user, "roles", [])]
        return is_reviewer(roles, self.reviewer_role)

    @discord.ui.button(label="Approve", style=discord.ButtonStyle.green, custom_id="clipzida:approve")
    async def approve(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if not self._allowed(interaction):
            await interaction.response.send_message("Reviewer role required.", ephemeral=True)
            return
        result = decide([str(r.id) for r in interaction.user.roles], self.reviewer_role,
                        "approve", self.post_id, str(interaction.user.id),
                        conn=init_db(self.db_path))
        await interaction.response.send_message(f"Post #{self.post_id}: {result}.", ephemeral=True)

    @discord.ui.button(label="Reject", style=discord.ButtonStyle.red, custom_id="clipzida:reject")
    async def reject(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if not self._allowed(interaction):
            await interaction.response.send_message("Reviewer role required.", ephemeral=True)
            return
        result = decide([str(r.id) for r in interaction.user.roles], self.reviewer_role,
                        "reject", self.post_id, str(interaction.user.id),
                        conn=init_db(self.db_path))
        await interaction.response.send_message(f"Post #{self.post_id}: {result}.", ephemeral=True)

    @discord.ui.button(label="Edit-caption", style=discord.ButtonStyle.gray, custom_id="clipzida:edit")
    async def edit(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if not self._allowed(interaction):
            await interaction.response.send_message("Reviewer role required.", ephemeral=True)
            return
        await interaction.response.send_modal(EditCaptionModal(self.post_id, self.reviewer_role, self.db_path))


class EditCaptionModal(discord.ui.Modal, title="Edit caption"):
    caption = discord.ui.TextInput(label="Caption", style=discord.TextStyle.long, required=True)

    def __init__(self, post_id: int, reviewer_role: str, db_path: str):
        super().__init__()
        self.post_id = post_id
        self.reviewer_role = reviewer_role
        self.db_path = db_path

    async def on_submit(self, interaction: discord.Interaction) -> None:
        if not is_reviewer([str(r.id) for r in getattr(interaction.user, "roles", [])], self.reviewer_role):
            await interaction.response.send_message("Reviewer role required.", ephemeral=True)
            return
        decide([str(r.id) for r in interaction.user.roles], self.reviewer_role, "approve",
               self.post_id, str(interaction.user.id),
               edits={"caption": str(self.caption.value)}, conn=init_db(self.db_path))
        caption = str(self.caption.value)
        await interaction.response.send_message(f"Post #{self.post_id}: caption updated and approved.", ephemeral=True)
        emoji = "✏️"
        embed = discord.Embed(
            title=f"{emoji} APPROVED (EDITED) — Post #{self.post_id}",
            description=(
                f"Caption: {caption[:200]}\n"
                f"Edited by: {interaction.user.id}\n"
                f"Decided at: {utcnow()}"
            ),
            color=discord.Color.green(),
        )
        try:
            await interaction.message.edit(embeds=[embed], view=None)
        except Exception:
            pass


def parse_component(custom_id: str) -> tuple[str, int] | None:
    parts = str(custom_id or "").split(":")
    if len(parts) == 3 and parts[0] == "clipzida" and parts[1] in {"approve", "reject", "edit"}:
        try:
            return parts[1], int(parts[2])
        except ValueError:
            return None
    return None


async def handle_component(interaction, custom_id: str, db_path: str,
                           reviewer_role: str) -> bool:
    """Handle a component interaction by custom_id — works for views posted by any process."""
    parsed = parse_component(custom_id)
    if parsed is None:
        return False
    action, post_id = parsed
    roles = [str(r.id) for r in getattr(interaction.user, "roles", [])]
    if not is_reviewer(roles, reviewer_role):
        await interaction.response.send_message("Reviewer role required.", ephemeral=True)
        return True
    if action in {"approve", "reject"}:
        caption = ""
        conn = init_db(db_path)
        row = conn.execute("SELECT caption FROM posts WHERE id=?", (post_id,)).fetchone()
        if row:
            caption = row["caption"] or ""
        conn.close()
        decide(roles, reviewer_role, action, post_id, str(interaction.user.id),
               conn=init_db(db_path))
        await interaction.response.send_message(f"Post #{post_id}: {action} recorded.", ephemeral=True)
        emoji = "✅" if action == "approve" else "❌"
        status_word = "APPROVED" if action == "approve" else "REJECTED"
        embed = discord.Embed(
            title=f"{emoji} {status_word} — Post #{post_id}",
            description=(
                f"Caption: {caption[:200]}\n"
                f"Decided by: {interaction.user.id}\n"
                f"Decided at: {utcnow()}"
            ),
            color=discord.Color.green() if action == "approve" else discord.Color.red(),
        )
        try:
            await interaction.message.edit(embeds=[embed], view=None)
        except Exception:
            pass  # message may be too old to edit; ephemeral reply still confirms
    elif action == "edit":
        await interaction.response.send_modal(EditCaptionModal(post_id, reviewer_role, db_path))
    return True


def make_bot() -> discord.Client:
    intents = discord.Intents.default()  # no message_content — slash + components only
    client = discord.Client(intents=intents)
    tree = discord.app_commands.CommandTree(client)

    @tree.command(name="ping", description="Clipzida bot health check")
    async def ping(interaction: discord.Interaction):
        await interaction.response.send_message("pong", ephemeral=True)

    @client.event
    async def on_interaction(interaction: discord.Interaction):
        if interaction.type == discord.InteractionType.component:
            await handle_component(interaction, str((interaction.data or {}).get("custom_id", "")),
                                   _DB_PATH, _REVIEWER_ROLE)

    @client.event
    async def on_ready():
        await tree.sync()
        print(f"CLIPZIDA bot ready: {client.user} in {len(client.guilds)} guild(s)", flush=True)
        channel_id = os.environ.get("DISCORD_REVIEW_CHANNEL_ID", "")
        if channel_id:
            from .publisher import publish_pending_reviews
            n = await publish_pending_reviews(client, _DB_PATH, channel_id, _REVIEWER_ROLE)
            print(f"Published {n} review embed(s)", flush=True)

    return client


def run() -> None:
    token = os.environ.get("DISCORD_BOT_TOKEN", "")
    if not token:
        raise RuntimeError("DISCORD_BOT_TOKEN not set")
    make_bot().run(token)


if __name__ == "__main__":
    run()
