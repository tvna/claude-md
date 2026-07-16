# AST graph: scripts/scan_apm_portability.py

This file is generated from `scripts/scan_apm_portability.py` by `python3 scripts/script_ast_graph.py all-doc`. Do not edit it by hand: content under `docs/generated/scripts/` is owned by the post-merge automation (refs #1540); update the source script instead.

## scan_line(...)

```mermaid
flowchart TD
    N001["scan_line(...)"]
    N002["issue_ref_hits = [f'{ISSUE_REF_HIT_PREFIX}{match.group(0)}' for match in FORBIDDEN_ISSUE_REF_PATTERN.finditer(line)]"]
    N003["if ACK_MARKER in line"]
    N004["return issue_ref_hits"]
    N005["hits = [token for token in FORBIDDEN_TOKENS if token in line]"]
    N006["for pattern in FORBIDDEN_PHRASE_PATTERNS:     match = pattern.search(line)     if match is not None:         hits.append(f'{PHRASE_HIT_PREFIX}{match.group(0)}')"]
    N007["extend(...)"]
    N008["extend(...)"]
    N009["return hits"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 -->|"true"| N004
    N003 -->|"false"| N005
    N005 --> N006
    N006 --> N007
    N007 --> N008
    N008 --> N009
```

## scan_text(...)

```mermaid
flowchart TD
    N001["scan_text(...)"]
    N002["hits = []"]
    N003["for lineno, line in enumerate(text.splitlines(), start=1):     for token in scan_line(line):         hits.append((lineno, token))"]
    N004["return hits"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
```

## scan_file(...)

```mermaid
flowchart TD
    N001["scan_file(...)"]
    N002["return scan_text(path.read_text(encoding='<str>'))"]
    N001 -->|"start"| N002
```

## _verify(...)

```mermaid
flowchart TD
    N001["_verify(...)"]
    N002["total = 0"]
    N003["for path in paths:     if not path.exists():         print(f'<str>{path}', file=sys.stderr)         total += 1         continue     for lineno, hit in scan_file(path):         if hit.startswith(PHRASE_HIT_PREFIX):             snippet = hit[len(PHRASE_HIT_PREFIX):]             kind = '<str>'             payload = repr(snippet)         elif hit.startswith(HARNESS_HIT_PREFIX):             snippet = hit[len(HARNESS_HIT_PREFIX):]             kind = '<str>'             payload = repr(snippet)         elif hit.startswith(ISSUE_REF_HIT_PREFIX):             snippet = hit[len(ISSUE_REF_HIT_PREFIX):]             kind = '<str>'             payload = repr(snippet)         else:             kind = '<str>'             payload = repr(hit)         print(f'<str>{path}<str>{lineno}<str>{kind}<str>{payload}<str>{ACK_MARKER}<str>', file=sys.stderr)         total += 1"]
    N004["if total"]
    N005["print(...)"]
    N006["return 1"]
    N007["print(...)"]
    N008["return 0"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 -->|"true"| N005
    N005 --> N006
    N004 -->|"false"| N007
    N007 --> N008
```

## _cmd_verify(...)

```mermaid
flowchart TD
    N001["_cmd_verify(...)"]
    N002["if not args.path"]
    N003["print(...)"]
    N004["return 2"]
    N005["paths = [Path(p) for p in args.path]"]
    N006["return _verify(paths)"]
    N001 -->|"start"| N002
    N002 -->|"true"| N003
    N003 --> N004
    N002 -->|"false"| N005
    N005 --> N006
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
