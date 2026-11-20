"""RED: review proxy generation for Discord-safe uploads."""
from clipping_tools.review.proxy import build_proxy_command, needs_proxy, proxy_params


def test_needs_proxy_true_when_over_discord_ceiling():
    assert needs_proxy(22_000_000, 10_000_000) is True


def test_needs_proxy_false_when_under_ceiling():
    assert needs_proxy(3_000_000, 10_000_000) is False


def test_proxy_params_are_discord_safe():
    p = proxy_params()
    assert p["width"] <= 540
    assert p["max_bytes"] <= 10_000_000


def test_build_proxy_command_is_portable_and_targeted():
    cmd = build_proxy_command("/in/master.mp4", "/out/proxy.mp4")
    assert cmd[0].endswith("ffmpeg")
    assert "libx264" in cmd and "scale=540:960" in cmd
    assert cmd[-1] == "/out/proxy.mp4"
