# AST graph: scripts/preflight_issue_ci_staleness.py

This file is generated from `scripts/preflight_issue_ci_staleness.py` by `python3 scripts/script_ast_graph.py all-doc`. Do not edit it by hand: content under `docs/generated/scripts/` is owned by the post-merge automation (refs #1540); update the source script instead.

## _looks_like_ci_failure(...)

```mermaid
flowchart TD
    N001["_looks_like_ci_failure(...)"]
    N002["text = lower(...)"]
    N003["if _ACTIONS_RUN_RE.search(text)"]
    N004["return True"]
    N005["return any((kw in text for kw in _CI_KEYWORDS))"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 -->|"true"| N004
    N003 -->|"false"| N005
```

## _has_verification_phrase(...)

```mermaid
flowchart TD
    N001["_has_verification_phrase(...)"]
    N002["return FRESH_MAIN_CHECK_PHRASE.lower() in body.lower()"]
    N001 -->|"start"| N002
```

## decide(...)

```mermaid
flowchart TD
    N001["decide(...)"]
    N002["if canonical_github_tool(tool_name) != _TARGET_TOOL"]
    N003["return None"]
    N004["method = get(...)"]
    N005["if method is not None and method != _TARGET_METHOD"]
    N006["return None"]
    N007["title = get(...)"]
    N008["body = get(...)"]
    N009["if not isinstance(title, str)"]
    N010["title = '<str>'"]
    N011["if not isinstance(body, str)"]
    N012["body = '<str>'"]
    N013["if not _looks_like_ci_failure(title, body)"]
    N014["return None"]
    N015["if _has_verification_phrase(body)"]
    N016["return None"]
    N017["return build_deny(_DENY_REASON)"]
    N001 -->|"start"| N002
    N002 -->|"true"| N003
    N002 -->|"false"| N004
    N004 --> N005
    N005 -->|"true"| N006
    N005 -->|"false"| N007
    N007 --> N008
    N008 --> N009
    N009 -->|"true"| N010
    N010 --> N011
    N009 -->|"false"| N011
    N011 -->|"true"| N012
    N012 --> N013
    N011 -->|"false"| N013
    N013 -->|"true"| N014
    N013 -->|"false"| N015
    N015 -->|"true"| N016
    N015 -->|"false"| N017
```

## main(...)

```mermaid
flowchart TD
    N001["main(...)"]
    N002["del argv"]
    N003["return run_tool_hook(script_name='<str>', decide=decide, auditable=True)"]
    N001 -->|"start"| N002
    N002 --> N003
```
