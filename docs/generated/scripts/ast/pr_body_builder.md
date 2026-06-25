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
    N012["if include_footer"]
    N013["footer = _build_footer(...)"]
    N014["body = sub(...)"]
    N015["body = sub(...)"]
    N016["body = join(...)"]
    N017["return body.rstrip('<str>') + '<str>'"]
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
    N012 -->|"true"| N013
    N013 --> N014
    N012 -->|"false"| N015
    N015 --> N016
    N014 --> N017
    N016 --> N017
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
    N011["add_argument(...)"]
    N012["add_parser(...)"]
    N013["args = parse_args(...)"]
    N014["if args.cmd == 'list-kinds'"]
    N015["for kind in list_kinds():     print(kind)"]
    N016["return 0"]
    N017["try"]
    N018["body = build(...)"]
    N019["except ValueError"]
    N020["print(...)"]
    N021["return 1"]
    N022["write(...)"]
    N023["return 0"]
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
    N013 --> N014
    N014 -->|"true"| N015
    N015 --> N016
    N014 -->|"false"| N017
    N017 -->|"try"| N018
    N017 -->|"raises"| N019
    N019 --> N020
    N020 --> N021
    N018 --> N022
    N022 --> N023
```
