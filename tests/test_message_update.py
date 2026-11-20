"""RED: approve/reject actions update the embed in-place so decisions persist."""
from unittest.mock import AsyncMock, MagicMock

from clipping_tools.review.bot import handle_component


class _Msg:
    def __init__(self):
        self.edit = AsyncMock()
        self.embeds = []
        self.components = []


class _Resp:
    def __init__(self):
        self.messages = []
    async def send_message(self, msg, **kw):
        self.messages.append((msg, kw))
        m = MagicMock()
        m.message = msg
        return m


def test_handle_component_edits_message_after_approve():
    interaction = MagicMock()
    interaction.user = MagicMock()
    interaction.user.roles = [MagicMock(id="reviewer-role")]
    interaction.user.id = "reviewer-1"
    interaction.response = _Resp()
    interaction.message = _Msg()

    asyncio_result = __import__("asyncio").run(
        handle_component(interaction, "clipzida:approve:99",
                         "/tmp/x.db", "reviewer-role")
    )
    assert asyncio_result is True
    interaction.message.edit.assert_awaited_once()
    call_kw = interaction.message.edit.call_args.kwargs
    assert call_kw["view"] is None
    embeds = call_kw["embeds"]
    assert len(embeds) == 1
    assert "APPROVED" in str(embeds[0].title).upper()


def test_handle_component_edits_message_after_reject():
    interaction = MagicMock()
    interaction.user = MagicMock()
    interaction.user.roles = [MagicMock(id="reviewer-role")]
    interaction.user.id = "reviewer-1"
    interaction.response = _Resp()
    interaction.message = _Msg()

    import asyncio
    result = asyncio.run(
        handle_component(interaction, "clipzida:reject:7",
                         "/tmp/x.db", "reviewer-role")
    )
    assert result is True
    interaction.message.edit.assert_awaited_once()
    call_kw = interaction.message.edit.call_args.kwargs
    assert call_kw["view"] is None
    embeds = call_kw["embeds"]
    assert "REJECTED" in str(embeds[0].title).upper()
