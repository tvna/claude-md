"""Schema tests for ``scripts/translations.json``.

Pure-data validation; no API calls and no imports from project scripts.
The file is consumed by ``scripts/sanitize_history.py`` (#102 Layer 1
P5) which trusts these invariants. Anchored to the schema shape
documented in ``docs/non-ascii-defense.md`` lines 55-69.

Refs #102.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pytest

TRANSLATIONS_PATH = (
    Path(__file__).resolve().parent.parent / "scripts" / "translations.json"
)

_HEX_64 = re.compile(r"^[0-9a-f]{64}$")
_NON_ASCII = re.compile(r"[^\x00-\x7F]")
_CROSSREF = re.compile(r"#(\d+)")
_TRIPLE_BACKTICK = re.compile(r"```")
_HTML_ENTITY = re.compile(r"&(?:[a-zA-Z]+|#\d+);")

_VALID_TYPES = {"issue", "pr", "issue_comment"}
_VALID_FIELDS = {"title", "body"}
_VALID_CONFIDENCES = {"high", "medium", "low"}


@pytest.fixture(scope="module")
def translations() -> dict[str, Any]:
    return json.loads(TRANSLATIONS_PATH.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# Top-level shape
# ---------------------------------------------------------------------------


class TestTopLevel:
    def test_file_exists_and_parses(self) -> None:
        assert TRANSLATIONS_PATH.is_file(), TRANSLATIONS_PATH
        json.loads(TRANSLATIONS_PATH.read_text(encoding="utf-8"))

    def test_required_keys_present(self, translations: dict[str, Any]) -> None:
        for key in ("schema_version", "source_sha256", "captured_at", "items"):
            assert key in translations, f"missing top-level key {key!r}"

    def test_schema_version_is_one(self, translations: dict[str, Any]) -> None:
        assert translations["schema_version"] == 1

    def test_source_sha256_is_64_hex(self, translations: dict[str, Any]) -> None:
        digest = translations["source_sha256"]
        assert isinstance(digest, str)
        assert _HEX_64.fullmatch(digest), f"not a 64-char lowercase hex: {digest!r}"

    def test_items_is_list(self, translations: dict[str, Any]) -> None:
        assert isinstance(translations["items"], list)


# ---------------------------------------------------------------------------
# Per-item shape
# ---------------------------------------------------------------------------


class TestItems:
    def test_every_item_has_required_keys(self, translations: dict[str, Any]) -> None:
        required = {"id", "type", "comment_id", "field",
                    "original", "translated", "confidence"}
        for index, item in enumerate(translations["items"]):
            missing = required - set(item)
            assert not missing, f"item index={index}: missing keys {missing}"

    def test_type_is_valid_enum(self, translations: dict[str, Any]) -> None:
        for item in translations["items"]:
            assert item["type"] in _VALID_TYPES, (
                f"id={item.get('id')}: type={item.get('type')!r} not in {_VALID_TYPES}"
            )

    def test_field_is_valid_enum(self, translations: dict[str, Any]) -> None:
        for item in translations["items"]:
            assert item["field"] in _VALID_FIELDS, (
                f"id={item.get('id')}: field={item.get('field')!r} not in {_VALID_FIELDS}"
            )

    def test_confidence_is_valid_enum(self, translations: dict[str, Any]) -> None:
        for item in translations["items"]:
            assert item["confidence"] in _VALID_CONFIDENCES, (
                f"id={item.get('id')}: confidence={item.get('confidence')!r} "
                f"not in {_VALID_CONFIDENCES}"
            )

    def test_comment_id_consistency(self, translations: dict[str, Any]) -> None:
        for item in translations["items"]:
            if item["type"] == "issue_comment":
                assert item["comment_id"] is not None, (
                    f"id={item.get('id')}: issue_comment must carry comment_id"
                )
            else:
                assert item["comment_id"] is None, (
                    f"id={item.get('id')}: non-comment item must have comment_id=null"
                )

    def test_translated_field_is_ascii_only(self, translations: dict[str, Any]) -> None:
        for item in translations["items"]:
            translated = item["translated"]
            assert isinstance(translated, str)
            offender = _NON_ASCII.search(translated)
            assert offender is None, (
                f"id={item.get('id')} field={item['field']}: translated contains "
                f"non-ASCII {offender.group()!r} at offset {offender.start()}"
            )

    def test_original_and_translated_differ(
        self, translations: dict[str, Any]
    ) -> None:
        for item in translations["items"]:
            assert item["original"] != item["translated"], (
                f"id={item.get('id')} field={item['field']}: original == translated "
                "is a noop entry and should not be in the mapping"
            )


# ---------------------------------------------------------------------------
# Structure preservation invariants
# ---------------------------------------------------------------------------


class TestPreservation:
    def test_crossref_numbers_preserved(self, translations: dict[str, Any]) -> None:
        for item in translations["items"]:
            originals = sorted(_CROSSREF.findall(item["original"]))
            translateds = sorted(_CROSSREF.findall(item["translated"]))
            assert originals == translateds, (
                f"id={item.get('id')} field={item['field']}: #NN cross-refs "
                f"diverged. original={originals} translated={translateds}"
            )

    def test_triple_backtick_fence_count_preserved(
        self, translations: dict[str, Any]
    ) -> None:
        for item in translations["items"]:
            o_count = len(_TRIPLE_BACKTICK.findall(item["original"]))
            t_count = len(_TRIPLE_BACKTICK.findall(item["translated"]))
            assert o_count == t_count, (
                f"id={item.get('id')} field={item['field']}: fence count diverged "
                f"({o_count} vs {t_count})"
            )

    def test_html_entities_preserved(self, translations: dict[str, Any]) -> None:
        for item in translations["items"]:
            originals = sorted(_HTML_ENTITY.findall(item["original"]))
            translateds = sorted(_HTML_ENTITY.findall(item["translated"]))
            assert originals == translateds, (
                f"id={item.get('id')} field={item['field']}: HTML entities diverged. "
                f"original={originals} translated={translateds}"
            )


# ---------------------------------------------------------------------------
# Uniqueness
# ---------------------------------------------------------------------------


class TestUniqueness:
    def test_entries_are_unique_by_natural_key(
        self, translations: dict[str, Any]
    ) -> None:
        seen: set[tuple[Any, ...]] = set()
        for index, item in enumerate(translations["items"]):
            key = (item["type"], item["id"], item["comment_id"], item["field"])
            assert key not in seen, (
                f"duplicate (type,id,comment_id,field) at index {index}: {key}"
            )
            seen.add(key)


# ---------------------------------------------------------------------------
# Self-mutation defense: P1/P3/P5 rollout PRs must be excluded
# ---------------------------------------------------------------------------


class TestSelfMutationExclusion:
    """The three rollout PRs (#102 P1/P3/P5) must not appear in the mapping.

    PR numbers are pinned in ``scripts/translations.json::meta.excluded_prs``
    so this test is data-driven; updating that list updates the assertion.
    """

    def test_excluded_pr_list_declared(self, translations: dict[str, Any]) -> None:
        meta = translations.get("meta") or {}
        assert "excluded_prs" in meta, (
            "meta.excluded_prs must declare which rollout PRs were filtered out"
        )
        assert isinstance(meta["excluded_prs"], list)

    def test_no_item_targets_an_excluded_pr(
        self, translations: dict[str, Any]
    ) -> None:
        excluded = set((translations.get("meta") or {}).get("excluded_prs") or [])
        for item in translations["items"]:
            if item["type"] != "pr":
                continue
            number = item.get("number")
            assert number not in excluded, (
                f"item id={item.get('id')} targets PR #{number} which is in "
                f"meta.excluded_prs={sorted(excluded)}"
            )
