from clipping_tools.review.render import (
    record_metrics,
    get_avg_retention,
    should_kill_underperformer,
    ab_test_variant,
    select_best_variant,
    auto_optimize_angle,
)
print("Phase 6 imports OK")

from clipping_tools.db import SCHEMA
assert "ab_tests" in SCHEMA
print("ab_tests table in schema OK")
