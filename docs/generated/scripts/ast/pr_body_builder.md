# AST graph: scripts/pr_body_builder.py

This file is generated from `scripts/pr_body_builder.py` by `python3 scripts/script_ast_graph.py all-doc`. Do not edit it by hand: content under `docs/generated/scripts/` is owned by the post-merge automation (refs #1540); update the source script instead.

## _build_footer(...)

```mermaid
flowchart TD
    N001["_build_footer(...)"]
    N002["if agent.strip().lower() == 'codex'"]
    N003["if not model"]
    N004["raise ValueError('<str>')"]
    N005["return build_codex_attribution_footer(model)"]
    N006["return f'<str>{agent}<str>{session_url}<str>'"]
    N001 -->|"start"| N002
    N002 -->|"true"| N003
    N003 -->|"true"| N004
    N003 -->|"false"| N005
    N002 -->|"false"| N006
```

## _is_builder_compatible(...)

```mermaid
flowchart TD
    N001["_is_builder_compatible(...)"]
    N002["text = read_text(...)"]
    N003["return not any((token in text for token in _WORKFLOW_ONLY_TOKENS))"]
    N001 -->|"start"| N002
    N002 --> N003
```

## list_kinds(...)

```mermaid
flowchart TD
    N001["list_kinds(...)"]
    N002["return sorted((p.stem for p in _DOMAIN_TEMPLATE_DIR.glob('<str>') if _is_builder_compatible(p)))"]
    N001 -->|"start"| N002
```

## build(...)

```mermaid
flowchart TD
    N001["build(...)"]
    N002["if kind is not None"]
    N003["kind_path = _DOMAIN_TEMPLATE_DIR / f'{kind}<str>'"]
    N004["if kind_path.exists() and _is_builder_compatible(kind_path)"]
    N005["template_path = kind_path"]
    N006["raw = read_text(...)"]
    N007["body = sub(...)"]
    N008["body = sub(...)"]
    N009["body = sub(...)"]
    N010["body = sub(...)"]
    N011["body = sub(...)"]
    N012["footer = _build_footer(...)"]
    N013["body = sub(...)"]
    N014["return body.rstrip('<str>') + '<str>'"]
    N001 -->|"start"| N002
    N002 -->|"true"| N003
    N003 --> N004
    N004 -->|"true"| N005
    N005 --> N006
    N004 -->|"false"| N006
    N002 -->|"false"| N006
    N006 --> N007
    N007 --> N008
    N008 --> N009
    N009 --> N010
    N010 --> N011
    N011 --> N012
    N012 --> N013
    N013 --> N014
```

## main(...)

```mermaid
flowchart TD
    N001["main(...)"]
    N002["parser = ArgumentParser(...)"]
    N003["sub = add_subparsers(...)"]
    N004["p_build = add_parser(...)"]
    N005["add_argument(...)"]
    N006["add_argument(...)"]
    N007["add_argument(...)"]
    N008["add_argument(...)"]
    N009["add_argument(...)"]
    N010["add_argument(...)"]
    N011["add_parser(...)"]
    N012["args = parse_args(...)"]
    N013["if args.cmd == 'list-kinds'"]
    N014["for kind in list_kinds():     print(kind)"]
    N015["return 0"]
    N016["try"]
    N017["body = build(...)"]
    N018["except ValueError"]
    N019["print(...)"]
    N020["return 1"]
    N021["write(...)"]
    N022["return 0"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 --> N005
    N005 --> N006
    N006 --> N007
    N007 --> N008
    N008 --> N009
    N009 --> N010
    N010 --> N011
    N011 --> N012
    N012 --> N013
    N013 -->|"true"| N014
    N014 --> N015
    N013 -->|"false"| N016
    N016 -->|"try"| N017
    N016 -->|"raises"| N018
    N018 --> N019
    N019 --> N020
    N017 --> N021
    N021 --> N022
```
