from clipping_tools.models import Angle, ComplianceVerdict, GateStatus, MomentSelection


def test_verdict_all_pass():
    v = ComplianceVerdict(rights=GateStatus.PASS, rockstar=GateStatus.PASS,
                          campaign=GateStatus.PASS, platform=GateStatus.PASS)
    assert v.ok and not v.needs_review


def test_verdict_review():
    v = ComplianceVerdict(rights=GateStatus.PASS, rockstar=GateStatus.REVIEW,
                          campaign=GateStatus.PASS, platform=GateStatus.PASS)
    assert not v.ok and v.needs_review


def test_verdict_fail_beats_review():
    v = ComplianceVerdict(rights=GateStatus.FAIL, rockstar=GateStatus.REVIEW,
                          campaign=GateStatus.PASS, platform=GateStatus.PASS)
    assert not v.ok and not v.needs_review


def test_verdict_default_denies():
    assert not ComplianceVerdict().ok


def test_moment_duration():
    m = MomentSelection(start=10.0, end=40.0, hook_title="TEST HOOK", angle=Angle.HYPE)
    assert m.duration == 30.0