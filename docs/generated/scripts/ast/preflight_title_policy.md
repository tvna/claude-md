# AST graph: scripts/preflight_title_policy.py

This file is generated from `scripts/preflight_title_policy.py` by `python3 scripts/script_ast_graph.py all-doc`. Do not edit it by hand: content under `docs/generated/scripts/` is owned by the post-merge automation (refs #1540); update the source script instead.

## extract_title(...)

```mermaid
flowchart TD
    N001["extract_title(...)"]
    N002["title = tool_input.get('<str>') or '<str>'"]
    N003["if not isinstance(title, str)"]
    N004["return '<str>'"]
    N005["return title"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 -->|"true"| N004
    N003 -->|"false"| N005
```

## extract_body(...)

```mermaid
flowchart TD
    N001["extract_body(...)"]
    N002["body = tool_input.get('<str>') or tool_input.get('<str>') or '<str>'"]
    N003["if not isinstance(body, str)"]
    N004["return '<str>'"]
    N005["return body"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 -->|"true"| N004
    N003 -->|"false"| N005
```

## kind_for_tool(...)

```mermaid
flowchart TD
    N001["kind_for_tool(...)"]
    N002["canonical = canonical_github_tool(...)"]
    N003["if canonical == 'mcp__github__issue_write'"]
    N004["return '<str>'"]
    N005["if canonical in _PR_TOOLS"]
    N006["return '<str>'"]
    N007["return None"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 -->|"true"| N004
    N003 -->|"false"| N005
    N005 -->|"true"| N006
    N005 -->|"false"| N007
```

## find_invalid_type(...)

```mermaid
flowchart TD
    N001["find_invalid_type(...)"]
    N002["if follows_naming_convention(title, kind=kind)"]
    N003["return None"]
    N004["head = strip(...)"]
    N005["if not head"]
    N006["return title.strip()[:40]"]
    N007["return head"]
    N001 -->|"start"| N002
    N002 -->|"true"| N003
    N002 -->|"false"| N004
    N004 --> N005
    N005 -->|"true"| N006
    N005 -->|"false"| N007
```

## build_non_ascii_deny_reason(...)

```mermaid
flowchart TD
    N001["build_non_ascii_deny_reason(...)"]
    N002["details = join(...)"]
    N003["return f'<str>{tool_name}<str>{kind}<str>{details}<str>{title!r}'"]
    N001 -->|"start"| N002
    N002 --> N003
```

## build_invalid_type_deny_reason(...)

```mermaid
flowchart TD
    N001["build_invalid_type_deny_reason(...)"]
    N002["hint = naming_convention_hint(...)"]
    N003["types_csv = allowed_types_csv(...)"]
    N004["return f'<str>{tool_name}<str>{kind}<str>{offending!r}<str>{hint}<str>{types_csv}<str>{title!r}<str>'"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
```

## build_issue_ref_deny_reason(...)

```mermaid
flowchart TD
    N001["build_issue_ref_deny_reason(...)"]
    N002["refs_csv = join(...)"]
    N003["return f'<str>{tool_name}<str>{refs_csv}<str>{title!r}<str>{suggested!r}<str>'"]
    N001 -->|"start"| N002
    N002 --> N003
```

## build_type_fit_deny_reason(...)

```mermaid
flowchart TD
    N001["build_type_fit_deny_reason(...)"]
    N002["return f'<str>{tool_name}<str>{kind}<str>{finding_text}<str>{title!r}<str>'"]
    N001 -->|"start"| N002
```

## decide(...)

```mermaid
flowchart TD
    N001["decide(...)"]
    N002["kind = kind_for_tool(...)"]
    N003["if kind is None"]
    N004["return None"]
    N005["title = extract_title(...)"]
    N006["if not title"]
    N007["return None"]
    N008["body = extract_body(...)"]
    N009["if not is_ascii_title(title)"]
    N010["findings = describe_non_ascii(...)"]
    N011["return build_deny(build_non_ascii_deny_reason(tool_name, kind, title, findings))"]
    N012["invalid_type = find_invalid_type(...)"]
    N013["if invalid_type is not None"]
    N014["return build_deny(build_invalid_type_deny_reason(tool_name, kind, title, invalid_type))"]
    N015["fit_findings = type_fit_findings(...)"]
    N016["if fit_findings"]
    N017["return build_deny(build_type_fit_deny_reason(tool_name, kind, title, format_type_fit_finding(fit_findings[0])))"]
    N018["if kind == 'pull_request' and pr_title_has_issue_ref(title) and (not pr_title_ref_is_exempt(title))"]
    N019["refs = pr_title_issue_refs(...)"]
    N020["suggested = pr_title_strip_issue_refs(...)"]
    N021["return build_deny(build_issue_ref_deny_reason(tool_name, title, refs, suggested))"]
    N022["return None"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 -->|"true"| N004
    N003 -->|"false"| N005
    N005 --> N006
    N006 -->|"true"| N007
    N006 -->|"false"| N008
    N008 --> N009
    N009 -->|"true"| N010
    N010 --> N011
    N009 -->|"false"| N012
    N012 --> N013
    N013 -->|"true"| N014
    N013 -->|"false"| N015
    N015 --> N016
    N016 -->|"true"| N017
    N016 -->|"false"| N018
    N018 -->|"true"| N019
    N019 --> N020
    N020 --> N021
    N018 -->|"false"| N022
```

## main(...)

```mermaid
flowchart TD
    N001["main(...)"]
    N002["del argv"]
    N003["return run_tool_hook('<str>', decide)"]
    N001 -->|"start"| N002
    N002 --> N003
```
