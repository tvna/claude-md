"""Tests for ``scripts/verify_shard_coverage.py``.

Refs #545. Exercises the completeness gate that asserts the union of
executed test node IDs across JUnit artifacts equals the universe
collected by ``pytest --collect-only -q``, with no duplicates.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import verify_shard_coverage as vsc

pytestmark = pytest.mark.shard_default


_COLLECTED_FIXTURE = """\
tests/test_a.py::test_one
tests/test_a.py::TestGroup::test_two
tests/test_b.py::test_three
tests/test_b.py::test_four[case-1]
tests/test_b.py::test_four[case-2]

3 tests collected in 0.05s
"""


def _junit(testcases: list[tuple[str, str]]) -> str:
    cases = "\n".join(f'    <testcase classname="{c}" name="{n}"/>' for c, n in testcases)
    return f"""<?xml version="1.0" encoding="utf-8"?>
<testsuites>
  <testsuite name="pytest" tests="{len(testcases)}">
{cases}
  </testsuite>
</testsuites>
"""


class TestParseCollected:
    def test_extracts_node_ids(self) -> None:
        nodes = vsc.parse_collected(_COLLECTED_FIXTURE)
        assert nodes == {
            "tests/test_a.py::test_one",
            "tests/test_a.py::TestGroup::test_two",
            "tests/test_b.py::test_three",
            "tests/test_b.py::test_four[case-1]",
            "tests/test_b.py::test_four[case-2]",
        }

    def test_ignores_summary_and_blank_lines(self) -> None:
        text = "\n\n3 tests collected in 0.05s\n"
        assert vsc.parse_collected(text) == set()

    def test_empty_input(self) -> None:
        assert vsc.parse_collected("") == set()


class TestJunitNodeId:
    def test_module_level(self) -> None:
        assert vsc.junit_node_id("tests.test_a", "test_one") == "tests/test_a.py::test_one"

    def test_class_level(self) -> None:
        assert (
            vsc.junit_node_id("tests.test_a.TestGroup", "test_two")
            == "tests/test_a.py::TestGroup::test_two"
        )

    def test_nested_class(self) -> None:
        assert (
            vsc.junit_node_id("tests.test_a.Outer.Inner", "test_three")
            == "tests/test_a.py::Outer.Inner::test_three"
        )

    def test_parametrize_name_preserved(self) -> None:
        assert (
            vsc.junit_node_id("tests.test_b", "test_four[case-1]")
            == "tests/test_b.py::test_four[case-1]"
        )


class TestParseJunit:
    def test_extracts_executed_node_ids(self) -> None:
        xml = _junit([
            ("tests.test_a", "test_one"),
            ("tests.test_a.TestGroup", "test_two"),
        ])
        assert vsc.parse_junit(xml) == {
            "tests/test_a.py::test_one",
            "tests/test_a.py::TestGroup::test_two",
        }

    def test_accepts_legacy_root(self) -> None:
        # junit_family=legacy produces a single <testsuite> root.
        xml = """<?xml version="1.0" ?>
<testsuite name="pytest" tests="1">
  <testcase classname="tests.test_a" name="test_x"/>
</testsuite>
"""
        assert vsc.parse_junit(xml) == {"tests/test_a.py::test_x"}

    def test_skipped_testcase_still_counted(self) -> None:
        xml = """<?xml version="1.0" ?>
<testsuites>
  <testsuite name="pytest" tests="1">
    <testcase classname="tests.test_a" name="test_skip">
      <skipped message="x"/>
    </testcase>
  </testsuite>
