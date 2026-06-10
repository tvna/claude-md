# AST graph: scripts/verify_readme_translation.py

This file is generated from `scripts/verify_readme_translation.py` by `python3 scripts/script_ast_graph.py all-doc`. Do not edit it by hand: content under `docs/generated/scripts/` is owned by the post-merge automation (refs #1540) -- update the source script instead.

## resolve_base(...)

```mermaid
flowchart TD
    N001["resolve_base(...)"]
    N002["explicit = get(...)"]
    N003["if explicit"]
    N004["return explicit"]
    N005["actions_base = get(...)"]
    N006["if actions_base"]
    N007["return f'<str>{actions_base}'"]
    N008["return '<str>'"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 -->|"true"| N004
    N003 -->|"false"| N005
    N005 --> N006
    N006 -->|"true"| N007
    N006 -->|"false"| N008
```

## changed_readmes(...)

```mermaid
flowchart TD
    N001["changed_readmes(...)"]
    N002["result = _run(...)"]
    N003["touched = {line.strip() for line in result.stdout.splitlines() if line.strip()}"]
    N004["return frozenset(touched & README_PATHS)"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
```

## body_has_skip_marker(...)

```mermaid
flowchart TD
    N001["body_has_skip_marker(...)"]
    N002["if not raw_body"]
    N003["return False"]
    N004["return _SKIP_MARKER_RE.search(raw_body) is not None"]
    N001 -->|"start"| N002
    N002 -->|"true"| N003
    N002 -->|"false"| N004
```

## evaluate_drift(...)

```mermaid
flowchart TD
    N001["evaluate_drift(...)"]
    N002["if 'README.md' not in changed"]
    N003["return (0, [])"]
    N004["missing = sorted(...)"]
    N005["if not missing"]
    N006["return (0, [])"]
    N007["if skip"]
    N008["return (0, [])"]
    N009["pretty = join(...)"]
    N010["return (1, [f'<str>{pretty}<str>'])"]
    N001 -->|"start"| N002
    N002 -->|"true"| N003
    N002 -->|"false"| N004
    N004 --> N005
    N005 -->|"true"| N006
    N005 -->|"false"| N007
    N007 -->|"true"| N008
    N007 -->|"false"| N009
    N009 --> N010
```

## _resolve_body(...)

```mermaid
flowchart TD
    N001["_resolve_body(...)"]
    N002["if args.body_file is not None"]
    N003["return Path(args.body_file).read_text(encoding='<str>')"]
    N004["return os.environ.get('<str>', '<str>')"]
    N001 -->|"start"| N002
    N002 -->|"true"| N003
    N002 -->|"false"| N004
```

## _resolve_base_ref(...)

```mermaid
flowchart TD
    N001["_resolve_base_ref(...)"]
    N002["if args.base_ref"]
    N003["return args.base_ref"]
    N004["return resolve_base()"]
    N001 -->|"start"| N002
    N002 -->|"true"| N003
    N002 -->|"false"| N004
```

## _cmd_verify(...)

```mermaid
flowchart TD
    N001["_cmd_verify(...)"]
    N002["base = _resolve_base_ref(...)"]
    N003["try"]
    N004["body = _resolve_body(...)"]
    N005["except FileNotFoundError"]
    N006["print(...)"]
    N007["return 1"]
    N008["try"]
    N009["changed = changed_readmes(...)"]
    N010["except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError)"]
    N011["print(...)"]
    N012["return 1"]
    N013["skip = body_has_skip_marker(...)"]
    N014["(code, errors) = evaluate_drift(...)"]
    N015["if code == 0"]
    N016["if 'README.md' in changed and skip"]
    N017["print(...)"]
    N018["if 'README.md' in changed"]
    N019["print(...)"]
    N020["if changed"]
    N021["pretty = join(...)"]
    N022["print(...)"]
    N023["print(...)"]
    N024["return 0"]
    N025["for line in errors:
    print(line, file=sys.stderr)"]
    N026["return 1"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 -->|"try"| N004
    N003 -->|"raises"| N005
    N005 --> N006
    N006 --> N007
    N004 --> N008
    N008 -->|"try"| N009
    N008 -->|"raises"| N010
    N010 --> N011
    N011 --> N012
    N009 --> N013
    N013 --> N014
    N014 --> N015
    N015 -->|"true"| N016
    N016 -->|"true"| N017
    N016 -->|"false"| N018
    N018 -->|"true"| N019
    N018 -->|"false"| N020
    N020 -->|"true"| N021
    N021 --> N022
    N020 -->|"false"| N023
    N017 --> N024
    N019 --> N024
    N022 --> N024
    N023 --> N024
    N015 -->|"false"| N025
    N025 --> N026
```

## main(...)

```mermaid
flowchart TD
    N001["main(...)"]
    N002["parser = ArgumentParser(...)"]
    N003["sub = add_subparsers(...)"]
    N004["p_verify = add_parser(...)"]
    N005["add_argument(...)"]
    N006["add_argument(...)"]
    N007["set_defaults(...)"]
    N008["args = parse_args(...)"]
    N009["return args.func(args)"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 --> N005
    N005 --> N006
    N006 --> N007
    N007 --> N008
    N008 --> N009
```

## _run(...)

```mermaid
flowchart TD
    N001["_run(...)"]
    N002["return runner(cmd, capture_output=True, text=True, timeout=_GIT_TIMEOUT_SECONDS, check=True)"]
    N001 -->|"start"| N002
```
