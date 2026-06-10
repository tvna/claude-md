# AST graph: scripts/pr_body_builder.py

This file is generated from `scripts/pr_body_builder.py` by `python3 scripts/script_ast_graph.py all-doc`. Do not edit it by hand: content under `docs/generated/scripts/` is owned by the post-merge automation (refs #1540) -- update the source script instead.

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

## build(...)

```mermaid
flowchart TD
    N001["build(...)"]
    N002["raw = read_text(...)"]
    N003["body = sub(...)"]
    N004["body = sub(...)"]
    N005["body = sub(...)"]
    N006["body = sub(...)"]
    N007["footer = _build_footer(...)"]
    N008["body = sub(...)"]
    N009["return body.rstrip('<str>') + '<str>'"]
    N001 -->|"start"| N002
    N002 --> N003
    N003 --> N004
    N004 --> N005
    N005 --> N006
    N006 --> N007
    N007 --> N008
    N008 --> N009
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
    N010["args = parse_args(...)"]
    N011["try"]
    N012["body = build(...)"]
    N013["except ValueError"]
    N014["print(...)"]
    N015["return 1"]
    N016["write(...)"]
    N017["return 0"]
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
    N011 -->|"try"| N012
    N011 -->|"raises"| N013
    N013 --> N014
    N014 --> N015
    N012 --> N016
    N016 --> N017
```
