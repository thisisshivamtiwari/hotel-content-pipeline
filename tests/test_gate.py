from hotel_content import gate


def _summary(oneshot_claims, rules_claims, dirty=0):
    row = {"clean_packs": 10, "rule_issues": 0, "shipped_dirty": dirty}
    return {
        "table": [
            {"model": "m", "arm": "oneshot", **row, "unsupported_claims": oneshot_claims},
            {"model": "m", "arm": "rules", **row, "unsupported_claims": rules_claims},
        ]
    }


def test_gate_passes_and_fails():
    rules = [{"arm": "rules", "metric": "unsupported_claims", "max_vs": "oneshot"}]
    assert gate.evaluate(_summary(5, 3), rules) == []
    assert gate.evaluate(_summary(3, 5), rules) == ["m rules: unsupported_claims = 5 > oneshot (3)"]


def test_gate_absolute_max():
    rules = [{"model": "m", "arm": "rules", "metric": "shipped_dirty", "max": 0}]
    assert gate.evaluate(_summary(0, 0, dirty=1), rules) == ["m rules: shipped_dirty = 1 > 0"]
