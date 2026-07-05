#!/usr/bin/env python3
"""CI gate: validate every ``.gitapex/*.toml`` against its sibling JSON Schema.

Issue #2342 moved five repo-specific config TOMLs from ``docs/`` into
``.gitapex/`` and added a JSON Schema per file (owner's schema-at-migration
decision), mirroring the ``.gitapex/ssot.json`` / ``ssot.schema.json``
precedent (``scan_ssot_schema.py``). Rather than five bespoke validators, this
gate is the single generic form the issue's own assumption allows: for every
``.gitapex/NAME.toml``, require a sibling ``.gitapex/NAME.schema.json`` and
validate the parsed TOML against it using the shared draft-2020-12 subset
engine in ``scripts/_json_schema_subset.py``.

Division of labor (same as the ssot precedent): this gate checks shape only
(types, required keys, item shapes). Referential integrity and semantic rules
stay with each file's existing normative validator: ``doc_graph.load_graph``
(node/edge enums, dangling edge endpoints), ``scan_pr_body_quality_drift.py``
and ``scan_quality_standard_drift.py`` (registry-vs-known-keys drift and
backing resolution), and ``audit_loop_engineering.py`` (working-tree drift) --
none of which this gate duplicates or replaces.

``.gitapex/ssot.json`` and ``.gitapex/ssot.schema.json`` are JSON, not TOML,
and are out of scope for this gate (``scan_ssot_schema.py`` already covers
them); the ``*.toml`` glob naturally excludes them.

Architecture: pure functions on top (:func:`discover_toml_files`,
:func:`verify_file`), a single filesystem-read IO boundary in :func:`main`.

Contract:
- Inputs: the ``verify`` subcommand; ``--gitapex-dir`` (default ``.gitapex``).
- Outputs: ``::error::`` annotations on stderr per violation or missing
  schema; an ``OK:`` line on success; exit 0 when every ``.gitapex/*.toml``
  has a sibling schema and validates against it, exit 1 otherwise, exit 64 on
  an unrecognised subcommand.
- Failure policy: fails loud (exit 1) per CLAUDE.md section 4; a TOML with no
  sibling schema, an unparseable TOML/schema file, or a shape violation all
  exit non-zero.

Tested by ``tests/test_scan_gitapex_schema.py``. Refs #2342, #2252.
"""

from __future__ import annotations

import argparse
import json
import sys
import tomllib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _json_schema_subset import SchemaError, validate_shape

_SCRIPT = "scan_gitapex_schema"
_REPO_ROOT = Path(__file__).resolve().parent.parent
_GITAPEX_DIR = ".gitapex"


def discover_toml_files(gitapex_dir: Path) -> list[Path]:
    """Return every ``*.toml`` file directly under *gitapex_dir*, sorted."""
    return sorted(gitapex_dir.glob("*.toml"))


def verify_file(toml_path: Path, *, display: str) -> list[str]:
    """Return violation strings for *toml_path*; empty means it validates.

    *display* is the path used in messages (repo-relative, for readable
    ``::error::`` annotations regardless of the caller's working directory).
    A missing sibling ``NAME.schema.json`` is itself a violation (every
    ``.gitapex/*.toml`` must be schema-validated per #2342).
    """
    schema_path = toml_path.with_suffix(".schema.json")
    if not schema_path.exists():
        return [f"{display}: no sibling schema {schema_path.name!r} found"]

    try:
        instance = tomllib.loads(toml_path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as exc:
        return [f"{display}: cannot parse TOML: {exc}"]

    try:
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return [f"{schema_path.name}: cannot parse JSON Schema: {exc}"]

    if not isinstance(schema, dict):
        raise SchemaError(f"{schema_path.name}: schema root is not a JSON object")

    return [
        f"{display}: {message}"
        for message in validate_shape(instance, schema, root_path=toml_path.name)
    ]


def cmd_verify(args: argparse.Namespace) -> int:
    gitapex_dir = _REPO_ROOT / args.gitapex_dir
    if not gitapex_dir.is_dir():
        print(
            f"::error::{_SCRIPT}: {gitapex_dir} is not a directory.",
            file=sys.stderr,
        )
        return 1

    toml_files = discover_toml_files(gitapex_dir)
    errors: list[str] = []
    for toml_path in toml_files:
        try:
            errors.extend(
                verify_file(toml_path, display=f"{args.gitapex_dir}/{toml_path.name}")
            )
        except SchemaError as exc:
            errors.append(str(exc))

    if errors:
        for message in errors:
            print(f"::error::{_SCRIPT}: {message}", file=sys.stderr)
        return 1

    print(
        f"OK: {_SCRIPT}: {len(toml_files)} {args.gitapex_dir}/*.toml file(s) validate "
        "against their sibling schema.",
        file=sys.stderr,
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    if argv is None:
        argv = sys.argv[1:]

    command = argv[0] if argv else None
    if command != "verify":
        print(
            f"::error::{_SCRIPT}: unknown subcommand {command!r}; expected 'verify'.",
            file=sys.stderr,
        )
        return 64

    parser = argparse.ArgumentParser(
        description="Validate every .gitapex/*.toml against its sibling JSON Schema."
    )
    parser.add_argument("command", help="Must be 'verify'.")
    parser.add_argument("--gitapex-dir", default=_GITAPEX_DIR)
    args = parser.parse_args(argv)

    return cmd_verify(args)


if __name__ == "__main__":
    raise SystemExit(main())
