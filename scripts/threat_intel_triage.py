#!/usr/bin/env python3
"""Classify whether an issue/PR needs threat intelligence handling.

The rule is intentionally deterministic and local: it reads title, body,
and labels, then decides whether to add:

* ``threat:intel-needed`` -- collect threat intelligence before routing.
* ``threat:response-needed`` -- security response is required; do not
  create an autonomous fix without investigation.

No external feeds are queried here. The workflow boundary can add richer
collection later, but this gate stays fast, testable, and dependency-free.
"""

from __future__ import annotations

import argparse
import json
import os
import re
from pathlib import Path
from typing import NamedTuple


INTEL_LABEL = "threat:intel-needed"
RESPONSE_LABEL = "threat:response-needed"
SECURITY_LABEL = "severity:security"
THREAT_LABELS = {INTEL_LABEL, RESPONSE_LABEL}


class Indicator(NamedTuple):
    name: str
    pattern: re.Pattern[str]


INTEL_INDICATORS = (
    Indicator("cve", re.compile(r"\bCVE-\d{4}-\d{4,}\b", re.IGNORECASE)),
    Indicator("ghsa", re.compile(r"\bGHSA-[0-9a-z]{4}-[0-9a-z]{4}-[0-9a-z]{4}\b", re.IGNORECASE)),
    Indicator("osv", re.compile(r"\bOSV-\d{4}-\d+\b", re.IGNORECASE)),
    Indicator("advisory", re.compile(r"\b(?:security advisory|advisory)\b", re.IGNORECASE)),
    Indicator("vulnerability", re.compile(r"\b(?:vulnerability|vulnerable|vuln)\b", re.IGNORECASE)),
    Indicator("exploit", re.compile(r"\b(?:exploit|exploitable|exploitation)\b", re.IGNORECASE)),
    Indicator("zero-day", re.compile(r"\b(?:zero[- ]day|0day)\b", re.IGNORECASE)),
    Indicator("malware", re.compile(r"\b(?:malware|backdoor|trojan)\b", re.IGNORECASE)),
    Indicator("malicious-package", re.compile(r"\bmalicious (?:package|dependency|release)\b", re.IGNORECASE)),
    Indicator("supply-chain", re.compile(r"\b(?:supply[- ]chain|dependency confusion|typosquat(?:ting)?)\b", re.IGNORECASE)),
    Indicator("secret-leak", re.compile(r"\b(?:secret|token|credential)s? (?:leak|leaked|exposed|exposure)\b", re.IGNORECASE)),
    Indicator("compromise", re.compile(r"\b(?:compromise|compromised|account takeover)\b", re.IGNORECASE)),
    Indicator("ioc", re.compile(r"\b(?:indicator of compromise|ioc)s?\b", re.IGNORECASE)),
)

RESPONSE_INDICATORS = (
    Indicator("active-exploitation", re.compile(r"\b(?:active exploitation|exploited in the wild|under attack)\b", re.IGNORECASE)),
    Indicator("exploit-available", re.compile(r"\b(?:public exploit|exploit available|poc exploit)\b", re.IGNORECASE)),
    Indicator("critical", re.compile(r"\bcritical\b", re.IGNORECASE)),
    Indicator("rce", re.compile(r"\b(?:RCE|remote code execution)\b", re.IGNORECASE)),
    Indicator("malicious-package", re.compile(r"\bmalicious (?:package|dependency|release)\b", re.IGNORECASE)),
    Indicator("secret-leak", re.compile(r"\b(?:secret|token|credential)s? (?:leak|leaked|exposed|exposure)\b", re.IGNORECASE)),
    Indicator("compromise", re.compile(r"\b(?:compromise|compromised|account takeover)\b", re.IGNORECASE)),
    Indicator("credential-action", re.compile(r"\b(?:rotate|revoke) (?:secret|token|credential)s?\b", re.IGNORECASE)),
)


