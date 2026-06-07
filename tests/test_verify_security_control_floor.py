"""Tests for ``scripts/verify_security_control_floor.py``.

The ``scripts/`` directory is added to ``sys.path`` via the ``pythonpath``
key under ``[tool.pytest.ini_options]`` in ``pyproject.toml``.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

import pytest
import verify_security_control_floor as floor

pytestmark = pytest.mark.shard_ci_ops

REPO_ROOT = Path(__file__).resolve().parents[1]
REAL_CONFIG = REPO_ROOT / ".github" / "security-control-floor.toml"


# ---------------------------------------------------------------------------
# evaluate (pure)
# ---------------------------------------------------------------------------


class TestEvaluate:
    def test_all_families_at_floor_is_clean(self) -> None:
        config = {
            "floor": "detect-and-file",
            "families": {
                "rulesets": {"tier": "detect-and-file"},
                "labels": {"tier": "detect-and-file"},
            },
        }
        assert floor.evaluate(config) == []

    def test_above_floor_is_clean(self) -> None:
        # No tier ranks above detect-and-file today, but the rule is >=, so a
        # family exactly at the floor passes. This guards the boundary.
        config = {
            "floor": "detect-only",
            "families": {"x": {"tier": "detect-and-file"}},
        }
        assert floor.evaluate(config) == []

    def test_below_floor_without_reason_is_violation(self) -> None:
        config = {
            "floor": "detect-and-file",
            "families": {"newcomer": {"tier": "detect-only"}},
        }
        errors = floor.evaluate(config)
        assert len(errors) == 1
        assert "newcomer" in errors[0]
        assert "below the floor" in errors[0]

    def test_below_floor_with_reason_is_exempt(self) -> None:
        config = {
            "floor": "detect-and-file",
            "families": {
                "advisory": {
                    "tier": "detect-only",
                    "exempt_reason": "advisory-only; warning never pages a human",
                }
            },
        }
        assert floor.evaluate(config) == []

    def test_blank_reason_does_not_exempt(self) -> None:
        config = {
            "floor": "detect-and-file",
            "families": {"x": {"tier": "pr-gate-only", "exempt_reason": "   "}},
        }
        assert len(floor.evaluate(config)) == 1

    def test_unknown_tier_is_violation(self) -> None:
        config = {
            "floor": "detect-and-file",
            "families": {"x": {"tier": "detect-and-pray"}},
        }
        errors = floor.evaluate(config)
        assert len(errors) == 1
        assert "tier must be one of" in errors[0]

    def test_unknown_floor_is_violation(self) -> None:
        config = {"floor": "nonsense", "families": {"x": {"tier": "detect-and-file"}}}
        errors = floor.evaluate(config)
        assert len(errors) == 1
        assert "floor must be one of" in errors[0]

    def test_empty_families_is_violation(self) -> None:
        assert floor.evaluate({"floor": "detect-and-file", "families": {}}) == [
            "[families] must be a non-empty table"
        ]

    def test_non_table_family_entry_is_violation(self) -> None:
        config = {"floor": "detect-and-file", "families": {"x": "detect-and-file"}}
        errors = floor.evaluate(config)
        assert len(errors) == 1
        assert "must be a table" in errors[0]


# ---------------------------------------------------------------------------
# main (thin IO)
# ---------------------------------------------------------------------------


class TestMain:
    def test_real_config_passes(self) -> None:
        # The committed floor file must satisfy its own gate: every scheduled
        # family is at detect-and-file, the one advisory family is exempted.
        assert floor.main(["--config", str(REAL_CONFIG)]) == 0

    def test_real_config_declares_target_families_at_floor(self) -> None:
        with REAL_CONFIG.open("rb") as handle:
            config = tomllib.load(handle)
        families = config["families"]
        for name in ("rulesets", "labels", "apm-instructions", "uv-pin-literal"):
            assert families[name]["tier"] == "detect-and-file"

    def test_below_floor_config_exits_1(self, tmp_path: Path) -> None:
        cfg = tmp_path / "floor.toml"
        cfg.write_text(
            'floor = "detect-and-file"\n\n'
            "[families.regression]\n"
            'tier = "detect-only"\n',
            encoding="utf-8",
        )
        assert floor.main(["--config", str(cfg)]) == 1

    def test_missing_config_exits_1(self, tmp_path: Path) -> None:
        assert floor.main(["--config", str(tmp_path / "absent.toml")]) == 1
