# AST graph: scripts/scan_allowlist_rationale.py

This file is generated from `scripts/scan_allowlist_rationale.py` by `python3 scripts/script_ast_graph.py all-doc`. Do not edit it by hand: content under `docs/generated/scripts/` is owned by the post-merge automation (refs #1540); update the source script instead.

## check_file(...)

```mermaid
flowchart TD
    N001["check_file(...)"]
    N002["try"]
    N003["rel = relative_to(...)"]
    N004["except ValueError"]
    N005["rel = path"]
    N006["errors = []"]
    N007["for lineno, raw in enumerate(path.read_text(encoding='<str>').splitlines(), start=1):     stripped = raw.strip()     if not stripped or stripped.startswith('<str>'):         continue     content, rationale = split_inline_comment(raw)     if content.startswith('<str>'):         continue     if not content:         continue     if not rationale:         errors.append(f'<str>{rel}<str>{lineno}<str>{content}<str>{rel}<str>{content}<str>')"]
    N008["return errors"]
    N001 -->|"start"| N002
    N002 -->|"try"| N003
    N002 -->|"raises"| N004
    N004 --> N005
    N003 --> N006
    N005 --> N006
    N006 --> N007
    N007 --> N008
```

## verify(...)

```mermaid
flowchart TD
    N001["verify(...)"]
    N002["network_dir = joinpath(...)"]
    N003["if not network_dir.is_dir()"]
    N004["return [f'<str>{network_dir}<str>']"]
    N005["files = sorted(...)"]
    N006["if not files"]
    N007["return [f'<str>{ALLOWLIST_GLOB}<str>{network_dir}<str>']"]
    N008["errors = []"]
    N009["for path in files:     errors.extend(check_file(path, repo_root))"]
    N010["return errors"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 -->|"true"| N004
    N003 -->|"false"| N005
    N005 --> N006
    N006 -->|"true"| N007
    N006 -->|"false"| N008
    N008 --> N009
    N009 --> N010
```

## _cmd_verify(...)

```mermaid
flowchart TD
    N001["_cmd_verify(...)"]
    N002["repo_root = resolve(...)"]
    N003["errors = verify(...)"]
    N004["for err in errors:     print(err, file=sys.stderr)"]
    N005["if errors"]
    N006["print(...)"]
    N007["return 1"]
    N008["print(...)"]
    N009["return 0"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 --> N005
    N005 -->|"true"| N006
    N006 --> N007
    N005 -->|"false"| N008
    N008 --> N009
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
