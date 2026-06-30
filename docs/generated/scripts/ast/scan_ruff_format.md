# AST graph: scripts/scan_ruff_format.py

This file is generated from `scripts/scan_ruff_format.py` by `python3 scripts/script_ast_graph.py all-doc`. Do not edit it by hand: content under `docs/generated/scripts/` is owned by the post-merge automation (refs #1540); update the source script instead.

## scan_line(...)

```mermaid
flowchart TD
    N001["scan_line(...)"]
    N002["if ACK_MARKER in line"]
    N003["return False"]
    N004["if _COMMENT_LINE.match(line) or _LABEL_LINE.match(line)"]
    N005["return False"]
    N006["return _RUFF_FORMAT.search(line) is not None"]
    N001 -->|"start"| N002
    N002 -->|"true"| N003
    N002 -->|"false"| N004
    N004 -->|"true"| N005
    N004 -->|"false"| N006
```

## scan_text(...)

```mermaid
flowchart TD
    N001["scan_text(...)"]
    N002["return [lineno for lineno, logical in flatten_shell_continuations(text) if scan_line(logical)]"]
    N001 -->|"start"| N002
```

## _iter_text_surfaces(...)

```mermaid
flowchart TD
    N001["_iter_text_surfaces(...)"]
    N002["paths = []"]
    N003["for subdir in _YAML_SURFACE_SUBDIRS:     directory = repo_root / subdir     if directory.exists():         paths.extend((p for p in sorted(directory.rglob('<str>')) if p.is_file() and p.suffix in ('<str>', '<str>')))"]
    N004["for rel in _HOOK_AND_CONFIG_FILES:     candidate = repo_root / rel     if candidate.is_file():         paths.append(candidate)"]
    N005["return paths"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 --> N005
```

## find_text_violations(...)

```mermaid
flowchart TD
    N001["find_text_violations(...)"]
    N002["violations = []"]
    N003["for path in _iter_text_surfaces(repo_root):     rel = path.relative_to(repo_root)     for lineno in scan_text(path.read_text(encoding='<str>', errors='<str>')):         violations.append((rel, lineno))"]
    N004["return violations"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
```

## find_manifest_violations(...)

```mermaid
flowchart TD
    N001["find_manifest_violations(...)"]
    N002["try"]
    N003["from preflight_steps import STEPS"]
    N004["except ImportError"]
    N005["return []"]
    N006["return [step.name for step in STEPS if any((a == '<str>' and b == '<str>' for a, b in zip(step.argv, step.argv[1:], strict=False)))]"]
    N001 -->|"start"| N002
    N002 -->|"try"| N003
    N002 -->|"raises"| N004
    N004 --> N005
    N003 --> N006
```

## _escape_annotation_property(...)

```mermaid
flowchart TD
    N001["_escape_annotation_property(...)"]
    N002["return value.replace('<str>', '<str>').replace('<str>', '<str>').replace('<str>', '<str>').replace('<str>', '<str>').replace('<str>', '<str>')"]
    N001 -->|"start"| N002
```

## _cmd_verify(...)

```mermaid
flowchart TD
    N001["_cmd_verify(...)"]
    N002["repo_root = resolve(...)"]
    N003["text_violations = find_text_violations(...)"]
    N004["manifest_violations = find_manifest_violations(...)"]
    N005["for rel, lineno in text_violations:     print(f'<str>{_escape_annotation_property(str(rel))}<str>{lineno}<str>{ACK_MARKER}<str>', file=sys.stderr)"]
    N006["for name in manifest_violations:     print(f'<str>{name}<str>', file=sys.stderr)"]
    N007["total = len(text_violations) + len(manifest_violations)"]
    N008["if total"]
    N009["print(...)"]
    N010["return 1"]
    N011["print(...)"]
    N012["return 0"]
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
    N011 --> N012
```

## main(...)

```mermaid
flowchart TD
    N001["main(...)"]
    N002["parser = ArgumentParser(...)"]
    N003["sub = add_subparsers(...)"]
    N004["p_verify = add_parser(...)"]
    N005["add_argument(...)"]
    N006["set_defaults(...)"]
    N007["args = parse_args(...)"]
    N008["return args.func(args)"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 --> N005
    N005 --> N006
    N006 --> N007
    N007 --> N008
```
