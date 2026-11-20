"""RED: only campaign-licensed broadcasters may enter the ingest queue."""
from clipping_tools.ingest_policy import licensed_from_campaigns, licensed_source_weight

LICENSED = {"dom", "dasgasd3m", "laurenhamdenn", "yourragegaming", "kaicenat", "lacy", "clix", "tomovids"}


def test_real_campaign_registry_yields_licensed_handles():
    import yaml
    from pathlib import Path
    data = yaml.safe_load((Path(__file__).resolve().parents[1] / "config/campaigns.yaml").read_text())
    handles = licensed_from_campaigns(data["campaigns"])
    assert "kaicenat" in handles
    assert "yourragegaming" in handles
    assert "laurenhamdenn" in handles
    assert "tomovids" not in handles  # paused_depleted campaign excluded


def test_licensed_broadcaster_gets_source_weight():
    assert licensed_source_weight("kaicenat", LICENSED) == 1.0


def test_unlicensed_broadcaster_is_rejected():
    assert licensed_source_weight("xQc", LICENSED) == 0.0


def test_broadcaster_name_is_normalized_case_and_www():
    assert licensed_source_weight("  KaiCenat  ", LICENSED) == 1.0