def parse_labels(raw: str | list[str] | tuple[str, ...]) -> set[str]:
    """Return normalized label names from comma/newline separated input."""
    if isinstance(raw, str):
        chunks = re.split(r"[,\n]", raw)
    else:
        chunks = []
        for item in raw:
            chunks.extend(re.split(r"[,\n]", item))
    return {chunk.strip() for chunk in chunks if chunk.strip()}


def find_indicators(text: str, indicators: tuple[Indicator, ...]) -> list[str]:
    """Return sorted-unique indicator names present in *text*."""
    return sorted({indicator.name for indicator in indicators if indicator.pattern.search(text)})


def classify(title: str, body: str, labels: set[str]) -> dict[str, object]:
    """Classify threat-intelligence and response requirements."""
    text = f"{title}\n{body}"
    intel_matches = find_indicators(text, INTEL_INDICATORS)
    response_matches = find_indicators(text, RESPONSE_INDICATORS)
    security_labeled = SECURITY_LABEL in labels

    intel_needed = security_labeled or bool(intel_matches) or bool(response_matches)
    response_needed = security_labeled or bool(response_matches)

    recommended_labels: list[str] = []
    if intel_needed:
        recommended_labels.append(INTEL_LABEL)
    if response_needed:
        recommended_labels.append(RESPONSE_LABEL)
    remove_labels = sorted((labels & THREAT_LABELS) - set(recommended_labels))

    return {
        "intel_needed": intel_needed,
        "response_needed": response_needed,
        "recommended_labels": recommended_labels,
        "remove_labels": remove_labels,
        "matched_intel_indicators": intel_matches,
        "matched_response_indicators": response_matches,
        "security_labeled": security_labeled,
    }


def _cmd_classify(args: argparse.Namespace) -> int:
    body = args.body or ""
    if args.body_file:
        body = Path(args.body_file).read_text(encoding="utf-8")
    labels = parse_labels(args.labels or os.environ.get("LABELS", ""))
    result = classify(args.title or os.environ.get("TITLE", ""), body, labels)

    if args.github_output:
        _write_github_output(Path(args.github_output), result)

    if args.format == "json":
        print(json.dumps(result, sort_keys=True))
        return 0

    print(f"intel_needed={_bool(result['intel_needed'])}")
    print(f"response_needed={_bool(result['response_needed'])}")
    print(f"recommended_labels={','.join(result['recommended_labels'])}")
    print(f"remove_labels={','.join(result['remove_labels'])}")
    print(f"matched_intel_indicators={','.join(result['matched_intel_indicators'])}")
    print(f"matched_response_indicators={','.join(result['matched_response_indicators'])}")
    return 0


def _write_github_output(path: Path, result: dict[str, object]) -> None:
    with path.open("a", encoding="utf-8") as handle:
        handle.write(f"intel_needed={_bool(result['intel_needed'])}\n")
        handle.write(f"response_needed={_bool(result['response_needed'])}\n")
        handle.write(f"recommended_labels={','.join(result['recommended_labels'])}\n")
        handle.write(f"remove_labels={','.join(result['remove_labels'])}\n")


def _bool(value: object) -> str:
    return "true" if bool(value) else "false"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_classify = sub.add_parser(
        "classify",
        help="Classify threat intelligence and response requirements.",
    )
    p_classify.add_argument("--title", help="Issue or PR title. Defaults to $TITLE.")
    p_classify.add_argument("--body", help="Issue or PR body text.")
    p_classify.add_argument("--body-file", help="Path to issue or PR body text.")
    p_classify.add_argument(
        "--labels",
        action="append",
        help="Comma or newline separated label names. Defaults to $LABELS.",
    )
    p_classify.add_argument(
        "--format",
        choices=("text", "json"),
        default="text",
        help="Output format.",
    )
    p_classify.add_argument(
        "--github-output",
        help="Append GitHub Actions outputs to this file.",
    )
    p_classify.set_defaults(func=_cmd_classify)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
