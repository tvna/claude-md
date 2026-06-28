# AST graph: scripts/scan_install_curl_retry_drift.py

This file is generated from `scripts/scan_install_curl_retry_drift.py` by `python3 scripts/script_ast_graph.py all-doc`. Do not edit it by hand: content under `docs/generated/scripts/` is owned by the post-merge automation (refs #1540); update the source script instead.

## _is_comment_line(...)

```mermaid
flowchart TD
    N001["_is_comment_line(...)"]
    N002["return line.lstrip().startswith('<str>')"]
    N001 -->|"start"| N002
```

## find_violations(...)

```mermaid
flowchart TD
    N001["find_violations(...)"]
    N002["violations = []"]
    N003["for path in paths:     try:         text = path.read_text(encoding='<str>')     except OSError:         continue     for line_no, line in enumerate(text.splitlines(), start=1):         if _is_comment_line(line):             continue         if _CURL.search(line):             violations.append((path, line_no, line.strip()))"]
    N004["return violations"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
```

## installer_paths(...)

```mermaid
flowchart TD
    N001["installer_paths(...)"]
    N002["return sorted((root / '<str>').glob(_INSTALLER_GLOB))"]
    N001 -->|"start"| N002
```

## main(...)

```mermaid
flowchart TD
    N001["main(...)"]
    N002["parser = ArgumentParser(...)"]
    N003["add_argument(...)"]
    N004["parse_args(...)"]
    N005["paths = installer_paths(...)"]
    N006["if not paths"]
    N007["print(...)"]
    N008["return 0"]
    N009["violations = find_violations(...)"]
    N010["for path, line_no, text in violations:     rel = path.relative_to(_REPO_ROOT) if path.is_relative_to(_REPO_ROOT) else path     print(f'<str>{rel}<str>{line_no}<str>{_SCRIPT}<str>{rel}<str>{text}', file=sys.stderr)"]
    N011["return 1 if violations else 0"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 --> N005
    N005 --> N006
    N006 -->|"true"| N007
    N007 --> N008
    N006 -->|"false"| N009
    N009 --> N010
    N010 --> N011
```
