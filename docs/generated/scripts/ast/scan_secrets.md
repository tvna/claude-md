# AST graph: scripts/scan_secrets.py

This file is generated from `scripts/scan_secrets.py` by `python3 scripts/script_ast_graph.py all-doc`. Do not edit it by hand: content under `docs/generated/scripts/` is owned by the post-merge automation (refs #1540) -- update the source script instead.

## _is_skipped(...)

```mermaid
flowchart TD
    N001["_is_skipped(...)"]
    N002["if rel_posix in ALLOWLIST_PATHS"]
    N003["return True"]
    N004["name = rel_posix.rsplit('<str>', 1)[-1]"]
    N005["if name in _SKIP_NAMES"]
    N006["return True"]
    N007["suffix = '<str>' if '<str>' not in name else '<str>' + name.rsplit('<str>', 1)[-1].lower()"]
    N008["return suffix in _SKIP_SUFFIXES"]
    N001 -->|"start"| N002
    N002 -->|"true"| N003
    N002 -->|"false"| N004
    N004 --> N005
    N005 -->|"true"| N006
    N005 -->|"false"| N007
    N007 --> N008
```

## iter_tracked_files(...)

```mermaid
flowchart TD
    N001["iter_tracked_files(...)"]
    N002["result = run_git(...)"]
    N003["for rel in result.stdout.split('<str>'):
    if not rel or _is_skipped(rel):
        continue
    yield (repo_root / rel)"]
    N004["end"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
```

## _read_text(...)

```mermaid
flowchart TD
    N001["_read_text(...)"]
    N002["try"]
    N003["return path.read_text(encoding='<str>')"]
    N004["except (OSError, UnicodeDecodeError)"]
    N005["return None"]
    N001 -->|"start"| N002
    N002 -->|"try"| N003
    N002 -->|"raises"| N004
    N004 --> N005
```

## find_violations(...)

```mermaid
flowchart TD
    N001["find_violations(...)"]
    N002["if paths is None"]
    N003["paths = iter_tracked_files(...)"]
    N004["findings = []"]
    N005["for path in paths:
    text = _read_text(path)
    if text is None:
        continue
    rel = path.relative_to(repo_root)
    for lineno, rule_id in scan_text(text):
        findings.append(Finding(path=rel, line=lineno, rule_id=rule_id))"]
    N006["return findings"]
    N001 -->|"start"| N002
    N002 -->|"true"| N003
    N003 --> N004
    N002 -->|"false"| N004
    N004 --> N005
    N005 --> N006
```

## main(...)

```mermaid
flowchart TD
    N001["main(...)"]
    N002["parser = ArgumentParser(...)"]
    N003["sub = add_subparsers(...)"]
    N004["add_parser(...)"]
    N005["add_parser(...)"]
    N006["args = parse_args(...)"]
    N007["findings = find_violations(...)"]
    N008["if args.cmd == 'list'"]
    N009["for f in findings:
    print(f'{f.path.as_posix()}<str>{f.line}<str>{f.rule_id}<str>')"]
    N010["return 0"]
    N011["if not findings"]
    N012["print(...)"]
    N013["return 0"]
    N014["for f in findings:
    print(f'<str>{f.path.as_posix()}<str>{f.line}<str>{f.rule_id}<str>{PRAGMA_ALLOWLIST}<str>', file=sys.stderr)"]
    N015["print(...)"]
    N016["return 1"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 --> N005
    N005 --> N006
    N006 --> N007
    N007 --> N008
    N008 -->|"true"| N009
    N009 --> N010
    N008 -->|"false"| N011
    N011 -->|"true"| N012
    N012 --> N013
    N011 -->|"false"| N014
    N014 --> N015
    N015 --> N016
```