</testsuites>
"""
        assert vsc.parse_junit(xml) == {"tests/test_a.py::test_skip"}


class TestCompare:
    def test_full_coverage_no_duplicates(self) -> None:
        collected = {"a", "b", "c"}
        per_shard = {"s1": {"a", "b"}, "s2": {"c"}}
        missing, duplicated = vsc.compare(collected, per_shard)
        assert missing == set()
        assert duplicated == {}

    def test_missing_detected(self) -> None:
        collected = {"a", "b", "c"}
        per_shard = {"s1": {"a"}, "s2": {"b"}}
        missing, duplicated = vsc.compare(collected, per_shard)
        assert missing == {"c"}
        assert duplicated == {}

    def test_duplicated_detected(self) -> None:
        collected = {"a", "b"}
        per_shard = {"s1": {"a", "b"}, "s2": {"a"}}
        missing, duplicated = vsc.compare(collected, per_shard)
        assert missing == set()
        assert duplicated == {"a": ["s1", "s2"]}


class TestFormatErrors:
    def test_missing_message(self) -> None:
        lines = vsc.format_errors({"tests/test_a.py::test_x"}, {}, set())
        assert len(lines) == 1
        assert "was collected but not executed" in lines[0]

    def test_duplicated_message_names_shards(self) -> None:
        lines = vsc.format_errors(set(), {"tests/test_a.py::test_x": ["s1", "s2"]}, set())
        assert "s1, s2" in lines[0]

    def test_extra_message(self) -> None:
        lines = vsc.format_errors(set(), {}, {"tests/test_a.py::ghost"})
        assert "JUnit and collection drifted" in lines[0]


class TestVerify:
    def test_happy_path(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        collected = tmp_path / "collected.txt"
        collected.write_text(_COLLECTED_FIXTURE)
        j1 = tmp_path / "junit-a.xml"
        j1.write_text(_junit([
            ("tests.test_a", "test_one"),
            ("tests.test_a.TestGroup", "test_two"),
        ]))
        j2 = tmp_path / "junit-b.xml"
        j2.write_text(_junit([
            ("tests.test_b", "test_three"),
            ("tests.test_b", "test_four[case-1]"),
            ("tests.test_b", "test_four[case-2]"),
        ]))
        assert vsc.verify(collected, [j1, j2]) == 0
        out = capsys.readouterr().out
        assert "5 collected node IDs covered exactly once" in out

    def test_missing_fails(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        collected = tmp_path / "collected.txt"
        collected.write_text(_COLLECTED_FIXTURE)
        j1 = tmp_path / "junit-a.xml"
        j1.write_text(_junit([("tests.test_a", "test_one")]))
        assert vsc.verify(collected, [j1]) == 1
        err = capsys.readouterr().err
        assert "was collected but not executed" in err

    def test_duplicated_fails(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        collected = tmp_path / "collected.txt"
        collected.write_text("tests/test_a.py::test_one\n")
        j1 = tmp_path / "junit-a.xml"
        j1.write_text(_junit([("tests.test_a", "test_one")]))
        j2 = tmp_path / "junit-b.xml"
        j2.write_text(_junit([("tests.test_a", "test_one")]))
        assert vsc.verify(collected, [j1, j2]) == 1
        err = capsys.readouterr().err
        assert "executed by multiple shards" in err

    def test_extra_executed_node_fails(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        collected = tmp_path / "collected.txt"
        collected.write_text("tests/test_a.py::test_one\n")
        j1 = tmp_path / "junit-a.xml"
        j1.write_text(_junit([
            ("tests.test_a", "test_one"),
            ("tests.test_a", "test_ghost"),
        ]))
        assert vsc.verify(collected, [j1]) == 1
        err = capsys.readouterr().err
        assert "JUnit and collection drifted" in err

    def test_no_junit_files(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        collected = tmp_path / "collected.txt"
        collected.write_text("")
        assert vsc.verify(collected, []) == 1
        err = capsys.readouterr().err
        assert "no JUnit artifacts" in err

    def test_unreadable_collected(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        j1 = tmp_path / "junit-a.xml"
        j1.write_text(_junit([]))
        assert vsc.verify(tmp_path / "missing.txt", [j1]) == 1
        err = capsys.readouterr().err
        assert "cannot read collected" in err

    def test_malformed_junit(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        collected = tmp_path / "collected.txt"
        collected.write_text("")
        bad = tmp_path / "junit-bad.xml"
        bad.write_text("not xml at all")
        assert vsc.verify(collected, [bad]) == 1
        err = capsys.readouterr().err
        assert "cannot parse JUnit" in err


class TestMain:
    def test_main_argv(self, tmp_path: Path) -> None:
        collected = tmp_path / "collected.txt"
        collected.write_text("tests/test_a.py::test_one\n")
        j1 = tmp_path / "junit-a.xml"
        j1.write_text(_junit([("tests.test_a", "test_one")]))
        assert vsc.main(["--collected", str(collected), "--junit", str(j1)]) == 0
