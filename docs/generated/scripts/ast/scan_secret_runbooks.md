# AST graph: scripts/scan_secret_runbooks.py

This file is generated from `scripts/scan_secret_runbooks.py` by `python3 scripts/script_ast_graph.py all-doc`. Do not edit it by hand: content under `docs/generated/scripts/` is owned by the post-merge automation (refs #1540) -- update the source script instead.

## rel(...)

```mermaid
flowchart TD
    N001["rel(...)"]
    N002["try"]
    N003["return path.relative_to(root)"]
    N004["except ValueError"]
    N005["return path"]
    N001 -->|"start"| N002
    N002 -->|"try"| N003
    N002 -->|"raises"| N004
    N004 --> N005
```

## collect_secret_uses(...)

```mermaid
flowchart TD
    N001["collect_secret_uses(...)"]
    N002["uses = []"]
    N003["for path in sorted((*workflows_dir.glob('<str>'), *workflows_dir.glob('<str>'))):
    for lineno, line in enumerate(path.read_text(encoding='<str>').splitlines(), start=1):
        for match in SECRET_REF_RE.finditer(line):
            name = match.group(1)
            if name in IGNORED_SECRETS:
                continue
            uses.append(SecretUse(name=name, path=rel(path, root), line=lineno))"]
    N004["return uses"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
```

## collect_runbooks(...)

```mermaid
flowchart TD
    N001["collect_runbooks(...)"]
    N002["return [Runbook(path=rel(path, root), text=path.read_text(encoding='<str>')) for path in sorted(runbooks_dir.glob('<str>'))]"]
    N001 -->|"start"| N002
```

## missing_requirements(...)

```mermaid
flowchart TD
    N001["missing_requirements(...)"]
    N002["return [requirement.name for requirement in REQUIREMENTS if not requirement.matches(secret, text)]"]
    N001 -->|"start"| N002
```

## best_documented_runbook(...)

```mermaid
flowchart TD
    N001["best_documented_runbook(...)"]
    N002["candidates = [runbook for runbook in runbooks if secret in runbook.text]"]
    N003["if not candidates"]
    N004["return (None, [requirement.name for requirement in REQUIREMENTS])"]
    N005["ranked = sorted(...)"]
    N006["return ranked[0]"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 -->|"true"| N004
    N003 -->|"false"| N005
    N005 --> N006
```

## format_refs(...)

```mermaid
flowchart TD
    N001["format_refs(...)"]
    N002["return '<str>'.join((f'{use.path.as_posix()}<str>{use.line}' for use in uses))"]
    N001 -->|"start"| N002
```

## verify(...)

```mermaid
flowchart TD
    N001["verify(...)"]
    N002["uses = collect_secret_uses(...)"]
    N003["runbooks = collect_runbooks(...)"]
    N004["errors = []"]
    N005["by_secret = {}"]
    N006["for use in uses:
    by_secret.setdefault(use.name, []).append(use)"]
    N007["for secret, secret_uses in sorted(by_secret.items()):
    runbook, missing = best_documented_runbook(secret, runbooks)
    if not missing:
        continue
    location = '<str>' if runbook is None else f'{runbook.path.as_posix()}<str>'
    errors.append(f'<str>{secret}<str>{format_refs(secret_uses)}<str>{location}<str>{'<str>'.join(missing)}')"]
    N008["return errors"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 --> N005
    N005 --> N006
    N006 --> N007
    N007 --> N008
```

## cmd_verify(...)

```mermaid
flowchart TD
    N001["cmd_verify(...)"]
    N002["root = Path(...)"]
    N003["errors = verify(...)"]
    N004["for error in errors:
    print(f'<str>{error}', file=sys.stderr)"]
    N005["if errors"]
    N006["return 1"]
    N007["print(...)"]
    N008["return 0"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 --> N005
    N005 -->|"true"| N006
    N005 -->|"false"| N007
    N007 --> N008
```

## build_parser(...)

```mermaid
flowchart TD
    N001["build_parser(...)"]
    N002["parser = ArgumentParser(...)"]
    N003["add_argument(...)"]
    N004["subparsers = add_subparsers(...)"]
    N005["verify_parser = add_parser(...)"]
    N006["set_defaults(...)"]
    N007["return parser"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 --> N005
    N005 --> N006
    N006 --> N007
```

## main(...)

```mermaid
flowchart TD
    N001["main(...)"]
    N002["parser = build_parser(...)"]
    N003["args = parse_args(...)"]
    N004["return int(args.func(args))"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
```
