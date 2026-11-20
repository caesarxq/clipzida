"""RED: angle tagging for drafts (funny / hype / news), fail to review when unclear."""
from clipping_tools.review.angles import classify_angle


def test_funny_keywords_classify_as_funny():
    assert classify_angle("lacy got caught creeping around mandy house 😂",
                          ["caught", "creeping", "lol"]) == "funny"


def test_fail_moment_keywords_classify_as_funny():
    assert classify_angle("he totally whiffed it", ["failed", "died", "bruh"]) == "funny"


def test_hype_keywords_classify_as_hype():
    assert classify_angle("INSANE 4K kill streak", ["insane", "crazy", "unbelievable"]) == "hype"


def test_news_keywords_classify_as_news():
    assert classify_angle("Rockstar confirms GTA 6 patch notes", ["release", "confirmed", "patch"]) == "news"


def test_no_signal_returns_none_for_human_review():
    assert classify_angle("someone walks across a street", ["walking", "street", "car"]) is None


def test_funny_wins_on_tie_with_news():
    assert classify_angle("rockstar patch lol caught", ["caught", "lol", "patch"]) == "funny"
